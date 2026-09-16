"""공공데이터포털 공통 HTTP 클라이언트.

포털 API 의 알려진 함정을 여기서 전부 흡수한다:
  1) dataType=JSON 을 줘도 게이트웨이 레벨 에러는 XML 로 온다
  2) 인증키는 Decoding 키를 params dict 로 넘겨야 한다 (이중 인코딩 방지)
  3) numOfRows 기본값이 10 이라 조용히 잘린다
  4) 응답 지연이 잦아 타임아웃 + 재시도가 필수다
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import urlsplit

import requests
import xmltodict

log = logging.getLogger(__name__)

# (연결, 읽기) 초. 해외 러너 → 국내 정부 서버는 연결 자체가 느릴 때가 있어
# 연결 타임아웃을 넉넉히 잡는다. GitHub Actions 에서 20초로는 부족했다.
DEFAULT_TIMEOUT = (25, 60)
MAX_RETRIES = 4
BACKOFF = 2.5

# 포털 공통 결과코드
OK_CODES = {"00", "000"}
NODATA_CODES = {"03", "003"}


class HostDown(RuntimeError):
    """이번 실행에서 이미 연결 불가로 판명된 서버.

    국내 정부 서버는 해외(GitHub Actions) 러너에서 통째로 닿지 않는 시간대가
    있다. 그럴 때 소스마다 4회씩 25초 연결 타임아웃을 다시 겪으면 한 번
    실행에 20분이 넘게 날아간다. 한 호스트가 재시도를 전부 소진하고
    연결조차 못 했으면, 같은 실행 안에서는 곧바로 포기한다."""


# 이번 프로세스에서 연결 자체가 불가능하다고 판명된 호스트 → 사유
_DEAD_HOSTS: dict[str, str] = {}


def mark_host_down(host: str, reason: str) -> None:
    if host and host not in _DEAD_HOSTS:
        log.error("%s 에 연결할 수 없습니다. 이번 실행에서는 더 시도하지 않습니다.", host)
        _DEAD_HOSTS[host] = reason


def reset_host_state() -> None:
    """테스트용 — 판정을 지운다."""
    _DEAD_HOSTS.clear()


class PortalError(RuntimeError):
    """공공데이터포털이 명시적으로 반환한 오류."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class NoData(PortalError):
    """정상 응답이지만 데이터가 없음 (에러 아님)."""


def _parse(text: str) -> Any:
    body = text.lstrip("﻿ \t\r\n")
    if body.startswith("<"):
        doc = xmltodict.parse(body)
        # 게이트웨이 레벨 오류 (서비스키 미등록, IP 미등록 등)
        if "OpenAPI_ServiceResponse" in doc:
            hdr = doc["OpenAPI_ServiceResponse"].get("cmmMsgHeader", {})
            raise PortalError(
                str(hdr.get("returnReasonCode", "?")),
                str(hdr.get("errMsg", "") or "") + " " + str(hdr.get("returnAuthMsg", "") or ""),
            )
        return doc
    return json.loads(body)


def _check_header(doc: Any) -> None:
    """서비스 레벨 resultCode 확인."""
    resp = doc.get("response") if isinstance(doc, dict) else None
    if not isinstance(resp, dict):
        return
    hdr = resp.get("header") or {}
    code = str(hdr.get("resultCode", "")).strip()
    msg = str(hdr.get("resultMsg", "")).strip()
    if not code:
        return
    if code in OK_CODES:
        return
    if code in NODATA_CODES:
        raise NoData(code, msg or "NODATA")
    raise PortalError(code, msg or "unknown service error")


def get(url: str, params: dict, *, timeout=DEFAULT_TIMEOUT,
        retries: int = MAX_RETRIES, check_header: bool = True) -> Any:
    """GET 후 JSON/XML 자동 판별 파싱. 일시적 오류는 지수 백오프 재시도."""
    host = urlsplit(url).hostname or ""
    if host in _DEAD_HOSTS:
        raise HostDown(f"{host} 에 연결할 수 없습니다: {_DEAD_HOSTS[host]}")

    last: Exception | None = None
    unreachable = 0          # 응답조차 못 받은 횟수 (연결 실패·타임아웃)
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, timeout=timeout,
                             headers={"User-Agent": "insta-databot/1.0"})
            r.raise_for_status()
            doc = _parse(r.text)
            if check_header:
                _check_header(doc)
            return doc
        except NoData:
            raise
        except PortalError as e:
            # 키/권한 문제는 재시도해도 소용없다
            if e.code in {"30", "31", "32", "20", "12", "22"}:
                raise
            last = e
        except requests.HTTPError as e:
            # 4xx 는 요청이 잘못된 것이라 재시도해도 같은 답이 온다.
            # (429 만 예외 — 잠시 뒤에 다시 하면 된다)
            code = getattr(e.response, "status_code", None)
            if code and 400 <= code < 500 and code != 429:
                raise
            last = e
        except (requests.ConnectionError, requests.Timeout) as e:
            # 서버가 대답을 아예 안 했다 — 응답이 이상한 것과는 다른 문제다.
            unreachable += 1
            last = e
        except (requests.RequestException, ValueError, json.JSONDecodeError) as e:
            last = e
        if attempt < retries:
            wait = BACKOFF ** attempt
            log.warning("요청 실패(%s/%s) %s · %.1fs 후 재시도", attempt, retries, last, wait)
            time.sleep(wait)
    if unreachable == retries:
        mark_host_down(host, str(last))
        raise HostDown(f"{host} 에 연결할 수 없습니다: {last}") from last
    raise RuntimeError(f"요청이 {retries}회 모두 실패했습니다: {last}") from last


def as_list(value: Any) -> list:
    """포털 응답은 항목이 1개면 dict, 0개면 None 으로 오는 경우가 많다."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def to_float(value: Any, default: float | None = None) -> float | None:
    """'-' , '', None, '통신장애' 같은 결측값을 안전하게 처리."""
    if value is None:
        return default
    s = str(value).strip().replace(",", "")
    if not s or s in {"-", "null", "None"}:
        return default
    try:
        return float(s)
    except ValueError:
        return default


def to_int(value: Any, default: int | None = None) -> int | None:
    f = to_float(value)
    return default if f is None else int(round(f))
