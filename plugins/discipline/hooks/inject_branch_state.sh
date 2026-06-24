#!/usr/bin/env bash
# SessionStart hook: surface stale or unmerged branches at session open.
# Stays silent when everything is clean; prints a warning block when action is needed.
# Auto-detects the main branch from origin/HEAD; override with DISCIPLINE_MAIN_BRANCH.
#
# Disable entirely by setting DISCIPLINE_INJECT_BRANCH_STATE=false or
# `inject-branch-state: false` in .claude/discipline.local.md.

set -euo pipefail

# Honor disable flag. Read from .claude/discipline.local.md if present.
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
LOCAL_CONFIG="${REPO_ROOT}/.claude/discipline.local.md"
if [[ "${DISCIPLINE_INJECT_BRANCH_STATE:-}" == "false" ]]; then
  exit 0
fi
if [[ -f "$LOCAL_CONFIG" ]] && grep -qE '^inject-branch-state:\s*false\s*$' "$LOCAL_CONFIG" 2>/dev/null; then
  exit 0
fi

# Require gh and python3 on PATH; exit silently if either is missing (fail-soft).
if ! command -v gh >/dev/null 2>&1; then
  exit 0
fi
if ! command -v python3 >/dev/null 2>&1; then
  exit 0
fi

cd "$REPO_ROOT"

# Detect main branch: env override > origin/HEAD > 'main'
if [[ -n "${DISCIPLINE_MAIN_BRANCH:-}" ]]; then
  MAIN_BRANCH="$DISCIPLINE_MAIN_BRANCH"
else
  MAIN_BRANCH="$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo main)"
  [[ -z "$MAIN_BRANCH" ]] && MAIN_BRANCH="main"
fi

UNPUSHED_WARN=5      # commits unpushed before flagging
BEHIND_WARN=20       # commits behind main before flagging
AGE_WARN_DAYS=3      # days since last commit before flagging inactive branch

warnings=()

while IFS= read -r branch; do
  [[ "$branch" == "$MAIN_BRANCH" ]] && continue

  # Unpushed commits on this branch
  tracking=$(git rev-parse --abbrev-ref "${branch}@{upstream}" 2>/dev/null || echo "")
  if [[ -z "$tracking" ]]; then
    unpushed=$(git rev-list --count "origin/${MAIN_BRANCH}..${branch}" 2>/dev/null || echo 0)
    tracking_note="(no remote)"
  else
    unpushed=$(git rev-list --count "${tracking}..${branch}" 2>/dev/null || echo 0)
    tracking_note=""
  fi

  # Commits ahead/behind main
  ahead=$(git rev-list --count "${MAIN_BRANCH}..${branch}" 2>/dev/null || echo 0)
  behind=$(git rev-list --count "${branch}..${MAIN_BRANCH}" 2>/dev/null || echo 0)

  # Age of last commit on this branch
  last_commit_ts=$(git log -1 --format="%ct" "${branch}" 2>/dev/null || echo 0)
  now_ts=$(date +%s)
  age_days=$(( (now_ts - last_commit_ts) / 86400 ))

  reasons=()

  if (( unpushed > UNPUSHED_WARN )); then
    reasons+=("${unpushed} unpushed commits ${tracking_note}")
  fi
  if (( behind > BEHIND_WARN )); then
    reasons+=("${behind} behind ${MAIN_BRANCH}")
  fi
  if (( age_days >= AGE_WARN_DAYS && ahead > 0 )); then
    reasons+=("last commit ${age_days}d ago")
  fi

  if (( ${#reasons[@]} > 0 )); then
    summary="${branch} - ${ahead} ahead / ${behind} behind ${MAIN_BRANCH}"
    for r in "${reasons[@]}"; do
      summary+=", ${r}"
    done
    warnings+=("warn: ${summary}")
  fi
done < <(git branch --format="%(refname:short)" 2>/dev/null)

if (( ${#warnings[@]} > 0 )); then
  cat <<EOF
{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"## Branch state\n\n$(printf -- '- %s\\n' "${warnings[@]}")\n"}}
EOF
fi
