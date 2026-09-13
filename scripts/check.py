"""설정·연결 점검. 키를 넣은 뒤 가장 먼저 실행해 보세요.

  python scripts/check.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config                                    # noqa: E402
from src.common import instagram                          # noqa: E402
from src.sources import air, oil, realestate, weather     # noqa: E402

OK, NG, SKIP = "✅", "❌", "⏭️ "


def check(name: str, fn):
    try:
        result = fn()
        print(f"{OK} {name} — {result}")
        return True
    except SystemExit as e:
        print(f"{SKIP}{name} — {e}")
        return None
    except Exception as e:                                 # noqa: BLE001
        print(f"{NG} {name}\n      {type(e).__name__}: {e}")
        return False


def main() -> int:
    now = datetime.now(config.KST)
    print(f"\n현재 시각 (KST): {now:%Y-%m-%d %H:%M}\n")
    print("── 환경변수 ──")
    for key in ["DATA_GO_KR_KEY", "OPINET_KEY", "IG_USER_ID",
                "IG_ACCESS_TOKEN", "PUBLIC_BASE_URL"]:
        v = getattr(config, key, "")
        print(f"{OK if v else NG} {key:<18} {'설정됨 (' + str(len(v)) + '자)' if v else '비어 있음'}")

    results = []
    print("\n── 공공데이터 API ──")
    if config.DATA_GO_KR_KEY:
        results.append(check("기상청 단기예보",
                             lambda: f"최고 {weather.fetch(now=now)['tmax']}°C"))
        results.append(check("에어코리아 대기질",
                             lambda: f"PM2.5 {air.fetch()['pm25']}㎍/㎥"))
        results.append(check("국토부 실거래가",
                             lambda: f"{realestate.fetch(now=now)['deal_count']}건"))
    else:
        print(f"{NG} DATA_GO_KR_KEY 가 없어 건너뜁니다.")
    if config.OPINET_KEY:
        results.append(check("오피넷 유가",
                             lambda: f"휘발유 {oil.fetch()['gasoline']}원"))
    else:
        print(f"{SKIP}오피넷 — OPINET_KEY 미설정 (유가 카드 미사용이면 정상)")

    print("\n── 인스타그램 ──")
    if config.IG_USER_ID and config.IG_ACCESS_TOKEN:
        results.append(check("게시 한도 조회",
                             lambda: f"잔여 {instagram.remaining_quota()}건"))
    else:
        print(f"{NG} IG_USER_ID / IG_ACCESS_TOKEN 미설정")

    failed = [r for r in results if r is False]
    print(f"\n{'모든 점검을 통과했습니다.' if not failed else f'{len(failed)}개 항목이 실패했습니다. 위 오류를 확인하세요.'}\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
