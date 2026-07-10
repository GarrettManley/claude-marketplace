"""Integration tests for run_with_flags.py wrapper."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

WRAPPER = Path(__file__).parent.parent / "scripts" / "run_with_flags.py"


def run_wrapper(args: list[str], stdin: str, env_overrides: dict[str, str] | None = None,
                encoding: str | None = None):
    """Invoke run_with_flags.py as a subprocess. Returns CompletedProcess.

    `encoding` pins how the child's stdout/stderr are decoded on the parent side.
    Default (None) uses text mode with the parent locale, matching every existing
    test. The cp1252 UTF-8-defense tests pass encoding="utf-8" so the child's
    post-fix UTF-8 bytes aren't mojibaked by a cp1252 parent (Windows default).
    """
    env = {**os.environ}
    # Strip pre-existing DISCIPLINE_ vars so tests are deterministic
    for k in list(env):
        if k.startswith("DISCIPLINE_"):
            del env[k]
    if env_overrides:
        env.update(env_overrides)
    kwargs: dict = dict(input=stdin, capture_output=True, env=env, timeout=10)
    if encoding:
        kwargs.update(encoding=encoding, errors="replace")
    else:
        kwargs["text"] = True
    return subprocess.run(["python3", str(WRAPPER), *args], **kwargs)


@pytest.fixture(autouse=True)
def _isolate_hook_error_log(monkeypatch, tmp_path):
    # run_with_flags appends hook errors under LEARNING_DATA_ROOT; keep every
    # test in this file (all invoke the wrapper) off the developer's real log.
    monkeypatch.setenv("LEARNING_DATA_ROOT", str(tmp_path / "learning-data"))


class TestPassthroughWhenDisabled:
    def test_disabled_hook_produces_no_stdout(self, tmp_path):
        # The wrapper should never invoke the inner script when disabled
        # AND must not echo stdin (would inject raw event JSON into SessionStart context)
        bogus_hook = tmp_path / "should_not_run.py"
        bogus_hook.write_text("import sys; sys.exit(99)")  # would fail loudly if invoked
        result = run_wrapper(
            [str(bogus_hook), "discipline:test:foo", "standard"],
            stdin='{"tool_name":"Edit"}',
            env_overrides={"DISCIPLINE_DISABLED_HOOKS": "discipline:test:foo"},
        )
        assert result.returncode == 0
        assert result.stdout == ""

    def test_profile_excluded_hook_produces_no_stdout(self, tmp_path):
        bogus_hook = tmp_path / "should_not_run.py"
        bogus_hook.write_text("import sys; sys.exit(99)")
        result = run_wrapper(
            [str(bogus_hook), "discipline:test:foo", "strict"],
            stdin='{"x":1}',
            env_overrides={"DISCIPLINE_HOOK_PROFILE": "minimal"},
        )
        assert result.returncode == 0
        assert result.stdout == ""


class TestInvokeWhenEnabled:
    def test_python_hook_main_called_with_stdin(self, tmp_path):
        hook = tmp_path / "echo_hook.py"
        hook.write_text(
            "import json, sys\n"
            "def main():\n"
            "    payload = json.load(sys.stdin)\n"
            "    print('saw:' + payload['tool_name'])\n"
            "    return 0\n"
            "if __name__ == '__main__':\n"
            "    sys.exit(main())\n"
        )
        result = run_wrapper(
            [str(hook), "discipline:test:echo", "standard"],
            stdin='{"tool_name":"Write"}',
        )
        assert result.returncode == 0
        assert "saw:Write" in result.stdout

    def test_python_hook_exit_code_propagated(self, tmp_path):
        hook = tmp_path / "blocking_hook.py"
        hook.write_text(
            "def main():\n"
            "    return 2\n"
            "import sys\n"
            "if __name__ == '__main__':\n"
            "    sys.exit(main())\n"
        )
        result = run_wrapper(
            [str(hook), "discipline:test:blocker", "standard"],
            stdin="{}",
        )
        assert result.returncode == 2

    def test_missing_script_does_not_break_chain(self, tmp_path):
        result = run_wrapper(
            [str(tmp_path / "no-such-file.py"), "discipline:test:ghost", "standard"],
            stdin='{"x":1}',
        )
        assert result.returncode == 0
        assert result.stdout == ""
        assert "not found" in result.stderr

    def test_shell_hook_invoked_via_subprocess(self, tmp_path):
        hook = tmp_path / "echo_hook.sh"
        hook.write_text("#!/usr/bin/env bash\ncat\necho 'shell-saw-stdin'\n")
        hook.chmod(0o755)
        result = run_wrapper(
            [str(hook), "discipline:test:shell", "standard"],
            stdin="payload-text",
        )
        assert result.returncode == 0
        assert "shell-saw-stdin" in result.stdout

    def test_python_hook_runtime_error_does_not_break_chain(self, tmp_path):
        hook = tmp_path / "broken_hook.py"
        hook.write_text("def main():\n    raise ValueError('boom')\n")
        result = run_wrapper(
            [str(hook), "discipline:test:broken", "standard"],
            stdin="{}",
        )
        # Errors swallowed so subsequent hooks still fire
        assert result.returncode == 0
        assert "runtime error" in result.stderr

    def test_python_hook_runtime_error_never_double_invokes(self, tmp_path):
        """Regression guard for the argv-detection fix's most important correctness
        property: the inspect.signature() check must never cause a hook's real
        runtime error to be reinterpreted as a signature mismatch and retried.
        Uses a counter file (not just a stderr substring, which a duplicated log
        line would still satisfy) so a future refactor that merges the two try
        blocks or adds a TypeError-based retry actually fails this test. Covers
        both calling conventions -- bare def main() and def main(argv=None) --
        since a regression could plausibly affect only one path."""
        counter = tmp_path / "counter.txt"
        counter.write_text("0", encoding="utf-8")

        bare_hook = tmp_path / "bare_broken_hook.py"
        bare_hook.write_text(
            f"from pathlib import Path\n"
            f"COUNTER = Path(r'{counter}')\n"
            "def main():\n"
            "    COUNTER.write_text(str(int(COUNTER.read_text()) + 1))\n"
            "    raise ValueError('boom')\n"
        )
        result = run_wrapper(
            [str(bare_hook), "discipline:test:bare-broken", "standard"],
            stdin="{}",
        )
        assert result.returncode == 0
        assert "runtime error" in result.stderr
        assert counter.read_text() == "1", "bare def main() was invoked more than once"

        counter.write_text("0", encoding="utf-8")
        argv_hook = tmp_path / "argv_broken_hook.py"
        argv_hook.write_text(
            f"from pathlib import Path\n"
            f"COUNTER = Path(r'{counter}')\n"
            "def main(argv=None):\n"
            "    COUNTER.write_text(str(int(COUNTER.read_text()) + 1))\n"
            "    raise ValueError('boom')\n"
        )
        result = run_wrapper(
            [str(argv_hook), "discipline:test:argv-broken", "standard"],
            stdin="{}",
        )
        assert result.returncode == 0
        assert "runtime error" in result.stderr
        assert counter.read_text() == "1", "def main(argv=None) was invoked more than once"

    def test_shell_hook_bash_source_self_location_works(self, tmp_path):
        """Regression: a real-world pattern (dirname "${BASH_SOURCE[0]}" to locate a
        sibling file) must survive being wrapped. The existing
        test_shell_hook_invoked_via_subprocess fixture doesn't reference BASH_SOURCE at
        all, which is exactly why this class of bug went uncaught (see
        plugins/discipline/hooks/inject_issues.sh:27 for the real pattern this mirrors)."""
        sibling = tmp_path / "sibling.txt"
        sibling.write_text("sibling-content")
        hook = tmp_path / "self_locating_hook.sh"
        hook.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
            'cat "$dir/sibling.txt"\n'
        )
        hook.chmod(0o755)
        result = run_wrapper(
            [str(hook), "discipline:test:self-locating", "standard"],
            stdin="",
        )
        assert result.returncode == 0, result.stderr
        assert "sibling-content" in result.stdout

    def test_python_hook_receives_empty_argv_not_wrapper_own_argv(self, tmp_path):
        """Regression: a hook using the standard `main(argv: list[str] | None = None)`
        idiom, falling back to sys.argv[1:] when argv is None, must see an empty list --
        not run_with_flags.py's own process argv (hook_script_path, hook_id,
        profile_csv). Mirrors the real pattern in
        plugins/retrospective/hooks/plan_completion_check.py:300-312, which would
        misinterpret its own script path as a CLI positional argument if this broke."""
        hook = tmp_path / "argv_fallback_hook.py"
        hook.write_text(
            "import sys\n"
            "def main(argv=None):\n"
            "    args = sys.argv[1:] if argv is None else argv\n"
            "    print('argv-was:' + repr(args))\n"
            "    return 0\n"
        )
        result = run_wrapper(
            [str(hook), "discipline:test:argv-fallback", "standard"],
            stdin="{}",
        )
        assert result.returncode == 0
        assert "argv-was:[]" in result.stdout

    def test_python_hook_zero_param_main_still_works(self, tmp_path):
        """Regression: real, currently-wrapped discipline hooks (todo_issue_hook.py,
        memory_tracker_check.py, frontmatter_lint.py, pitfalls_pointer.py,
        spec_companion_check.py) use bare `def main():` with no parameters at all --
        the fix for the argv-leak bug above must not break these. This mirrors the
        pre-existing test_python_hook_main_called_with_stdin/
        test_python_hook_exit_code_propagated fixtures but asserts explicitly on the
        zero-param case so a regression here fails with a clear name, not just
        collateral failures in unrelated tests."""
        hook = tmp_path / "zero_param_hook.py"
        hook.write_text(
            "def main():\n"
            "    print('zero-param-ran')\n"
            "    return 0\n"
        )
        result = run_wrapper(
            [str(hook), "discipline:test:zero-param", "standard"],
            stdin="{}",
        )
        assert result.returncode == 0
        assert "zero-param-ran" in result.stdout


class TestHookErrorLog:
    """hb-rap: run_with_flags persists swallowed hook errors to a bounded log."""

    def _load_module(self):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("_rwf_probe", WRAPPER)
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_runtime_error_appended_to_hook_error_log(self, tmp_path):
        import json as _json
        hook = tmp_path / "boom.py"
        hook.write_text("def main():\n    raise ValueError('kaboom')\n")
        result = run_wrapper([str(hook), "id", "standard"], stdin="{}")
        assert result.returncode == 0
        assert "runtime error" in result.stderr
        log = self._load_module()._learning_data_root() / "hooks-errors.jsonl"
        rec = _json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
        assert rec["hook"] == "boom.py"
        assert "kaboom" in rec["error"]

    def test_hook_error_log_append_is_bounded(self, tmp_path):
        rwf = self._load_module()
        for i in range(rwf._MAX_HOOK_ERRORS + 50):
            rwf._append_hook_error("h.py", f"e{i}")
        log = rwf._learning_data_root() / "hooks-errors.jsonl"
        lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == rwf._MAX_HOOK_ERRORS

    def test_hook_error_log_write_failure_never_breaks_chain(self, tmp_path):
        hook = tmp_path / "boom2.py"
        hook.write_text("def main():\n    raise ValueError('x')\n")
        blocker = tmp_path / "blocker"
        blocker.write_text("i am a file, not a dir")
        result = run_wrapper(
            [str(hook), "id", "standard"], stdin="{}",
            env_overrides={"LEARNING_DATA_ROOT": str(blocker / "sub")},
        )
        assert result.returncode == 0


class TestUtf8Defense:
    """hb-zxg: the wrapper reconfigures stdio to UTF-8 before importing/running a
    hook, so a wrapped hook's non-ASCII stdout can't crash on a cp1252 console
    (the surface.py `->` class of bug). The crash class is stdout (strict cp1252),
    not stderr (which uses backslashreplace and never raises).
    """

    def _load_module(self):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("_rwf_utf8_probe", WRAPPER)
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_nonascii_hook_stdout_survives_cp1252(self, tmp_path):
        """Reproduction of the surface.py crash class. The hook prints U+2192 (not
        encodable in cp1252) to stdout. Under a cp1252 stdout (PYTHONIOENCODING),
        pre-fix the print raises UnicodeEncodeError inside the hook's main(), which
        the wrapper swallows -> the arrow never reaches stdout. Post-fix, _force_utf8
        reconfigures stdout to UTF-8 first, so the print succeeds and the arrow is
        emitted. The discriminating signal is arrow-in-stdout, NOT the exit code
        (the wrapper returns 0 either way)."""
        hook = tmp_path / "arrow_hook.py"
        hook.write_text(
            "def main():\n"
            "    print('arrow:\\u2192')\n"
            "    return 0\n",
            encoding="utf-8",
        )
        result = run_wrapper(
            [str(hook), "discipline:test:arrow", "standard"],
            stdin="{}",
            env_overrides={"PYTHONIOENCODING": "cp1252"},
            encoding="utf-8",
        )
        assert result.returncode == 0
        assert "arrow:→" in result.stdout, (
            "post-fix the wrapper must reconfigure stdout to UTF-8 so the hook's "
            f"arrow reaches stdout; got stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        # And the crash must not have been swallowed as a runtime error.
        assert "runtime error" not in result.stderr

    def test_lone_surrogate_hook_error_does_not_break_chain(self, tmp_path):
        """Regression for the errors-handler reset: reconfigure(encoding=...) alone
        resets stderr from backslashreplace to strict, so a hook error message
        carrying a lone surrogate would crash the swallow-site stderr print and exit
        non-zero -- breaking the hook chain. _force_utf8 must preserve backslashreplace
        so this stays exit 0. Uses default (non-cp1252) streams: stderr starts as
        backslashreplace, and a bare reconfigure would flip it to strict."""
        hook = tmp_path / "surrogate_hook.py"
        # The file content is ASCII (`\udcff` literal); the hook parses it to a lone
        # surrogate at runtime and raises it in the exception message.
        hook.write_text(
            "def main():\n"
            "    raise ValueError('bad-\\udcff-name')\n",
            encoding="utf-8",
        )
        result = run_wrapper(
            [str(hook), "discipline:test:surrogate", "standard"],
            stdin="{}",
        )
        assert result.returncode == 0, (
            "a lone-surrogate hook error must not crash the wrapper's stderr print; "
            f"stderr={result.stderr!r}"
        )

    def test_shell_hook_nonascii_utf8_stdout_survives(self, tmp_path):
        """The spawn path must decode child output as UTF-8, not the cp1252 locale.
        A shell hook emitting U+0410 (UTF-8 bytes D0 90; 0x90 is unmapped in cp1252)
        pre-fix crashed subprocess's reader thread -> result.stdout None -> TypeError
        -> exit 1, unlogged. Post-fix it decodes cleanly."""
        hook = tmp_path / "cyrillic_hook.sh"
        # printf raw UTF-8 bytes for U+0410 so the test doesn't depend on the shell's
        # own locale for encoding the source.
        hook.write_text("#!/usr/bin/env bash\nprintf 'cyr:\\xd0\\x90\\n'\n")
        hook.chmod(0o755)
        result = run_wrapper(
            [str(hook), "discipline:test:cyr", "standard"],
            stdin="",
            encoding="utf-8",
        )
        assert result.returncode == 0, result.stderr
        assert "cyr:А" in result.stdout

    def test_force_utf8_reconfigures_encoding_and_preserves_errors(self, monkeypatch):
        """Success path: a real cp1252 stream is flipped to UTF-8 and its error
        handler is PRESERVED. Preserving backslashreplace is exactly what keeps the
        swallow-site stderr prints unraisable; a bare reconfigure(encoding=...) resets
        errors to strict (CPython), which the lone-surrogate test above would fail."""
        import io as _io
        rwf = self._load_module()
        w = _io.TextIOWrapper(_io.BytesIO(), encoding="cp1252", errors="backslashreplace")
        monkeypatch.setattr(sys, "stdout", w)
        monkeypatch.setattr(sys, "stderr", _io.StringIO())
        monkeypatch.setattr(sys, "stdin", _io.StringIO())
        rwf._force_utf8()
        assert w.encoding == "utf-8"
        assert w.errors == "backslashreplace"

    def test_force_utf8_is_noop_when_unreconfigurable(self, monkeypatch):
        """Must never raise when a stream can't reconfigure. Covers the AttributeError
        arm (StringIO has no reconfigure) and the ValueError arm (a closed stream)."""
        import io as _io
        rwf = self._load_module()
        closed = _io.TextIOWrapper(_io.BytesIO(), encoding="cp1252")
        closed.close()  # reconfigure on a closed stream raises ValueError
        monkeypatch.setattr(sys, "stdout", _io.StringIO())      # AttributeError arm
        monkeypatch.setattr(sys, "stderr", closed)              # ValueError arm
        monkeypatch.setattr(sys, "stdin", _io.StringIO())
        rwf._force_utf8()  # no assertion needed: the test is that this does not raise

    def test_append_hook_error_sanitizes_surrogates(self, tmp_path):
        """A hook error carrying a lone surrogate (e.g. a surrogateescaped byte in an
        exception message) must be sanitized before it enters the sink, so a
        downstream strict-UTF-8 reader (the stewardship briefing's write_text) can't
        crash on it. Regression for the render_briefing surrogate-write crash."""
        import json as _json
        rwf = self._load_module()  # LEARNING_DATA_ROOT isolated by the autouse fixture
        rwf._append_hook_error("h.py", "runtime error: cannot open \udce9")
        log = rwf._learning_data_root() / "hooks-errors.jsonl"
        raw = log.read_text(encoding="utf-8")  # sink file itself must be strict-UTF-8
        rec = _json.loads(raw.splitlines()[-1])
        rec["error"].encode("utf-8")  # must NOT raise (pre-fix this raises on \udce9)
        assert "\udce9" not in rec["error"]
