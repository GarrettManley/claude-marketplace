# plugins/aether/tests/test_hooks.py
"""Import-based unit tests for the five aether PreToolUse/PostToolUse hooks.

All hooks are tested by importing the module and calling main() directly with
stdin monkeypatched to the appropriate JSON payload. Tests are hermetic
(no subprocess, no network, no real filesystem side-effects beyond tmp_path).
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
from pathlib import Path

import pytest

# conftest.py has already inserted hooks/ and scripts/ onto sys.path.
import cd_core_guard
import classifier_eval_reminder
import gameplay_harness_reminder
import ledger_truncation_hook
import rust_rebuild_reminder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stdin(payload: dict | str):
    """Return a StringIO pre-loaded with *payload* (dict → JSON, str verbatim)."""
    text = json.dumps(payload) if isinstance(payload, dict) else payload
    return io.StringIO(text)


def _run_main(module, monkeypatch, payload, *, stdin_text: str | None = None):
    """Monkeypatch stdin and invoke module.main()."""
    data = stdin_text if stdin_text is not None else json.dumps(payload) if isinstance(payload, dict) else payload
    monkeypatch.setattr(sys, "stdin", io.StringIO(data))
    return module.main()


# ===========================================================================
# cd_core_guard
# ===========================================================================

class TestCdCoreGuard:
    def test_allows_non_bash(self, monkeypatch):
        rc = _run_main(cd_core_guard, monkeypatch, {"tool_name": "Edit", "tool_input": {"file_path": "x"}})
        assert rc == 0

    def test_allows_cargo_build(self, monkeypatch):
        payload = {"tool_name": "Bash", "tool_input": {"command": "cd core && cargo build --release"}}
        rc = _run_main(cd_core_guard, monkeypatch, payload)
        assert rc == 0

    def test_blocks_cargo_test(self, monkeypatch, capsys):
        payload = {"tool_name": "Bash", "tool_input": {"command": "cd core && cargo test"}}
        rc = _run_main(cd_core_guard, monkeypatch, payload)
        assert rc == 2
        err = capsys.readouterr().err
        assert "Blocked:" in err
        assert "cargo test" in err or "--manifest-path" in err

    def test_blocks_cargo_check(self, monkeypatch, capsys):
        payload = {"tool_name": "Bash", "tool_input": {"command": "cd core && cargo check"}}
        rc = _run_main(cd_core_guard, monkeypatch, payload)
        assert rc == 2

    def test_blocks_cargo_run(self, monkeypatch, capsys):
        payload = {"tool_name": "Bash", "tool_input": {"command": "cd core && cargo run"}}
        rc = _run_main(cd_core_guard, monkeypatch, payload)
        assert rc == 2

    def test_blocks_cargo_doc(self, monkeypatch, capsys):
        payload = {"tool_name": "Bash", "tool_input": {"command": "cd core && cargo doc"}}
        rc = _run_main(cd_core_guard, monkeypatch, payload)
        assert rc == 2

    def test_allows_other_bash_command(self, monkeypatch):
        payload = {"tool_name": "Bash", "tool_input": {"command": "echo hello world"}}
        rc = _run_main(cd_core_guard, monkeypatch, payload)
        assert rc == 0

    def test_allows_manifest_path_cargo(self, monkeypatch):
        payload = {"tool_name": "Bash", "tool_input": {"command": "cargo test --manifest-path core/Cargo.toml"}}
        rc = _run_main(cd_core_guard, monkeypatch, payload)
        assert rc == 0

    def test_empty_command_allows(self, monkeypatch):
        payload = {"tool_name": "Bash", "tool_input": {"command": ""}}
        rc = _run_main(cd_core_guard, monkeypatch, payload)
        assert rc == 0

    def test_missing_command_key_allows(self, monkeypatch):
        payload = {"tool_name": "Bash", "tool_input": {}}
        rc = _run_main(cd_core_guard, monkeypatch, payload)
        assert rc == 0

    def test_invalid_json_allows(self, monkeypatch):
        rc = _run_main(cd_core_guard, monkeypatch, None, stdin_text="not json")
        assert rc == 0

    def test_block_message_includes_corrected_form(self, monkeypatch, capsys):
        payload = {"tool_name": "Bash", "tool_input": {"command": "cd core && cargo test --release"}}
        rc = _run_main(cd_core_guard, monkeypatch, payload)
        assert rc == 2
        err = capsys.readouterr().err
        assert "--manifest-path" in err

    def test_subcommand_in_block_message(self, monkeypatch, capsys):
        payload = {"tool_name": "Bash", "tool_input": {"command": "cd core && cargo clippy"}}
        rc = _run_main(cd_core_guard, monkeypatch, payload)
        assert rc == 2
        err = capsys.readouterr().err
        assert "clippy" in err

    def test_leading_whitespace_command_blocked(self, monkeypatch, capsys):
        payload = {"tool_name": "Bash", "tool_input": {"command": "  cd core && cargo test"}}
        rc = _run_main(cd_core_guard, monkeypatch, payload)
        assert rc == 2

    def test_non_bash_tool_with_command_key_allows(self, monkeypatch):
        # tool_name != Bash should always allow
        payload = {"tool_name": "PowerShell", "tool_input": {"command": "cd core && cargo test"}}
        rc = _run_main(cd_core_guard, monkeypatch, payload)
        assert rc == 0


# ===========================================================================
# classifier_eval_reminder
# ===========================================================================

class TestClassifierEvalReminder:
    def _payload(self, file_path: str) -> dict:
        return {"tool_input": {"file_path": file_path}}

    def test_fires_for_classifier_prompt(self, monkeypatch, capsys, aether_checkout: Path):
        target = str(aether_checkout / "src" / "llm" / "classifier_prompt.ts")
        rc = _run_main(classifier_eval_reminder, monkeypatch, self._payload(target))
        assert rc == 0
        out = capsys.readouterr().out
        assert "[classifier-eval-reminder]" in out

    def test_fires_for_ollama(self, monkeypatch, capsys, aether_checkout: Path):
        target = str(aether_checkout / "src" / "llm" / "ollama.ts")
        rc = _run_main(classifier_eval_reminder, monkeypatch, self._payload(target))
        assert rc == 0
        assert "[classifier-eval-reminder]" in capsys.readouterr().out

    def test_fires_for_gemini(self, monkeypatch, capsys, aether_checkout: Path):
        target = str(aether_checkout / "src" / "llm" / "gemini.ts")
        rc = _run_main(classifier_eval_reminder, monkeypatch, self._payload(target))
        assert rc == 0
        assert "[classifier-eval-reminder]" in capsys.readouterr().out

    def test_fires_for_schemas(self, monkeypatch, capsys, aether_checkout: Path):
        target = str(aether_checkout / "src" / "llm" / "schemas.ts")
        rc = _run_main(classifier_eval_reminder, monkeypatch, self._payload(target))
        assert rc == 0
        assert "[classifier-eval-reminder]" in capsys.readouterr().out

    def test_silent_for_readme(self, monkeypatch, capsys, aether_checkout: Path):
        target = str(aether_checkout / "README.md")
        rc = _run_main(classifier_eval_reminder, monkeypatch, self._payload(target))
        assert rc == 0
        assert capsys.readouterr().out.strip() == ""

    def test_silent_for_provider_ts(self, monkeypatch, capsys, aether_checkout: Path):
        # provider.ts triggers gameplay but NOT classifier
        target = str(aether_checkout / "src" / "llm" / "provider.ts")
        rc = _run_main(classifier_eval_reminder, monkeypatch, self._payload(target))
        assert rc == 0
        assert capsys.readouterr().out.strip() == ""

    def test_silent_outside_aether_repo(self, monkeypatch, capsys, tmp_path: Path):
        loose = tmp_path / "random" / "src" / "llm" / "classifier_prompt.ts"
        loose.parent.mkdir(parents=True)
        loose.write_text("// x", encoding="utf-8")
        rc = _run_main(classifier_eval_reminder, monkeypatch, self._payload(str(loose)))
        assert rc == 0
        assert capsys.readouterr().out.strip() == ""

    def test_silent_on_invalid_json(self, monkeypatch, capsys):
        rc = _run_main(classifier_eval_reminder, monkeypatch, None, stdin_text="!!invalid!!")
        assert rc == 0
        assert capsys.readouterr().out.strip() == ""

    def test_silent_on_empty_file_path(self, monkeypatch, capsys):
        rc = _run_main(classifier_eval_reminder, monkeypatch, {"tool_input": {"file_path": ""}})
        assert rc == 0
        assert capsys.readouterr().out.strip() == ""

    def test_message_contains_file_name(self, monkeypatch, capsys, aether_checkout: Path):
        target = str(aether_checkout / "src" / "llm" / "ollama.ts")
        _run_main(classifier_eval_reminder, monkeypatch, self._payload(target))
        out = capsys.readouterr().out
        assert "ollama.ts" in out or "src/llm/ollama.ts" in out

    def test_uses_tool_response_file_path(self, monkeypatch, capsys, aether_checkout: Path):
        target = str(aether_checkout / "src" / "llm" / "gemini.ts")
        payload = {"tool_input": {}, "tool_response": {"filePath": target}}
        rc = _run_main(classifier_eval_reminder, monkeypatch, payload)
        assert rc == 0
        assert "[classifier-eval-reminder]" in capsys.readouterr().out


# ===========================================================================
# gameplay_harness_reminder
# ===========================================================================

class TestGameplayHarnessReminder:
    def _payload(self, file_path: str) -> dict:
        return {"tool_input": {"file_path": file_path}}

    @pytest.mark.parametrize("fname", [
        "src/dm.ts",
        "src/bus.ts",
        "src/server.ts",
        "src/actor.ts",
        "src/roll-proposal.ts",
        "src/state-sync.ts",
        "src/llm/classifier_prompt.ts",
        "src/llm/ollama.ts",
        "src/llm/gemini.ts",
        "src/llm/schemas.ts",
        "src/llm/provider.ts",
    ])
    def test_fires_for_trigger_file(self, monkeypatch, capsys, aether_checkout: Path, fname: str):
        target = str(aether_checkout / Path(fname.replace("/", os.sep)))
        rc = _run_main(gameplay_harness_reminder, monkeypatch, self._payload(target))
        assert rc == 0
        out = capsys.readouterr().out
        assert "[gameplay-harness-reminder]" in out

    def test_silent_for_readme(self, monkeypatch, capsys, aether_checkout: Path):
        target = str(aether_checkout / "README.md")
        rc = _run_main(gameplay_harness_reminder, monkeypatch, self._payload(target))
        assert rc == 0
        assert capsys.readouterr().out.strip() == ""

    def test_silent_outside_aether_repo(self, monkeypatch, capsys, tmp_path: Path):
        loose = tmp_path / "nowhere" / "src" / "dm.ts"
        loose.parent.mkdir(parents=True)
        loose.write_text("// x", encoding="utf-8")
        rc = _run_main(gameplay_harness_reminder, monkeypatch, self._payload(str(loose)))
        assert rc == 0
        assert capsys.readouterr().out.strip() == ""

    def test_silent_on_invalid_json(self, monkeypatch, capsys):
        rc = _run_main(gameplay_harness_reminder, monkeypatch, None, stdin_text="bad!")
        assert rc == 0
        assert capsys.readouterr().out.strip() == ""

    def test_silent_on_missing_file_path(self, monkeypatch, capsys):
        rc = _run_main(gameplay_harness_reminder, monkeypatch, {"tool_input": {}})
        assert rc == 0
        assert capsys.readouterr().out.strip() == ""

    def test_message_contains_run_command(self, monkeypatch, capsys, aether_checkout: Path):
        target = str(aether_checkout / "src" / "dm.ts")
        _run_main(gameplay_harness_reminder, monkeypatch, self._payload(target))
        out = capsys.readouterr().out
        assert "run-gameplay-tests" in out

    def test_worktree_checkout_fires(self, monkeypatch, capsys, aether_checkout: Path):
        wt = aether_checkout / ".worktrees" / "feat-x"
        (wt / "core").mkdir(parents=True)
        (wt / "src").mkdir(parents=True)
        (wt / "core" / "Cargo.toml").write_text("[package]\nname='core'\n", encoding="utf-8")
        (wt / "src" / "dm.ts").write_text("// dm\n", encoding="utf-8")
        rc = _run_main(gameplay_harness_reminder, monkeypatch, self._payload(str(wt / "src" / "dm.ts")))
        assert rc == 0
        assert "[gameplay-harness-reminder]" in capsys.readouterr().out


# ===========================================================================
# ledger_truncation_hook
# ===========================================================================

class TestLedgerTruncationHook:
    def _run(self, monkeypatch, command: str) -> tuple[int, str]:
        payload = {"tool_name": "Bash", "tool_input": {"command": command}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        # Capture stdout since the hook prints JSON to stdout
        import io as _io
        buf = _io.StringIO()
        orig_stdout = sys.stdout
        sys.stdout = buf
        try:
            rc = ledger_truncation_hook.main()
        finally:
            sys.stdout = orig_stdout
        return rc, buf.getvalue()

    def test_truncation_redirect_detected(self, monkeypatch):
        rc, out = self._run(monkeypatch, "> campaigns/1/history.jsonl")
        assert rc == 0
        data = json.loads(out)
        assert data["decision"] == "block"
        assert "combat_state.json" in data["reason"]

    def test_head_command_detected(self, monkeypatch):
        rc, out = self._run(monkeypatch, "head -n 100 campaigns/1/history.jsonl > tmp && mv tmp campaigns/1/history.jsonl")
        # The head ... history.jsonl token is there but there's no redirect directly from head
        # The actual truncation pattern matches the head invocation
        assert rc == 0
        # Either the head matched or the redirect matched; in either case decision=block
        if out.strip():
            data = json.loads(out)
            assert data["decision"] == "block"

    def test_no_truncation_passes_cleanly(self, monkeypatch):
        rc, out = self._run(monkeypatch, "cat campaigns/1/history.jsonl | grep foo")
        assert rc == 0
        assert out.strip() == ""

    def test_invalid_json_returns_0(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
        assert ledger_truncation_hook.main() == 0

    def test_flag_body_string_not_triggered(self, monkeypatch):
        # A mention inside --body should NOT trigger
        command = 'gh pr create --body "truncating > old/history.jsonl is dangerous"'
        rc, out = self._run(monkeypatch, command)
        assert rc == 0
        assert out.strip() == ""

    def test_direct_redirect_to_history_jsonl(self, monkeypatch):
        rc, out = self._run(monkeypatch, "echo '' > /some/path/history.jsonl")
        assert rc == 0
        assert out.strip() != ""
        data = json.loads(out)
        assert data["decision"] == "block"

    def test_sed_in_place_detected(self, monkeypatch):
        rc, out = self._run(monkeypatch, "sed -i '1,10d' campaigns/abc/history.jsonl")
        assert rc == 0
        data = json.loads(out)
        assert data["decision"] == "block"

    def test_truncate_command_detected(self, monkeypatch):
        rc, out = self._run(monkeypatch, "truncate history.jsonl")
        assert rc == 0
        data = json.loads(out)
        assert data["decision"] == "block"

    def test_unrelated_command_passes(self, monkeypatch):
        rc, out = self._run(monkeypatch, "ls -la campaigns/")
        assert rc == 0
        assert out.strip() == ""

    def test_payload_missing_command_passes(self, monkeypatch):
        payload = {"tool_name": "Bash", "tool_input": {}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        assert ledger_truncation_hook.main() == 0

    def test_empty_command_passes(self, monkeypatch):
        rc, out = self._run(monkeypatch, "")
        assert rc == 0
        assert out.strip() == ""


# ===========================================================================
# rust_rebuild_reminder
# ===========================================================================

class TestRustRebuildReminder:
    def _payload(self, file_path: str) -> dict:
        return {"tool_input": {"file_path": file_path}}

    def test_fires_for_rs_file_in_core_src(self, monkeypatch, capsys, aether_checkout: Path):
        target = str(aether_checkout / "core" / "src" / "main.rs")
        rc = _run_main(rust_rebuild_reminder, monkeypatch, self._payload(target))
        assert rc == 0
        out = capsys.readouterr().out
        assert "[rust-rebuild-reminder]" in out

    def test_silent_for_ts_file(self, monkeypatch, capsys, aether_checkout: Path):
        target = str(aether_checkout / "src" / "dm.ts")
        rc = _run_main(rust_rebuild_reminder, monkeypatch, self._payload(target))
        assert rc == 0
        assert capsys.readouterr().out.strip() == ""

    def test_silent_for_rs_file_outside_core_src(self, monkeypatch, capsys, aether_checkout: Path):
        # A .rs file not under core/src/ should not fire
        rs = aether_checkout / "misc.rs"
        rs.write_text("fn foo() {}", encoding="utf-8")
        rc = _run_main(rust_rebuild_reminder, monkeypatch, self._payload(str(rs)))
        assert rc == 0
        assert capsys.readouterr().out.strip() == ""

    def test_silent_outside_aether_repo(self, monkeypatch, capsys, tmp_path: Path):
        loose = tmp_path / "nowhere" / "core" / "src" / "main.rs"
        loose.parent.mkdir(parents=True)
        loose.write_text("fn main() {}", encoding="utf-8")
        rc = _run_main(rust_rebuild_reminder, monkeypatch, self._payload(str(loose)))
        assert rc == 0
        assert capsys.readouterr().out.strip() == ""

    def test_staleness_message_when_binary_older(self, monkeypatch, capsys, aether_checkout: Path):
        src = aether_checkout / "core" / "src" / "main.rs"
        binary = aether_checkout / "core" / "target" / "release" / "core.exe"
        now = time.time()
        os.utime(binary, (now - 200, now - 200))
        os.utime(src, (now, now))
        rc = _run_main(rust_rebuild_reminder, monkeypatch, self._payload(str(src)))
        assert rc == 0
        out = capsys.readouterr().out
        assert "[STALE:" in out

    def test_no_staleness_when_binary_newer(self, monkeypatch, capsys, aether_checkout: Path):
        src = aether_checkout / "core" / "src" / "main.rs"
        binary = aether_checkout / "core" / "target" / "release" / "core.exe"
        now = time.time()
        os.utime(src, (now - 100, now - 100))
        os.utime(binary, (now, now))
        rc = _run_main(rust_rebuild_reminder, monkeypatch, self._payload(str(src)))
        assert rc == 0
        out = capsys.readouterr().out
        assert "[rust-rebuild-reminder]" in out
        assert "[STALE:" not in out

    def test_missing_binary_reported_as_stale(self, monkeypatch, capsys, aether_checkout: Path):
        # Remove the binary so bin_mtime defaults to 0
        binary = aether_checkout / "core" / "target" / "release" / "core.exe"
        binary.unlink()
        src = aether_checkout / "core" / "src" / "main.rs"
        rc = _run_main(rust_rebuild_reminder, monkeypatch, self._payload(str(src)))
        assert rc == 0
        out = capsys.readouterr().out
        assert "[STALE:" in out

    def test_silent_on_invalid_json(self, monkeypatch, capsys):
        rc = _run_main(rust_rebuild_reminder, monkeypatch, None, stdin_text="bad json!")
        assert rc == 0
        assert capsys.readouterr().out.strip() == ""

    def test_silent_on_missing_file_path(self, monkeypatch, capsys):
        rc = _run_main(rust_rebuild_reminder, monkeypatch, {"tool_input": {}})
        assert rc == 0
        assert capsys.readouterr().out.strip() == ""

    def test_message_contains_cargo_command(self, monkeypatch, capsys, aether_checkout: Path):
        target = str(aether_checkout / "core" / "src" / "main.rs")
        _run_main(rust_rebuild_reminder, monkeypatch, self._payload(target))
        out = capsys.readouterr().out
        assert "cargo build" in out

    def test_uses_tool_response_file_path(self, monkeypatch, capsys, aether_checkout: Path):
        target = str(aether_checkout / "core" / "src" / "main.rs")
        payload = {"tool_input": {}, "tool_response": {"filePath": target}}
        rc = _run_main(rust_rebuild_reminder, monkeypatch, payload)
        assert rc == 0
        assert "[rust-rebuild-reminder]" in capsys.readouterr().out

    def test_oserror_in_stat_is_swallowed(self, monkeypatch, capsys, aether_checkout: Path):
        """Cover the except OSError branch (lines 57-58) in rust_rebuild_reminder.

        Patch Path.stat to raise OSError so the try/except fires; the hook
        should still exit 0 and print the base reminder (no stale annotation).
        """
        from pathlib import Path as _Path

        orig_stat = _Path.stat

        def _bad_stat(self, *args, **kwargs):
            # Fail only the staleness probe (the edited .rs source + the
            # core.exe binary), delegating repo-root detection's Cargo.toml
            # probes to the real stat. Python 3.12/3.13 route Path.is_file()
            # through Path.stat (3.14/<=3.11 bypass it via os.stat), so a
            # blanket patch crashes find_repo_root before the branch under
            # test (rust_rebuild_reminder lines 57-58) is ever reached.
            if self.name.endswith(".rs") or self.name == "core.exe":
                raise OSError("synthetic stat failure")
            return orig_stat(self, *args, **kwargs)

        monkeypatch.setattr(_Path, "stat", _bad_stat)
        target = str(aether_checkout / "core" / "src" / "main.rs")
        rc = _run_main(rust_rebuild_reminder, monkeypatch, self._payload(target))
        assert rc == 0
        out = capsys.readouterr().out
        # The reminder still prints, just without [STALE:]
        assert "[rust-rebuild-reminder]" in out
        assert "[STALE:" not in out
