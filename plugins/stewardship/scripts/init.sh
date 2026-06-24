#!/usr/bin/env bash
# init.sh — stewardship plugin initializer (Unix/macOS/Linux/Git-Bash)
# Registers the nightly steward scheduler via cron (or launchd hint).
#
# Contract:
#   --force    Re-install even if already configured.
#   --quiet    Suppress the status line.
#   Exit 0:    success OR already-configured.
#   Exit 1:    hard failure.
#
# Status line format:
#   [init:stewardship] <CONFIGURED|already configured|FAILED> — <detail>

set -euo pipefail

PLUGIN_NAME="stewardship"
TASK_COMMENT="stewardship-nightly-steward"

force=0
quiet=0

for arg in "$@"; do
    case "$arg" in
        --force) force=1 ;;
        --quiet) quiet=1 ;;
    esac
done

status_line() {
    if [ "$quiet" -eq 0 ]; then
        printf '[init:%s] %s\n' "$PLUGIN_NAME" "$1"
    fi
}

# Resolve plugin root (parent of this script's directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TEMPLATE="${SCRIPT_DIR}/nightly-scheduler.cron.template"

# Build the cron command: run the nightly wrapper via python3 at 03:00 daily.
# We use the drift_check.py + auto_memory_housekeep.py scripts as the canonical
# nightly entry — mirrors what register_nightly.ps1 does on Windows.
CRON_COMMAND="0 3 * * * python3 \"${PLUGIN_ROOT}/scripts/drift_check.py\" >> \"\${HOME}/.local/share/stewardship-plugin/logs/nightly.log\" 2>&1 && python3 \"${PLUGIN_ROOT}/scripts/auto_memory_housekeep.py\" >> \"\${HOME}/.local/share/stewardship-plugin/logs/nightly.log\" 2>&1"

# If the cross-platform scheduler template exists, read the cron line from it.
if [ -f "${TEMPLATE}" ]; then
    # Extract the first non-comment, non-empty line from the template.
    TEMPLATE_LINE="$(grep -v '^[[:space:]]*#' "${TEMPLATE}" | grep -v '^[[:space:]]*$' | head -1 || true)"
    if [ -n "${TEMPLATE_LINE}" ]; then
        # Substitute the plugin root placeholder if present, else use as-is.
        CRON_COMMAND="$(echo "${TEMPLATE_LINE}" | sed "s|{{PLUGIN_ROOT}}|${PLUGIN_ROOT}|g")"
    fi
fi

# ---------------------------------------------------------------------------
# Detect whether cron is available (skip gracefully on systems without it)
# ---------------------------------------------------------------------------
if ! command -v crontab >/dev/null 2>&1; then
    status_line "skipped — crontab not found on this system; add the following line manually:
  ${CRON_COMMAND}"
    exit 0
fi

# ---------------------------------------------------------------------------
# Read existing crontab (allow empty / no crontab yet)
# ---------------------------------------------------------------------------
EXISTING_CRONTAB="$(crontab -l 2>/dev/null || true)"

# Check for an existing stewardship entry
if echo "${EXISTING_CRONTAB}" | grep -qF "${TASK_COMMENT}"; then
    if [ "$force" -eq 0 ]; then
        status_line "already configured — nightly steward cron entry found (use --force to re-install)"
        exit 0
    fi
    # --force: remove the old entry before re-adding
    EXISTING_CRONTAB="$(echo "${EXISTING_CRONTAB}" | grep -vF "${TASK_COMMENT}" || true)"
fi

# ---------------------------------------------------------------------------
# Install the cron entry
# ---------------------------------------------------------------------------
LOG_DIR="${HOME}/.local/share/stewardship-plugin/logs"
mkdir -p "${LOG_DIR}"

NEW_CRON_LINE="${CRON_COMMAND} # ${TASK_COMMENT}"

{
    if [ -n "${EXISTING_CRONTAB}" ]; then
        printf '%s\n' "${EXISTING_CRONTAB}"
    fi
    printf '%s\n' "${NEW_CRON_LINE}"
} | crontab - || {
    status_line "FAILED — could not write crontab"
    exit 1
}

status_line "CONFIGURED — nightly steward cron entry registered at 03:00 daily
  Cron line: ${NEW_CRON_LINE}
  Log dir:   ${LOG_DIR}"
