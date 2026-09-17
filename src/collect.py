"""수집만 하는 단계 — 발행과 분리한다.

문제. 해외 러너에서 국내 정부 서버는 시간대에 따라 돌아가며 막힌다. 어느
아침엔 수출입은행만 살아 있고 그날 밤엔 수출입은행만 죽어 있는 식이다.
발행 시각에 하필 그 서버가 죽어 있으면 카드를 못 만든다.

해법. '언제 받느냐' 와 '언제 올리느냐' 를 떼어놓는다. 이 명령은 두 시간마다
돌면서 닿는 소스만 받아 캐시에 쌓는다. 하루 중 아무 때나 한 번만 성공하면
그날 발행은 살아난다. 발행 워크플로는 평소처럼 직접 받아보고, 실패할 때만
이 캐시로 대신한다 (src/common/cache.py).

실시간 관측값(미세먼지·생활기상지수)은 일부러 빠져 있다. 몇 시간 전 값을
지금 값인 척 내보낼 수 없기 때문이다.
"""
from __future__ import annotations

import logging
from datetime import datetime

from src import config
from src.common import http
from src.sources import apply, boxoffice, exchange, missing, realestate, weather

log = logging.getLogger("collect")

# 이름 → 수집 함수. 이름은 로그용이고, 실제 캐시 키는 각 소스가 정한다.
TARGETS = {
    "날씨": lambda now: weather.fetch(now=now),
    "박스오피스(일별)": lambda now: boxoffice.fetch_daily(now=now),
    "박스오피스(주말)": lambda now: boxoffice.fetch_weekly(now=now),
    "환율": lambda now: exchange.fetch(now=now),
    "아파트 실거래": lambda now: realestate.fetch(now=now),
    "청약": lambda now: apply.fetch(now=now),
    "실종자": lambda now: missing.fetch(now=now),
}


def run() -> int:
    """닿는 데까지 받아서 캐시에 쌓는다. 하나도 못 받아도 실패로 끝내지 않는다.

    이 작업이 빨간 X 를 띄우면 '오늘 뭔가 잘못됐다' 는 신호가 닳아버린다.
    국내 서버가 안 닿는 건 흔한 일이고, 그래서 두 시간마다 다시 오는 것이다.
    """
    now = datetime.now(config.KST)
    ok, failed = [], []
    for label, fn in TARGETS.items():
        try:
            fn(now)
        except http.NoData as e:
            log.info("⏭️  %s: 오늘은 데이터가 없습니다 (%s)", label, e)
        except Exception as e:                  # noqa: BLE001
            log.warning("❌ %s: %s", label, e)
            failed.append(label)
        else:
            ok.append(label)
            log.info("✅ %s 받았습니다", label)

    print(f"받음 {len(ok)} / 실패 {len(failed)}")
    if ok:
        print("  ✅ " + ", ".join(ok))
    if failed:
        print("  ❌ " + ", ".join(failed))
    return 0
