"""샘플 데이터 — API 키 없이 디자인/레이아웃을 확인할 때 쓴다.

실제 수집 함수만 바꿔 끼우고 나머지 경로(cards → 템플릿 → 렌더러)는 그대로 타므로,
여기서 잘 보이면 실데이터에서도 동일한 위치/폰트로 나온다.
텍스트 길이를 일부러 길게 넣어 자동 축소가 동작하는지도 함께 확인한다.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime

from src import cards
from src.sources import (air, apply, boxoffice, exchange, lifeindex, missing,
                         oil, price, realestate, weather)

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


BOXOFFICE = {
    "kind": "daily", "target": "20260914",
    "target_label": "9월 14일", "range_label": "9월 14일 하루",
    "movie_count": 10, "total_man": "48.2",
    "top": {"rank": "1", "title": "어쩌면 우리는 헤어지지 않았을지도",
            "open": "2026-09-03", "audi": "182,417", "audi_man": "18.2",
            "acc_man": "241.8", "move": "순위 유지", "screens": "1,204"},
    "rows": [
        {"rank": "1", "title": "어쩌면 우리는 헤어지지 않았을지도", "open": "2026-09-03",
         "audi_man": "18.2", "acc_man": "241.8", "move": "순위 유지", "screens": "1,204"},
        {"rank": "2", "title": "폭풍의 언덕", "open": "2026-09-10",
         "audi_man": "11.7", "acc_man": "63.4", "move": "▲ 1", "screens": "982"},
        {"rank": "3", "title": "고양이 탐정단", "open": "2026-09-12",
         "audi_man": "7.9", "acc_man": "19.2", "move": "신규 진입", "screens": "754"},
    ],
}

BOXOFFICE_WEEKLY = dict(BOXOFFICE, kind="weekly",
                        target_label="9월 11일~9월 13일",
                        range_label="9월 11일~9월 13일 주말",
                        total_man="132.6")

EXCHANGE = {
    "date": "20260914", "date_label": "9월 14일",
    "usd": {"unit": "USD", "name": "미국 달러", "flag": "🇺🇸", "rate": "1,398.50",
            "diff": 4.2, "delta": "전일 대비 +4.20원", "dir": "up",
            "ttb": "1,384.70", "tts": "1,412.30"},
    "items": [
        {"unit": "USD", "name": "미국 달러", "flag": "🇺🇸", "rate": "1,398.50", "delta": "전일 대비 +4.20원", "dir": "up", "ttb": "1,384.70", "tts": "1,412.30"},
        {"unit": "JPY(100)", "name": "일본 엔 100", "flag": "🇯🇵", "rate": "942.18", "delta": "전일 대비 -1.80원", "dir": "down", "ttb": "932.9", "tts": "951.4"},
        {"unit": "EUR", "name": "유로", "flag": "🇪🇺", "rate": "1,521.40", "delta": "전일 대비 +2.10원", "dir": "up", "ttb": "1,506.1", "tts": "1,536.7"},
        {"unit": "CNH", "name": "중국 위안", "flag": "🇨🇳", "rate": "196.34", "delta": "전일과 동일", "dir": "flat", "ttb": "194.3", "tts": "198.3"},
    ],
}
EXCHANGE["others"] = EXCHANGE["items"][1:]

LIFEINDEX = {
    "region": "서울", "date": "20260915", "date_label": "9월 15일",
    "base_time": "06시 발표",
    "head": {"kind": "uv", "label": "자외선", "value": "7", "text": "높음", "grade": 3,
             "series": [{"label": "지금", "value": "7"}, {"label": "+6h", "value": "5"},
                        {"label": "+12h", "value": "0"}, {"label": "+18h", "value": "3"},
                        {"label": "+24h", "value": "8"}]},
    "items": [
        {"kind": "uv", "label": "자외선", "value": "7", "text": "높음", "grade": 3, "series": []},
        {"kind": "senta", "label": "체감온도", "value": "28", "text": "", "grade": 2, "series": []},
        {"kind": "air", "label": "대기정체", "value": "62", "text": "보통", "grade": 2, "series": []},
    ],
}
LIFEINDEX["others"] = LIFEINDEX["items"][1:]

PRICE = {
    "date_label": "9월 15일",
    "head": {"name": "계란", "unit": "특란 30개", "price": "7,180",
             "delta": "전일 대비 +120원", "dir": "up", "month_pct": "+4.2%"},
    "items": [
        {"name": "계란", "unit": "특란 30개", "price": "7,180", "delta": "전일 대비 +120원", "dir": "up", "month_pct": "+4.2%"},
        {"name": "배추", "unit": "1포기", "price": "4,920", "delta": "전일 대비 -310원", "dir": "down", "month_pct": "-12.5%"},
        {"name": "삼겹살", "unit": "100g", "price": "2,640", "delta": "전일과 동일", "dir": "flat", "month_pct": "+1.1%"},
        {"name": "대파", "unit": "1kg", "price": "3,180", "delta": "전일 대비 +90원", "dir": "up", "month_pct": "+7.8%"},
    ],
    "up_count": 2, "down_count": 1, "watch_count": 4,
}
PRICE["rest"] = PRICE["items"][1:]

_APPLY_ITEMS = [
    {"name": "힐스테이트 청계리버", "area": "서울", "addr": "서울 성동구 용답동 232-1",
     "kind": "APT", "households": "1,020", "households_n": 1020,
     "begin_label": "9/17", "end_label": "9/19"},
    {"name": "e편한세상 동탄파크레이크", "area": "경기", "addr": "경기 화성시 능동 1100",
     "kind": "APT", "households": "684", "households_n": 684,
     "begin_label": "9/22", "end_label": "9/24"},
    {"name": "더샵 부산에코델타", "area": "부산", "addr": "부산 강서구 명지동 3-2",
     "kind": "APT", "households": "412", "households_n": 412,
     "begin_label": "9/24", "end_label": "9/26"},
]
APPLY = {
    "date_label": "9월 15일", "period_label": "9/15~9/29",
    "count": 3, "total_households": "2,116", "area_count": 3,
    "areas": ["경기", "부산", "서울"],
    "head": _APPLY_ITEMS[0], "items": _APPLY_ITEMS, "rest": _APPLY_ITEMS[1:],
}

_MISSING_ITEMS = [
    {"name": "홍길동", "age": "당시 7세 · 현재 21세", "sex": "남자", "target": "아동",
     "place": "서울특별시 성북구", "day": "2012.9.16", "years": 14,
     "feature": "120cm · 보통 · 짧은머리(생머리)", "photo": None},
    {"name": "김영희", "age": "82세", "sex": "여자", "target": "치매",
     "place": "경기도 수원시", "day": "2026.9.2", "years": 0,
     "feature": "155cm · 왜소 · 단발머리", "photo": None},
    {"name": "이철수", "age": "45세", "sex": "남자", "target": "지적장애",
     "place": "부산광역시 해운대구", "day": "2026.8.11", "years": 0,
     "feature": "172cm · 보통 · 캐주얼차림", "photo": None},
]
MISSING = {
    "date_label": "9월 15일",
    "head": _MISSING_ITEMS[0], "items": _MISSING_ITEMS, "rest": _MISSING_ITEMS[1:],
    "count": 3, "shown": 3, "long_cases": 1, "max_years": 14, "with_photo": 0,
}

DATA = {
    "weather": WEATHER, "air": AIR, "realestate": REALESTATE, "oil": OIL,
    "boxoffice": BOXOFFICE, "boxoffice_weekly": BOXOFFICE_WEEKLY,
    "exchange": EXCHANGE, "lifeindex": LIFEINDEX, "price": PRICE, "apply": APPLY,
    "missing": MISSING,
}
MODULES = {
    "weather": weather, "air": air, "realestate": realestate, "oil": oil,
    "boxoffice": boxoffice, "boxoffice_weekly": boxoffice,
    "exchange": exchange, "lifeindex": lifeindex, "price": price, "apply": apply,
    "missing": missing,
}
# 박스오피스만 fetch 함수 이름이 다르다
FETCH_ATTR = {"boxoffice": "fetch_daily", "boxoffice_weekly": "fetch_weekly"}


@contextmanager
def _patched(kind: str):
    mod = MODULES[kind]
    attr = FETCH_ATTR.get(kind, "fetch")
    original = getattr(mod, attr)
    setattr(mod, attr, lambda *a, **k: DATA[kind])
    try:
        yield
    finally:
        setattr(mod, attr, original)


def build(kind: str, now: datetime):
    with _patched(kind):
        return cards.CARDS[kind](now)
