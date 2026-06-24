#!/usr/bin/env bash
# PostToolUse(ExitPlanMode) — drops a .marker file in the workspace's
# retrospectives/pending/ directory so the next SessionStart can remind
# about an outstanding retrospective.
#
# NOTE: "ExitPlanMode" as a PostToolUse matcher may not fire reliably
# in every Claude Code version. If markers are never dropped
# automatically, just run /plan-retrospective manually — the skill
# works without the marker.
set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../skills/plan-retrospective/scripts/find_workspace_root.sh
source "$PLUGIN_DIR/../skills/plan-retrospective/scripts/find_workspace_root.sh"

PROJECT_DIR="$(find_workspace_root)" || {
  echo "exit-plan-mode-marker: cannot locate workspace root; skipping retrospective marker" >&2
  exit 0
}
if [ ! -d "$PROJECT_DIR" ]; then
  echo "exit-plan-mode-marker: workspace root '$PROJECT_DIR' is not a directory; skipping" >&2
  exit 0
fi

PENDING_DIR="$PROJECT_DIR/retrospectives/pending"
DONE_DIR="$PROJECT_DIR/retrospectives/done"

mkdir -p "$PENDING_DIR"

# Pick the most recently modified plan file in the user's plans dir.
# This is the one ExitPlanMode just approved. Fragile if two plans
# were edited within the same second; acceptable because the failure
# mode is a mis-named marker, not data loss.
plans_dir="$HOME/.claude/plans"
latest_plan=""
if [ -d "$plans_dir" ]; then
  latest_plan=$(ls -t "$plans_dir/"*.md 2>/dev/null | head -n 1 || true)
fi
[ -z "$latest_plan" ] && exit 0

slug=$(basename "$latest_plan" .md)

# Skip if a done retro already exists (e.g., re-approval after edits).
[ -f "$DONE_DIR/$slug.md" ] && exit 0

# Skip if marker already exists.
[ -f "$PENDING_DIR/$slug.marker" ] && exit 0

printf '%s\n' "$latest_plan" > "$PENDING_DIR/$slug.marker"
exit 0
