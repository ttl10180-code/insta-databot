"""발행 기록과 점검.

지키려는 것 두 가지다.
  1) 워크플로마다 올리는 카드가 다르니, 기록은 반드시 '얹어야' 한다.
     통째로 덮어쓰면 환율을 올린 실행이 날씨 기록을 지운다.
  2) 조용한 게 정상인 경우(주말 환율, 주간 카드)와 고장을 구분해야 한다.
     구분 못 하면 빨간 X 가 닳아서 아무도 안 본다.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from src import config, health
from src.common import cache, postlog


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(postlog, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "")      # 네트워크 차단
    yield


def _stamp(days_ago: float) -> str:
    return (datetime.now(config.KST) - timedelta(days=days_ago)).isoformat(timespec="seconds")


def test_다른_워크플로의_기록을_지우지_않는다():
    postlog.record(["weather", "air"])
    postlog.record(["exchange"])                 # 환율 워크플로가 따로 돈다
    assert set(postlog.load()) == {"weather", "air", "exchange"}


def test_빈_목록은_기록을_건드리지_않는다():
    postlog.record(["weather"])
    before = postlog.load()
    postlog.record([])
    assert postlog.load() == before


def test_기록이_아예_없으면_실패로_보지_않는다():
    """기능을 막 켠 직후가 이 상태다. 여기서 빨간 X 가 뜨면 안 된다."""
    assert health.run() == 0


def test_주기_안에_있으면_통과한다(monkeypatch):
    monkeypatch.setattr(postlog, "load", lambda: {
        k: _stamp(0.2) for k in health.WATCH})
    assert health.run() == 0


def test_너무_오래_조용하면_실패한다(monkeypatch):
    rec = {k: _stamp(0.2) for k in health.WATCH}
    rec["missing"] = _stamp(3.5)                 # 실종자 3.5일째 무소식
    monkeypatch.setattr(postlog, "load", lambda: rec)
    assert health.run() == 1


def test_주말에_환율이_쉬는_것은_고장이_아니다(monkeypatch):
    """금요일에 올리고 월요일 아침까지 조용한 건 정상이다."""
    rec = {k: _stamp(0.2) for k in health.WATCH}
    rec["exchange"] = _stamp(3.0)
    monkeypatch.setattr(postlog, "load", lambda: rec)
    assert health.run() == 0


def test_주간_카드는_일주일_조용해도_괜찮다(monkeypatch):
    rec = {k: _stamp(0.2) for k in health.WATCH}
    rec["apply"] = _stamp(7.5)
    rec["realestate"] = _stamp(7.5)
    monkeypatch.setattr(postlog, "load", lambda: rec)
    assert health.run() == 0


def test_기록_파일은_사람이_읽을_수_있는_형태다():
    postlog.record(["weather"])
    raw = json.loads((postlog._path()).read_text(encoding="utf-8"))
    assert "weather" in raw and raw["weather"].startswith("20")
