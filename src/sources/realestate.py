"""국토교통부 아파트 매매 실거래가 → 부동산 카드 데이터.

이 API 는 XML 만 지원한다 (JSON 파라미터 없음).
"""
from __future__ import annotations

import logging
from datetime import datetime

from src import config
from src.common import http

log = logging.getLogger(__name__)

BASE = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev"
OP = "getRTMSDataSvcAptTradeDev"

MIN_DEALS = 10          # 이보다 적으면 직전 달로 후퇴
PYEONG = 3.305785       # 1평 = 3.305785㎡


def _prev_month(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[4:])
    return f"{y-1}12" if m == 1 else f"{y}{m-1:02d}"


def _fetch_one(lawd_cd: str, deal_ymd: str) -> list[dict]:
    doc = http.get(
        f"{BASE}/{OP}",
        {
            "serviceKey": config.DATA_GO_KR_KEY,
            "LAWD_CD": lawd_cd,
            "DEAL_YMD": deal_ymd,
            "pageNo": 1,
            "numOfRows": 1000,
        },
    )
    body = doc.get("response", {}).get("body") or {}
    items = (body.get("items") or {})
    if not isinstance(items, dict):
        return []
    return http.as_list(items.get("item"))


def _parse_deal(it: dict, lawd_cd: str) -> dict | None:
    # 해제된 거래(계약 취소)는 집계에서 제외
    if str(it.get("cdealType") or "").strip().upper() == "O":
        return None
    raw = str(it.get("dealAmount") or "").strip().replace(",", "")
    if not raw.isdigit():
        return None
    man_won = int(raw)                       # 단위: 만원
    area = http.to_float(it.get("excluUseAr"))
    if not area:
        return None
    return {
        "gu": config.LAWD_NAMES.get(lawd_cd, lawd_cd),
        "name": (it.get("aptNm") or "").strip(),
        "dong": (it.get("umdNm") or "").strip(),
        "area": round(area, 1),
        "floor": http.to_int(it.get("floor"), 0),
        "man_won": man_won,
        "per_pyeong": round(man_won / (area / PYEONG)),
        "day": http.to_int(it.get("dealDay"), 0),
    }


def fetch(lawd_cds: list[str] = None, now: datetime = None) -> dict:
    lawd_cds = lawd_cds or config.REALESTATE_LAWD_CDS
    now = now or datetime.now(config.KST)
    ym = now.strftime("%Y%m")

    deals: list[dict] = []
    for attempt in range(2):
        deals = []
        ok_gu, failed_gu = [], []
        for cd in lawd_cds:
            try:
                rows = _fetch_one(cd, ym)
            except http.NoData:
                rows = []
            except Exception as e:                # noqa: BLE001
                # 이 API 는 해외에서 붙을 때 간헐적으로 타임아웃이 난다.
                # 한 구가 실패했다고 카드를 통째로 버리지 않는다.
                log.warning("실거래 %s 조회 실패, 건너뜀: %s",
                            config.LAWD_NAMES.get(cd, cd), e)
                failed_gu.append(cd)
                continue
            ok_gu.append(cd)
            for it in rows:
                d = _parse_deal(it, cd)
                if d:
                    deals.append(d)
            log.info("실거래 %s %s: %d건 누적", config.LAWD_NAMES.get(cd, cd), ym, len(deals))
        if failed_gu:
            log.warning("조회 실패한 시군구 %d곳은 집계에서 제외합니다: %s",
                        len(failed_gu),
                        ", ".join(config.LAWD_NAMES.get(c, c) for c in failed_gu))
        if len(deals) >= MIN_DEALS or attempt == 1:
            break
        ym = _prev_month(ym)          # 월초라 표본이 적으면 직전 달로
        log.info("표본 부족 → %s 로 재조회", ym)

    if not deals:
        raise http.NoData("03", f"{ym} 실거래 데이터가 없습니다")

    # 전월 대비 평균가 변화. 실패해도 카드는 나가야 하므로 조용히 건너뛴다.
    # 비교 대상은 이번 달에 성공한 시군구로 맞춘다 (표본이 다르면 증감이 왜곡된다).
    prev_ym = _prev_month(ym)
    prev_deals: list[dict] = []
    for cd in ok_gu:
        try:
            for it in _fetch_one(cd, prev_ym):
                d = _parse_deal(it, cd)
                if d:
                    prev_deals.append(d)
        except Exception as e:                    # noqa: BLE001
            log.warning("전월(%s) %s 조회 실패, 증감 계산에서 제외: %s",
                        prev_ym, config.LAWD_NAMES.get(cd, cd), e)
            prev_deals = []
            break

    avg = sum(d["man_won"] for d in deals) / len(deals)
    prev_avg = (sum(d["man_won"] for d in prev_deals) / len(prev_deals)) if prev_deals else None

    if prev_avg:
        pct = (avg - prev_avg) / prev_avg * 100
        direction = "up" if pct > 0.3 else "down" if pct < -0.3 else "flat"
        delta_text = f"전월 대비 {pct:+.1f}%"
    else:
        direction, delta_text = "flat", "전월 데이터 없음"

    top = sorted(deals, key=lambda d: d["man_won"], reverse=True)[:3]

    return {
        "ym": ym,
        "ym_label": f"{int(ym[:4])}년 {int(ym[4:])}월",
        "gu_names": [config.LAWD_NAMES.get(c, c) for c in ok_gu],
        "deal_count": f"{len(deals):,}",
        "avg_price": f"{avg / 10000:.1f}",                 # 만원 → 억
        "per_pyeong": f"{round(sum(d['per_pyeong'] for d in deals) / len(deals)):,}",
        "delta_dir": direction,
        "delta_text": delta_text,
        "top": [{
            "name": t["name"],
            "dong": f"{t['gu']} {t['dong']}",
            "area": t["area"],
            "floor": t["floor"],
            "price": f"{t['man_won'] / 10000:.1f}억",
        } for t in top],
    }
