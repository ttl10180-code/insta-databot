"""무엇이 '실제로 올라갔는지' 를 기록한다.

왜 필요한가. 지금 구조에서는 실행이 초록불로 끝나도 아무것도 안 올라갈 수
있다. 수집이 '오늘은 데이터 없음'(NoData)을 돌려주면 그 카드는 오류가
아니라 건너뛰기로 처리되고, 실행은 성공으로 끝나기 때문이다. 그 판단 자체는
맞다 — 키가 없거나 정말 데이터가 없는 날 빨간 X 가 뜨면 진짜 고장과
구분이 안 된다. 문제는 그 대가로 '며칠째 안 올라갔다' 가 아무 데도 안
보이게 됐다는 것이다. 실제로 9월 18일 00:33 실종자 실행이 2분 45초 동안
초록불로 돌고 아무것도 올리지 않았다.

그래서 워크플로의 성공 여부가 아니라 '마지막으로 올린 시각' 을 카드 종류별로
남긴다. 하루 조용한 건 정상이고, 사흘 조용한 건 고장이다. 그 차이는 실행
기록이 아니라 이 기록에서만 보인다.

저장 위치는 캐시와 같은 gh-pages 의 cache/ 다. 추가 권한도 비용도 없고,
읽을 때는 깃허브 CDN 이라 러너에서 늘 닿는다.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

import requests

from src import config
from src.common.cache import CACHE_DIR

log = logging.getLogger(__name__)

NAME = "posted"
READ_TIMEOUT = (10, 20)


def _path():
    return CACHE_DIR / f"{NAME}.json"


def load() -> dict[str, str]:
    """카드 종류 → 마지막으로 올린 시각(ISO). 못 읽으면 빈 기록."""
    local = _path()
    if local.exists():
        try:
            return dict(json.loads(local.read_text(encoding="utf-8")))
        except Exception:                       # noqa: BLE001
            pass
    if not config.PUBLIC_BASE_URL:
        log.warning("PUBLIC_BASE_URL 이 없어 발행 기록을 읽지 못합니다.")
        return {}
    try:
        r = requests.get(f"{config.PUBLIC_BASE_URL}/cache/{NAME}.json",
                         timeout=READ_TIMEOUT)
        if r.status_code == 404:
            return {}                           # 아직 한 번도 안 올렸다
        r.raise_for_status()
        return dict(r.json())
    except Exception as e:                      # noqa: BLE001
        log.warning("발행 기록을 읽지 못했습니다: %s", e)
        return {}


def record(kinds) -> None:
    """방금 올린 카드들을 기록에 얹는다.

    반드시 기존 기록 위에 '얹어야' 한다. 워크플로마다 올리는 카드가 다른데
    통째로 덮어쓰면, 환율을 올린 실행이 날씨 기록을 지워버린다.
    """
    kinds = [k for k in kinds if k]
    if not kinds:
        return
    merged = load()
    now = datetime.now(config.KST).isoformat(timespec="seconds")
    for kind in kinds:
        merged[kind] = now
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _path().write_text(json.dumps(merged, ensure_ascii=False, indent=2,
                                      sort_keys=True), encoding="utf-8")
        log.info("발행 기록 갱신: %s", ", ".join(kinds))
    except Exception as e:                      # noqa: BLE001
        log.warning("발행 기록 저장 실패(무시): %s", e)
