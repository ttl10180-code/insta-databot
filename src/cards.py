"""카드 정의 — 데이터 수집 → 템플릿 컨텍스트 → 캡션까지 카드 종류별로 묶는다.

새 카드를 추가하려면 build_*() 함수를 하나 더 쓰고 CARDS 에 등록하면 된다.
레이아웃/폰트는 templates/ 쪽에서 이미 고정되어 있으므로 여기서는 내용만 다룬다.
"""
from __future__ import annotations

from datetime import datetime

from src import config
from src.sources import (air, apply, boxoffice, exchange, lifeindex,
                         missing, oil, price, realestate, weather)

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
        "mascot": mascot_file(theme),
    }


def mascot_file(theme: str, mood: str | None = None) -> str:
    """마스코트 이미지 파일명. 무드 버전이 없으면 기본형으로 조용히 되돌아간다.
    렌더는 templates/ 기준 상대경로로 읽으므로 파일명만 넘긴다."""
    base = theme.replace("theme-", "")
    if mood:
        candidate = config.ROOT / "assets" / "mascot" / f"odi-{base}-{mood}.png"
        if candidate.exists():
            return f"odi-{base}-{mood}.png"
    return f"odi-{base}.png"


def _bg(theme: str, variant: str) -> str:
    """배경 아트 파일 이름. assets/bg/<theme>-<variant>.jpg 가 없으면
    템플릿이 레이어를 아예 그리지 않으므로 그냥 기존 그라디언트로 나간다."""
    return f"{theme}-{variant}"


def _dir_variant(value: str | None) -> str:
    return value if value in ("up", "down") else "flat"


# --------------------------------------------------------------------------
def build_weather(now: datetime) -> tuple[str, dict, str]:
    d = weather.fetch(now=now)
    label = date_label_ymd(d.get("date"), now)
    ctx = _base(
        now,
        eyebrow="오늘의 날씨",
        title=f"{config.WEATHER_REGION} 오늘 {d['sky_text']}",
        subtitle=f"최저 {d['tmin']}° · 강수확률 최대 {d['pop_max']}% · 습도 {d['reh']}%",
        theme="theme-weather",
        source="기상청 단기예보 (공공데이터포털)",
    )
    ctx["date_label"] = label
    ctx["d"] = d
    if (d.get("pop_max") or 0) >= 60:
        variant = "snow" if (d.get("tmax") or 99) <= 1 else "rain"
    else:
        variant = {"맑음": "sunny", "구름많음": "cloudy"}.get(d.get("sky_text"), "overcast")
    ctx["bg"] = _bg("weather", variant)
    if variant in ("rain", "snow"):
        ctx["mascot"] = mascot_file("weather", "umbrella")

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
        title=f"{d['sido']} 초미세먼지 {d['pm25_text']}",
        subtitle=f"PM2.5 {d['pm25']}㎍/㎥ · PM10 {d['pm10']}㎍/㎥ · 측정소 {d['station_count']}곳 평균",
        theme="theme-air",
        source="한국환경공단 에어코리아 (공공데이터포털)",
    )
    ctx["d"] = d
    grade = d.get("pm25_grade") or d.get("khai_grade") or 2
    ctx["bg"] = _bg("air", {1: "good", 2: "normal", 3: "bad", 4: "verybad"}.get(grade, "normal"))
    if grade >= 3:
        ctx["mascot"] = mascot_file("air", "mask")

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
        title=f"{d['ym_label']} 아파트 평균",
        subtitle=f"{gu_label} · 신고 {d['deal_count']}건",
        theme="theme-realestate",
        source="국토교통부 실거래가 (공공데이터포털)",
    )
    ctx["d"] = d
    ctx["bg"] = _bg("realestate", _dir_variant(d.get("delta_dir")))

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
        title="전국 휘발유 평균",
        subtitle=" · ".join(f"{f['name']} {f['price']}원" for f in d["fuels"][1:]) or d["gasoline_delta"],
        theme="theme-oil",
        source="한국석유공사 오피넷",
    )
    ctx["d"] = d
    ctx["bg"] = _bg("oil", _dir_variant(d.get("gasoline_dir")))

    fuel_lines = chr(10).join(f"· {f['name']} {f['price']}원 ({f['delta']})" for f in d["fuels"])
    cheap_lines = chr(10).join(f"· {c['name']} {c['price']} — {c['addr']}" for c in d["cheapest"])
    caption = f"""⛽ 오늘의 전국 평균 유가

{fuel_lines}

{('최저가 주유소' + chr(10) + cheap_lines) if d['cheapest'] else ''}

주유 전에 한 번 확인하세요.

📊 출처 : 한국석유공사 오피넷

#기름값 #유가 #휘발유 #경유 #주유소 #최저가주유소 #오피넷 #생활정보 #자동차 #절약"""
    return "oil.html", ctx, caption


