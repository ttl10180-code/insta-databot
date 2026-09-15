"""한국부동산원 청약홈 분양정보 → 청약 일정 카드 데이터.

공공데이터포털(odcloud) 키를 그대로 쓴다.
이번 주에 접수가 시작되는 APT 공고를 모은다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from src import config
from src.common import http

log = logging.getLogger(__name__)

URL = "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail"


def _d(v: str | None) -> datetime | None:
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def fetch(now: datetime | None = None, days: int = 14) -> dict:
    if not config.DATA_GO_KR_KEY:
        raise http.NoData("03", "DATA_GO_KR_KEY 가 없습니다")

    now = now or datetime.now(config.KST)
    today = datetime(now.year, now.month, now.day)
    until = today + timedelta(days=days)

    log.info("청약홈 분양정보 조회")
    doc = http.get(URL, {
        "serviceKey": config.DATA_GO_KR_KEY,
        "page": 1, "perPage": 100,
    }, check_header=False)

    rows = http.as_list(doc.get("data") if isinstance(doc, dict) else doc)
    upcoming = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        begin = _d(r.get("RCEPT_BGNDE"))
        if not begin or not (today <= begin <= until):
            continue
        area = (r.get("SUBSCRPT_AREA_CODE_NM") or "").strip()
        if config.APPLY_AREAS and not any(a in area for a in config.APPLY_AREAS):
            continue
        cnt = http.to_int(r.get("TOT_SUPLY_HSHLDCO"))
        upcoming.append({
            "name": (r.get("HOUSE_NM") or "").strip(),
            "area": area,
            "addr": (r.get("HSSPLY_ADRES") or "").strip(),
            "kind": (r.get("HOUSE_SECD_NM") or "").strip(),
            "households": f"{cnt:,}" if cnt is not None else "-",
            "households_n": cnt or 0,
            "begin": begin,
            "begin_label": f"{begin.month}/{begin.day}",
            "end_label": (lambda e: f"{e.month}/{e.day}" if e else "-")(_d(r.get("RCEPT_ENDDE"))),
        })

    if not upcoming:
        raise http.NoData("03", f"향후 {days}일 내 청약 접수 시작 공고가 없습니다")

    upcoming.sort(key=lambda x: (x["begin"], -x["households_n"]))
    total = sum(x["households_n"] for x in upcoming)
    areas = sorted({x["area"] for x in upcoming if x["area"]})
    return {
        "date_label": f"{today.month}월 {today.day}일",
        "period_label": f"{today.month}/{today.day}~{until.month}/{until.day}",
        "count": len(upcoming),
        "total_households": f"{total:,}",
        "area_count": len(areas),
        "areas": areas,
        "head": upcoming[0],
        "items": upcoming,
        "rest": upcoming[1:],
    }
