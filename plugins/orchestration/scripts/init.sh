#!/usr/bin/env bash
# init.sh — orchestration plugin initializer
# Sets up ~/.claude/context/tiers.local.json and ~/.claude/context/hardware-profile.md
# from the plugin's shipped templates when those files are absent.
#
# Usage:
#   ./init.sh            # idempotent: no-op if already configured
#   ./init.sh --force    # overwrite existing files with fresh templates
#   ./init.sh --quiet    # suppress the status line
set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTEXT_DIR="${HOME}/.claude/context"

force=0
quiet=0
for arg in "$@"; do
    case "$arg" in
        --force)  force=1 ;;
        --quiet)  quiet=1 ;;
        *)
            echo "[init:orchestration] FAILED — unknown argument: $arg" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
status_line() {
    # $1 = verb  $2 = detail
    if [ "$quiet" -eq 0 ]; then
        echo "[init:orchestration] $1 — $2"
    fi
}

note() {
    # $1 = full line — quiet-gated supplementary output (post-init reminders)
    if [ "$quiet" -eq 0 ]; then
        echo "$1"
    fi
}

copy_if_absent() {
    # $1 = source  $2 = dest  $3 = label
    local src="$1" dest="$2" label="$3"
    if [ -f "$dest" ] && [ "$force" -eq 0 ]; then
        echo "already configured:$label"   # caller reads this
        return 0
    fi
    cp "$src" "$dest"
    echo "configured:$label"
}

# ---------------------------------------------------------------------------
# Ensure context dir exists
# ---------------------------------------------------------------------------
mkdir -p "$CONTEXT_DIR"

# ---------------------------------------------------------------------------
# (1) tiers.local.json
# ---------------------------------------------------------------------------
TIERS_SRC="${PLUGIN_DIR}/configs/tiers.json"
TIERS_DEST="${CONTEXT_DIR}/tiers.local.json"

if [ ! -f "$TIERS_SRC" ]; then
    status_line "FAILED" "source not found: ${TIERS_SRC}"
    exit 1
fi

tiers_result="$(copy_if_absent "$TIERS_SRC" "$TIERS_DEST" "tiers.local.json")"

# ---------------------------------------------------------------------------
# (2) hardware-profile.md
# ---------------------------------------------------------------------------
PROFILE_TEMPLATE="${PLUGIN_DIR}/context/hardware-profile.template.md"
PROFILE_DEST="${CONTEXT_DIR}/hardware-profile.md"

if [ ! -f "$PROFILE_TEMPLATE" ]; then
    status_line "FAILED" "template not found: ${PROFILE_TEMPLATE}"
    exit 1
fi

profile_result="$(copy_if_absent "$PROFILE_TEMPLATE" "$PROFILE_DEST" "hardware-profile.md")"

# ---------------------------------------------------------------------------
# Compose status line
# ---------------------------------------------------------------------------
configured_list=()
already_list=()

for result in "$tiers_result" "$profile_result"; do
    label="${result#*:}"
    case "$result" in
        configured:*)      configured_list+=("$label") ;;
        already\ configured:*) already_list+=("$label") ;;
    esac
done

if [ ${#configured_list[@]} -gt 0 ] && [ ${#already_list[@]} -eq 0 ]; then
    detail="created: $(IFS=', '; echo "${configured_list[*]}")"
    status_line "CONFIGURED" "$detail"
    note "[init:orchestration] REMINDER: edit ~/.claude/context/tiers.local.json — fill in <path-to>/llama-server.exe, <path-to-models>/, <GPU model>, and <N> GB VRAM ceiling."
    note "[init:orchestration] REMINDER: edit ~/.claude/context/hardware-profile.md — replace all <placeholder> values with your real hardware details."
elif [ ${#configured_list[@]} -eq 0 ] && [ ${#already_list[@]} -gt 0 ]; then
    detail="$(IFS=', '; echo "${already_list[*]}")"
    status_line "already configured" "$detail"
else
    # mixed: some created, some already existed
    detail=""
    if [ ${#configured_list[@]} -gt 0 ]; then
        detail="created: $(IFS=', '; echo "${configured_list[*]}")"
    fi
    if [ ${#already_list[@]} -gt 0 ]; then
        [ -n "$detail" ] && detail="$detail; "
        detail="${detail}already configured: $(IFS=', '; echo "${already_list[*]}")"
    fi
    status_line "CONFIGURED" "$detail"
    if printf '%s\n' "${configured_list[@]}" | grep -q "tiers.local.json"; then
        note "[init:orchestration] REMINDER: edit ~/.claude/context/tiers.local.json — fill in <path-to>/llama-server.exe, <path-to-models>/, <GPU model>, and <N> GB VRAM ceiling."
    fi
    if printf '%s\n' "${configured_list[@]}" | grep -q "hardware-profile.md"; then
        note "[init:orchestration] REMINDER: edit ~/.claude/context/hardware-profile.md — replace all <placeholder> values with your real hardware details."
    fi
fi

exit 0
