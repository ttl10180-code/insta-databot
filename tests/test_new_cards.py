"""추가 주제 6종의 회귀 테스트.

두 가지를 지킨다:
  1) 기관 키가 없으면 '크래시'가 아니라 NoData 로 조용히 건너뛴다
     (다른 카드의 발행을 막으면 안 된다)
  2) 샘플 데이터로 10종 카드의 컨텍스트와 캡션이 모두 만들어진다
     (템플릿 변수 오타를 렌더 전에 잡는다)
"""
from __future__ import annotations

from datetime import datetime

import pytest

from src import cards, config, sample
from src.common import http
from src.sources import apply, boxoffice, exchange, price

NOW = datetime(2026, 9, 15, 9, 0)


@pytest.mark.parametrize("call, attrs", [
    (lambda: boxoffice.fetch_daily(now=NOW), ["KOBIS_KEY"]),
    (lambda: boxoffice.fetch_weekly(now=NOW), ["KOBIS_KEY"]),
    (lambda: exchange.fetch(now=NOW), ["EXIM_KEY"]),
    (lambda: price.fetch(now=NOW), ["KAMIS_KEY", "KAMIS_ID"]),
    (lambda: apply.fetch(now=NOW), ["DATA_GO_KR_KEY"]),
])
def test_missing_key_skips_quietly(monkeypatch, call, attrs):
    for name in attrs:
        monkeypatch.setattr(config, name, "")
    with pytest.raises(http.NoData):
        call()


@pytest.mark.parametrize("kind", sorted(cards.CARDS))
def test_sample_card_builds(kind):
    template, ctx, caption = sample.build(kind, NOW)
    assert template.endswith(".html")
    assert ctx["title"] and ctx["theme"].startswith("theme-")
    assert ctx["handle"] and ctx["source"]
    assert len(caption) > 80
    # 캡션에 미치환 자리표시자가 남아 있지 않아야 한다
    assert "{" not in caption and "None" not in caption


def test_mascot_mood_falls_back_when_missing():
    """무드 이미지가 없으면 조용히 기본 마스코트로 돌아가야 한다.
    (없는 파일을 가리키면 카드에 깨진 이미지가 박힌다)"""
    assert cards.mascot_file("theme-air", "mask") == "odi-air-mask.png"
    assert cards.mascot_file("theme-air", "sombrero") == "odi-air.png"
    assert cards.mascot_file("theme-oil") == "odi-oil.png"


@pytest.mark.parametrize("kind", sorted(cards.CARDS))
def test_mascot_image_exists(kind):
    """모든 카드가 실제로 존재하는 마스코트 파일을 가리킨다."""
    _, ctx, _ = sample.build(kind, NOW)
    assert (config.ROOT / "assets" / "mascot" / ctx["mascot"]).exists()


def test_render_survives_a_missing_key(monkeypatch, tmp_path):
    """키가 없는 카드 하나 때문에 워크플로 전체가 죽으면 안 된다.

    2026-09-15 첫 실행에서 KOBIS_KEY 가 없다는 이유로 render 가 exit 1 을
    돌려 워크플로가 통째로 실패했다. 그 회귀를 막는다.
    """
    from argparse import Namespace
    from src import main

    monkeypatch.setattr(config, "KOBIS_KEY", "")
    monkeypatch.setattr(config, "OUT_DIR", tmp_path)
    monkeypatch.setattr(main.config, "OUT_DIR", tmp_path)

    # 키 없는 카드만 → 오류가 아니라 '오늘은 없음'
    code = main.cmd_render(Namespace(kinds=["boxoffice"], sample=False, story=False))
    assert code == 0

    # 키 없는 카드 + 정상 카드 → 정상 카드는 그대로 나온다
    code = main.cmd_render(Namespace(kinds=["boxoffice", "weather"], sample=True, story=False))
    assert code == 0
    assert list(tmp_path.glob("*-weather.jpg"))