# --------------------------------------------------------------------------
def _build_boxoffice(now: datetime, d: dict) -> tuple[str, dict, str]:
    daily = d["kind"] == "daily"
    eyebrow = "어제의 영화" if daily else "주말 영화"
    ctx = _base(
        now,
        eyebrow=eyebrow,
        title=f"1위 {d['top']['title']}",
        subtitle=f"{d['range_label']} 관객 {d['top']['audi_man']}만 명",
        theme="theme-boxoffice",
        source="영화진흥위원회 박스오피스",
    )
    ctx["d"] = d
    ctx["bg"] = _bg("boxoffice", "base")

    lines = "\n".join(
        f"{r['rank']}위 {r['title']} — {r['audi_man']}만 명 (누적 {r['acc_man']}만)"
        for r in d["rows"]
    )
    caption = f"""🎬 {d['target_label']} 박스오피스

{d['range_label']} 1위는 '{d['top']['title']}' 입니다.
관객 {d['top']['audi_man']}만 명, 누적 {d['top']['acc_man']}만 명이에요.

{lines}

집계 대상 {d['movie_count']}편, 전체 관객 {d['total_man']}만 명.

📊 출처 : 영화진흥위원회 영화관입장권통합전산망

#박스오피스 #영화순위 #{'오늘의영화' if daily else '주말영화'} #영화추천 #극장 #관객수 #영화진흥위원회 #공공데이터 #데이터시각화 #오늘의데이터"""
    return "boxoffice.html", ctx, caption


def build_boxoffice(now: datetime) -> tuple[str, dict, str]:
    return _build_boxoffice(now, boxoffice.fetch_daily(now=now))


def build_boxoffice_weekly(now: datetime) -> tuple[str, dict, str]:
    return _build_boxoffice(now, boxoffice.fetch_weekly(now=now))


# --------------------------------------------------------------------------
def build_exchange(now: datetime) -> tuple[str, dict, str]:
    d = exchange.fetch(now=now)
    ctx = _base(
        now,
        eyebrow="오늘의 환율",
        title="달러 매매기준율",
        subtitle=f"{d['date_label']} 기준 · {d['usd']['delta']}",
        theme="theme-exchange",
        source="한국수출입은행 환율정보",
    )
    ctx["date_label"] = f"{d['date_label']} 기준"
    ctx["d"] = d
    ctx["bg"] = _bg("exchange", _dir_variant(d["usd"].get("dir")))

    lines = "\n".join(f"· {i['flag']} {i['name']} {i['rate']}원 ({i['delta']})" for i in d["items"])
    caption = f"""💱 {d['date_label']} 환율

달러 매매기준율은 {d['usd']['rate']}원, {d['usd']['delta']}입니다.

{lines}

송금 보낼 때 {d['usd']['tts']}원 / 받을 때 {d['usd']['ttb']}원.
매매기준율은 은행 고시 기준이라 실제 환전 금액과는 차이가 있습니다.

📊 출처 : 한국수출입은행 현재환율 API / 공공데이터포털

#환율 #달러환율 #엔화 #유로 #위안 #오늘의환율 #해외여행 #직구 #공공데이터 #오늘의데이터"""
    return "exchange.html", ctx, caption


# --------------------------------------------------------------------------
def build_lifeindex(now: datetime) -> tuple[str, dict, str]:
    d = lifeindex.fetch(now=now)
    head = d["head"]
    ctx = _base(
        now,
        eyebrow="오늘의 생활지수",
        title=f"{d['region']} {head['label']} {head['text'] or head['value']}",
        subtitle=f"{d['base_time']} · {head['label']} {head['value']}",
        theme="theme-lifeindex",
        source="기상청 생활기상지수 (공공데이터포털)",
    )
    ctx["d"] = d
    ctx["bg"] = _bg("lifeindex", {1: "low", 2: "mid", 3: "high", 4: "extreme"}.get(
        head.get("grade"), "mid"))

    lines = "\n".join(f"· {i['label']} {i['value']} {i['text']}".rstrip() for i in d["items"])
    caption = f"""🌤 {d['region']} {d['date_label']} 생활지수

{head['label']}는 {head['value']}{(' (' + head['text'] + ')') if head['text'] else ''} 입니다.

{lines}

{d['base_time']} 기준이며 3시간 간격 예측값입니다.

📊 출처 : 기상청 생활기상지수 조회서비스 / 공공데이터포털

#생활기상지수 #자외선지수 #체감온도 #오늘날씨 #건강관리 #기상청 #공공데이터 #데이터시각화 #오늘의데이터"""
    return "lifeindex.html", ctx, caption


