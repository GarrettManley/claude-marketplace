#!/usr/bin/env python3
"""Verify NOTICE exists whenever any in-tree file claims upstream adaptation.

The marketplace vendors code adapted from affaan-m/everything-claude-code under the
MIT License. Any file carrying the inline "Adapted from affaan-m" attribution obliges
us to ship a NOTICE that preserves the upstream copyright + license grant. This gate
fails the build if that obligation is unmet, so attribution and NOTICE can never
silently drift apart.

Run: python3 ci/check-notice.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRIGGER = "Adapted from affaan-m"
NOTICE = ROOT / "NOTICE"
REQUIRED_IN_NOTICE = ("Affaan Mustafa", "MIT License")


def triggering_files() -> list[str]:
    """Tracked files carrying the attribution phrase (NOTICE excluded so its own
    enumeration does not self-trigger). `git grep` exit 1 means no matches."""
    out = subprocess.run(
        # Exclude NOTICE (its own enumeration of the phrase) and this gate script
        # (its TRIGGER constant) so neither self-triggers the requirement.
        ["git", "-C", str(ROOT), "grep", "-l", TRIGGER, "--",
         ".", ":(exclude)NOTICE", ":(exclude)ci/check-notice.py"],
        capture_output=True,
        text=True,
    )
    if out.returncode not in (0, 1):
        # git grep exit 0 = matches, 1 = no matches; anything else is a failure —
        # exit >=2 (not a repo, bad pathspec) or a negative signal code from a
        # killed process (e.g. -9 SIGKILL on OOM/timeout). Treating any of these
        # as "no matches" would let the NOTICE gate silently pass on a git failure
        # (hb-duz), so fail loud.
        raise RuntimeError(
            f"git grep failed (exit {out.returncode}) while scanning "
            f"{ROOT} for upstream attribution: {out.stderr.strip()}"
        )
    return [line for line in out.stdout.splitlines() if line.strip()]


def main() -> int:
    files = triggering_files()
    if not files:
        print("check-notice: no upstream-attribution files; NOTICE not required.")
        return 0
    if not NOTICE.is_file() or not NOTICE.read_text(encoding="utf-8").strip():
        print(
            f"check-notice: {len(files)} file(s) say '{TRIGGER}' but NOTICE is missing "
            "or empty. Ship a NOTICE preserving the upstream MIT grant.",
            file=sys.stderr,
        )
        for f in files:
            print(f"  - {f}", file=sys.stderr)
        return 1
    text = NOTICE.read_text(encoding="utf-8")
    missing = [s for s in REQUIRED_IN_NOTICE if s not in text]
    if missing:
        print(
            "check-notice: NOTICE exists but is missing required upstream grant text: "
            f"{', '.join(missing)}.",
            file=sys.stderr,
        )
        return 1
    print(f"check-notice: clean ({len(files)} attributed file(s); NOTICE present).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
