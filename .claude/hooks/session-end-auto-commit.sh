#!/usr/bin/env bash
# SessionEnd hook: if the working tree is dirty, run pytest; commit + push +
# open a PR only when tests pass and we're not sitting on main/master.
set -uo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$REPO_ROOT" || exit 0

STATUS_SNAPSHOT=$(git status --porcelain --untracked-files=all)
if [ -z "$STATUS_SNAPSHOT" ]; then
  exit 0
fi

BRANCH=$(git rev-parse --abbrev-ref HEAD)
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
WARNING_FILE="tmp/UNCOMMITTED_WARNING.txt"

write_warning() {
  mkdir -p tmp
  {
    echo "$1"
    echo "Timestamp: $TIMESTAMP"
    echo "Branch: $BRANCH"
    echo
    echo "---- git status ----"
    echo "$STATUS_SNAPSHOT"
    if [ -n "${2:-}" ]; then
      echo
      echo "---- pytest output ----"
      echo "$2"
    fi
  } > "$WARNING_FILE"
}

# Prefer the project's own virtualenv so imports of project dependencies
# (rank_bm25, sentence_transformers, etc.) actually resolve.
if [ -x "rag_app_env/Scripts/python.exe" ]; then
  PYTHON="rag_app_env/Scripts/python.exe"
else
  PYTHON="python"
fi

TEST_LOG=$(mktemp)
"$PYTHON" -m pytest >"$TEST_LOG" 2>&1
TEST_EXIT=$?
TEST_OUTPUT=$(cat "$TEST_LOG")
rm -f "$TEST_LOG"

if [ $TEST_EXIT -ne 0 ]; then
  write_warning "SessionEnd hook: uncommitted changes were found but 'pytest' failed, so nothing was committed." "$TEST_OUTPUT"
  exit 0
fi

if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
  write_warning "SessionEnd hook: uncommitted changes passed pytest, but the current branch is '$BRANCH'. Skipped auto-commit/push to avoid pushing straight to $BRANCH with no PR review. Create a feature branch and end the session again to get an auto-commit + PR."
  exit 0
fi

# Tests passed on a non-main branch: drop any stale warning from a previous
# failed run, then stage everything and commit.
rm -f "$WARNING_FILE"
git add -A

if git diff --cached --quiet; then
  exit 0
fi

CHANGED_FILES=$(git diff --cached --name-only)
FILE_COUNT=$(echo "$CHANGED_FILES" | wc -l)
FILE_LIST=$(echo "$CHANGED_FILES" | sed 's/^/  - /' | head -20)
if [ "$FILE_COUNT" -gt 20 ]; then
  FILE_LIST="$FILE_LIST
  ... and $((FILE_COUNT - 20)) more file(s)"
fi

COMMIT_SUBJECT="chore: commit uncommitted session changes ($FILE_COUNT file(s))"
COMMIT_BODY="Auto-committed by the SessionEnd hook after pytest passed with a dirty working tree.

Files changed:
$FILE_LIST"

git commit -m "$COMMIT_SUBJECT

$COMMIT_BODY

Co-Authored-By: Claude <noreply@anthropic.com>" || exit 0

git push -u origin "$BRANCH" 2>/dev/null || exit 0

if command -v gh >/dev/null 2>&1; then
  gh pr create \
    --title "$COMMIT_SUBJECT" \
    --body "$COMMIT_BODY

🤖 Auto-created by the SessionEnd hook." \
    --head "$BRANCH" >/dev/null 2>&1 || true
fi

exit 0
