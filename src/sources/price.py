"""KAMIS 농수산물 소매가격 → 장바구니 물가 카드 데이터.

kamis.or.kr 에서 발급하는 인증키 + 아이디를 함께 요구한다.
dailySalesList 는 주요 품목의 당일 소매가와 등락을 한 번에 준다.
"""
from __future__ import annotations

import logging
from datetime import datetime

from src import config
from src.common import http

log = logging.getLogger(__name__)

URL = "https://www.kamis.or.kr/service/price/xml.do"

# 카드에 올릴 품목 우선순위. 응답의 item_name 과 부분일치로 고른다.
PICKS = ["계란", "배추", "무", "쌀", "삼겹살", "돼지고기", "양파", "대파", "감자", "사과"]
UNIT_FIX = {"1": "", "개": "개"}


def _num(v) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("원", "").strip())
    except ValueError:
        return None


def _pick_name(row: dict) -> str:
    return (row.get("item_name") or row.get("productName") or "").strip()


def fetch(now: datetime | None = None) -> dict:
    if not (config.KAMIS_KEY and config.KAMIS_ID):
        raise http.NoData("03", "KAMIS_KEY / KAMIS_ID 가 없어 물가 카드를 건너뜁니다")

    log.info("KAMIS 주요 품목 소매가 조회")
    doc = http.get(URL, {
        "action": "dailySalesList",
        "p_cert_key": config.KAMIS_KEY,
        "p_cert_id": config.KAMIS_ID,
        "p_returntype": "json",
    }, check_header=False)

    rows = http.as_list(doc.get("price") if isinstance(doc, dict) else doc)
    rows = [r for r in rows if isinstance(r, dict) and _num(r.get("dpr1")) is not None]
    if not rows:
        raise http.NoData("03", "KAMIS 응답에 가격 데이터가 없습니다")

    # 관심 품목을 우선순위대로, 없으면 응답 순서대로 채운다
    chosen, seen = [], set()
    for want in PICKS:
        for r in rows:
            name = _pick_name(r)
            if want in name and name not in seen:
                chosen.append(r)
                seen.add(name)
                break
    for r in rows:
        if len(chosen) >= 6:
            break
        name = _pick_name(r)
        if name not in seen:
            chosen.append(r)
            seen.add(name)

    items = []
    for r in chosen[:6]:
        today = _num(r.get("dpr1"))
        yday = _num(r.get("dpr2"))
        month = _num(r.get("dpr3"))
        diff = None if (today is None or yday is None) else today - yday
        pct = None
        if today is not None and month:
            pct = (today - month) / month * 100
        items.append({
            "name": _pick_name(r),
            "unit": (r.get("unit") or "").strip(),
            "price": f"{today:,.0f}" if today is not None else "-",
            "delta": _delta_text(diff),
            "dir": "flat" if diff is None or abs(diff) < 1 else ("up" if diff > 0 else "down"),
            "month_pct": f"{pct:+.1f}%" if pct is not None else "-",
        })

    head = items[0]
    up = sum(1 for i in items if i["dir"] == "up")
    down = sum(1 for i in items if i["dir"] == "down")
    day = str(rows[0].get("lastest_day") or "").strip()
    return {
        "date_label": day or (now or datetime.now(config.KST)).strftime("%m월 %d일"),
        "head": head,
        "items": items,
        "rest": items[1:],
        "up_count": up,
        "down_count": down,
        "watch_count": len(items),
    }


def _delta_text(diff: float | None) -> str:
    if diff is None:
        return "전일 대비 -"
    if abs(diff) < 1:
        return "전일과 동일"
    return f"전일 대비 {diff:+,.0f}원"
