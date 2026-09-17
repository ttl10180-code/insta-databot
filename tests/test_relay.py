"""서울 중계 — 켜고 끄기, 그리고 무엇보다 '중계가 죽어도 어제처럼 돈다'.

새 경로를 깔았는데 그 경로가 무너져서 발행이 멈추면, 고치려던 문제를 더
키운 것이다. 그래서 되돌아가기(fallback)를 가장 무겁게 검사한다.
"""
from __future__ import annotations

import base64
import json

import pytest
import requests

from src import config
from src.common import http, relay


@pytest.fixture
def relay_on(monkeypatch):
    monkeypatch.setattr(config, "KR_RELAY_URL", "https://example.supabase.co/functions/v1/databot-kr")
    monkeypatch.setattr(config, "KR_RELAY_KEY", "test-key")


def _relay_reply(payload: dict, status: int = 200) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps(payload).encode()
    r.headers["content-type"] = "application/json"
    return r


def test_설정이_없으면_중계를_쓰지_않는다(monkeypatch):
    monkeypatch.setattr(config, "KR_RELAY_URL", "")
    monkeypatch.setattr(config, "KR_RELAY_KEY", "")
    assert relay.enabled() is False


def test_중계_응답을_직접_연결과_같은_모양으로_돌려준다(relay_on, monkeypatch):
    body = '{"response":{"header":{"resultCode":"00"},"body":{"items":{"item":[1]}}}}'
    monkeypatch.setattr(requests, "post", lambda *a, **k: _relay_reply({
        "status": 200, "content_type": "application/json",
        "body_b64": base64.b64encode(body.encode()).decode()}))

    r = relay.request("GET", "https://apis.data.go.kr/x", params={"a": 1})
    assert r.status_code == 200
    assert r.json()["response"]["header"]["resultCode"] == "00"
    r.raise_for_status()                    # 직접 연결일 때와 같은 인터페이스


def test_charset_이_없으면_UTF8_로_읽는다(relay_on, monkeypatch):
    """국내 포털은 charset 을 자주 빠뜨린다. requests 는 그때 ISO-8859-1 로
    추정해 한글을 깨뜨린다."""
    monkeypatch.setattr(requests, "post", lambda *a, **k: _relay_reply({
        "status": 200, "content_type": "application/json",
        "body_b64": base64.b64encode('{"m":"맑음"}'.encode()).decode()}))
    assert relay.request("GET", "https://apis.data.go.kr/x").json()["m"] == "맑음"


def test_서울에서도_못_닿으면_되돌아갈_수_있게_알린다(relay_on, monkeypatch):
    monkeypatch.setattr(requests, "post",
                        lambda *a, **k: _relay_reply({"error": "timeout"}, status=504))
    with pytest.raises(relay.RelayUnavailable):
        relay.request("GET", "https://apis.data.go.kr/x")


def test_중계기가_죽어도_직접_연결로_카드는_나간다(relay_on, monkeypatch):
    """이 테스트가 이 기능의 존재 조건이다."""
    def relay_down(*a, **k):
        raise requests.ConnectionError("중계기 다운")

    calls = {"direct": 0}

    def direct(url, params=None, timeout=None, headers=None):
        calls["direct"] += 1
        r = requests.Response()
        r.status_code = 200
        r._content = b'{"response":{"header":{"resultCode":"00"},"body":{"ok":1}}}'
        r.encoding = "utf-8"
        return r

    monkeypatch.setattr(requests, "post", relay_down)
    monkeypatch.setattr(requests, "get", direct)
    monkeypatch.setattr(http, "_DEAD_HOSTS", {})

    doc = http.get("https://apis.data.go.kr/x", {"a": 1})
    assert doc["response"]["body"]["ok"] == 1
    assert calls["direct"] == 1
