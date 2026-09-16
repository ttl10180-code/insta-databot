"""기상청 생활기상지수 → 생활지수 카드 데이터.

공공데이터포털 키를 그대로 쓴다.

주의 — 서비스 주소와 실제 경로가 어긋나 있다. 포털 화면에는
"생활기상지수 조회서비스(4.0)" 으로 적혀 있지만, 실제 호출 경로는
`LivingWthrIdxServiceV5` 이고 오퍼레이션도 `...V5` 로 끝난다.
V4 경로로 부르면 전부 400 이 돌아온다 (2026-09 확인).

4.0 에서 이 서비스에 남은 지수는 자외선·대기정체 두 개뿐이다.
체감온도·동파가능은 이 서비스에 없다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from src import config
from src.common import http

log = logging.getLogger(__name__)

BASE = "https://apis.data.go.kr/1360000/LivingWthrIdxServiceV5"

# (엔드포인트, 표시명, 등급 키, 첫 예측 시각)
# 자외선은 h0(지금)부터, 대기정체는 h3 부터 온다 — 시작점이 다르다.
INDEXES = [
    ("getUVIdxV5", "자외선", "uv", 0),
    ("getAirDiffusionIdxV5", "대기정체", "air", 3),
]

GRADES = {
    "uv":  [(3, "낮음", 1), (6, "보통", 2), (8, "높음", 3), (11, "매우높음", 3), (99, "위험", 4)],
    "air": [(38, "낮음", 1), (63, "보통", 2), (88, "높음", 3), (999, "매우높음", 4)],
}

# 발표는 3시간 간격(00/03/…/21). 최근 발표분이 아직 안 올라왔을 수 있어
# 몇 칸 뒤로 물러나며 찾는다.
STEP_HOURS = 3
LOOKBACK_STEPS = 4


def _grade(kind: str, value: float | None) -> tuple[str, int]:
    if value is None:
        return "-", 2
    table = GRADES.get(kind)
    if not table:
        return "", 2
    for limit, text, g in table:
        if value < limit:
            return text, g
    return table[-1][1], table[-1][2]


def _base_times(now: datetime) -> list[str]:
    """최근 발표 시각부터 과거로 몇 개."""
    t = now.replace(minute=0, second=0, microsecond=0)
    t = t - timedelta(hours=t.hour % STEP_HOURS)
    return [(t - timedelta(hours=STEP_HOURS * i)).strftime("%Y%m%d%H")
            for i in range(LOOKBACK_STEPS)]


def _call(endpoint: str, area: str, time_str: str) -> dict | None:
    try:
        doc = http.get(f"{BASE}/{endpoint}", {
            "serviceKey": config.DATA_GO_KR_KEY,
            "pageNo": 1, "numOfRows": 10, "dataType": "JSON",
            "areaNo": area, "time": time_str,
        })
    except http.NoData:
        return None
    except Exception as e:              # noqa: BLE001
        # 하나가 죽어도 나머지로 카드를 만든다 (전부 죽으면 아래에서 NoData).
        log.info("%s(%s) 건너뜀: %s", endpoint, time_str, e)
        return None
    items = http.as_list(
        (((doc.get("response") or {}).get("body") or {}).get("items") or {}).get("item"))
    return items[0] if items else None


def _fetch_index(endpoint: str, area: str, times: list[str]) -> tuple[dict, str] | None:
    """발표 시각을 뒤로 물리며 값이 들어 있는 응답을 찾는다.

    밤에는 자외선 예측값이 통째로 빈 문자열로 오기 때문에, 응답이 왔다는
    것만으로는 부족하고 숫자가 하나라도 있어야 쓸모가 있다."""
    for t in times:
        item = _call(endpoint, area, t)
        if not item:
            continue
        if any(http.to_float(v) is not None
               for k, v in item.items() if k.startswith("h")):
            return item, t
    return None


def fetch(now: datetime | None = None) -> dict:
    if not config.DATA_GO_KR_KEY:
        raise http.NoData("03", "DATA_GO_KR_KEY 가 없습니다")

    now = now or datetime.now(config.KST)
    times = _base_times(now)
    area = config.LIFEINDEX_AREA

    found = []
    used_time = times[0]          # 카드에 적는 기준 시각 = 첫 지수가 쓴 발표분
    for endpoint, label, kind, first_h in INDEXES:
        got = _fetch_index(endpoint, area, times)
        if not got:
            continue
        item, t = got
        if not found:
            used_time = t

        now_v = None
        for h in range(first_h, 25, STEP_HOURS):
            now_v = http.to_float(item.get(f"h{h}"))
            if now_v is not None:
                break
        text, g = _grade(kind, now_v)

        series = []
        for h in range(first_h, 79, STEP_HOURS):
            v = http.to_float(item.get(f"h{h}"))
            if v is None:
                continue
            series.append({"label": "지금" if h == 0 else f"+{h}h",
                           "value": f"{v:.0f}"})
            if len(series) >= 5:
                break

        found.append({
            "kind": kind, "label": label,
            "value": f"{now_v:.0f}" if now_v is not None else "-",
            "text": text, "grade": g, "series": series,
        })

    if not found:
        raise http.NoData("03", "생활기상지수 응답이 비어 있습니다 (계절·지역 확인)")

    head = found[0]
    d = datetime.strptime(used_time[:8], "%Y%m%d")
    return {
        "region": config.LIFEINDEX_REGION,
        "date": used_time[:8],
        "date_label": f"{d.month}월 {d.day}일",
        "base_time": f"{used_time[8:]}시 발표",
        "head": head,
        "items": found,
        "others": found[1:],
    }
