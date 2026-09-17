"""국내 API 를 서울(Supabase Edge Function)을 거쳐 부른다.

왜. 해외 GitHub Actions 러너에서 국내 정부 서버는 시간대에 따라 통째로
닿지 않는다. 2026-09-18 00:25 KST 에 같은 3분 안에서 확인한 결과:

    호스트                  해외(러너)      서울(Supabase)
    apis.data.go.kr         400            400   (0.5초)
    www.safetydata.go.kr    200            200   (0.8초)
    www.safe182.go.kr       200            200   (0.6초)
    oapi.koreaexim.go.kr    200            302   (0.5초)
    www.kobis.or.kr         연결 실패       200   (3.0초)

그래서 요청만 서울을 거치게 한다. 데이터를 저쪽에 저장하지는 않는다 —
통과만 시킨다. 저장은 gh-pages 의 cache/ 가 맡는다 (src/common/cache.py).

설정이 없으면 이 모듈은 통째로 잠들어 있고, 모든 게 어제까지와 똑같이
동작한다. 새 경로가 고장났을 때 발행 전체가 멈추면 고치려던 문제를 더
키우는 셈이라, 중계 실패는 언제나 직접 연결로 되돌아간다.
"""
from __future__ import annotations

import base64
import logging

import requests

from src import config

log = logging.getLogger(__name__)

# 중계기(Supabase)는 깃허브에서 늘 닿는다. 국내 쪽 지연은 저쪽의 25초 제한이
# 잡아주므로, 여기서는 그보다 조금만 넉넉하게 잡으면 된다.
TIMEOUT = (10, 40)


class RelayUnavailable(RuntimeError):
    """중계가 안 됐다. 호출 측은 직접 연결로 되돌아가면 된다."""


def enabled() -> bool:
    return bool(config.KR_RELAY_URL and config.KR_RELAY_KEY)


def _why(r: requests.Response) -> str:
    try:
        return str(r.json().get("error", ""))[:200]
    except Exception:                           # noqa: BLE001
        return r.text[:200]


def request(method: str, url: str, *, params: dict | None = None,
            headers: dict | None = None, form: dict | None = None) -> requests.Response:
    """중계기를 통해 한 번 요청한다. 재시도는 호출 측(http.get)이 맡는다.

    응답은 진짜 requests.Response 로 만들어 돌려준다. 그래야 raise_for_status()
    부터 .text 까지 직접 연결일 때와 똑같이 동작해서, 부르는 쪽 코드가
    '중계인지 아닌지' 를 알 필요가 없다.
    """
    spec: dict = {"url": url, "method": method.upper()}
    if params:
        spec["params"] = {k: str(v) for k, v in params.items() if v is not None}
    if headers:
        spec["headers"] = headers
    if form:
        spec["form"] = {k: str(v) for k, v in form.items() if v is not None}

    try:
        r = requests.post(
            config.KR_RELAY_URL, json=spec, timeout=TIMEOUT,
            headers={"Authorization": f"Bearer {config.KR_RELAY_KEY}",
                     "apikey": config.KR_RELAY_KEY,
                     "content-type": "application/json"})
    except requests.RequestException as e:
        raise RelayUnavailable(f"중계기에 닿지 못했습니다: {e}") from e

    if r.status_code == 504:
        raise RelayUnavailable(f"서울에서도 닿지 않았습니다: {_why(r)}")
    if r.status_code != 200:
        raise RelayUnavailable(f"중계기 오류 {r.status_code}: {_why(r)}")

    try:
        payload = r.json()
        body = base64.b64decode(payload["body_b64"])
    except Exception as e:                      # noqa: BLE001
        raise RelayUnavailable(f"중계 응답을 읽지 못했습니다: {e}") from e

    out = requests.Response()
    out.status_code = int(payload.get("status", 200))
    out._content = body                         # noqa: SLF001
    out.url = url
    content_type = str(payload.get("content_type") or "application/json")
    out.headers["content-type"] = content_type
    # 국내 포털은 charset 을 안 적어 보내는 경우가 많다. requests 는 그때
    # ISO-8859-1 로 추정해 한글을 깨뜨리므로, 명시가 없으면 UTF-8 로 못 박는다.
    if "charset=" not in content_type.lower():
        out.encoding = "utf-8"
    return out
