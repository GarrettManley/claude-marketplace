#!/usr/bin/env python3
"""Verify vendored hook-runtime files stay byte-identical to the canonical copies.

Canonical: plugins/discipline/scripts/{hook_flags.py,run_with_flags.py}.
Vendored consumers: learning, stewardship.

Plugins install as isolated per-version subtrees in the plugin cache, so a
repo-level shared lib can never ship with a plugin — the files are vendored
verbatim instead, and this gate fails on any divergence. The files are written
plugin-agnostic (env prefix derived from the hook id namespace), so byte
identity is achievable with no per-plugin patching.

Usage:
    python3 ci/check-vendored-sync.py          # check; exit 1 on drift
    python3 ci/check-vendored-sync.py --fix    # copy canonical over consumers
"""
from __future__ import annotations

import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANONICAL_PLUGIN = "discipline"
CONSUMER_PLUGINS = ("learning", "stewardship")
VENDORED_FILES = ("scripts/hook_flags.py", "scripts/run_with_flags.py")


def main(argv: list[str]) -> int:
    fix = "--fix" in argv
    drift: list[str] = []
    for rel in VENDORED_FILES:
        canonical = ROOT / "plugins" / CANONICAL_PLUGIN / rel
        if not canonical.is_file():
            print(f"check-vendored-sync: canonical missing: {canonical}", file=sys.stderr)
            return 1
        for consumer in CONSUMER_PLUGINS:
            target = ROOT / "plugins" / consumer / rel
            if target.is_file() and filecmp.cmp(canonical, target, shallow=False):
                continue
            if fix:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(canonical, target)
                print(f"check-vendored-sync: fixed plugins/{consumer}/{rel}")
            else:
                drift.append(f"plugins/{consumer}/{rel}")
    if drift:
        print(
            f"check-vendored-sync: DRIFT from canonical plugins/{CANONICAL_PLUGIN}/ in:"
        )
        for d in drift:
            print(f"  - {d}")
        print("Edit the canonical copy, then run: python3 ci/check-vendored-sync.py --fix")
        return 1
    print("check-vendored-sync: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
