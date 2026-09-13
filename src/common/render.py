"""HTML 템플릿 → 1080x1080 JPEG 카드 렌더러.

인스타그램 요건에 맞춰 내보낸다:
  - 1080x1080 (1:1, 허용 비율 4:5 ~ 1.91:1 안쪽)
  - JPEG / sRGB (공식 지원 포맷은 JPEG 뿐)
  - 8MB 미만
"""
from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image
from playwright.sync_api import sync_playwright

from src import config

log = logging.getLogger(__name__)

CANVAS = 1080
MAX_BYTES = 8 * 1024 * 1024

_env = Environment(
    loader=FileSystemLoader(str(config.TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=False,
    lstrip_blocks=False,
)


def build_html(template: str, context: dict) -> str:
    return _env.get_template(template).render(**context)


def render_card(template: str, context: dict, out_path: Path) -> Path:
    """템플릿과 데이터를 받아 JPEG 카드 한 장을 만든다."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    html = build_html(template, context)
    # 상대경로(tokens.css, ../fonts/…)가 그대로 동작하도록 templates/ 안에 임시 저장
    tmp = config.TEMPLATE_DIR / f"._render_{out_path.stem}.html"
    tmp.write_text(html, encoding="utf-8")

    png_path = out_path.with_suffix(".png")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--font-render-hinting=none",
                                              "--force-color-profile=srgb"])
            page = browser.new_page(
                viewport={"width": CANVAS, "height": CANVAS},
                device_scale_factor=1,
            )
            page.goto(tmp.as_uri(), wait_until="networkidle")
            # 폰트 로드 + 자동축소 완료까지 대기 (두부 현상/레이스 컨디션 방지)
            page.wait_for_function("document.fonts.status === 'loaded'", timeout=15000)
            page.wait_for_selector("html[data-render-ready='1']", timeout=15000)
            page.screenshot(path=str(png_path), full_page=False)
            browser.close()
    finally:
        tmp.unlink(missing_ok=True)

    jpeg_path = _to_jpeg(png_path, out_path.with_suffix(".jpg"))
    png_path.unlink(missing_ok=True)
    log.info("카드 생성: %s (%.1f KB)", jpeg_path.name, jpeg_path.stat().st_size / 1024)
    return jpeg_path


def _to_jpeg(src: Path, dst: Path) -> Path:
    """PNG → sRGB JPEG. 8MB 넘으면 품질을 낮춰 재저장."""
    im = Image.open(src)
    if im.mode != "RGB":
        bg = Image.new("RGB", im.size, (255, 255, 255))
        rgba = im.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[-1])
        im = bg
    if im.size != (CANVAS, CANVAS):
        im = im.resize((CANVAS, CANVAS), Image.LANCZOS)

    for quality in (94, 88, 82, 75, 68):
        im.save(dst, "JPEG", quality=quality, optimize=True, progressive=True,
                subsampling=0)
        if dst.stat().st_size < MAX_BYTES:
            break
    return dst
