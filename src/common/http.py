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

import requests
import xmltodict

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20
MAX_RETRIES = 3
BACKOFF = 2.0

# 포털 공통 결과코드
OK_CODES = {"00", "000"}
NODATA_CODES = {"03", "003"}


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


def get(url: str, params: dict, *, timeout: int = DEFAULT_TIMEOUT,
        retries: int = MAX_RETRIES, check_header: bool = True) -> Any:
    """GET 후 JSON/XML 자동 판별 파싱. 일시적 오류는 지수 백오프 재시도."""
    last: Exception | None = None
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
        except (requests.RequestException, ValueError, json.JSONDecodeError) as e:
            last = e
        if attempt < retries:
            wait = BACKOFF ** attempt
            log.warning("요청 실패(%s/%s) %s · %.1fs 후 재시도", attempt, retries, last, wait)
            time.sleep(wait)
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
