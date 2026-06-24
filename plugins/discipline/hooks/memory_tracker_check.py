#!/usr/bin/env python3
"""PostToolUse hook: nudge auto-memory `type: project` files to cite a tracker id.

Runs after Write/Edit/MultiEdit. When the touched file is an auto-memory file
(under `.../.claude/projects/<slug>/memory/<file>.md`, excluding the `MEMORY.md`
index) whose frontmatter declares `type: project`, it must cite a tracker id —
a beads id (e.g. `hb-9yw.6`, `bd-abc1`) or a GitHub issue (`#N`) — so status
lives in the tracker, not duplicated as prose that drifts. See the auto-memory
convention in the home-root `CLAUDE.md`.

This is a **warning**, never a block: memory writes are routine and must not be
interrupted. A non-conforming write succeeds and emits a `systemMessage` nudge.

Scope is matched on the raw file path (not the git-repo-relative path), so the
check still fires when memory is authored while the cwd is some *other* repo —
`normalize_path_to_repo` keys off the repo root detected at fire time and would
otherwise miss. The relative path is computed only for the message text.

Gating: enabled in the `standard`/`strict` profiles via run_with_flags; disable
with `DISCIPLINE_DISABLED_HOOKS=discipline:post-edit:memory-tracker-check`.
The tracker-id regex honours `bd-id-pattern` / `DISCIPLINE_BD_ID_PATTERN`.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from discipline_config import get_config, normalize_path_to_repo  # noqa: E402

# Auto-memory file: `.../.claude/projects/<slug>/memory/<file>.md`. Matched with
# .search() against the POSIX-normalised raw path, so it works whether the path
# is repo-relative or absolute.
MEMORY_PATH_RE = re.compile(r"(?:^|/)\.claude/projects/[^/]+/memory/[^/]+\.md$")

# `type: project` on its own frontmatter line (top-level or nested under
# `metadata:`). Line-anchored with [ \t]* (not \s*, which would span newlines)
# so `node_type:` and body prose can't trip it; the value is end-anchored and
# quote-tolerant so `type: "project"` matches but `type: project-management`
# / `type: projects` do not.
TYPE_PROJECT_RE = re.compile(r"""(?m)^[ \t]*type:[ \t]*["']?project["']?[ \t]*$""")


def emit_warn(message: str) -> None:
    print(json.dumps({"systemMessage": message}))
    sys.exit(0)


def frontmatter_block(text: str) -> str | None:
    """Return the text between the opening `---` (line 1) and its closing `---`.

    None when the file has no frontmatter (no `---` on line 1, or no close
    within the first 60 lines). Mirrors the 60-line bound used elsewhere.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, min(len(lines), 60)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i])
    return None


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    raw = (
        data.get("tool_input", {}).get("file_path")
        or data.get("tool_response", {}).get("filePath")
        or ""
    )
    if not raw:
        sys.exit(0)

    posix = raw.replace("\\", "/")
    if not MEMORY_PATH_RE.search(posix):
        sys.exit(0)
    if posix.rsplit("/", 1)[-1] == "MEMORY.md":
        # The index is curated separately; it is not a typed memory file.
        sys.exit(0)

    try:
        # utf-8-sig strips an optional BOM (harmless when absent); without it a
        # BOM would make line 1 != '---' and silently disable the whole check.
        text = Path(raw).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        sys.exit(0)

    block = frontmatter_block(text)
    if block is None or not TYPE_PROJECT_RE.search(block):
        sys.exit(0)

    cfg = get_config()
    # GitHub `#N` (boundary-anchored so hex colors like `#1a2b3c`, anchor links,
    # and `##` headings don't masquerade as a citation) OR a beads id.
    if re.search(r"(?<![\w#])#\d+\b", text) or re.search(cfg.bd_id_pattern, text):
        sys.exit(0)

    rel = normalize_path_to_repo(raw, cfg.repo_root)
    emit_warn(
        f"memory_tracker_check: {rel} is type:project but cites no tracker id. "
        "Open it with a `Tracker:` line citing a beads id (e.g. `hb-9yw.6`) or a "
        "GitHub issue (`#N`) instead of duplicating status prose. See the "
        "auto-memory convention in CLAUDE.md."
    )


if __name__ == "__main__":
    main()
