"""GitHub Pages 에 카드 이미지가 실제로 올라갔는지 확인 후 진행.

Pages 배포는 푸시 후 수십 초 걸린다. 이 대기 없이 게시하면
인스타그램이 이미지를 못 받아 9004 / 2207052 오류가 난다.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests

BASE = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
TIMEOUT_SEC = int(os.getenv("PAGES_WAIT_SEC", "420"))
INTERVAL = 10


def main() -> int:
    if not BASE:
        print("::error::PUBLIC_BASE_URL 이 비어 있습니다. 저장소 Variables 에 설정하세요.")
        return 1

    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "out")
    files = sorted(out_dir.glob("*.jpg"))
    if not files:
        print("::error::확인할 이미지가 없습니다.")
        return 1

    urls = [f"{BASE}/cards/{f.name}" for f in files]
    deadline = time.time() + TIMEOUT_SEC
    pending = list(urls)

    while pending and time.time() < deadline:
        still = []
        for url in pending:
            try:
                r = requests.get(url, timeout=20,
                                 headers={"Cache-Control": "no-cache"})
                ctype = r.headers.get("Content-Type", "")
                if r.status_code == 200 and ctype.startswith("image/"):
                    print(f"✅ 공개 확인: {url} ({len(r.content):,} bytes)")
                    continue
                print(f"… 대기 중 {url} → {r.status_code} {ctype}")
            except requests.RequestException as e:
                print(f"… 대기 중 {url} → {e}")
            still.append(url)
        pending = still
        if pending:
            time.sleep(INTERVAL)

    if pending:
        print("::error::다음 이미지가 공개되지 않았습니다:\n  " + "\n  ".join(pending))
        print("GitHub Pages 가 gh-pages 브랜치로 설정되어 있는지 확인하세요.")
        return 1

    print("모든 카드가 공개 URL 로 접근 가능합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
