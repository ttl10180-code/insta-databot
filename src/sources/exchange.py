"""한국수출입은행 환율 → 환율 카드 데이터.

koreaexim.go.kr 에서 직접 발급하는 authkey 를 쓴다 (공공데이터포털 키 아님).
주말·공휴일에는 빈 배열이 오므로 최대 7일 전까지 거슬러 올라간다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from src import config
from src.common import http

log = logging.getLogger(__name__)

URL = "https://www.koreaexim.go.kr/site/program/financial/exchangeJSON"

# 카드에 올릴 통화: (응답 cur_unit, 표시명, 이모지)
WANTED = [
    ("USD", "미국 달러", "🇺🇸"),
    ("JPY(100)", "일본 엔 100", "🇯🇵"),
    ("EUR", "유로", "🇪🇺"),
    ("CNH", "중국 위안", "🇨🇳"),
]


def _num(v) -> float | None:
    """'1,398.5' 같은 문자열을 실수로."""
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def _fetch_day(key: str, ymd: str) -> list[dict]:
    doc = http.get(URL, {"authkey": key, "searchdate": ymd, "data": "AP01"},
                   check_header=False)
    rows = doc if isinstance(doc, list) else http.as_list(doc)
    # result=1 이 정상. 휴일이면 빈 배열이거나 result=2(데이터 없음)
    return [r for r in rows if isinstance(r, dict) and str(r.get("result")) == "1"]


def fetch(now: datetime | None = None) -> dict:
    if not config.EXIM_KEY:
        raise http.NoData("03", "EXIM_KEY 가 없어 환율 카드를 건너뜁니다")

    now = now or datetime.now(config.KST)
    rows, used = [], None
    for back in range(0, 8):          # 오늘 → 최대 7일 전까지 영업일 탐색
        ymd = (now - timedelta(days=back)).strftime("%Y%m%d")
        log.info("수출입은행 환율 조회 %s", ymd)
        try:
            rows = _fetch_day(config.EXIM_KEY, ymd)
        except http.PortalError:
            rows = []
        if rows:
            used = ymd
            break
    if not rows:
        raise http.NoData("03", "최근 7일간 환율 데이터를 찾지 못했습니다")

    by_unit = {str(r.get("cur_unit", "")).strip(): r for r in rows}

    # 전 영업일과 비교해 등락을 만든다 (실패해도 카드는 나간다)
    prev = {}
    base = datetime.strptime(used, "%Y%m%d")
    for back in range(1, 8):
        ymd = (base - timedelta(days=back)).strftime("%Y%m%d")
        try:
            prows = _fetch_day(config.EXIM_KEY, ymd)
        except http.PortalError:
            prows = []
        if prows:
            prev = {str(r.get("cur_unit", "")).strip(): r for r in prows}
            break

    items = []
    for unit, name, flag in WANTED:
        r = by_unit.get(unit)
        if not r:
            continue
        cur = _num(r.get("deal_bas_r"))
        old = _num((prev.get(unit) or {}).get("deal_bas_r"))
        diff = None if (cur is None or old is None) else cur - old
        items.append({
            "unit": unit,
            "name": name,
            "flag": flag,
            "rate": f"{cur:,.2f}" if cur is not None else "-",
            "diff": diff,
            "delta": _delta_text(diff),
            "dir": "flat" if diff is None or abs(diff) < 0.005 else ("up" if diff > 0 else "down"),
            "ttb": f"{_num(r.get('ttb')):,.2f}" if _num(r.get("ttb")) else "-",
            "tts": f"{_num(r.get('tts')):,.2f}" if _num(r.get("tts")) else "-",
        })
    if not items:
        raise http.NoData("03", "카드에 쓸 통화가 응답에 없습니다")

    d = datetime.strptime(used, "%Y%m%d")
    usd = next((i for i in items if i["unit"] == "USD"), items[0])
    return {
        "date": used,
        "date_label": f"{d.month}월 {d.day}일",
        "usd": usd,
        "items": items,
        "others": [i for i in items if i["unit"] != usd["unit"]],
    }


def _delta_text(diff: float | None) -> str:
    if diff is None:
        return "전일 대비 -"
    if abs(diff) < 0.005:
        return "전일과 동일"
    return f"전일 대비 {diff:+,.2f}원"
