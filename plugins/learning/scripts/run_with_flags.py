#!/usr/bin/env python3
# vendored: plugins/<plugin>/scripts/run_with_flags.py — canonical copy lives in
# plugins/discipline/scripts/; ci/check-vendored-sync.py keeps all copies byte-identical.
"""Wrapper that gates plugin hooks via profile + disable-list.

Usage:
    python3 run_with_flags.py <hook_script> <hook_id> <profile_csv>

Reads stdin once (capped at 1 MiB). If the hook is disabled, exits 0 without
producing stdout (preserves the hook chain without leaking event JSON into
SessionStart additionalContext). Otherwise, imports
the hook module via importlib and calls its main() with stdin restored -- no
second python3 cold-start.

Shell scripts (.sh, .bash) are invoked via subprocess.run since they can't
be importlib'd; the double-spawn cost is acceptable for SessionStart hooks.

Adapted from affaan-m/everything-claude-code @ 4774946d, scripts/hooks/run-with-flags.js.
"""
from __future__ import annotations

import io
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Make the plugin's scripts/ importable so we can use hook_flags
sys.path.insert(0, str(Path(__file__).parent))
from hook_flags import is_hook_enabled  # noqa: E402

MAX_STDIN_BYTES = 1024 * 1024  # 1 MiB; bigger payloads get truncated


def _read_stdin() -> str:
    """Read up to MAX_STDIN_BYTES from stdin. Truncates silently."""
    raw = sys.stdin.read(MAX_STDIN_BYTES)
    return raw


def _passthrough(stdin_text: str) -> int:  # noqa: ARG001
    """Exit cleanly without producing stdout. Hook chain continues.

    Why suppress stdout: Claude Code's SessionStart hooks treat stdout as
    additionalContext that gets injected into the session. Echoing the raw
    event JSON when a hook is disabled would silently leak `session_id`,
    `transcript_path`, etc. into the model's context. Other event types
    (PreToolUse/PostToolUse) don't use stdout for context, so suppressing
    it costs nothing there either.

    The stdin_text parameter is retained so call sites read uniform — kept
    explicit rather than removed so callers don't accidentally start using
    a different no-op pattern.
    """
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(
            "usage: run_with_flags.py <hook_script> <hook_id> <profile_csv>",
            file=sys.stderr,
        )
        return 2

    hook_script = argv[1]
    hook_id = argv[2]
    profile_csv = argv[3]

    stdin_text = _read_stdin()

    if not is_hook_enabled(hook_id, profile_csv):
        return _passthrough(stdin_text)

    # Hook is enabled -- invoke it.
    script_path = Path(hook_script)
    if not script_path.is_file():
        # Don't break the hook chain on misconfiguration
        print(
            f"run_with_flags: hook script not found: {hook_script}",
            file=sys.stderr,
        )
        return _passthrough(stdin_text)

    suffix = script_path.suffix.lower()
    if suffix in {".sh", ".bash", ".zsh"}:
        # Shell scripts: spawn (can't importlib)
        return _spawn_shell(script_path, stdin_text)
    if suffix == ".py":
        return _import_and_run_python(script_path, stdin_text)
    # Unknown: try shelling out as a last resort
    return _spawn_generic(script_path, stdin_text)


def _resolve_bash() -> str:
    """Resolve a POSIX bash interpreter.

    On Windows a bare ``bash`` frequently resolves to ``C:\\Windows\\System32\\bash.exe``
    -- the WSL launcher -- which on a machine with no WSL distro installed prints a
    UTF-16 "...to install" stub and exits non-zero (it never runs the script). Prefer
    Git Bash there; fall back to PATH lookup on POSIX.
    """
    if os.name == "nt":
        for candidate in (
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files\Git\usr\bin\bash.exe",
        ):
            if Path(candidate).is_file():
                return candidate
    return shutil.which("bash") or "bash"


def _spawn_shell(script_path: Path, stdin_text: str) -> int:
    # Passing a Windows path as a bash argument fails on Windows regardless of
    # whether bash resolves to Git Bash (MSYS mangles the path) or WSL bash
    # (path is inaccessible from the Linux side).  Reading the script content
    # and using `bash -c` avoids the argument entirely.  This is safe for the
    # gated shell hooks because none uses $0/BASH_SOURCE/dirname "$0" --
    # they resolve directories via `git rev-parse --show-toplevel`.
    try:
        script_content = script_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        print(f"run_with_flags: cannot read shell script {script_path.name}: {e}", file=sys.stderr)
        return _passthrough(stdin_text)
    result = subprocess.run(
        [_resolve_bash(), "-c", script_content],
        input=stdin_text,
        capture_output=True,
        text=True,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


def _spawn_generic(script_path: Path, stdin_text: str) -> int:
    result = subprocess.run(
        [str(script_path)],
        input=stdin_text,
        capture_output=True,
        text=True,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


def _import_and_run_python(script_path: Path, stdin_text: str) -> int:
    """Import the hook module and call main(). Falls back to subprocess if no main()."""
    # Restore stdin so the imported main() can read it
    sys.stdin = io.StringIO(stdin_text)

    module_name = f"_plugin_hook_{script_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        return _passthrough(stdin_text)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except SystemExit as e:
        # Hook called sys.exit() at module top level (legacy style)
        return int(e.code) if e.code is not None else 0
    except Exception as e:  # noqa: BLE001
        print(f"run_with_flags: import error in {script_path.name}: {e}", file=sys.stderr)
        return 0  # don't break the chain

    main_fn = getattr(module, "main", None)
    if not callable(main_fn):
        # No main(); module top-level already ran (and didn't exit). Treat as success.
        return 0
    try:
        result = main_fn()
        return int(result) if result is not None else 0
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0
    except Exception as e:  # noqa: BLE001
        print(f"run_with_flags: runtime error in {script_path.name}: {e}", file=sys.stderr)
        return 0  # don't break the chain


if __name__ == "__main__":
    sys.exit(main(sys.argv))
