#!/usr/bin/env bash
# out/ 의 카드 이미지를 gh-pages 브랜치의 cards/ 로 올린다.
# 인스타그램은 공개 HTTPS 이미지 URL 만 받으므로 이 단계가 필수다.
set -euo pipefail

BRANCH="${PAGES_BRANCH:-gh-pages}"
WORKDIR="$(mktemp -d)"

# 카드가 하나도 안 만들어졌을 수 있다 (키 없음 등). 그건 오류가 아니라 '오늘은 없음'이다.
if ! ls out/*.jpg >/dev/null 2>&1; then
  echo "::notice::out/ 에 업로드할 .jpg 가 없어 배포를 건너뜁니다."
  exit 0
fi

git config --global user.name  "github-actions[bot]"
git config --global user.email "41898282+github-actions[bot]@users.noreply.github.com"

# actions/checkout 은 현재 브랜치만 얕게 가져오므로 gh-pages 의 로컬 참조가 없다.
# 원격에 브랜치가 있어도 곧바로 worktree 를 만들면 'invalid reference' 로 죽는다.
# 그래서 먼저 원격 참조를 받아온다.
git fetch --no-tags --prune origin \
  "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH" 2>/dev/null || true

if git show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
  echo "기존 $BRANCH 브랜치를 이어서 씁니다."
  git worktree add --force -B "$BRANCH" "$WORKDIR" "refs/remotes/origin/$BRANCH"
else
  echo "$BRANCH 브랜치가 없어 새로 만듭니다."
  git worktree add --force --detach "$WORKDIR"
  git -C "$WORKDIR" checkout --orphan "$BRANCH"
  git -C "$WORKDIR" reset --hard
fi

mkdir -p "$WORKDIR/cards"
cp out/*.jpg "$WORKDIR/cards/"

# Jekyll 처리를 끄고(언더스코어 파일 무시 방지), 모바일 인덱스를 만든다.
# 자동 게시가 막혀 있어도 이 페이지만 폰에서 열면 저장·복사로 바로 올릴 수 있다.
touch "$WORKDIR/.nojekyll"
python3 tools/build_index.py "$WORKDIR"

cd "$WORKDIR"
git add -A
if git diff --cached --quiet; then
  echo "변경 사항이 없어 푸시를 생략합니다."
else
  git commit -m "cards: $(date -u +%Y-%m-%dT%H:%MZ)"
  git push origin "HEAD:$BRANCH"
fi

cd - >/dev/null
git worktree remove --force "$WORKDIR"
echo "✅ gh-pages 배포 완료"
