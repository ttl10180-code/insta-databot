"""프로필 이미지(인스타 프로필 사진 · 페이스북 커버) 렌더러."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "profile"
JOBS = [("profile_avatar.html", "avatar.png", 1080, 1080),
        ("profile_cover.html", "cover.png", 1640, 624)]

OUT.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(args=["--font-render-hinting=none", "--force-color-profile=srgb"])
    for tpl, name, w, h in JOBS:
        page = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        page.goto((ROOT / "templates" / tpl).as_uri(), wait_until="networkidle")
        page.wait_for_function("document.fonts.status === 'loaded'", timeout=15000)
        page.screenshot(path=str(OUT / name))
        page.close()
        print("saved", OUT / name)
    b.close()
