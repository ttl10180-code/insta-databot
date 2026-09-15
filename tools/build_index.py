"""gh-pages 용 모바일 인덱스 페이지 생성기.

  python3 tools/build_index.py <출력폴더>

오늘 만든 카드 4장을 캡션과 함께 한 페이지에 모은다.
폰에서 이 페이지만 열면 이미지 저장 + 캡션 복사가 바로 된다.
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
LABEL = {
    "weather": "날씨", "air": "대기질", "lifeindex": "생활지수",
    "boxoffice": "박스오피스", "boxoffice_weekly": "주말 박스오피스",
    "exchange": "환율", "price": "장바구니 물가",
    "realestate": "부동산", "apply": "아파트 청약", "oil": "유가",
    "missing": "실종자 찾기",
}


def main(dest: Path) -> None:
    cards_dir = dest / "cards"

    def kind_of(name: str) -> str:
        m = re.match(r"\d{8}-([a-z_]+?)(-story)?\.jpg$", name)
        return m.group(1) if m else ""

    def is_story(name: str) -> bool:
        return name.endswith("-story.jpg")

    files = sorted((p.name for p in cards_dir.glob("*.jpg")), reverse=True)

    captions = {}
    manifest = ROOT / "out" / "captions.json"
    if manifest.exists():
        for row in json.loads(manifest.read_text(encoding="utf-8")):
            captions[row["kind"]] = row["caption"]

    today = max((re.match(r"(\d{8})-", f).group(1) for f in files if re.match(r"\d{8}-", f)), default="")
    todays = [f for f in files if f.startswith(today)] if today else []
    stories = {kind_of(f): f for f in todays if is_story(f)}
    todays = [f for f in todays if not is_story(f)]
    older = [f for f in files if f.startswith(today) is False and not is_story(f)][:40]

    order = ["missing", "weather", "air", "lifeindex", "boxoffice",
             "boxoffice_weekly", "exchange", "price", "realestate", "apply", "oil"]
    todays.sort(key=lambda f: order.index(kind_of(f)) if kind_of(f) in order else 99)

    date_label = ""
    if today:
        d = datetime.strptime(today, "%Y%m%d")
        date_label = f"{d.month}월 {d.day}일"

    blocks = []
    for f in todays:
        k = kind_of(f)
        cap = captions.get(k, "")
        sf = stories.get(k)
        story_link = (f'\n      <a class="story" href="cards/{html.escape(sf)}" target="_blank">'
                      f'스토리 버전 (1080×1920) 열기</a>') if sf else ""
        blocks.append(f"""
    <section class="card">
      <h2><span class="dot {html.escape(k)}"></span>{html.escape(LABEL.get(k, k))}</h2>
      <a href="cards/{html.escape(f)}" target="_blank"><img src="cards/{html.escape(f)}" alt="{html.escape(k)}" loading="lazy"></a>
      <div class="cap">
        <pre id="c-{html.escape(k)}">{html.escape(cap)}</pre>
        <button type="button" data-for="c-{html.escape(k)}">캡션 복사</button>
      </div>{story_link}
    </section>""")

    archive = "".join(f'<li><a href="cards/{html.escape(f)}">{html.escape(f)}</a></li>' for f in older)
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    (dest / "index.html").write_text(f"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>오늘의 데이터 카드</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 20px 16px 56px; background: #0A1020; color: #E8EDF7;
         font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", sans-serif;
         max-width: 620px; margin-inline: auto; }}
  header h1 {{ font-size: 26px; margin: 0 0 6px; letter-spacing: -.02em; }}
  header p {{ margin: 0 0 26px; color: #8FA0BF; font-size: 14px; }}
  .card {{ margin-bottom: 34px; }}
  .card h2 {{ font-size: 17px; margin: 0 0 10px; display: flex; align-items: center; gap: 9px; }}
  .dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
  .dot.weather {{ background: #3B82F6; }} .dot.air {{ background: #14B8A6; }}
  .dot.realestate {{ background: #F59E0B; }} .dot.oil {{ background: #F97316; }}
  .dot.lifeindex {{ background: #84CC16; }} .dot.boxoffice {{ background: #8B5CF6; }}
  .dot.boxoffice_weekly {{ background: #8B5CF6; }} .dot.exchange {{ background: #06B6D4; }}
  .dot.price {{ background: #F43F5E; }} .dot.apply {{ background: #D97706; }}
  .dot.missing {{ background: #4A7BD9; }}
  img {{ width: 100%; border-radius: 16px; display: block; }}
  .cap {{ margin-top: 12px; background: #141C31; border: 1px solid #22304F;
          border-radius: 14px; padding: 14px; }}
  pre {{ margin: 0 0 12px; white-space: pre-wrap; word-break: break-word;
         font-family: inherit; font-size: 14px; line-height: 1.65; color: #CBD7EC; }}
  button {{ width: 100%; padding: 12px; border: 0; border-radius: 10px; background: #2563EB;
            color: #fff; font-size: 15px; font-weight: 700; cursor: pointer; }}
  button.done {{ background: #16A34A; }}
  a.story {{ display: block; margin-top: 10px; padding: 12px; text-align: center;
             border: 1px solid #2E3E61; border-radius: 10px; color: #9FC2FF;
             text-decoration: none; font-size: 14px; font-weight: 600; }}
  details {{ margin-top: 30px; color: #8FA0BF; font-size: 13px; }}
  details a {{ color: #7FB3FF; }}
  li {{ margin: 4px 0; }}
  footer {{ margin-top: 34px; color: #5D6C88; font-size: 12px; text-align: center; }}
</style></head>
<body>
<header>
  <h1>오늘의 데이터 카드</h1>
  <p>{html.escape(date_label)} · 이미지를 길게 눌러 저장하고, 캡션은 복사 버튼으로</p>
</header>
{"".join(blocks) or "<p>오늘 생성된 카드가 없습니다.</p>"}
<details><summary>지난 카드 보기</summary><ul>{archive}</ul></details>
<footer>마지막 갱신 {html.escape(now)} KST · 출처 공공데이터포털</footer>
<script>
document.querySelectorAll('button[data-for]').forEach(function (b) {{
  b.addEventListener('click', function () {{
    var t = document.getElementById(b.dataset.for).textContent;
    navigator.clipboard.writeText(t).then(function () {{
      b.textContent = '복사됨'; b.classList.add('done');
      setTimeout(function () {{ b.textContent = '캡션 복사'; b.classList.remove('done'); }}, 1600);
    }});
  }});
}});
</script>
</body></html>
""", encoding="utf-8")
    print(f"index.html 생성: 오늘 {len(todays)}장, 보관 {len(older)}장")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
