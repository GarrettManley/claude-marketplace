#!/usr/bin/env bash
set -euo pipefail

# discipline/scripts/init.sh
# Scaffold an optional project-local config at ./.claude/discipline.local.md
# from the plugin's examples/discipline.local.md if absent.
#
# Usage: init.sh [--force] [--quiet]

FORCE=0
QUIET=0

for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --quiet) QUIET=1 ;;
    *) ;;
  esac
done

# Resolve paths relative to this script's own location.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
plugin_dir="$(cd "${script_dir}/.." && pwd)"
example_file="${plugin_dir}/examples/discipline.local.md"
target_dir="./.claude"
target_file="${target_dir}/discipline.local.md"

# Verify the example template exists — hard failure if missing.
if [[ ! -f "${example_file}" ]]; then
  echo "[init:discipline] FAILED — example template not found: ${example_file}"
  exit 1
fi

# Already configured?
if [[ -f "${target_file}" && "${FORCE}" -eq 0 ]]; then
  if [[ "${QUIET}" -eq 0 ]]; then
    echo "[init:discipline] already configured — ${target_file} exists (use --force to overwrite)"
  fi
  exit 0
fi

# Create .claude/ dir if absent.
if [[ ! -d "${target_dir}" ]]; then
  mkdir -p "${target_dir}"
fi

# Copy the example template.
cp "${example_file}" "${target_file}"

if [[ "${QUIET}" -eq 0 ]]; then
  echo "[init:discipline] CONFIGURED — wrote ${target_file}"
fi
exit 0
