"""기상청 생활기상지수 → 생활지수 카드 데이터.

공공데이터포털 키를 그대로 쓴다. 지수마다 서비스가 갈려 있고
계절에 따라 열리고 닫히는 것(체감온도=여름, 동파=겨울)이 있어서,
여러 개를 호출해 '응답이 온 것만' 카드에 올린다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from src import config
from src.common import http

log = logging.getLogger(__name__)

BASE = "https://apis.data.go.kr/1360000/LivingWthrIdxServiceV4"

# (엔드포인트, 표시명, 단위, 임계값 → 등급 함수용 키)
INDEXES = [
    ("getUVIdxV4", "자외선", "uv"),
    ("getSenTaIdxV4", "체감온도", "senta"),
    ("getAirDiffusionIdxV4", "대기정체", "air"),
    ("getWinterWthrIdxV4", "동파가능", "winter"),
]

GRADES = {
    "uv":     [(3, "낮음", 1), (6, "보통", 2), (8, "높음", 3), (11, "매우높음", 3), (99, "위험", 4)],
    "air":    [(50, "낮음", 1), (75, "보통", 2), (100, "높음", 3), (999, "매우높음", 4)],
    "winter": [(25, "낮음", 1), (50, "보통", 2), (75, "높음", 3), (999, "매우높음", 4)],
}


def _grade(kind: str, value: float | None) -> tuple[str, int]:
    if value is None:
        return "-", 2
    table = GRADES.get(kind)
    if not table:                       # 체감온도처럼 등급 체계가 없는 지수
        return "", 2
    for limit, text, g in table:
        if value < limit:
            return text, g
    return table[-1][1], table[-1][2]


def _base_time(now: datetime) -> str:
    """생활기상지수는 06시/18시 발표. 가장 최근 발표 시각을 만든다."""
    t = now
    if t.hour < 6:
        t = t - timedelta(days=1)
        return t.strftime("%Y%m%d") + "18"
    if t.hour < 18:
        return t.strftime("%Y%m%d") + "06"
    return t.strftime("%Y%m%d") + "18"


def _call(endpoint: str, area: str, time_str: str) -> dict | None:
    try:
        doc = http.get(f"{BASE}/{endpoint}", {
            "serviceKey": config.DATA_GO_KR_KEY,
            "pageNo": 1, "numOfRows": 10, "dataType": "JSON",
            "areaNo": area, "time": time_str,
        })
    except Exception as e:              # noqa: BLE001
        # 지수마다 서비스가 갈려 있어 어떤 건 400 을 주고 어떤 건 닫혀 있다.
        # 하나가 죽어도 나머지로 카드를 만든다 (전부 죽으면 아래에서 NoData).
        log.info("%s 건너뜀: %s", endpoint, e)
        return None
    items = http.as_list(
        (((doc.get("response") or {}).get("body") or {}).get("items") or {}).get("item"))
    return items[0] if items else None


def fetch(now: datetime | None = None) -> dict:
    if not config.DATA_GO_KR_KEY:
        raise http.NoData("03", "DATA_GO_KR_KEY 가 없습니다")

    now = now or datetime.now(config.KST)
    time_str = _base_time(now)
    area = config.LIFEINDEX_AREA

    found = []
    for endpoint, label, kind in INDEXES:
        item = _call(endpoint, area, time_str)
        if not item:
            continue
        # h0 = 발표 시각 기준 현재, h3/h6… = 3시간 간격 예측
        now_v = http.to_float(item.get("h0"))
        if now_v is None:
            now_v = http.to_float(item.get("h3"))
        text, g = _grade(kind, now_v)
        series = []
        for h in (0, 6, 12, 18, 24):
            v = http.to_float(item.get(f"h{h}"))
            if v is None:
                continue
            series.append({"label": f"+{h}h" if h else "지금", "value": f"{v:.0f}"})
        found.append({
            "kind": kind, "label": label,
            "value": f"{now_v:.0f}" if now_v is not None else "-",
            "text": text, "grade": g, "series": series,
        })

    if not found:
        raise http.NoData("03", "생활기상지수 응답이 비어 있습니다 (계절·지역 확인)")

    head = found[0]
    d = datetime.strptime(time_str[:8], "%Y%m%d")
    return {
        "region": config.LIFEINDEX_REGION,
        "date": time_str[:8],
        "date_label": f"{d.month}월 {d.day}일",
        "base_time": f"{time_str[8:]}시 발표",
        "head": head,
        "items": found,
        "others": found[1:],
    }
