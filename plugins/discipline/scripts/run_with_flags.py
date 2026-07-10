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

import inspect
import io
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Make the plugin's scripts/ importable so we can use hook_flags
sys.path.insert(0, str(Path(__file__).parent))
from hook_flags import is_hook_enabled  # noqa: E402

MAX_STDIN_BYTES = 1024 * 1024  # 1 MiB; bigger payloads get truncated

_MAX_HOOK_ERRORS = 200  # ring-buffer cap: a hook that fails every call can't grow the log unbounded


def _learning_data_root() -> Path:
    """Resolve the learning plugin's data root — a replica of
    stewardship/render_briefing.py's learning_data_root(). Replicated not
    imported: run_with_flags is vendored into every plugin and must stay
    self-contained. A test pins this equal to the render_briefing copy.
    """
    explicit = os.environ.get("LEARNING_DATA_ROOT")
    if explicit:
        return Path(explicit)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "claude-marketplace" / "learning"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "claude-marketplace" / "learning"
    return Path.home() / ".local" / "share" / "claude-marketplace" / "learning"


def _append_hook_error(hook_name: str, error: str) -> None:
    """Best-effort, bounded, atomic append of a swallowed hook error.

    Never raises (every path in this wrapper returns 0). Keeps the last
    _MAX_HOOK_ERRORS records so a hook failing on every invocation can't grow
    the file without bound. A lost record under concurrent appends is acceptable
    for telemetry; the tempfile + os.replace makes each write corruption-free.
    """
    try:
        root = _learning_data_root()
        root.mkdir(parents=True, exist_ok=True)
        log = root / "hooks-errors.jsonl"
        prior = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
        rec = json.dumps({"ts": time.time(), "hook": hook_name, "error": error})
        lines = prior[-(_MAX_HOOK_ERRORS - 1):] + [rec]
        fd, tmp = tempfile.mkstemp(dir=str(root), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, log)
    except Exception:  # noqa: BLE001 -- best-effort telemetry, never break the chain
        pass


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
    # Pass the real script path directly rather than reading its content into
    # `bash -c <text>`. The prior approach broke any script using
    # `dirname "${BASH_SOURCE[0]}"` for self-location (BASH_SOURCE is unset
    # under `bash -c`) -- confirmed live-broken for
    # plugins/discipline/hooks/inject_issues.sh. Git Bash (which _resolve_bash()
    # already prefers on Windows) handles a Windows-style path passed as the
    # script argument correctly -- confirmed empirically with a real
    # backslash-separated str(Path) value (not just a hand-typed forward-slash
    # path): dirname "${BASH_SOURCE[0]}" resolves correctly and the script's
    # own sibling-file lookup succeeds. On POSIX there was never a
    # path-translation concern to begin with.
    result = subprocess.run(
        [_resolve_bash(), str(script_path)],
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
        _append_hook_error(script_path.name, f"import error: {e}")
        print(f"run_with_flags: import error in {script_path.name}: {e}", file=sys.stderr)
        return 0  # don't break the chain

    main_fn = getattr(module, "main", None)
    if not callable(main_fn):
        # No main(); module top-level already ran (and didn't exit). Treat as success.
        return 0
    # Detect the calling convention BEFORE invoking -- some currently-wrapped hooks
    # (todo_issue_hook.py, memory_tracker_check.py, frontmatter_lint.py,
    # pitfalls_pointer.py, spec_companion_check.py) use bare `def main():` with no
    # parameters; others (plan_completion_check.py and the standard idiom generally)
    # use `def main(argv: list[str] | None = None)`. Calling the latter with zero
    # args leaks this process's own sys.argv (hook_script_path, hook_id,
    # profile_csv) into the hook when it falls back from argv=None -- calling the
    # former with one arg raises TypeError. Checking parameter *kind* (not just
    # whether any parameters exist) avoids misclassifying a keyword-only-only
    # signature (e.g. `def main(*, flag=None)`) as argv-taking, which would
    # otherwise raise TypeError on `main_fn([])`. Introspection failure of any
    # kind (e.g. a C-extension callable) falls back to the zero-arg call,
    # matching prior behavior. This check is intentionally OUTSIDE the
    # try/except below: a genuine runtime error raised by the hook's own body
    # during the real call must never be reinterpreted as a signature
    # mismatch and retried -- double-invoking a hook with side effects would
    # be silent data corruption.
    _ARGV_PARAM_KINDS = (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.VAR_POSITIONAL,
    )
    try:
        takes_argv = any(
            p.kind in _ARGV_PARAM_KINDS
            for p in inspect.signature(main_fn).parameters.values()
        )
    except Exception:
        takes_argv = False
    try:
        result = main_fn([]) if takes_argv else main_fn()
        return int(result) if result is not None else 0
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0
    except Exception as e:  # noqa: BLE001
        _append_hook_error(script_path.name, f"runtime error: {e}")
        print(f"run_with_flags: runtime error in {script_path.name}: {e}", file=sys.stderr)
        return 0  # don't break the chain


if __name__ == "__main__":
    sys.exit(main(sys.argv))
