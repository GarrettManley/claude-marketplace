#!/usr/bin/env bash
# setup.sh — one-command marketplace setup (Unix/macOS/Linux/Git-Bash)
#
# Detects the OS, then runs each plugin's scripts/init.sh (if present),
# passing through --force/--quiet, collects each init's status line, and
# prints a final config-status summary table.
#
# Contract:
#   --force    Re-scaffold each plugin even if already configured.
#   --quiet    Suppress per-plugin status lines (the summary table still prints).
#   Exit 0:    every init succeeded OR was already configured.
#   Exit 1:    at least one init hard-failed (or could not be executed).
#
# Plugins are initialized in a fixed order; one plugin's failure does not abort
# the rest — every init runs, and the table reports each outcome.

set -euo pipefail

PLUGINS=(evidence orchestration stewardship discipline git)

quiet=0
# Only --force is passed through to each child init. --quiet is NOT forwarded:
# we always want the child's status line so the summary table is meaningful;
# our own --quiet suppresses echoing that captured output and the [setup] lines.
passthru=()
for arg in "$@"; do
    case "$arg" in
        --force) passthru+=("--force") ;;
        --quiet) quiet=1 ;;
        *)
            echo "setup: unknown argument: $arg" >&2
            echo "usage: setup.sh [--force] [--quiet]" >&2
            exit 1
            ;;
    esac
done

# Resolve the repo root from this script's own location (scripts/ -> repo root).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PLUGINS_DIR="${REPO_ROOT}/plugins"

# Detect the host OS (informational; init.sh handles platform specifics itself).
detect_os() {
    case "$(uname -s)" in
        Linux*)             echo "Linux" ;;
        Darwin*)            echo "macOS" ;;
        MINGW*|MSYS*|CYGWIN*) echo "Windows (Git-Bash)" ;;
        *)                  echo "$(uname -s)" ;;
    esac
}
OS_NAME="$(detect_os)"

emit() {
    # Honour --quiet for the chatty per-plugin lines; the table always prints.
    if [ "$quiet" -eq 0 ]; then
        printf '%s\n' "$1"
    fi
}

emit "[setup] OS: ${OS_NAME}"
emit "[setup] repo root: ${REPO_ROOT}"
emit "[setup] initializing plugins: ${PLUGINS[*]}"
emit ""

# Per-plugin outcome accumulators (parallel arrays keyed by index).
RESULT_PLUGIN=()
RESULT_STATE=()
RESULT_DETAIL=()
hard_fail=0

# Map an init's status word to a normalized table state.
# A status line looks like: "[init:<plugin>] <STATE> — <detail>"
classify() {
    # $1 = full status line; echoes "<STATE>\t<detail>"
    local line="$1" body state detail
    # Strip the "[init:<plugin>] " prefix if present.
    body="${line#\[init:*\] }"
    # Split on the first " — " (em dash) separator.
    if [[ "$body" == *" — "* ]]; then
        state="${body%% — *}"
        detail="${body#* — }"
    else
        state="$body"
        detail=""
    fi
    printf '%s\t%s' "$state" "$detail"
}

for plugin in "${PLUGINS[@]}"; do
    init_sh="${PLUGINS_DIR}/${plugin}/scripts/init.sh"

    if [ ! -f "$init_sh" ]; then
        RESULT_PLUGIN+=("$plugin")
        RESULT_STATE+=("missing")
        RESULT_DETAIL+=("no scripts/init.sh in this plugin")
        emit "[setup] ${plugin}: no init.sh — skipping"
        continue
    fi

    # Run the init, capturing stdout and its exit code without aborting the loop.
    set +e
    output="$(bash "$init_sh" "${passthru[@]}" 2>&1)"
    rc=$?
    set -e

    # The contract guarantees exactly one "[init:<plugin>] <STATE> — ..." status
    # line; a plugin may also emit extra REMINDER lines. Grab the first status
    # line for the table, but echo the full output through when not quiet.
    if [ "$quiet" -eq 0 ] && [ -n "$output" ]; then
        printf '%s\n' "$output"
    fi

    status_line="$(printf '%s\n' "$output" | grep -m1 '^\[init:' || true)"
    if [ -z "$status_line" ]; then
        status_line="$(printf '%s\n' "$output" | head -1)"
    fi

    parsed="$(classify "$status_line")"
    state="${parsed%%$'\t'*}"
    detail="${parsed#*$'\t'}"

    RESULT_PLUGIN+=("$plugin")
    RESULT_STATE+=("$state")
    RESULT_DETAIL+=("$detail")

    if [ "$rc" -ne 0 ]; then
        hard_fail=1
    fi
done

# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------
emit ""
echo "================ marketplace setup summary ================"
printf '%-14s  %-18s  %s\n' "PLUGIN" "STATE" "DETAIL"
printf '%-14s  %-18s  %s\n' "------" "-----" "------"
for i in "${!RESULT_PLUGIN[@]}"; do
    # Keep details on one line; collapse any embedded newlines to spaces.
    detail_oneline="$(printf '%s' "${RESULT_DETAIL[$i]}" | tr '\n' ' ')"
    printf '%-14s  %-18s  %s\n' \
        "${RESULT_PLUGIN[$i]}" "${RESULT_STATE[$i]}" "${detail_oneline}"
done
echo "=========================================================="

if [ "$hard_fail" -ne 0 ]; then
    echo "[setup] FAILED — one or more plugin inits hard-failed (see table above)"
    exit 1
fi

echo "[setup] OK — all plugin inits succeeded or were already configured"
exit 0
