"""발행 점검 — '며칠째 안 올라간 카드' 를 찾아낸다.

워크플로가 초록불이라는 것과 카드가 올라갔다는 것은 다른 말이다. 수집이
'오늘은 데이터 없음' 을 돌려주면 그 카드는 조용히 건너뛰어지고 실행은
성공으로 끝난다. 그래서 실행 기록이 아니라 실제 발행 기록을 본다
(src/common/postlog.py).

하루 조용한 건 정상이다. 환율은 주말에 안 나가고, 주간 카드는 일주일에 한
번이다. 그래서 종류마다 '이만큼 조용하면 고장' 선을 따로 잡는다. 그 선을
넘은 게 하나라도 있으면 빨간 X 를 띄운다 — 이 점검만큼은 시끄러워야 한다.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

from src import config
from src.common import postlog

log = logging.getLogger("health")

# 카드 종류 → (사람이 읽을 이름, 이만큼 조용하면 고장으로 본다(일))
#
# 기준은 '예정 주기 + 하루' 정도로 넉넉하게 잡았다. 빡빡하게 잡으면 공휴일
# 하루에도 빨간 X 가 떠서, 경고가 닳아 아무도 안 보게 된다.
WATCH = {
    "weather":          ("날씨",            2),
    "air":              ("대기질",          2),
    "lifeindex":        ("생활기상지수",    2),
    "boxoffice":        ("박스오피스",      2),
    "missing":          ("실종자 찾기",     2),
    "exchange":         ("환율",            4),   # 평일만 — 주말·연휴를 감안
    "boxoffice_weekly": ("주말 박스오피스", 9),
    "realestate":       ("아파트 실거래",   9),
    "apply":            ("청약",            9),
    # 물가·유가는 아직 보류 상태라 지켜보지 않는다. 켜면 여기에 넣는다.
}


def _summary(lines: list[str]) -> None:
    """깃허브 실행 요약에도 남긴다. 로그를 펼쳐보지 않아도 보이게."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        pass


def run() -> int:
    posted = postlog.load()
    now = datetime.now(config.KST)

    rows, overdue, never = [], [], []
    for kind, (label, limit) in WATCH.items():
        stamp = posted.get(kind)
        if not stamp:
            never.append(label)
            rows.append(f"| {label} | 기록 없음 | — | ⬜ |")
            continue
        try:
            when = datetime.fromisoformat(stamp)
        except ValueError:
            rows.append(f"| {label} | 읽을 수 없음 | — | ⬜ |")
            continue
        days = (now - when).total_seconds() / 86400
        ok = days <= limit
        if not ok:
            overdue.append(f"{label} ({days:.1f}일째)")
        rows.append(f"| {label} | {when:%m-%d %H:%M} | {days:.1f}일 | "
                    f"{'✅' if ok else '❌'} |")

    _summary(["## 발행 점검", "",
              "| 카드 | 마지막 발행 | 경과 | |",
              "|---|---|---|---|", *rows])
    for r in rows:
        print(r)

    if never:
        # '한 번도 안 올림' 은 고장이 아니라 아직 시작 안 한 것일 수 있다.
        # (기록 기능을 켠 직후가 그렇다.) 그래서 알리되 실패로 보지 않는다.
        log.warning("아직 발행 기록이 없는 카드: %s", ", ".join(never))
    if overdue:
        log.error("너무 오래 안 올라간 카드: %s", ", ".join(overdue))
        print(f"::error::너무 오래 안 올라간 카드 — {', '.join(overdue)}")
        return 1

    log.info("지켜보는 카드 %d종 모두 정상 주기 안에 있습니다.",
             len(WATCH) - len(never))
    return 0
