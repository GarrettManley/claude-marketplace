#!/usr/bin/env bash
set -euo pipefail

# init.sh — git@garrettmanley plugin initialiser
# Scaffolds an optional project-local commit-message rules file
# (.claude/commit-message-rules.yaml) from the bundled example when run inside
# a git repo. No global/user-level machine config is required by this plugin.

PLUGIN_NAME="git"
RULES_FILENAME=".claude/commit-message-rules.yaml"

# ── option parsing ────────────────────────────────────────────────────────────
FORCE=false
QUIET=false
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=true ;;
    --quiet) QUIET=true ;;
    *) ;;
  esac
done

# ── helpers ───────────────────────────────────────────────────────────────────
_print() {
  if [ "$QUIET" = false ]; then
    printf '%s\n' "$1"
  fi
}

_status() {
  # $1 = state word, $2 = detail
  _print "[init:${PLUGIN_NAME}] $1 — $2"
}

# ── locate the example rules bundled with this skill ─────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXAMPLE_RULES="${SCRIPT_DIR}/../skills/commit-message/rules.example.yaml"

if [ ! -f "$EXAMPLE_RULES" ]; then
  _status "FAILED" "bundled example rules not found at: ${EXAMPLE_RULES}"
  exit 1
fi

# ── detect git repo ───────────────────────────────────────────────────────────
if ! GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  _status "skipped" "not inside a git repository; run from a project root to scaffold commit-message-rules.yaml"
  exit 0
fi

TARGET="${GIT_ROOT}/${RULES_FILENAME}"

# ── idempotency check ─────────────────────────────────────────────────────────
if [ -f "$TARGET" ] && [ "$FORCE" = false ]; then
  _status "already configured" "${RULES_FILENAME} already exists in this repo (use --force to overwrite)"
  exit 0
fi

# ── scaffold ──────────────────────────────────────────────────────────────────
mkdir -p "$(dirname "$TARGET")"
cp "$EXAMPLE_RULES" "$TARGET"

_status "CONFIGURED" "scaffolded ${RULES_FILENAME} from bundled example; edit to match your project's CI guard"
exit 0
