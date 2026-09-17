"""캐시 대체 동작 — 국내 서버가 안 닿는 날 카드가 나가는지, 그리고
안 나가야 할 때 안 나가는지를 함께 묶어둔다.

여기서 지키려는 선은 하나다. '오래된 값을 오늘 값인 척 내보내지 않는다.'
그래서 대체가 되는 경우만큼 대체가 막히는 경우도 같은 무게로 검사한다.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from src import config
from src.common import cache
from src.common.http import NoData


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "")   # 네트워크 차단
    cache.begin()
    yield


def _boom():
    raise RuntimeError("연결할 수 없습니다")


def test_성공하면_저장하고_표시는_남기지_않는다():
    assert cache.remember("t", lambda: {"v": 1}, max_age_days=3) == {"v": 1}
    assert cache.stale_note() is None


def test_실패하면_지난_수집분으로_대신하고_표시를_남긴다():
    cache.remember("t", lambda: {"v": 1}, max_age_days=3)
    cache.begin()
    assert cache.remember("t", _boom, max_age_days=3) == {"v": 1}
    assert "수집분" in (cache.stale_note() or "")


def test_캐시가_없으면_원래_오류를_그대로_올린다():
    with pytest.raises(RuntimeError):
        cache.remember("처음보는것", _boom, max_age_days=3)


def test_허용기간이_0이면_대체하지_않는다():
    """실시간 관측값(미세먼지 등)은 몇 시간만 지나도 그냥 틀린 값이다."""
    cache.remember("t", lambda: {"v": 1}, max_age_days=3)
    cache.begin()
    with pytest.raises(RuntimeError):
        cache.remember("t", _boom, max_age_days=0)


def test_너무_오래된_캐시는_쓰지_않는다():
    cache.remember("t", lambda: {"v": 1}, max_age_days=3)
    path = cache.CACHE_DIR / "t.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["saved_at"] = (datetime.now(config.KST) - timedelta(days=9)).isoformat()
    path.write_text(json.dumps(raw), encoding="utf-8")
    cache.begin()
    with pytest.raises(RuntimeError):
        cache.remember("t", _boom, max_age_days=3)


def test_오늘은_데이터가_없다는_응답은_캐시로_덮지_않는다():
    """'서버가 안 닿는다' 와 '오늘은 그런 게 없다' 는 다른 일이다.
    후자를 캐시로 덮으면 없는 날에 지난주 값을 오늘인 척 올리게 된다."""
    cache.remember("t", lambda: {"v": 1}, max_age_days=3)
    cache.begin()
    with pytest.raises(NoData):
        cache.remember("t", lambda: (_ for _ in ()).throw(NoData("03", "없음")),
                       max_age_days=3)


def test_어제_받아둔_단기예보로_오늘_날씨를_만든다(monkeypatch):
    """단기예보는 사흘치가 한 번에 온다. 어제 응답 안에 오늘 예보가 이미
    들어 있으므로, 이때 캐시로 만든 카드는 낡은 값이 아니라 맞는 값이다."""
    from src.sources import weather

    now = datetime.now(config.KST)
    items = []
    for day in (0, 1):
        ymd = (now + timedelta(days=day)).strftime("%Y%m%d")
        for hour in range(0, 24, 3):
            for cat, val in (("TMP", "20"), ("SKY", "3"), ("PTY", "0"),
                             ("POP", "20"), ("REH", "55"), ("WSD", "2.1")):
                items.append({"fcstDate": ymd, "fcstTime": f"{hour:02d}00",
                              "category": cat, "fcstValue": val})
        items.append({"fcstDate": ymd, "fcstTime": "0600",
                      "category": "TMN", "fcstValue": "14"})

    cache.save("weather-raw", items)
    monkeypatch.setattr(weather, "_live_items", lambda *a, **k: _boom())
    cache.begin()

    data = weather.fetch(now=now)
    assert data["date"] == now.strftime("%Y%m%d")
    assert "수집분" in (cache.stale_note() or "")
