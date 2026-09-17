"""기상청 단기예보 조회서비스 → 날씨 카드 데이터."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from src import config
from src.common import cache, http

log = logging.getLogger(__name__)

BASE = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"

# 단기예보 발표 시각 (1일 8회). 각 시각 +10분 이후부터 제공된다.
RELEASE_HOURS = [2, 5, 8, 11, 14, 17, 20, 23]
RELEASE_DELAY_MIN = 10

SKY_TEXT = {1: "맑음", 3: "구름많음", 4: "흐림"}
SKY_ICON = {1: "☀️", 3: "⛅", 4: "☁️"}
# 단기예보 PTY: 0없음 1비 2비/눈 3눈 4소나기
PTY_TEXT = {0: "", 1: "비", 2: "비/눈", 3: "눈", 4: "소나기"}
PTY_ICON = {1: "🌧️", 2: "🌨️", 3: "❄️", 4: "🌦️"}


def latest_base(now: datetime) -> tuple[str, str]:
    """지금 시점에 실제로 제공되는 가장 최근 발표 회차를 고른다."""
    cursor = now - timedelta(minutes=RELEASE_DELAY_MIN)
    for _ in range(2):
        for hour in sorted(RELEASE_HOURS, reverse=True):
            if cursor.hour >= hour:
                return cursor.strftime("%Y%m%d"), f"{hour:02d}00"
        # 02시 이전이면 전날 2300 회차
        cursor = cursor - timedelta(days=1)
        cursor = cursor.replace(hour=23, minute=59)
    raise RuntimeError("발표 회차를 계산하지 못했습니다")


def _live_items(nx: int, ny: int, now: datetime) -> list[dict]:
    base_date, base_time = latest_base(now)
    log.info("단기예보 조회 base=%s %s (nx=%s ny=%s)", base_date, base_time, nx, ny)

    doc = http.get(
        f"{BASE}/getVilageFcst",
        {
            "serviceKey": config.DATA_GO_KR_KEY,
            "pageNo": 1,
            "numOfRows": 1000,          # 기본값 10 → 반드시 크게
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": nx,
            "ny": ny,
        },
    )
    return http.as_list(doc["response"]["body"]["items"]["item"])


def fetch(nx: int = None, ny: int = None, now: datetime = None) -> dict:
    """단기예보는 사흘치가 한 번에 온다. 그래서 여기서는 '가공한 결과' 가
    아니라 '응답 원본' 을 캐시하고, 읽을 때 오늘 기준으로 다시 계산한다.

    어제 받아둔 응답 안에도 오늘 예보가 들어 있으니, 이 경우 캐시로 만든
    카드는 낡은 값이 아니라 그냥 맞는 값이다. (반대로 미세먼지 같은
    실시간 관측값은 이렇게 할 수 없어서 아예 캐시하지 않는다.)"""
    nx = config.WEATHER_NX if nx is None else nx
    ny = config.WEATHER_NY if ny is None else ny
    now = now or datetime.now(config.KST)
    items = cache.remember(
        "weather-raw", lambda: _live_items(nx, ny, now), max_age_days=2)
    return _shape(items, now)


def _wind_text(ms: float) -> str:
    """기상청 풍속 구분: 4 미만 약함, 9 미만 약간 강함, 14 미만 강함."""
    if ms < 4:
        return "약한 바람"
    if ms < 9:
        return "약간 강한 바람"
    if ms < 14:
        return "강한 바람"
    return "매우 강한 바람"


def _shape(items: list[dict], now: datetime) -> dict:
    """예보 항목들을 카드용 구조로 정리."""
    today = now.strftime("%Y%m%d")
    by_slot: dict[tuple[str, str], dict[str, str]] = {}
    for it in items:
        key = (it["fcstDate"], it["fcstTime"])
        by_slot.setdefault(key, {})[it["category"]] = it["fcstValue"]

    today_slots = {k: v for k, v in by_slot.items() if k[0] == today}
    if not today_slots:                       # 심야 실행 시 오늘 슬롯이 없을 수 있음
        target = min(k[0] for k in by_slot)
        today_slots = {k: v for k, v in by_slot.items() if k[0] == target}
        today = target

    # TMN/TMX 는 하루 한 번만 나온다
    tmn = tmx = None
    for vals in today_slots.values():
        tmn = http.to_float(vals.get("TMN"), tmn)
        tmx = http.to_float(vals.get("TMX"), tmx)
    temps = [http.to_float(v.get("TMP")) for v in today_slots.values()]
    temps = [t for t in temps if t is not None]
    if tmn is None and temps:
        tmn = min(temps)
    if tmx is None and temps:
        tmx = max(temps)

    pops = [http.to_int(v.get("POP"), 0) for v in today_slots.values()]
    rehs = [http.to_int(v.get("REH")) for v in today_slots.values()]
    rehs = [r for r in rehs if r is not None]
    wsds = [http.to_float(v.get("WSD")) for v in today_slots.values()]
    wsds = [w for w in wsds if w is not None]

    # 대표 하늘상태: 오늘 슬롯 중 최빈값
    skies = [http.to_int(v.get("SKY")) for v in today_slots.values()]
    skies = [s for s in skies if s in SKY_TEXT]
    sky = max(set(skies), key=skies.count) if skies else 1
    ptys = [http.to_int(v.get("PTY"), 0) for v in today_slots.values()]
    rain = next((p for p in ptys if p), 0)

    sky_text = PTY_TEXT.get(rain) or SKY_TEXT.get(sky, "맑음")
    sky_icon = PTY_ICON.get(rain) or SKY_ICON.get(sky, "☀️")

    # 시간별 스트립: 지금 이후 슬롯을 3시간 간격으로 6칸.
    # 단기예보는 1시간 단위로 오기 때문에 연속으로 뽑으면 6시간밖에 못 보여준다.
    # 3시간 간격이면 카드 한 장에 하루 흐름(18시간)이 담긴다.
    ordered = sorted(by_slot.items())
    now_key = (now.strftime("%Y%m%d"), now.strftime("%H00"))
    upcoming = [x for x in ordered if x[0] >= now_key] or ordered
    upcoming = upcoming[::3][:6]

    hours = []
    for (fdate, ftime), vals in upcoming:
        p = http.to_int(vals.get("PTY"), 0)
        s = http.to_int(vals.get("SKY"), 1)
        hours.append({
            "time": f"{int(ftime[:2])}시",
            "icon": PTY_ICON.get(p) or SKY_ICON.get(s, "☀️"),
            "temp": http.to_int(vals.get("TMP"), 0),
            "pop": http.to_int(vals.get("POP"), 0),
        })

    return {
        "date": today,
        "tmax": round(tmx) if tmx is not None else "-",
        "tmin": round(tmn) if tmn is not None else "-",
        "sky_text": sky_text,
        "sky_icon": sky_icon,
        "pop_max": max(pops) if pops else 0,
        "reh": round(sum(rehs) / len(rehs)) if rehs else "-",
        "wsd": f"{max(wsds):.1f}" if wsds else "-",
        "wsd_text": _wind_text(max(wsds)) if wsds else "",
        "gap": round(tmx - tmn) if (tmx is not None and tmn is not None) else "-",
        "hours": hours,
    }
