"""수집 결과 캐시 — 국내 서버가 안 닿는 날에도 카드가 나가게 한다.

배경. 해외(GitHub Actions) 러너에서 국내 정부 서버는 시간대에 따라 통째로
닿지 않는다. 어느 날 아침엔 수출입은행만 살아 있고, 그날 밤엔 수출입은행만
죽어 있는 식으로 돌아가며 막힌다. 재시도를 아무리 촘촘히 해도, 발행 시각에
그 서버가 죽어 있으면 카드는 못 만든다.

그래서 수집에 성공하면 결과를 gh-pages 의 cache/ 에 JSON 으로 남긴다.
다음 실행에서 같은 소스가 실패하면 마지막으로 성공한 값을 대신 쓴다.

왜 gh-pages 인가. 카드 이미지를 이미 올리는 곳이라 추가 권한도 비용도 없고,
읽을 때는 깃허브 CDN 이라 국내 서버와 달리 러너에서 늘 닿는다.

정직함 규칙 두 가지. 이게 이 모듈의 존재 이유이자 한계다.

  1) 오래된 값에는 반드시 '언제 받은 값인지' 가 카드에 찍힌다.
     stale_note() 를 렌더 쪽에서 읽어 출처 줄에 붙인다.

  2) 소스마다 허용 기간이 다르다. 사흘 전 환율은 주말이 끼면 정상이지만,
     사흘 전 실시간 미세먼지는 그냥 틀린 값이다. 틀린 값을 오늘 값인 척
     내보내느니 카드를 거르는 편이 낫다. 그래서 실시간 관측값(미세먼지)은
     아예 캐시하지 않고, 예보값(날씨·자외선)은 원본 응답을 통째로 캐시해서
     읽을 때 오늘 기준으로 다시 계산한다 — 어제 받은 예보 안에 오늘 예보가
     이미 들어 있기 때문에, 이 경우는 오래된 값이 아니라 그냥 맞는 값이다.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

import requests

from src import config
from src.common.http import NoData

log = logging.getLogger(__name__)

CACHE_DIR = config.OUT_DIR / "cache"
READ_TIMEOUT = (10, 20)          # 깃허브 CDN 이라 넉넉할 이유가 없다

# 이번 카드를 만드는 동안 캐시로 때운 소스가 있으면 여기에 남는다.
_served: dict[str, str] = {}


def begin() -> None:
    """카드 한 장을 만들기 직전에 호출한다. 직전 카드의 흔적을 지운다."""
    _served.clear()


def stale_note() -> str | None:
    """직전 카드가 캐시로 만들어졌으면 '9월 16일 수집' 같은 문구를 돌려준다."""
    if not _served:
        return None
    oldest = min(_served.values())
    try:
        d = datetime.fromisoformat(oldest).astimezone(config.KST)
    except ValueError:
        return "지난 수집분"
    return f"{d.month}월 {d.day}일 수집분"


def _url(name: str) -> str:
    return f"{config.PUBLIC_BASE_URL}/cache/{name}.json"


def save(name: str, payload) -> None:
    """수집 성공분을 남긴다. 저장 실패는 조용히 넘긴다 — 발행을 막을 일이 아니다."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (CACHE_DIR / f"{name}.json").write_text(
            json.dumps(
                {"saved_at": datetime.now(config.KST).isoformat(timespec="seconds"),
                 "payload": payload},
                ensure_ascii=False),
            encoding="utf-8")
    except Exception as e:                      # noqa: BLE001
        log.warning("%s 캐시 저장 실패(무시): %s", name, e)


def load(name: str, max_age_days: float):
    """마지막 성공분을 읽는다. 없거나 너무 오래됐으면 None.

    로컬(out/cache)을 먼저 보고, 없으면 공개 URL 에서 받는다. 러너는 매번
    새 체크아웃이라 사실상 공개 URL 쪽을 쓴다.
    """
    raw = None
    local = CACHE_DIR / f"{name}.json"
    if local.exists():
        try:
            raw = json.loads(local.read_text(encoding="utf-8"))
        except Exception:                       # noqa: BLE001
            raw = None
    if raw is None and not config.PUBLIC_BASE_URL:
        # 여기서 조용히 None 을 돌려주면 '캐시가 없다' 와 '캐시를 읽을 주소를
        # 모른다' 가 구분되지 않는다. 실제로 이 차이 때문에 9월 18일 아침
        # 카드가 세 번 다 그냥 실패했다.
        log.error("PUBLIC_BASE_URL 이 없어 %s 캐시를 읽을 수 없습니다. "
                  "워크플로의 env 설정을 확인하세요.", name)
        return None
    if raw is None:
        try:
            r = requests.get(_url(name), timeout=READ_TIMEOUT)
            if r.status_code == 404:
                return None                     # 아직 한 번도 성공한 적이 없다
            r.raise_for_status()
            raw = r.json()
        except Exception as e:                  # noqa: BLE001
            log.warning("%s 캐시를 읽지 못했습니다: %s", name, e)
            return None
    if not isinstance(raw, dict) or "payload" not in raw:
        return None

    saved_at = str(raw.get("saved_at", ""))
    try:
        when = datetime.fromisoformat(saved_at)
    except ValueError:
        return None
    age = datetime.now(config.KST) - when
    if age > timedelta(days=max_age_days):
        log.warning("%s 캐시가 너무 오래됐습니다 (%s일 전). 쓰지 않습니다.",
                    name, age.days)
        return None

    _served[name] = saved_at
    log.warning("⚠️  %s 를 %s 에 받아둔 값으로 대신합니다.", name, saved_at)
    return raw["payload"]


def remember(name: str, fetch, *, max_age_days: float):
    """fetch() 를 부르고, 성공하면 저장하고, 실패하면 마지막 성공분으로 때운다.

    NoData 는 그대로 올려보낸다. '서버가 안 닿는다' 와 '오늘은 그런 데이터가
    없다' 는 전혀 다른 일이고, 후자는 캐시로 덮으면 안 된다 — 없는 날에
    지난주 값을 오늘인 척 올리게 된다.
    """
    try:
        payload = fetch()
    except NoData:
        raise
    except Exception as e:                      # noqa: BLE001
        log.error("%s 수집 실패: %s", name, e)
        if max_age_days <= 0:
            raise
        cached = load(name, max_age_days)
        if cached is None:
            raise
        return cached
    save(name, payload)
    return payload
