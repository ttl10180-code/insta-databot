"""워크플로가 각 단계에 필요한 값을 실제로 넘기는지 본다.

왜 이런 테스트가 있나. 캐시 되돌아가기를 만들어 놓고도 9월 18일 아침 카드가
세 번 다 실패했다. 코드는 멀쩡했고 캐시 파일도 있었다. 카드를 만드는 단계에
PUBLIC_BASE_URL 을 안 넘겨서, 캐시를 어디서 읽어야 하는지 몰랐을 뿐이다.

파이썬만 테스트하면 이런 건 안 잡힌다. 로컬에서는 캐시 파일이 디스크에 있어
통과하고, 러너에서는 매번 새 체크아웃이라 공개 URL 로만 읽을 수 있기 때문이다.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _steps():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for job in (doc.get("jobs") or {}).values():
            for step in (job.get("steps") or []):
                yield path.name, step


def _runs(step, *needles) -> bool:
    run = str(step.get("run") or "")
    return any(n in run for n in needles)


# --sample 은 샘플 데이터로 디자인만 확인하는 경로라 수집도 캐시도 타지 않는다.
CACHE_READERS = [
    (name, step) for name, step in _steps()
    if _runs(step, "src.main render", "src.main post", "src.main collect",
                 "src.main health")
    and "--sample" not in str(step.get("run") or "")
]


def test_캐시를_쓰는_단계를_하나라도_찾았다():
    """워크플로 구조가 바뀌어 아래 검사가 통째로 비어버리는 걸 막는다."""
    assert CACHE_READERS, "src.main 을 실행하는 단계를 못 찾았습니다"


@pytest.mark.parametrize("name,step", CACHE_READERS,
                         ids=[f"{n}:{(s.get('name') or s['run'])[:24]}"
                              for n, s in CACHE_READERS])
def test_지난_수집분을_읽을_주소를_넘긴다(name, step):
    env = step.get("env") or {}
    assert "PUBLIC_BASE_URL" in env, (
        f"{name} 의 '{step.get('name')}' 단계에 PUBLIC_BASE_URL 이 없습니다. "
        "국내 서버가 안 닿을 때 지난 수집분을 읽지 못하고 그냥 실패합니다."
    )
