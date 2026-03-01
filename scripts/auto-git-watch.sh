#!/usr/bin/env bash
# auto-git-watch.sh
# 监听 scripts/ 目录变化，自动 add → commit → push
# 用法：bash scripts/auto-git-watch.sh
# 停止：Ctrl+C

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WATCH_DIR="$REPO_DIR/scripts"

echo "[auto-git] 开始监听: $WATCH_DIR"
echo "[auto-git] 按 Ctrl+C 停止"

fswatch -o "$WATCH_DIR" | while read -r count; do
  cd "$REPO_DIR" || exit 1

  # 有实际变动才提交
  if ! git diff --quiet || git ls-files --others --exclude-standard | grep -q .; then
    TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
    git add -A
    git commit -m "auto: scripts updated @ $TIMESTAMP"
    git push
    echo "[auto-git] ✓ 已提交并推送 @ $TIMESTAMP"
  fi
done
