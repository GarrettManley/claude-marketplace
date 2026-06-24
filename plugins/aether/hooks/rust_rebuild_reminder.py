"""PostToolUse hook: remind to rebuild + retest the Rust core after edits to core/src/.

CLAUDE.md says "REQUIRED whenever you change anything under core/src — the
TS layer execs the compiled binary at core/target/release/core.exe." A
silent settings.local.json hook auto-rebuilds, but its stderr is discarded;
build failures vanish and a stale binary keeps shipping. This reminder
surfaces the invariant explicitly:

  1. Build status: was core.exe modified after the edited .rs file?
  2. Rerun guidance: integration tests + harness exec the binary, so a
     stale build silently fakes a green run.

Triggered after Edit/Write/MultiEdit to any file under core/src/. The repo root
(and thus the binary path for the staleness probe) is resolved via aether_repo
(nearest core/Cargo.toml ancestor), so the hook is checkout-location- and
directory-name-independent and no-ops outside an Aether repo. Exit 0 always —
never blocks the edit; the silent rebuild already runs. Purely informational,
mirroring gameplay_harness_reminder.py.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from aether_repo import edited_file_path, load_payload, repo_relative  # noqa: E402


BINARY_REL = "core/target/release/core.exe"


def main() -> int:
    payload = load_payload()
    raw = edited_file_path(payload) if payload is not None else None
    if not raw:
        return 0

    root, rel = repo_relative(raw)
    if rel is None or not rel.startswith("core/src/") or not rel.endswith(".rs"):
        return 0

    # Compute staleness: if binary mtime < edited file mtime, rebuild is
    # outstanding (or the silent auto-rebuild failed). Resolved against the
    # detected repo root, so this works wherever the checkout lives.
    stale_msg = ""
    try:
        src_mtime = (root / rel).stat().st_mtime
        binary = root / BINARY_REL
        bin_mtime = binary.stat().st_mtime if binary.exists() else 0
        if bin_mtime < src_mtime:
            delta = int(time.time() - src_mtime)
            stale_msg = (
                f" [STALE: {BINARY_REL} is older than {rel} "
                f"by ~{delta}s — silent auto-rebuild may have failed]"
            )
    except OSError:
        pass

    print(
        f"[rust-rebuild-reminder] {rel} changed{stale_msg}. "
        "TS layer execs core.exe; verify the rebuild succeeded "
        "(`cargo build --manifest-path core/Cargo.toml --release`) "
        "before running integration tests, the gameplay harness, "
        "or any Sage-call path. (CLAUDE.md: \"REQUIRED whenever you "
        "change anything under core/src\".)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
