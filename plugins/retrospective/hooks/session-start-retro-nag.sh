#!/usr/bin/env bash
# SessionStart — surfaces any outstanding plan retrospectives as a system
# reminder so they aren't forgotten across sessions.
set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../skills/plan-retrospective/scripts/find_workspace_root.sh
source "$PLUGIN_DIR/../skills/plan-retrospective/scripts/find_workspace_root.sh"

PROJECT_DIR="$(find_workspace_root)" || {
  echo "session-start-retro-nag: cannot locate workspace root; skipping retro check" >&2
  exit 0
}
if [ ! -d "$PROJECT_DIR" ]; then
  exit 0
fi

PENDING_DIR="$PROJECT_DIR/retrospectives/pending"

[ -d "$PENDING_DIR" ] || exit 0

# Collect markers, ignoring glob-literal output when no files match.
markers=()
while IFS= read -r -d '' f; do
  markers+=("$f")
done < <(find "$PENDING_DIR" -maxdepth 1 -name '*.marker' -print0 2>/dev/null || true)

[ ${#markers[@]} -eq 0 ] && exit 0

echo "Outstanding plan retrospectives — run /plan-retrospective for each:"
for m in "${markers[@]}"; do
  slug=$(basename "$m" .marker)
  echo "  - $slug"
done
exit 0
