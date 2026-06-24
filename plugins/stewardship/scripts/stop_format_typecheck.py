"""Stop hook: batch format + typecheck all files edited this response.

Reads the accumulator written by post_edit_accumulator.py, groups files
by language and project root, and dispatches:
  - typescript: npx prettier --write, then npx tsc --noEmit
  - python:     ruff format, then ruff check
  - rust:       cargo fmt, then cargo check

Non-blocking: tool failures go to stderr; the hook always exits 0.
Per-batch timeout is proportional to batch count so total < 270s.

Adapted from affaan-m/everything-claude-code @ 4774946d,
scripts/hooks/stop-format-typecheck.js (Biome/Prettier/tsc only).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from language_detect import detect_language, find_project_root  # noqa: E402
from post_edit_accumulator import get_accumulator_path  # noqa: E402

DEFAULT_TIMEOUT_S = int(os.environ.get("STEWARDSHIP_FORMAT_TIMEOUT_S", "90"))
TOTAL_BUDGET_S = 270  # Stop hook ceiling is 300s; leave 30s headroom


def group_files(paths: list[str]) -> list[dict[str, Any]]:
    """Group by (language, project_root). Files with no detected project root
    are skipped (silent — most language tools need a project root anyway).
    """
    groups: dict[tuple[str, Path], list[Path]] = {}
    for raw in paths:
        p = Path(raw).resolve()
        if not p.exists():
            continue
        lang = detect_language(p)
        if not lang:
            continue
        root = find_project_root(p, lang)
        if root is None:
            continue
        key = (lang, root)
        groups.setdefault(key, []).append(p)
    return [
        {"language": lang, "root": root, "files": files}
        for (lang, root), files in groups.items()
    ]


def build_commands_for(language: str, root: Path, files: list[Path]) -> list[dict[str, Any]]:
    """Build the subprocess commands for a single (language, root, files) group.

    Each command dict has: {"bin": str, "args": list[str], "cwd": Path,
    "shell": bool, "label": str}. shell=True is needed on Windows for .cmd shims.
    """
    cmds: list[dict[str, Any]] = []
    is_win = sys.platform == "win32"

    if language == "typescript":
        npx_bin = "npx.cmd" if is_win else "npx"
        file_args = [str(f) for f in files]
        cmds.append({
            "bin": npx_bin,
            "args": [npx_bin, "prettier", "--write", *file_args],
            "cwd": root,
            "shell": is_win,
            "label": "prettier",
        })
        # Only typecheck .ts/.tsx/.mts/.cts (not .js/.jsx)
        ts_files = [f for f in files if f.suffix.lower() in {".ts", ".tsx", ".mts", ".cts"}]
        if ts_files:
            cmds.append({
                "bin": npx_bin,
                "args": [npx_bin, "tsc", "--noEmit"],
                "cwd": root,
                "shell": is_win,
                "label": "tsc",
            })
    elif language == "python":
        file_args = [str(f) for f in files]
        cmds.append({
            "bin": "ruff",
            "args": ["ruff", "format", *file_args],
            "cwd": root,
            "shell": False,
            "label": "ruff format",
        })
        cmds.append({
            "bin": "ruff",
            "args": ["ruff", "check", *file_args],
            "cwd": root,
            "shell": False,
            "label": "ruff check",
        })
    elif language == "rust":
        cmds.append({
            "bin": "cargo",
            "args": ["cargo", "fmt"],
            "cwd": root,
            "shell": False,
            "label": "cargo fmt",
        })
        cmds.append({
            "bin": "cargo",
            "args": ["cargo", "check"],
            "cwd": root,
            "shell": False,
            "label": "cargo check",
        })
    return cmds


def _run_command(cmd: dict[str, Any], timeout_s: int) -> None:
    bin_ = cmd["bin"]
    if not shutil.which(bin_):
        return  # tool not on PATH — silent skip
    try:
        result = subprocess.run(
            cmd["args"],
            cwd=str(cmd["cwd"]),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            shell=cmd["shell"],
        )
    except (subprocess.TimeoutExpired, OSError):
        return
    if result.returncode != 0:
        sys.stderr.write(
            f"[stewardship:stop-format-typecheck] {cmd['label']} failed in {cmd['cwd']}:\n"
        )
        for line in (result.stdout + result.stderr).splitlines()[:20]:
            sys.stderr.write(line + "\n")


def main(argv: list[str] | None = None) -> int:
    accum_path = Path(get_accumulator_path())
    if not accum_path.exists():
        return 0
    try:
        raw = accum_path.read_text(encoding="utf-8")
    except OSError:
        return 0
    try:
        accum_path.unlink()
    except OSError:
        pass
    paths = list(dict.fromkeys(  # dedupe, preserve order
        line.strip() for line in raw.splitlines() if line.strip()
    ))
    if not paths:
        return 0
    groups = group_files(paths)
    if not groups:
        return 0

    # Total batches across all language groups
    total_cmds = sum(
        len(build_commands_for(g["language"], g["root"], g["files"]))
        for g in groups
    )
    per_cmd_timeout = (
        min(DEFAULT_TIMEOUT_S, TOTAL_BUDGET_S // max(total_cmds, 1))
        if total_cmds > 0
        else DEFAULT_TIMEOUT_S
    )

    test_skip = os.environ.get("STEWARDSHIP_TEST_NO_INVOKE") == "1"

    for g in groups:
        for cmd in build_commands_for(g["language"], g["root"], g["files"]):
            if test_skip:
                continue
            _run_command(cmd, per_cmd_timeout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
