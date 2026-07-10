"""Integration tests for run_with_flags.py wrapper."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

WRAPPER = Path(__file__).parent.parent / "scripts" / "run_with_flags.py"


def run_wrapper(args: list[str], stdin: str, env_overrides: dict[str, str] | None = None):
    """Invoke run_with_flags.py as a subprocess. Returns CompletedProcess."""
    env = {**os.environ}
    # Strip pre-existing DISCIPLINE_ vars so tests are deterministic
    for k in list(env):
        if k.startswith("DISCIPLINE_"):
            del env[k]
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        ["python3", str(WRAPPER), *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )


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