# --------------------------------------------------------------------------
def build_price(now: datetime) -> tuple[str, dict, str]:
    d = price.fetch(now=now)
    head = d["head"]
    ctx = _base(
        now,
        eyebrow="장바구니 물가",
        title=f"{head['name']} {head['price']}원",
        subtitle=f"{head['delta']} · 오른 품목 {d['up_count']}개",
        theme="theme-price",
        source="농산물유통정보 KAMIS",
    )
    ctx["d"] = d
    ctx["bg"] = _bg("price", _dir_variant(head.get("dir")))

    lines = "\n".join(f"· {i['name']} {i['price']}원 ({i['delta']})" for i in d["items"])
    caption = f"""🧺 {d['date_label']} 장바구니 물가

{head['name']} 소매가는 {head['price']}원, {head['delta']}입니다.

{lines}

조사 품목 {d['watch_count']}개 중 {d['up_count']}개가 오르고 {d['down_count']}개가 내렸습니다.
전국 평균 소매가 기준이라 동네 마트 가격과는 차이가 있습니다.

📊 출처 : 농산물유통정보(KAMIS) 일별 소매가격

#장바구니물가 #물가 #생활물가 #계란값 #채소값 #장보기 #KAMIS #공공데이터 #데이터시각화 #오늘의데이터"""
    return "price.html", ctx, caption


# --------------------------------------------------------------------------
def build_apply(now: datetime) -> tuple[str, dict, str]:
    d = apply.fetch(now=now)
    ctx = _base(
        now,
        eyebrow="아파트 청약",
        title=f"{d['period_label']} 청약 일정",
        subtitle=f"{d['period_label']} · 총 {d['total_households']}세대",
        theme="theme-apply",
        source="한국부동산원 청약홈 (공공데이터포털)",
    )
    ctx["d"] = d
    ctx["bg"] = _bg("apply", "base")

    lines = "\n".join(
        f"· {r['begin_label']} {r['name']} ({r['area']} · {r['households']}세대)"
        for r in d["items"][:5]
    )
    caption = f"""🏗 {d['period_label']} 아파트 청약 일정

접수가 시작되는 공고는 {d['count']}건, 총 {d['total_households']}세대입니다.

{lines}

가장 빠른 접수는 {d['head']['begin_label']} {d['head']['name']} 입니다.
청약 자격과 세부 일정은 청약홈 공고문을 꼭 확인하세요.

📊 출처 : 한국부동산원 청약홈 분양정보 / 공공데이터포털

#아파트청약 #청약 #분양 #청약일정 #청약홈 #내집마련 #부동산 #공공데이터 #데이터시각화 #오늘의데이터"""
    return "apply.html", ctx, caption


# --------------------------------------------------------------------------
def build_missing(now: datetime) -> tuple[str, dict, str]:
    """실종경보 카드.

    사진은 싣지 않는다. 경찰이 공개한 범위(이름·나이·성별·실종일·장소)만
    그대로 옮기고, 판단이나 추측은 한 줄도 덧붙이지 않는다.
    """
    d = missing.fetch(now=now)
    head = d["head"]
    ctx = _base(
        now,
        eyebrow="실종자 찾기",
        title="이 얼굴을 기억해 주세요",
        subtitle=f"실종경보 {d['count']}명 · 제보는 국번없이 182",
        theme="theme-missing",
        source="경찰청 안전Dream 실종경보",
    )
    ctx["d"] = d
    ctx["bg"] = _bg("missing", "base")

    lines = "\n".join(
        f"· {r['name']} ({r['age']}, {r['sex']}) — {r['day']} {r['place']}"
        for r in d["items"]
    )
    caption = f"""🔎 실종경보가 발령된 {d['count']}명을 찾고 있습니다

{lines}

혹시 보신 적 있으신가요? 확실하지 않아도 괜찮습니다.
· 제보 전화 : 국번없이 182 (24시간)
· 안전Dream : www.safe182.go.kr

한 번의 공유가 가족에게 돌아가는 길이 됩니다.

📊 자료 출처: 경찰청

#실종자찾기 #실종경보 #182 #안전드림 #함께찾아요 #공유부탁드립니다 #실종아동 #치매어르신 #공공데이터 #오늘의데이터"""
    return "missing.html", ctx, caption


CARDS = {
    "weather": build_weather,
    "air": build_air,
    "realestate": build_realestate,
    "oil": build_oil,
    "boxoffice": build_boxoffice,
    "boxoffice_weekly": build_boxoffice_weekly,
    "exchange": build_exchange,
    "lifeindex": build_lifeindex,
    "price": build_price,
    "apply": build_apply,
    "missing": build_missing,
}
