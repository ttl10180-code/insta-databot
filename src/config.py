"""환경설정 — 모든 키는 환경변수(GitHub Secrets)에서 읽는다."""
from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

try:                                   # 로컬 개발 편의: .env 자동 로드
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:                    # CI 에서는 환경변수를 직접 주입하므로 없어도 된다
    pass

def env(name: str, default: str = "") -> str:
    """환경변수 읽기. 빈 문자열은 '설정 안 함'으로 본다.

    GitHub Actions 에서 정의되지 않은 vars.X 는 빈 문자열로 주입된다.
    os.getenv(name, default) 는 이때 default 가 아니라 '' 를 돌려주기 때문에
    코드의 기본값이 조용히 덮어써진다. 그래서 한 겹 감싼다.
    """
    value = os.getenv(name)
    return default if value is None or not value.strip() else value.strip()


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except ValueError:
        return default


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "templates"
FONT_DIR = ROOT / "fonts"
OUT_DIR = Path(env("OUT_DIR") or (ROOT / "out"))

KST = ZoneInfo("Asia/Seoul")

# ---------------- 공공데이터포털 ----------------
# 포털의 "일반 인증키(Decoding)" 를 그대로 넣는다. requests 가 알아서 인코딩한다.
DATA_GO_KR_KEY = env("DATA_GO_KR_KEY")
# 오피넷은 별도 사이트에서 발급받는 certkey
OPINET_KEY = env("OPINET_KEY")

# ---------------- 인스타그램 ----------------
# IG_LOGIN_MODE: "instagram" (graph.instagram.com) | "facebook" (graph.facebook.com)
IG_LOGIN_MODE = env("IG_LOGIN_MODE", "facebook").lower()
IG_API_VERSION = env("IG_API_VERSION", "v26.0")
IG_USER_ID = env("IG_USER_ID")
IG_ACCESS_TOKEN = env("IG_ACCESS_TOKEN")
IG_APP_ID = env("IG_APP_ID")
IG_APP_SECRET = env("IG_APP_SECRET")

IG_GRAPH_HOST = (
    "https://graph.instagram.com" if IG_LOGIN_MODE == "instagram"
    else "https://graph.facebook.com"
)

# ---------------- 이미지 호스팅 ----------------
# GitHub Pages 공개 URL 접두사. 예: https://ttl10180-code.github.io/insta-databot
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL").rstrip("/")

# ---------------- 브랜딩 ----------------
HANDLE = env("CARD_HANDLE", "@daily.data.kr")
DRY_RUN = env("DRY_RUN", "0") == "1"

# ---------------- 지역 설정 ----------------
# 기상청 격자 (서울 중구 기준)
WEATHER_NX = env_int("WEATHER_NX", 60)
WEATHER_NY = env_int("WEATHER_NY", 127)
WEATHER_REGION = env("WEATHER_REGION", "서울")

# 에어코리아 시도명
AIR_SIDO = env("AIR_SIDO", "서울")

# 실거래가 대상 시군구 (법정동코드 앞 5자리)
REALESTATE_LAWD_CDS = [
    c.strip() for c in env(
        "REALESTATE_LAWD_CDS",
        "11680,11650,11710,11440,11560",  # 강남, 서초, 송파, 마포, 영등포
    ).split(",") if c.strip()
]

LAWD_NAMES = {
    "11110": "종로구", "11140": "중구",   "11170": "용산구", "11200": "성동구",
    "11215": "광진구", "11230": "동대문구", "11260": "중랑구", "11290": "성북구",
    "11305": "강북구", "11320": "도봉구", "11350": "노원구", "11380": "은평구",
    "11410": "서대문구", "11440": "마포구", "11470": "양천구", "11500": "강서구",
    "11530": "구로구", "11545": "금천구", "11560": "영등포구", "11590": "동작구",
    "11620": "관악구", "11650": "서초구", "11680": "강남구", "11710": "송파구",
    "11740": "강동구",
}

# 오피넷 지역코드 (01=서울)
OPINET_AREA = env("OPINET_AREA", "01")


def require(*names: str) -> None:
    """필수 환경변수 확인. 없으면 명확한 메시지와 함께 중단."""
    missing = [n for n in names if not globals().get(n)]
    if missing:
        raise SystemExit(
            "[설정 오류] 다음 환경변수가 비어 있습니다: "
            + ", ".join(missing)
            + "\n→ .env 또는 GitHub Secrets 를 확인하세요. SETUP.md 참고."
        )
