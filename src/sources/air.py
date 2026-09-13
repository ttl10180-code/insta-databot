"""에어코리아 대기오염정보 → 대기질 카드 데이터."""
from __future__ import annotations

import logging
from datetime import datetime

from src import config
from src.common import http

log = logging.getLogger(__name__)

BASE = "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc"

GRADE_TEXT = {1: "좋음", 2: "보통", 3: "나쁨", 4: "매우나쁨"}


def _grade(value: float | None, kind: str) -> int:
    """등급이 결측일 때 농도로 직접 환산 (환경부 기준)."""
    if value is None:
        return 2
    if kind == "pm10":
        cuts = (30, 80, 150)
    else:  # pm25
        cuts = (15, 35, 75)
    if value <= cuts[0]:
        return 1
    if value <= cuts[1]:
        return 2
    if value <= cuts[2]:
        return 3
    return 4


def fetch(sido: str = None) -> dict:
    sido = sido or config.AIR_SIDO
    log.info("에어코리아 시도별 실시간 측정정보 조회: %s", sido)
    doc = http.get(
        f"{BASE}/getCtprvnRltmMesureDnsty",
        {
            "serviceKey": config.DATA_GO_KR_KEY,
            "returnType": "json",       # 기상청과 파라미터명이 다르다 (dataType 아님)
            "numOfRows": 200,
            "pageNo": 1,
            "sidoName": sido,
            "ver": "1.3",
        },
    )
    items = http.as_list(doc["response"]["body"].get("items"))
    return _shape(items, sido)


def _shape(items: list[dict], sido: str) -> dict:
    stations = []
    for it in items:
        pm10 = http.to_float(it.get("pm10Value"))
        pm25 = http.to_float(it.get("pm25Value"))
        if pm10 is None and pm25 is None:
            continue                      # 통신장애/점검 측정소 제외
        stations.append({
            "name": (it.get("stationName") or "").strip(),
            "mang": (it.get("mangName") or "").strip(),
            "pm10": pm10,
            "pm25": pm25,
            "khai": http.to_float(it.get("khaiValue")),
            "khai_grade": http.to_int(it.get("khaiGrade")),
            "time": (it.get("dataTime") or "").strip(),
        })

    if not stations:
        raise http.NoData("03", "유효한 측정소 데이터가 없습니다")

    # 도로변대기 측정소는 구조적으로 수치가 높아 시(도) 평균을 왜곡한다.
    # 에어코리아 공식 시도 평균도 도시대기 기준이므로 도시대기만 쓴다.
    urban = [s for s in stations if s["mang"] == "도시대기"]
    if urban:
        stations = urban

    def avg(key):
        vals = [s[key] for s in stations if s[key] is not None]
        return sum(vals) / len(vals) if vals else None

    pm10_avg, pm25_avg, khai_avg = avg("pm10"), avg("pm25"), avg("khai")
    khai_grade = (max(1, min(4, round(khai_avg / 50) + 1))
                  if khai_avg is not None else 2)
    if khai_avg is not None:
        khai_grade = 1 if khai_avg <= 50 else 2 if khai_avg <= 100 else 3 if khai_avg <= 250 else 4

    worst = sorted(
        [s for s in stations if s["pm25"] is not None],
        key=lambda s: s["pm25"], reverse=True,
    )[:3]

    data_time = next((s["time"] for s in stations if s["time"]), "")
    return {
        "sido": sido,
        "data_time": data_time,
        "khai": round(khai_avg) if khai_avg is not None else "-",
        "khai_grade": khai_grade,
        "khai_text": GRADE_TEXT[khai_grade],
        "pm10": round(pm10_avg) if pm10_avg is not None else "-",
        "pm10_text": GRADE_TEXT[_grade(pm10_avg, "pm10")],
        "pm10_grade": _grade(pm10_avg, "pm10"),
        "pm25": round(pm25_avg) if pm25_avg is not None else "-",
        "pm25_text": GRADE_TEXT[_grade(pm25_avg, "pm25")],
        "pm25_grade": _grade(pm25_avg, "pm25"),
        "station_count": len(stations),
        "worst": [{
            "name": s["name"],
            "pm25": round(s["pm25"]),
            "pm10": round(s["pm10"]) if s["pm10"] is not None else "-",
            "grade_text": GRADE_TEXT[_grade(s["pm25"], "pm25")],
        } for s in worst],
    }
