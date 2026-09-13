"""샘플 데이터 — API 키 없이 디자인/레이아웃을 확인할 때 쓴다.

실제 수집 함수만 바꿔 끼우고 나머지 경로(cards → 템플릿 → 렌더러)는 그대로 타므로,
여기서 잘 보이면 실데이터에서도 동일한 위치/폰트로 나온다.
텍스트 길이를 일부러 길게 넣어 자동 축소가 동작하는지도 함께 확인한다.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime

from src import cards
from src.sources import air, oil, realestate, weather

WEATHER = {
    "date": "20260912",
    "tmax": 29, "tmin": 21,
    "sky_text": "구름많음", "sky_icon": "⛅",
    "pop_max": 60, "reh": 68,
    "wsd": "5.2", "wsd_text": "약간 강한 바람", "gap": 8,
    "hours": [
        {"time": "9시",  "icon": "⛅",  "temp": 24, "pop": 20},
        {"time": "12시", "icon": "☀️",  "temp": 27, "pop": 10},
        {"time": "15시", "icon": "⛅",  "temp": 29, "pop": 30},
        {"time": "18시", "icon": "🌧️", "temp": 26, "pop": 60},
        {"time": "21시", "icon": "🌧️", "temp": 23, "pop": 50},
        {"time": "24시", "icon": "☁️",  "temp": 21, "pop": 20},
    ],
}

AIR = {
    "sido": "서울", "data_time": "2026-09-12 14:00",
    "khai": 78, "khai_grade": 2, "khai_text": "보통",
    "pm10": 41, "pm10_text": "보통", "pm10_grade": 2,
    "pm25": 23, "pm25_text": "보통", "pm25_grade": 2,
    "station_count": 40,
    "worst": [
        {"name": "영등포구", "pm25": 38, "pm10": 61, "grade_text": "나쁨"},
        {"name": "동대문구", "pm25": 34, "pm10": 55, "grade_text": "보통"},
        {"name": "강서구",   "pm25": 31, "pm10": 52, "grade_text": "보통"},
    ],
}

REALESTATE = {
    "ym": "202608", "ym_label": "2026년 8월",
    "gu_names": ["강남구", "서초구", "송파구", "마포구", "영등포구"],
    "deal_count": "1,284",
    "avg_price": "21.4",
    "per_pyeong": "7,320",
    "delta_dir": "up", "delta_text": "전월 대비 +1.8%",
    "top": [
        {"name": "래미안대치팰리스", "dong": "강남구 대치동", "area": 114.2, "floor": 18, "price": "48.5억"},
        {"name": "아크로리버파크",   "dong": "서초구 반포동", "area": 84.9,  "floor": 22, "price": "45.0억"},
        {"name": "헬리오시티",       "dong": "송파구 가락동", "area": 84.9,  "floor": 12, "price": "27.3억"},
    ],
}

OIL = {
    "trade_dt": "20260912",
    "gasoline": "1,642.4",
    "gasoline_delta": "전일 대비 -1.2원",
    "gasoline_dir": "down",
    "fuels": [
        {"name": "휘발유", "price": "1,642", "delta": "전일 대비 -1.2원"},
        {"name": "경유",   "price": "1,521", "delta": "전일 대비 +0.5원"},
        {"name": "LPG",    "price": "1,034", "delta": "전일과 동일"},
    ],
    "cheapest": [
        {"name": "만남의광장주유소", "addr": "서울 서초구 양재대로 12길 73", "price": "1,499원"},
        {"name": "SK에너지 도봉주유소", "addr": "서울 도봉구 도봉로 950", "price": "1,528원"},
        {"name": "현대오일뱅크 강서점", "addr": "서울 강서구 공항대로 411", "price": "1,535원"},
    ],
}

DATA = {"weather": WEATHER, "air": AIR, "realestate": REALESTATE, "oil": OIL}
MODULES = {"weather": weather, "air": air, "realestate": realestate, "oil": oil}


@contextmanager
def _patched(kind: str):
    mod = MODULES[kind]
    original = mod.fetch
    mod.fetch = lambda *a, **k: DATA[kind]
    try:
        yield
    finally:
        mod.fetch = original


def build(kind: str, now: datetime):
    with _patched(kind):
        return cards.CARDS[kind](now)
