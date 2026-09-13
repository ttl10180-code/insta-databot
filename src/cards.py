"""카드 정의 — 데이터 수집 → 템플릿 컨텍스트 → 캡션까지 카드 종류별로 묶는다.

새 카드를 추가하려면 build_*() 함수를 하나 더 쓰고 CARDS 에 등록하면 된다.
레이아웃/폰트는 templates/ 쪽에서 이미 고정되어 있으므로 여기서는 내용만 다룬다.
"""
from __future__ import annotations

from datetime import datetime

from src import config
from src.sources import air, oil, realestate, weather

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


def date_label(now: datetime) -> str:
    return f"{now.month}월 {now.day}일 ({WEEKDAYS[now.weekday()]})"


def date_label_ymd(ymd: str, fallback: datetime) -> str:
    """예보 대상 날짜(YYYYMMDD)로 라벨을 만든다.

    심야에 실행되면 '오늘' 슬롯이 없어 다음 날 예보로 넘어가는데,
    그때 헤더 날짜가 실행 시각을 따라가면 데이터와 어긋난다.
    """
    try:
        d = datetime.strptime(ymd, "%Y%m%d")
    except (TypeError, ValueError):
        return date_label(fallback)
    return f"{d.month}월 {d.day}일 ({WEEKDAYS[d.weekday()]})"


def _base(now: datetime, *, eyebrow: str, title: str, subtitle: str,
          theme: str, source: str) -> dict:
    return {
        "eyebrow": eyebrow,
        "date_label": date_label(now),
        "title": title,
        "subtitle": subtitle,
        "theme": theme,
        "source": source,
        "handle": config.HANDLE,
    }


# --------------------------------------------------------------------------
def build_weather(now: datetime) -> tuple[str, dict, str]:
    d = weather.fetch(now=now)
    label = date_label_ymd(d.get("date"), now)
    ctx = _base(
        now,
        eyebrow="오늘의 날씨",
        title=f"{config.WEATHER_REGION} 오늘 {d['sky_text']}, 최고 {d['tmax']}도",
        subtitle=f"최저 {d['tmin']}° · 강수확률 최대 {d['pop_max']}% · 습도 {d['reh']}%",
        theme="theme-weather",
        source="기상청 단기예보 (공공데이터포털)",
    )
    ctx["date_label"] = label
    ctx["d"] = d

    caption = f"""☀️ {config.WEATHER_REGION} {label} 날씨

{config.WEATHER_REGION}은 {d['sky_text']}, 최고 {d['tmax']}도 최저 {d['tmin']}도입니다.
강수확률은 최대 {d['pop_max']}%, 평균 습도는 {d['reh']}%예요.

시간대별 기온
{chr(10).join(f"· {h['time']} {h['temp']}° (강수 {h['pop']}%)" for h in d['hours'])}

매일 아침 공공데이터로 만든 날씨 카드를 올립니다.

📊 출처 : 기상청 단기예보 조회서비스 / 공공데이터포털

#오늘날씨 #날씨 #{config.WEATHER_REGION}날씨 #날씨정보 #기상청 #공공데이터 #데이터시각화 #일상정보 #출근길 #날씨예보"""
    return "weather.html", ctx, caption


# --------------------------------------------------------------------------
def build_air(now: datetime) -> tuple[str, dict, str]:
    d = air.fetch()
    ctx = _base(
        now,
        eyebrow="오늘의 대기질",
        title=f"{d['sido']} 초미세먼지 '{d['pm25_text']}'",
        subtitle=f"PM2.5 {d['pm25']}㎍/㎥ · PM10 {d['pm10']}㎍/㎥ · 측정소 {d['station_count']}곳 평균",
        theme="theme-air",
        source="한국환경공단 에어코리아 (공공데이터포털)",
    )
    ctx["d"] = d

    worst_lines = chr(10).join(
        f"· {w['name']} PM2.5 {w['pm25']}㎍/㎥ ({w['grade_text']})" for w in d["worst"]
    )
    caption = f"""😷 {d['sido']} 대기질 ({d['data_time']} 기준)

초미세먼지(PM2.5) {d['pm25']}㎍/㎥ — {d['pm25_text']}
미세먼지(PM10) {d['pm10']}㎍/㎥ — {d['pm10_text']}
통합대기환경지수 {d['khai']} — {d['khai_text']}

오늘 수치가 높은 곳
{worst_lines}

'나쁨' 이상이면 외출 시 마스크 챙기세요.

📊 출처 : 한국환경공단 에어코리아 / 공공데이터포털

#미세먼지 #초미세먼지 #대기질 #오늘미세먼지 #에어코리아 #공공데이터 #{d['sido']}날씨 #생활정보 #마스크 #환경"""
    return "air.html", ctx, caption


# --------------------------------------------------------------------------
def build_realestate(now: datetime) -> tuple[str, dict, str]:
    d = realestate.fetch(now=now)
    gu_label = " · ".join(d["gu_names"])
    ctx = _base(
        now,
        eyebrow="아파트 실거래",
        title=f"{d['ym_label']} 평균 {d['avg_price']}억",
        subtitle=f"{gu_label} · 신고 {d['deal_count']}건",
        theme="theme-realestate",
        source="국토교통부 실거래가 (공공데이터포털)",
    )
    ctx["d"] = d

    top_lines = chr(10).join(
        f"· {t['name']} {t['price']} ({t['dong']} 전용 {t['area']}㎡)" for t in d["top"]
    )
    caption = f"""🏢 {d['ym_label']} 아파트 매매 실거래

대상 : {gu_label}
신고 건수 {d['deal_count']}건
평균 거래가 {d['avg_price']}억 ({d['delta_text']})
3.3㎡당 평균 {d['per_pyeong']}만원

최고가 거래
{top_lines}

계약 해제된 거래는 집계에서 제외했습니다.
실거래는 계약 후 30일 내 신고라 최근 월은 수치가 계속 갱신됩니다.

📊 출처 : 국토교통부 아파트 매매 실거래가 상세자료 / 공공데이터포털

#아파트실거래가 #부동산 #서울아파트 #실거래가 #부동산정보 #재테크 #공공데이터 #아파트시세 #내집마련 #부동산공부"""
    return "realestate.html", ctx, caption


# --------------------------------------------------------------------------
def build_oil(now: datetime) -> tuple[str, dict, str]:
    d = oil.fetch()
    ctx = _base(
        now,
        eyebrow="오늘의 기름값",
        title=f"전국 휘발유 평균 {d['gasoline']}원",
        subtitle=" · ".join(f"{f['name']} {f['price']}원" for f in d["fuels"][1:]) or d["gasoline_delta"],
        theme="theme-oil",
        source="한국석유공사 오피넷",
    )
    ctx["d"] = d

    fuel_lines = chr(10).join(f"· {f['name']} {f['price']}원 ({f['delta']})" for f in d["fuels"])
    cheap_lines = chr(10).join(f"· {c['name']} {c['price']} — {c['addr']}" for c in d["cheapest"])
    caption = f"""⛽ 오늘의 전국 평균 유가

{fuel_lines}

{('최저가 주유소' + chr(10) + cheap_lines) if d['cheapest'] else ''}

주유 전에 한 번 확인하세요.

📊 출처 : 한국석유공사 오피넷

#기름값 #유가 #휘발유 #경유 #주유소 #최저가주유소 #오피넷 #생활정보 #자동차 #절약"""
    return "oil.html", ctx, caption


CARDS = {
    "weather": build_weather,
    "air": build_air,
    "realestate": build_realestate,
    "oil": build_oil,
}
