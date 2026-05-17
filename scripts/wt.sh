#!/usr/bin/env bash
set -euo pipefail

BRANCH="${1:-}"
if [[ -z "$BRANCH" ]]; then
  echo "Usage: bash scripts/wt.sh <branch-name>" >&2
  exit 1
fi

PROJECT_DIR="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
WORKTREES_DIR="${PROJECT_DIR}-worktrees"
TARGET="$WORKTREES_DIR/$BRANCH"

mkdir -p "$WORKTREES_DIR"
git -C "$PROJECT_DIR" worktree add -b "$BRANCH" "$TARGET"

if [[ -f "$PROJECT_DIR/.env" ]]; then
  cp "$PROJECT_DIR/.env" "$TARGET/.env"
  echo "  Copied .env"
fi

if [[ -d "$PROJECT_DIR/.claude" ]]; then
  cp -r "$PROJECT_DIR/.claude" "$TARGET/.claude"
  echo "  Copied .claude/"
fi

echo ""
echo "Worktree ready:"
echo "  Path:   $TARGET"
echo "  Branch: $BRANCH"
echo ""
echo "Open with: cd \"$TARGET\""
