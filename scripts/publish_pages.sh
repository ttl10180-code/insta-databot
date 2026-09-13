#!/usr/bin/env bash
# out/ 의 카드 이미지를 gh-pages 브랜치의 cards/ 로 올린다.
# 인스타그램은 공개 HTTPS 이미지 URL 만 받으므로 이 단계가 필수다.
set -euo pipefail

BRANCH="${PAGES_BRANCH:-gh-pages}"
WORKDIR="$(mktemp -d)"

if ! ls out/*.jpg >/dev/null 2>&1; then
  echo "::error::out/ 에 업로드할 .jpg 가 없습니다."
  exit 1
fi

git config --global user.name  "github-actions[bot]"
git config --global user.email "41898282+github-actions[bot]@users.noreply.github.com"

if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
  git worktree add --checkout "$WORKDIR" "$BRANCH"
else
  echo "gh-pages 브랜치가 없어 새로 만듭니다."
  git worktree add --detach "$WORKDIR"
  git -C "$WORKDIR" checkout --orphan "$BRANCH"
  git -C "$WORKDIR" reset --hard
fi

mkdir -p "$WORKDIR/cards"
cp out/*.jpg "$WORKDIR/cards/"

# Jekyll 처리를 끄고(언더스코어 파일 무시 방지), 간단한 인덱스를 남긴다
touch "$WORKDIR/.nojekyll"
{
  echo "<!doctype html><meta charset=utf-8><title>data cards</title>"
  echo "<h1>공공데이터 인스타 카드</h1><ul>"
  ls -1 "$WORKDIR/cards" | sort -r | head -60 | while read -r f; do
    echo "<li><a href=\"cards/$f\">$f</a></li>"
  done
  echo "</ul>"
} > "$WORKDIR/index.html"

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
