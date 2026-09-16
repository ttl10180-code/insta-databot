"""주제·상황별 배경 아트 생성기 (OpenAI 이미지 API).

매일 새로 만들지 않는다. 데이터 '상태'마다 한 장씩만 만들어 저장소에 캐시해 두고
계속 재사용한다. 비 오는 날 배경, 미세먼지 나쁜 날 배경처럼 상태가 바뀔 때만
그림이 바뀌므로, 카드 톤은 일정하면서 비용은 최초 1회로 끝난다.

  OPENAI_API_KEY=... python3 tools/build_backgrounds.py           # 없는 것만 생성
  OPENAI_API_KEY=... python3 tools/build_backgrounds.py --force   # 전부 다시 생성
  python3 tools/build_backgrounds.py --list                       # 목록만 확인

결과: assets/bg/<theme>-<variant>.jpg
파일이 없으면 카드는 기존 그라디언트 배경으로 그냥 나간다 (실패해도 발행은 계속된다).
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
import time
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

from punch_backgrounds import punch

sys.path.insert(0, str(Path(__file__).resolve().parent))   # punch_backgrounds 를 옆에서 찾는다
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "bg"
API = "https://api.openai.com/v1/images/generations"
MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
SIZE = "1024x1024"

# 모든 배경이 공유하는 규칙. 카드 위에 글자가 올라가므로
# 중앙은 비우고, 문자·캐릭터·로고는 절대 넣지 않는다.
STYLE = (
    "Bold abstract 3D background artwork for a social media data card. "
    "Soft clay-render aesthetic with dramatic studio lighting, strong rim light and a "
    "clear light source, smooth matte surfaces, deep shadows next to bright highlights. "
    "Rich saturated {tone} palette, cinematic, confident. "
    "Composition: large sculptural forms occupy the right half and the upper-right; "
    "the left side stays open so text can sit there. No text, no letters, no numbers, "
    "no logos, no characters, no people, no animals. Not photorealistic. Square."
)

# (테마, 변형, 톤, 모티프)
VARIANTS = [
    ("weather", "sunny",    "deep navy blue", "a warm soft light bloom in the upper right, faint lens glow, clear calm sky feeling"),
    ("weather", "cloudy",   "deep navy blue", "soft rounded cloud forms drifting in the upper area, gentle volumetric haze"),
    ("weather", "overcast", "deep navy blue", "a heavy flat blanket of soft grey-blue cloud, diffused light, no sun"),
    ("weather", "rain",     "deep navy blue", "fine diagonal rain streaks in the upper right, blurred water droplets, wet reflective sheen"),
    ("weather", "snow",     "deep navy blue", "slow falling soft snow particles, frosted bokeh, cold still air"),

    ("air", "good",     "deep teal green", "crystal clear air, soft clean gradient, a few bright floating particles, open and fresh"),
    ("air", "normal",   "deep teal green", "light atmospheric haze, subtle floating dust motes"),
    ("air", "bad",      "deep teal green", "thick smoggy haze layers, dense drifting particles, heavy air"),
    ("air", "verybad",  "deep teal green", "very dense dust storm haze, murky layered smog, oppressive atmosphere"),

    ("realestate", "up",   "deep amber brown", "soft clay apartment block shapes rising like a staircase toward the upper right"),
    ("realestate", "down", "deep amber brown", "soft clay apartment block shapes stepping downward toward the lower right"),
    ("realestate", "flat", "deep amber brown", "an even row of soft clay apartment block shapes along the bottom edge"),

    ("oil", "up",   "deep burnt orange", "a soft rising curve of glossy liquid, warm reflective sheen in the upper right"),
    ("oil", "down", "deep burnt orange", "a soft descending curve of glossy liquid toward the lower right"),
    ("oil", "flat", "deep burnt orange", "a still level pool of glossy liquid along the bottom, calm reflection"),

    ("exchange", "up",   "deep ocean cyan", "a smooth rising ribbon curve of light in the upper right, soft glassy highlights"),
    ("exchange", "down", "deep ocean cyan", "a smooth descending ribbon curve of light toward the lower right"),
    ("exchange", "flat", "deep ocean cyan", "a level horizontal ribbon of light, still water surface feeling"),

    ("price", "up",   "deep rose red", "soft rounded grocery-basket shapes stacked upward at the right, warm glow"),
    ("price", "down", "deep rose red", "soft rounded grocery-basket shapes settling low at the right"),
    ("price", "flat", "deep rose red", "soft rounded grocery-basket shapes resting evenly along the bottom"),

    ("lifeindex", "low",     "deep lime green", "gentle diffused daylight, calm soft gradient, safe and easy mood"),
    ("lifeindex", "mid",     "deep lime green", "moderate directional light rays from the upper right, mild intensity"),
    ("lifeindex", "high",    "deep lime green", "strong bright light rays burning from the upper right, heat shimmer"),
    ("lifeindex", "extreme", "deep lime green", "harsh intense light flare dominating the upper right, scorching air distortion"),

    ("boxoffice", "base", "deep violet purple", "soft velvet cinema curtain folds along the right edge, a faint projector light cone"),
    ("apply",     "base", "deep bronze gold",  "soft clay construction crane and tower silhouettes along the right edge, blueprint calm"),
]


def prompt_for(tone: str, motif: str) -> str:
    return STYLE.format(tone=tone) + " " + motif + "."


def generate(key: str, prompt: str) -> Image.Image:
    r = requests.post(
        API,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": MODEL, "prompt": prompt, "size": SIZE, "n": 1},
        timeout=(20, 180),
    )
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:300]}")
    item = r.json()["data"][0]
    if item.get("b64_json"):
        raw = base64.b64decode(item["b64_json"])
    else:                                    # 일부 모델은 URL 로 준다
        raw = requests.get(item["url"], timeout=(20, 120)).content
    return Image.open(BytesIO(raw)).convert("RGB")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="이미 있는 것도 다시 생성")
    ap.add_argument("--list", action="store_true", help="목록만 출력")
    ap.add_argument("--only", default="", help="이 테마만 (예: weather)")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    todo = [v for v in VARIANTS if not args.only or v[0] == args.only]

    if args.list:
        for theme, variant, tone, motif in todo:
            path = OUT / f"{theme}-{variant}.jpg"
            print(f"{'있음' if path.exists() else '없음'}  {path.name}")
        return 0

    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        print("OPENAI_API_KEY 가 없습니다. 배경 생성을 건너뜁니다.", file=sys.stderr)
        return 0                              # 키가 없다고 CI 를 깨뜨리지 않는다

    made, skipped, failed = 0, 0, 0
    for theme, variant, tone, motif in todo:
        path = OUT / f"{theme}-{variant}.jpg"
        if path.exists() and not args.force:
            skipped += 1
            continue
        try:
            im = generate(key, prompt_for(tone, motif))
            # 원본은 카드에 깔면 그라디언트와 구분이 안 될 만큼 어둡다.
            # 여기서 한 번만 펴 준다 (이미 있는 파일에 다시 돌리면 과해진다).
            im = punch(im.resize((1080, 1080), Image.LANCZOS))
            im.save(path, "JPEG", quality=90, optimize=True)
            print(f"생성 {path.name}")
            made += 1
            time.sleep(1.2)                   # 레이트 리밋 여유
        except Exception as e:                # 한 장 실패가 전체를 멈추지 않게
            print(f"실패 {path.name}: {e}", file=sys.stderr)
            failed += 1

    print(f"완료 — 생성 {made} / 건너뜀 {skipped} / 실패 {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
