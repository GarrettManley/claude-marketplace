#!/usr/bin/env python3
"""PostToolUse hook: surface area-specific pitfalls doc on edit.

Disabled by default - opt in by setting both `pitfalls-root` and
`pitfalls-routes` in .claude/discipline.local.md (or env vars).

When configured, on every Edit/Write/MultiEdit the hook checks if the
edited path matches one of the configured route keys. If it matches,
it prints a pointer line like:

    [pitfalls] you edited src/dm.ts; relevant pitfalls live in docs/pitfalls/dm-cycle.md

Routes config format (single line in the .local.md frontmatter):

    pitfalls-routes: src/dm.ts=dm-cycle; src/llm/=llm-classifier; core/src/=rust-core

Keys ending in `/` are prefix matches. Bare keys are exact matches.
First matching route wins; otherwise the hook is silent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from discipline_config import get_config, normalize_path_to_repo  # noqa: E402


def resolve_area(path: str, routes: dict) -> str | None:
    """Return the area slug for a normalized repo-relative path, or None.

    Exact matches win over prefix matches. Among prefix matches, the
    longest-match wins.
    """
    if path in routes:
        return routes[path]
    best_prefix = ""
    best_area = None
    for key, area in routes.items():
        if key.endswith("/") and path.startswith(key) and len(key) > len(best_prefix):
            best_prefix = key
            best_area = area
    return best_area


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    cfg = get_config()
    if not cfg.pitfalls_root or not cfg.pitfalls_routes:
        return 0

    raw = (
        data.get("tool_input", {}).get("file_path")
        or data.get("tool_response", {}).get("filePath")
        or ""
    )
    if not raw:
        return 0

    rel = normalize_path_to_repo(raw, cfg.repo_root)
    area = resolve_area(rel, cfg.pitfalls_routes)
    if area is None:
        return 0

    pitfalls_root = cfg.pitfalls_root.rstrip("/")
    print(
        f"[pitfalls] you edited {rel}; relevant pitfalls live in "
        f"{pitfalls_root}/{area}.md"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
