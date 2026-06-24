#!/usr/bin/env bash
# SessionStart hook: surface open GitHub issues as additionalContext.
# Auto-detects the repo from origin remote; override with DISCIPLINE_REPO.
#
# Disable entirely by setting DISCIPLINE_INJECT_ISSUES=false or
# `inject-issues: false` in .claude/discipline.local.md.

set -euo pipefail

if [[ "${DISCIPLINE_INJECT_ISSUES:-}" == "false" ]]; then
  exit 0
fi

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
LOCAL_CONFIG="${REPO_ROOT}/.claude/discipline.local.md"
if [[ -f "$LOCAL_CONFIG" ]] && grep -qE '^inject-issues:\s*false\s*$' "$LOCAL_CONFIG" 2>/dev/null; then
  exit 0
fi

# Require uv on PATH; exit silently if missing (fail-soft). uv resolves an
# interpreter cross-platform, matching the rest of hooks.json (a system
# interpreter is not guaranteed on a stock Windows + Git Bash setup).
if ! command -v uv >/dev/null 2>&1; then
  exit 0
fi

dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec uv run --no-project "$dir/../scripts/_inject_issues.py"
