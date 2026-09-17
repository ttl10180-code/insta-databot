#!/usr/bin/env bash
# out/ 의 카드 이미지와 수집 캐시를 gh-pages 브랜치로 올린다.
#   cards/ — 인스타그램은 공개 HTTPS 이미지 URL 만 받으므로 이 단계가 필수다.
#   cache/ — 국내 서버가 안 닿는 날 카드를 살리는 지난 수집분 (src/common/cache.py).
#
# 발행 워크플로와 수집 워크플로가 둘 다 여기로 들어온다. 둘이 겹치면 푸시가
# 거절될 수 있어서, 거절되면 원격의 새 끝점 위에 처음부터 다시 얹고 재시도한다.
# (둘을 같은 concurrency 그룹으로 묶는 방법도 있지만, 그러면 대기 중이던 발행이
#  뒤에 온 수집에 밀려 취소될 수 있다. 게시를 조용히 건너뛰는 건 최악이다.)
set -euo pipefail

BRANCH="${PAGES_BRANCH:-gh-pages}"
ATTEMPTS="${PAGES_PUSH_ATTEMPTS:-3}"

# 카드가 하나도 안 만들어졌을 수 있다 (키 없음 등). 그건 오류가 아니라 '오늘은 없음'이다.
# 다만 수집에는 성공했는데 렌더에서 넘어진 경우가 있으므로, 올릴 캐시가 있으면
# 카드가 없어도 배포는 한다 — 그 캐시가 내일 카드를 살린다.
if ! ls out/*.jpg >/dev/null 2>&1 && ! ls out/cache/*.json >/dev/null 2>&1; then
  echo "::notice::out/ 에 업로드할 것이 없어 배포를 건너뜁니다."
  exit 0
fi

git config --global user.name  "github-actions[bot]"
git config --global user.email "41898282+github-actions[bot]@users.noreply.github.com"

attempt_push() {
  local workdir
  workdir="$(mktemp -d)"

  # actions/checkout 은 현재 브랜치만 얕게 가져오므로 gh-pages 의 로컬 참조가 없다.
  # 원격에 브랜치가 있어도 곧바로 worktree 를 만들면 'invalid reference' 로 죽는다.
  git fetch --no-tags --prune origin \
    "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH" 2>/dev/null || true

  if git show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
    git worktree add --force -B "$BRANCH" "$workdir" "refs/remotes/origin/$BRANCH"
  else
    echo "$BRANCH 브랜치가 없어 새로 만듭니다."
    git worktree add --force --detach "$workdir"
    git -C "$workdir" checkout --orphan "$BRANCH"
    git -C "$workdir" reset --hard
  fi

  mkdir -p "$workdir/cards"
  cp out/*.jpg "$workdir/cards/" 2>/dev/null || true

  # 이번에 수집에 성공한 원본을 cache/ 에 덮어쓴다. 실패한 소스는 파일을 만들지
  # 않으므로 지난 성공분이 그대로 남는다 (덮어쓰기만 하고 지우지 않는다).
  if ls out/cache/*.json >/dev/null 2>&1; then
    mkdir -p "$workdir/cache"
    cp out/cache/*.json "$workdir/cache/"
  fi

  # Jekyll 처리를 끄고(언더스코어 파일 무시 방지), 모바일 인덱스를 만든다.
  # 자동 게시가 막혀 있어도 이 페이지만 폰에서 열면 저장·복사로 바로 올릴 수 있다.
  touch "$workdir/.nojekyll"
  python3 tools/build_index.py "$workdir"

  local rc=0
  (
    cd "$workdir"
    git add -A
    if git diff --cached --quiet; then
      echo "변경 사항이 없어 푸시를 생략합니다."
      exit 0
    fi
    git commit -q -m "pages: $(date -u +%Y-%m-%dT%H:%MZ)"
    git push origin "HEAD:$BRANCH"
  ) || rc=$?

  git worktree remove --force "$workdir" || true
  return "$rc"
}

for i in $(seq 1 "$ATTEMPTS"); do
  if attempt_push; then
    echo "✅ gh-pages 배포 완료"
    exit 0
  fi
  echo "::warning::gh-pages 푸시 실패 ($i/$ATTEMPTS). 원격의 최신 상태 위에 다시 얹습니다."
  sleep $(( i * 5 ))
done

echo "::error::gh-pages 배포에 $ATTEMPTS 번 모두 실패했습니다."
exit 1
