#!/usr/bin/env bash
# Maintainer pre-merge gate. Run from the repo root before merging any PR.
# Exit 0 = clean. Exit non-zero = failures printed to stdout.
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)" || {
  echo "verify: cannot determine repo root" >&2
  exit 1
}
echo "[verify] lint-no-bare-python"
python3 "$ROOT/ci/lint-no-bare-python.py"
echo "[verify] OK"

echo "[verify] ruff"
if python3 -m ruff --version >/dev/null 2>&1; then
  python3 -m ruff check "$ROOT/ci" "$ROOT/plugins"
else
  echo "ruff not installed — run: python3 -m pip install -r requirements-dev.txt" >&2
  exit 1
fi
echo "[verify] OK"

echo "[verify] check-versions"
python3 "$ROOT/ci/check-versions.py" --check
echo "[verify] OK"

echo "[verify] validate-plugins"
python3 "$ROOT/ci/validate-plugins.py"
echo "[verify] OK"

echo "[verify] verify-hook-runtime-controls"
python3 "$ROOT/ci/verify_hook_runtime_controls.py"
echo "[verify] OK"

echo "[verify] check-vendored-sync"
python3 "$ROOT/ci/check-vendored-sync.py"
echo "[verify] OK"

echo "[verify] lint-frontmatter"
python3 "$ROOT/ci/lint-frontmatter.py"
echo "[verify] OK"

echo "[verify] gen-skill-index --check"
python3 "$ROOT/ci/gen-skill-index.py" --check
echo "[verify] OK"

echo "[verify] check-notice"
python3 "$ROOT/ci/check-notice.py"
echo "[verify] OK"

echo "[verify] check-doc-links"
python3 "$ROOT/ci/check-doc-links.py"
echo "[verify] OK"
