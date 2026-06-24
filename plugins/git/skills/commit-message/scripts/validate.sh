#!/usr/bin/env bash
# /commit-message --validate <ref> — validates a commit message against a rule set.
#
# Usage:
#   validate.sh HEAD
#   validate.sh <SHA>
#   validate.sh HEAD --rules /path/to/rules.yaml
#
# Exit codes:
#   0  — valid
#   1  — validation failed (diagnostic printed to stderr)
#   2  — usage error

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ $# -lt 1 ]; then
  echo "Usage: validate.sh <ref> [--rules <path>]" >&2
  exit 2
fi

REF="$1"
shift

RULES_FILE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --rules)
      RULES_FILE="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

# Resolve default rule file: project-local first, then the bundled example.
# Use ${GIT_ROOT:+...} so an empty GIT_ROOT never produces "/.claude/..." paths.
if [ -z "$RULES_FILE" ]; then
  GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
  if [ -z "$GIT_ROOT" ]; then
    echo "validate: warning: not inside a git repository; project-local rules not searched" >&2
  fi
  for candidate in \
    "${GIT_ROOT:+${GIT_ROOT}/.claude/commit-message-rules.yaml}" \
    "${SCRIPT_DIR}/../rules.example.yaml"; do
    [ -z "$candidate" ] && continue
    if [ -f "$candidate" ]; then
      RULES_FILE="$candidate"
      break
    fi
  done
fi

# Write commit message to a temp file (avoids quoting issues passing to Python).
TMP_MSG=$(mktemp)
GIT_ERR=$(mktemp)
trap 'rm -f "$TMP_MSG" "$GIT_ERR"' EXIT

git log -1 --format="%B" "$REF" > "$TMP_MSG" 2>"$GIT_ERR" || {
  echo "validate: cannot read commit message for '$REF'" >&2
  [ -s "$GIT_ERR" ] && cat "$GIT_ERR" >&2
  exit 2
}

uv run --no-project "${SCRIPT_DIR}/validate.py" "$REF" "$TMP_MSG" "${RULES_FILE:-}"
