#!/usr/bin/env bash
# Resolve the Claude workspace root for retrospective artifact placement.
#
# Strategy: walk upward from $PWD looking for a .claude/ directory — that
# directory marks "this is the Claude workspace root, not a nested code repo."
# Falls back to git rev-parse --show-toplevel for workspaces without .claude/.
#
# Why: git rev-parse --show-toplevel resolves to the nearest git root, which
# is the nested code repo (e.g., your-app/) when Claude is invoked from inside
# it — placing retro files in the wrong repo. The .claude/ walk finds the true
# workspace root regardless of which git repo is active.
#
# Exit codes:
#   0 — workspace root found (printed to stdout)
#   1 — could not determine workspace root (diagnostic on stderr)

find_workspace_root() {
  local dir="$PWD"
  while [ "$dir" != "/" ]; do
    if [ -d "$dir/.claude" ]; then
      echo "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  # No .claude/ found — fall back to git root (original behavior, backward-compatible)
  local git_root
  git_root=$(git rev-parse --show-toplevel 2>/dev/null)
  if [ -n "$git_root" ]; then
    echo "$git_root"
    return 0
  fi
  echo "find_workspace_root: cannot determine workspace root (no .claude/ found, not in a git repo)" >&2
  return 1
}
