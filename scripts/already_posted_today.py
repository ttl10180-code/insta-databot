"""오늘(한국시간) 이 워크플로가 이미 성공했는지 확인한다.

예약 실행을 하루 여러 번 잡아 두었기 때문에 필요한 장치다. 국내 공공 API 가
잠깐 안 닿거나 깃허브 예약이 통째로 밀려도 그날 안에 다시 시도하게 하되,
이미 잘 올라간 날에 두 번 올리는 일은 없어야 한다.

판단 근거는 깃허브의 실행 기록이다. 같은 워크플로가 오늘 한 번이라도
success 로 끝났으면 '완료' 로 본다. 게시가 실패한 날은 워크플로도 실패로
끝나므로, 다음 예약분이 다시 시도한다.

성공/실패를 알 수 없으면(API 오류 등) '아직 안 올림' 쪽으로 판단한다.
빠뜨리는 것보다 한 번 더 시도하는 쪽이 낫고, 중복은 인스타그램 쪽
게시 한도와 concurrency 로도 한 겹 더 막혀 있다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def _out(done: bool, why: str) -> int:
    print(f"{'이미 올림' if done else '아직 안 올림'} — {why}")
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"done={'true' if done else 'false'}\n")
    return 0


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    wf = os.environ.get("GITHUB_WORKFLOW", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not repo or not wf:
        return _out(False, "실행 정보를 읽지 못했습니다")

    try:
        raw = subprocess.run(
            ["gh", "api", f"repos/{repo}/actions/runs",
             "-X", "GET", "-f", "status=success", "-f", "per_page=30",
             "--jq", ".workflow_runs[] | {name, id, created_at}"],
            capture_output=True, text=True, timeout=60, check=True).stdout
    except Exception as e:                        # noqa: BLE001
        return _out(False, f"실행 기록 조회 실패: {e}")

    today = datetime.now(KST).date()
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("name") != wf or str(row.get("id")) == run_id:
            continue
        when = datetime.fromisoformat(
            str(row.get("created_at", "")).replace("Z", "+00:00"))
        if when.astimezone(KST).date() == today:
            return _out(True, f"오늘 {when.astimezone(KST):%H:%M} 에 성공한 실행이 있습니다")

    return _out(False, "오늘 성공한 실행이 없습니다")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:            # noqa: BLE001
        # 이 검사가 실패했다고 그날 게시를 통째로 막으면 본말이 전도된다.
        sys.exit(_out(False, f"검사 중 오류: {e}"))
