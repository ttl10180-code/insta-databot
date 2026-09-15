"""농수산물 일별 소매가 → 장바구니 물가 카드 데이터.

KAMIS 사이트의 별도 키 대신 공공데이터포털의
'한국농수산식품유통공사_일별 도,소매 가격정보 조회' 를 쓴다.
같은 데이터인데 DATA_GO_KR_KEY 하나로 되고 심의도 자동승인이다.

품목코드를 하나하나 맞춰 넣는 대신, 부류(채소·축산 등) 단위로 받아 와서
품목명으로 고른다. 코드표가 바뀌어도 잘 깨지지 않고, 어떤 품목이 실제로
내려오는지 로그로 남아 다음에 조정하기도 쉽다.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from src import config
from src.common import http

log = logging.getLogger(__name__)

URL = "https://apis.data.go.kr/B552845/perDay/price"

# 카드에 올릴 품목: (부류코드, 품목명 조각). 위에서부터 우선순위.
# 품목명은 부분일치로 찾으므로 응답의 정확한 표기를 몰라도 걸린다.
WANTED = [
    ("500", "계란"),
    ("200", "배추"),
    ("500", "삼겹살"),
    ("200", "대파"),
    ("100", "쌀"),
    ("200", "양파"),
    ("400", "사과"),
]
# 부류코드: 100 식량작물 / 200 채소류 / 300 특용작물 / 400 과일류 / 500 축산물 / 600 수산물
MAX_ITEMS = 6


def _num(v) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def _call(params: dict) -> dict:
    """한 번 호출하고 header/body 를 그대로 돌려준다."""
    doc = http.get(URL, dict(params, serviceKey=config.DATA_GO_KR_KEY),
                   check_header=False) or {}
    if not isinstance(doc, dict):
        return {}
    return doc


def _rows_of(doc: dict) -> list[dict]:
    """응답 모양이 두 가지다.
    표준 포털형: body.items.item[] / odcloud형: 최상위 data[]"""
    if isinstance(doc.get("data"), list):
        return [r for r in doc["data"] if isinstance(r, dict)]
    body = doc.get("body") or doc.get("response", {}).get("body") or {}
    if not isinstance(body, dict):
        return []
    items = body.get("items")
    if isinstance(items, dict):
        items = items.get("item")
    return [r for r in http.as_list(items) if isinstance(r, dict)]


def _result_of(doc: dict) -> str:
    head = doc.get("header") or doc.get("response", {}).get("header") or {}
    code = head.get("resultCode") or head.get("result_code")
    msg = head.get("resultMsg") or head.get("result_msg")
    return f"{code} {msg}".strip()


# 조사일자 표기가 20260915 인지 2026-09-15 인지 응답을 봐야 안다.
# 첫 호출에서 먹히는 쪽을 찾아 두고 이후 부류에도 같은 표기를 쓴다.
_DATE_FORMATS = ("%Y%m%d", "%Y-%m-%d")
_date_fmt: str | None = None


def _fetch_category(ctgry: str, since_dt: datetime, until_dt: datetime) -> list[dict]:
    """한 부류의 기간 내 가격 레코드. 날짜 표기를 모르면 순서대로 시도한다."""
    global _date_fmt
    base = {"pageNo": 1, "numOfRows": 1000, "returnType": "JSON",
            "cond[ctgry_cd::EQ]": ctgry}

    formats = (_date_fmt,) if _date_fmt else _DATE_FORMATS
    rows: list[dict] = []
    for fmt in formats:
        doc = _call(dict(base, **{
            "cond[exmn_ymd::GTE]": since_dt.strftime(fmt),
            "cond[exmn_ymd::LTE]": until_dt.strftime(fmt),
        }))
        rows = _rows_of(doc)
        if rows:
            _date_fmt = fmt
            break
        log.info("부류 %s · 날짜표기 %s → 0건 (%s)", ctgry, fmt, _result_of(doc) or "헤더 없음")

    if not rows:
        # 조건을 전부 떼고 맨몸으로 한 번 찔러, 응답이 어떻게 생겼는지 남긴다.
        # (부류 필터까지 떼야 한다 — 코드값이 틀렸을 가능성도 있다)
        doc = _call({"pageNo": 1, "numOfRows": 3, "returnType": "JSON"})
        # 응답을 그대로 찍는다. 인증키는 응답에 실리지 않으니 안전하다.
        log.warning("부류 %s · 조건 없는 맨몸 응답 원문:\n%s", ctgry,
                    json.dumps(doc, ensure_ascii=False)[:1200])
        return []

    retail = [r for r in rows if "소매" in str(r.get("se_nm", ""))]
    log.info("부류 %s: 전체 %d건, 소매 %d건", ctgry, len(rows), len(retail))
    return retail or rows


def _pick(rows: list[dict], name_part: str) -> tuple[dict, dict | None] | None:
    """품목명이 걸리는 레코드 중 최신 조사일과 그 직전 조사일을 짝지어 준다."""
    hit = [r for r in rows
           if name_part in str(r.get("item_nm", ""))
           and _num(r.get("exmn_dd_prc")) is not None]
    if not hit:
        return None
    hit.sort(key=lambda r: str(r.get("exmn_ymd", "")), reverse=True)
    latest = hit[0]
    day = str(latest.get("exmn_ymd"))
    # 같은 품목·같은 등급의 이전 조사일을 찾는다
    prev = next((r for r in hit
                 if str(r.get("exmn_ymd")) < day
                 and r.get("grd_cd") == latest.get("grd_cd")), None)
    return latest, prev


def _delta_text(diff: float | None) -> str:
    if diff is None:
        return "전일 대비 -"
    if abs(diff) < 1:
        return "전일과 동일"
    return f"전일 대비 {diff:+,.0f}원"


def fetch(now: datetime | None = None) -> dict:
    if not config.DATA_GO_KR_KEY:
        raise http.NoData("03", "DATA_GO_KR_KEY 가 없습니다")

    now = now or datetime.now(config.KST)
    # 조사일은 며칠씩 밀려 올라오므로 넉넉히 30일을 본다.
    until_dt = now
    since_dt = now - timedelta(days=30)

    cache: dict[str, list[dict]] = {}
    items, missing = [], []
    for ctgry, name_part in WANTED:
        if len(items) >= MAX_ITEMS:
            break
        if ctgry not in cache:
            try:
                cache[ctgry] = _fetch_category(ctgry, since_dt, until_dt)
            except http.PortalError as e:
                log.warning("부류 %s 조회 실패: %s", ctgry, e)
                cache[ctgry] = []
        found = _pick(cache[ctgry], name_part)
        if not found:
            missing.append(name_part)
            continue
        latest, prev = found
        today = _num(latest.get("exmn_dd_prc"))
        before = _num((prev or {}).get("exmn_dd_prc"))
        diff = None if (today is None or before is None) else today - before
        unit = f"{latest.get('unit_sz') or ''}{latest.get('unit') or ''}".strip()
        items.append({
            "name": str(latest.get("item_nm") or name_part).strip(),
            "unit": unit or "-",
            "price": f"{today:,.0f}",
            "delta": _delta_text(diff),
            "dir": "flat" if diff is None or abs(diff) < 1 else ("up" if diff > 0 else "down"),
            "day": str(latest.get("exmn_ymd") or ""),
            "grade": str(latest.get("grd_nm") or "").strip(),
        })

    if missing:
        log.info("응답에 없어 건너뛴 품목: %s", ", ".join(missing))
    if not items:
        raise http.NoData("03", "가격 데이터를 한 건도 찾지 못했습니다 (활용신청 승인 여부 확인)")

    day = items[0]["day"]
    label = day
    for fmt in _DATE_FORMATS:
        try:
            d = datetime.strptime(day, fmt)
        except ValueError:
            continue
        label = f"{d.month}월 {d.day}일"
        break

    head = items[0]
    return {
        "date_label": label,
        "head": head,
        "items": items,
        "rest": items[1:],
        "up_count": sum(1 for i in items if i["dir"] == "up"),
        "down_count": sum(1 for i in items if i["dir"] == "down"),
        "watch_count": len(items),
    }
