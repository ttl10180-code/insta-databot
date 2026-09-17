"""영화진흥위원회 박스오피스 → 영화 카드 데이터.

공공데이터포털이 아니라 kobis.or.kr 에서 직접 발급하는 key 를 쓴다.
일별(searchDailyBoxOfficeList) / 주간(searchWeeklyBoxOfficeList) 두 가지를 지원한다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from src import config
from src.common import cache, http

log = logging.getLogger(__name__)

BASE = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice"


def _require_key() -> str:
    if not config.KOBIS_KEY:
        raise http.NoData("03", "KOBIS_KEY 가 없어 박스오피스 카드를 건너뜁니다")
    return config.KOBIS_KEY


def _man(n: float | None) -> str:
    """관객수를 '만 명' 단위로 읽기 좋게."""
    if n is None:
        return "-"
    if n >= 10000:
        return f"{n / 10000:,.1f}"
    return f"{n / 10000:.2f}"


def _rank_move(inten: str | None, old_new: str | None) -> str:
    if (old_new or "").upper() == "NEW":
        return "신규 진입"
    v = http.to_int(inten)
    if v is None or v == 0:
        return "순위 유지"
    return f"{'▲' if v > 0 else '▼'} {abs(v)}"


def _rows(items: list[dict], top: int) -> list[dict]:
    out = []
    for r in items[:top]:
        audi = http.to_int(r.get("audiCnt"))
        acc = http.to_int(r.get("audiAcc"))
        out.append({
            "rank": r.get("rank"),
            "title": (r.get("movieNm") or "").strip(),
            "open": (r.get("openDt") or "").strip(),
            "audi": f"{audi:,}" if audi is not None else "-",
            "audi_man": _man(audi),
            "acc_man": _man(acc),
            "move": _rank_move(r.get("rankInten"), r.get("rankOldAndNew")),
            "screens": (lambda v: f"{v:,}" if v is not None else "-")(http.to_int(r.get("scrnCnt"))),
        })
    return out


def _live_fetch_daily(now: datetime | None = None, top: int = 5) -> dict:
    """어제 일별 박스오피스. KOBIS 는 당일 집계가 없어 하루 전을 본다."""
    key = _require_key()
    now = now or datetime.now(config.KST)
    target = (now - timedelta(days=1)).strftime("%Y%m%d")

    log.info("KOBIS 일별 박스오피스 조회 target=%s", target)
    doc = http.get(f"{BASE}/searchDailyBoxOfficeList.json",
                   {"key": key, "targetDt": target}, check_header=False)
    items = http.as_list((doc.get("boxOfficeResult") or {}).get("dailyBoxOfficeList"))
    if not items:
        raise http.NoData("03", f"{target} 박스오피스 데이터가 없습니다")

    rows = _rows(items, top)
    d = datetime.strptime(target, "%Y%m%d")
    return {
        "kind": "daily",
        "target": target,
        "target_label": f"{d.month}월 {d.day}일",
        "range_label": f"{d.month}월 {d.day}일 하루",
        "top": rows[0],
        "rows": rows,
        "total_man": _man(sum(http.to_int(r.get("audiCnt")) or 0 for r in items)),
        "movie_count": len(items),
    }


def _live_fetch_weekly(now: datetime | None = None, top: int = 5) -> dict:
    """지난 주말(금~일) 박스오피스. weekGb=1 이 '주말' 집계다."""
    key = _require_key()
    now = now or datetime.now(config.KST)
    # 지난 주 일요일을 기준일로 넣으면 그 주 집계가 나온다
    target = (now - timedelta(days=now.weekday() + 1)).strftime("%Y%m%d")

    log.info("KOBIS 주말 박스오피스 조회 target=%s", target)
    doc = http.get(f"{BASE}/searchWeeklyBoxOfficeList.json",
                   {"key": key, "targetDt": target, "weekGb": "1"},
                   check_header=False)
    result = doc.get("boxOfficeResult") or {}
    items = http.as_list(result.get("weeklyBoxOfficeList"))
    if not items:
        raise http.NoData("03", f"{target} 주말 박스오피스 데이터가 없습니다")

    rows = _rows(items, top)
    show_range = str(result.get("showRange") or "")
    label = show_range
    if "~" in show_range:
        a, b = show_range.split("~")[:2]
        try:
            da, db = datetime.strptime(a, "%Y%m%d"), datetime.strptime(b, "%Y%m%d")
            label = f"{da.month}월 {da.day}일~{db.month}월 {db.day}일"
        except ValueError:
            pass
    return {
        "kind": "weekly",
        "target": target,
        "target_label": label,
        "range_label": f"{label} 주말",
        "top": rows[0],
        "rows": rows,
        "total_man": _man(sum(http.to_int(r.get("audiCnt")) or 0 for r in items)),
        "movie_count": len(items),
    }


def fetch_daily(now: datetime | None = None, top: int = 5) -> dict:
    """수집 실패 시 마지막 성공분으로 대신한다 (최대 사흘)."""
    return cache.remember(
        "boxoffice-daily", lambda: _live_fetch_daily(now, top), max_age_days=3)


def fetch_weekly(now: datetime | None = None, top: int = 5) -> dict:
    """수집 실패 시 마지막 성공분으로 대신한다 (최대 열흘)."""
    return cache.remember(
        "boxoffice-weekly", lambda: _live_fetch_weekly(now, top), max_age_days=10)
