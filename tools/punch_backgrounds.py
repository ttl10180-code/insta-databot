"""배경 아트를 카드에 얹었을 때 형태가 보이도록 후보정한다.

이미지 API 가 내놓는 원본은 "아주 어둡게, 저채도" 로 주문해서 받기 때문에
그대로 카드에 깔면 그라디언트와 구분이 안 된다. 실제로는 3D 형태가 다
들어 있는데 어둠에 묻혀 있을 뿐이라, 레벨·감마·채도만 펴 주면 살아난다.
카드 쪽 어둡기는 templates/base.css 의 스크림이 맡는다.

한 번 보정한 파일에 다시 돌리면 과하게 익으므로, 새로 만든 파일에만
적용한다 (build_backgrounds.py 가 생성 직후 호출한다).

  python3 tools/punch_backgrounds.py assets/bg     # 폴더 전체 (백필용)
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
from PIL import Image, ImageEnhance


def punch(im: Image.Image) -> Image.Image:
    a = np.asarray(im.convert("RGB")).astype(np.float32) / 255.0
    lo, hi = np.percentile(a, 1.0), np.percentile(a, 99.5)
    a = np.clip((a - lo) / max(hi - lo, 1e-6), 0, 1)   # 자동 레벨
    a = a ** 0.86                                       # 중간톤을 들어올린다
    out = Image.fromarray((a * 255).astype(np.uint8))
    out = ImageEnhance.Color(out).enhance(1.50)
    out = ImageEnhance.Contrast(out).enhance(1.22)
    return out


def main(argv: list[str]) -> int:
    root = pathlib.Path(argv[1] if len(argv) > 1 else "assets/bg")
    for p in sorted(root.glob("*.jpg")):
        punch(Image.open(p)).save(p, "JPEG", quality=90, optimize=True)
        print("보정", p.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
