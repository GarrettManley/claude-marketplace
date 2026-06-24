#!/usr/bin/env bash
set -euo pipefail

# evidence/scripts/init.sh
# Generate the HMAC override key at ~/.claude/evidence-override-key if absent.
# The key is 64 hex chars (32 bytes) from a CSPRNG.  Permissions are set to
# 600 so only the owning user can read/write it.
#
# Usage: init.sh [--force] [--quiet]
#
# --force   Regenerate the key even if it already exists.
#           WARNING: this invalidates all outstanding HMAC tokens.
# --quiet   Suppress the status line (still exits 0 on success).

FORCE=0
QUIET=0

for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --quiet) QUIET=1 ;;
    *) ;;
  esac
done

KEY_PATH="${HOME}/.claude/evidence-override-key"
KEY_DIR="${HOME}/.claude"

# Already configured?
if [[ -f "${KEY_PATH}" && "${FORCE}" -eq 0 ]]; then
  if [[ "${QUIET}" -eq 0 ]]; then
    echo "[init:evidence] already configured — ${KEY_PATH} exists (use --force to regenerate; this invalidates outstanding tokens)"
  fi
  exit 0
fi

# Ensure ~/.claude/ directory exists.
mkdir -p "${KEY_DIR}"

# Generate 64 hex chars (32 bytes) from Python's CSPRNG.
# Python 3 is required; fall back with a clear error if absent.
if ! command -v python3 > /dev/null 2>&1; then
  echo "[init:evidence] FAILED — python3 not found; install Python 3 and retry"
  exit 1
fi

python3 -c "import secrets; print(secrets.token_hex(32), end='')" > "${KEY_PATH}"

# Restrict permissions: owner read/write only.
chmod 600 "${KEY_PATH}"

if [[ "${QUIET}" -eq 0 ]]; then
  echo "[init:evidence] CONFIGURED — wrote ${KEY_PATH} (chmod 600)"
fi
exit 0
