"""오피넷 유가정보 → 유가 카드 데이터.

주의: 이 API 는 공공데이터포털에 'LINK' 로 등록되어 있고,
실제 호출은 opinet.co.kr 에 오피넷이 발급한 certkey 로 한다.
(공공데이터포털의 serviceKey 를 쓰지 않는다)
일 300회 제한이 있으므로 하루 1~2회만 호출할 것.
"""
from __future__ import annotations

import logging

from src import config
from src.common import http

log = logging.getLogger(__name__)

BASE = "https://www.opinet.co.kr/api"

PRODUCTS = {
    "B027": "휘발유",
    "D047": "경유",
    "K015": "LPG",
    "B034": "고급휘발유",
    "C004": "실내등유",
}
CARD_PRODUCTS = ["B027", "D047", "K015"]


def _delta_text(diff: float | None) -> str:
    if diff is None:
        return "전일 대비 -"
    if abs(diff) < 0.05:
        return "전일과 동일"
    return f"전일 대비 {diff:+.1f}원"


def fetch(area: str = None) -> dict:
    area = area or config.OPINET_AREA
    if not config.OPINET_KEY:
        # 다른 카드와 같게 — 키가 없으면 이 카드만 조용히 건너뛴다.
        # SystemExit 를 던지면 같은 실행의 다른 카드까지 죽는다.
        raise http.NoData("03", "OPINET_KEY 가 없습니다 (오피넷에서 발급 필요)")

    log.info("오피넷 전국 평균 유가 조회")
    doc = http.get(f"{BASE}/avgAllPrice.do",
                   {"out": "json", "code": config.OPINET_KEY},
                   check_header=False)
    rows = http.as_list((doc.get("RESULT") or {}).get("OIL"))
    prices = {str(r.get("PRODCD")): r for r in rows}
    if not prices:
        raise http.NoData("03", "오피넷 평균가 응답이 비어 있습니다")

    gas = prices.get("B027", {})
    gas_price = http.to_float(gas.get("PRICE"))
    gas_diff = http.to_float(gas.get("DIFF"))

    fuels = []
    for code in CARD_PRODUCTS:
        r = prices.get(code)
        if not r:
            continue
        p = http.to_float(r.get("PRICE"))
        fuels.append({
            "name": PRODUCTS.get(code, code),
            "price": f"{p:,.0f}" if p is not None else "-",
            "delta": _delta_text(http.to_float(r.get("DIFF"))),
        })

    # 지역 최저가 주유소 TOP3 (실패해도 카드는 나가도록 방어)
    cheapest = []
    try:
        doc2 = http.get(f"{BASE}/lowTop10.do",
                        {"out": "json", "code": config.OPINET_KEY,
                         "area": area, "prodcd": "B027", "cnt": 3},
                        check_header=False)
        for r in http.as_list((doc2.get("RESULT") or {}).get("OIL"))[:3]:
            p = http.to_float(r.get("PRICE"))
            cheapest.append({
                "name": (r.get("OS_NM") or "").strip(),
                "addr": (r.get("NEW_ADR") or r.get("VAN_ADR") or "").strip(),
                "price": f"{p:,.0f}원" if p is not None else "-",
            })
    except Exception as e:                       # noqa: BLE001
        log.warning("최저가 주유소 조회 실패(카드는 계속 생성): %s", e)

    trade_dt = str(gas.get("TRADE_DT") or "")
    direction = ("flat" if gas_diff is None or abs(gas_diff) < 0.05
                 else "up" if gas_diff > 0 else "down")

    return {
        "trade_dt": trade_dt,
        "gasoline": f"{gas_price:,.1f}" if gas_price is not None else "-",
        "gasoline_delta": _delta_text(gas_diff),
        "gasoline_dir": direction,
        "fuels": fuels,
        "cheapest": cheapest,
    }
