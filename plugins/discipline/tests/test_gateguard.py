import json
import os
import sys
import tempfile
from pathlib import Path
import pytest

# Make scripts/ importable
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from gateguard import (
    resolve_session_key,
    load_state,
    save_state,
    mark_checked,
    is_checked,
    prune_checked_entries,
    MAX_CHECKED_ENTRIES,
    ROUTINE_BASH_SESSION_KEY,
)


@pytest.fixture
def tmp_state_dir(monkeypatch, tmp_path):
    """Redirect gateguard state dir to a per-test tmp_path; reset the cached state file between tests."""
    monkeypatch.setenv("GATEGUARD_STATE_DIR", str(tmp_path))
    import gateguard
    # Reset the module-level cache + STATE_DIR
    gateguard._active_state_file = None
    gateguard.STATE_DIR = tmp_path
    return tmp_path


def test_resolve_session_key_from_session_id(tmp_state_dir):
    key = resolve_session_key({"session_id": "abc-123"})
    assert key == "abc-123"


def test_resolve_session_key_sanitizes_long_value(tmp_state_dir):
    long_id = "x" * 200
    key = resolve_session_key({"session_id": long_id})
    assert key.startswith("sid-")  # falls through to hash
    assert len(key) <= 32


def test_resolve_session_key_uses_transcript_fallback(tmp_state_dir):
    key = resolve_session_key({"transcript_path": "/tmp/t.jsonl"})
    assert key.startswith("tx-")


def test_resolve_session_key_uses_cwd_fallback(tmp_state_dir):
    key = resolve_session_key({})
    assert key.startswith("proj-")


def test_load_state_returns_empty_when_no_file(tmp_state_dir):
    state = load_state()
    assert state["checked"] == []
    assert "last_active" in state


def test_save_and_load_round_trip(tmp_state_dir):
    mark_checked("/path/a.py")
    mark_checked("/path/b.py")
    state = load_state()
    assert "/path/a.py" in state["checked"]
    assert "/path/b.py" in state["checked"]


def test_is_checked_true_after_mark(tmp_state_dir):
    mark_checked("/path/x.py")
    assert is_checked("/path/x.py")


def test_is_checked_false_initially(tmp_state_dir):
    assert not is_checked("/path/never-marked.py")


def test_state_expires_after_30min(tmp_state_dir):
    mark_checked("/path/old.py")
    import gateguard
    state_file = gateguard._get_state_file({})
    data = json.loads(state_file.read_text())
    data["last_active"] = 0  # epoch — definitely > 30min ago
    state_file.write_text(json.dumps(data))
    gateguard._active_state_file = None
    assert not is_checked("/path/old.py")


def test_prune_caps_at_max_entries(tmp_state_dir):
    entries = [f"/file/{i}.py" for i in range(MAX_CHECKED_ENTRIES + 50)]
    result = prune_checked_entries(entries)
    assert len(result) <= MAX_CHECKED_ENTRIES


def test_prune_preserves_routine_bash_key(tmp_state_dir):
    entries = [f"/file/{i}.py" for i in range(MAX_CHECKED_ENTRIES + 50)]
    entries.append(ROUTINE_BASH_SESSION_KEY)
    result = prune_checked_entries(entries)
    assert ROUTINE_BASH_SESSION_KEY in result


from gateguard import is_destructive_bash


class TestDestructiveBash:
    @pytest.mark.parametrize("cmd", [
        "rm -rf /tmp/foo",
        "rm -fr /tmp/foo",
        "rm -r -f /tmp/foo",
        "rm --recursive --force /tmp/foo",
    ])
    def test_rm_destructive(self, cmd):
        assert is_destructive_bash(cmd)

    @pytest.mark.parametrize("cmd", [
        "rm /tmp/foo",        # no -r
        "rm -i /tmp/foo",     # interactive
        "rm -r /tmp/foo",     # no -f
    ])
    def test_rm_non_destructive(self, cmd):
        assert not is_destructive_bash(cmd)

    @pytest.mark.parametrize("cmd", [
        "git push --force",
        "git push -f origin main",
        "git push origin +main",
        "git push origin +refs/heads/main",
    ])
    def test_git_push_force_destructive(self, cmd):
        assert is_destructive_bash(cmd)

    def test_git_push_force_with_lease_allowed(self):
        # ecc treats --force-with-lease as safety-checked
        assert not is_destructive_bash("git push --force-with-lease origin main")

    def test_git_reset_hard_destructive(self):
        assert is_destructive_bash("git reset --hard origin/main")

    def test_git_clean_force_destructive(self):
        assert is_destructive_bash("git clean -fdx")

    def test_sql_drop_table_destructive_bare(self):
        # Bare phrase outside quotes IS destructive
        assert is_destructive_bash("echo drop table users | psql")

    def test_sql_drop_table_inside_single_quotes_allowed(self):
        # Inside single quotes - bash treats literally, gateguard strips quoted strings
        # (matching ecc's stripQuotedStrings behavior)
        assert not is_destructive_bash("psql -c 'drop table users;'")

    def test_dd_if_destructive(self):
        assert is_destructive_bash("dd if=/dev/zero of=/dev/sda")

    def test_destructive_inside_dollar_paren(self):
        assert is_destructive_bash("echo y | $(rm -rf /tmp/foo)")

    def test_destructive_inside_backticks(self):
        assert is_destructive_bash("echo y | `rm -rf /tmp/foo`")


from gateguard import (
    sanitize_path,
    is_claude_settings_path,
    is_doc_path,
    is_subagent_invocation,
    edit_gate_msg,
    write_gate_msg,
    destructive_bash_msg,
)


class TestPathSanitization:
    def test_strips_control_chars(self):
        assert "\x00" not in sanitize_path("path\x00with-null.py")

    def test_strips_bidi_overrides(self):
        # U+202E is RIGHT-TO-LEFT OVERRIDE
        assert "‮" not in sanitize_path("file‮.exe.py")

    def test_caps_at_500_chars(self):
        long = "/" + "a" * 600
        assert len(sanitize_path(long)) <= 500


class TestAllowlists:
    @pytest.mark.parametrize("path", [
        "/home/u/.claude/settings.json",
        "C:\\Users\\g\\.claude\\settings.local.json",
        "/foo/.claude/settings.darwin.json",
    ])
    def test_claude_settings_bypass(self, path):
        assert is_claude_settings_path(path)

    def test_non_settings_path_not_bypassed(self):
        assert not is_claude_settings_path("/foo/.claude/agents/x.md")

    @pytest.mark.parametrize("path", [
        "/repo/README.md",
        "C:\\Users\\g\\docs\\spec.md",
        "/repo/notes.markdown",
        "/repo/CHANGELOG.txt",
        "/repo/docs/guide.rst",
        "/repo/READme.MD",  # case-insensitive (non-config doc)
        "/repo/archive.tar.md",  # multi-dot, classified by final suffix
    ])
    def test_doc_path_exempt(self, path):
        assert is_doc_path(path)

    @pytest.mark.parametrize("path", [
        "/repo/main.py",
        "/repo/src/app.ts",
        "/repo/hooks.json",
        "/repo/Cargo.toml",
        "/repo/script.ps1",
        "/repo/no_extension",
        "/repo/notes.md.bak",  # doc ext not final -> gated (no naive substring match)
        "/docs.md/app.py",     # .md in a directory segment, not the basename
        "/repo/.gitignore",    # dotfile with no suffix -> dot<=0 guard
    ])
    def test_code_path_not_exempt(self, path):
        assert not is_doc_path(path)

    @pytest.mark.parametrize("path", [
        "/repo/CLAUDE.md",
        "/repo/AGENTS.md",
        "/repo/GEMINI.md",
        "C:\\Users\\g\\claude.MD",  # case-insensitive
        "/nested/project/AGENTS.md",
    ])
    def test_agent_config_md_not_exempt(self, path):
        # Behavior-bearing config files stay gated despite the .md extension.
        assert not is_doc_path(path)


class TestSubagentBypass:
    def test_subagent_detected_via_agent_id(self):
        assert is_subagent_invocation({"agent_id": "sub-123"})

    def test_subagent_detected_via_parent_tool_use_id(self):
        assert is_subagent_invocation({"parent_tool_use_id": "tool-456"})

    def test_main_agent_not_subagent(self):
        assert not is_subagent_invocation({"session_id": "main"})


class TestGateMessages:
    def test_edit_msg_includes_file_path(self):
        assert "/path/x.py" in edit_gate_msg("/path/x.py")

    def test_edit_msg_includes_4_facts(self):
        msg = edit_gate_msg("/x.py")
        assert all(f"{n}." in msg for n in (1, 2, 3, 4))

    def test_write_msg_includes_file_path(self):
        assert "/path/new.py" in write_gate_msg("/path/new.py")

    def test_destructive_msg_present(self):
        msg = destructive_bash_msg()
        assert "Destructive command" in msg


import io


from gateguard import main, _deny_result_json


@pytest.fixture
def gateguard_input(monkeypatch):
    """Helper: feed JSON to stdin, capture stdout."""
    def _call(event: dict):
        in_buf = io.StringIO(json.dumps(event))
        out_buf = io.StringIO()
        monkeypatch.setattr("sys.stdin", in_buf)
        monkeypatch.setattr("sys.stdout", out_buf)
        rc = main([])
        return rc, out_buf.getvalue()
    return _call


class TestDispatcher:
    def test_first_edit_denies(self, tmp_state_dir, gateguard_input):
        rc, out = gateguard_input({
            "tool_name": "Edit",
            "tool_input": {"file_path": "/path/x.py"},
            "session_id": "test-1",
        })
        assert rc == 0
        payload = json.loads(out)
        assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "Fact-Forcing Gate" in payload["hookSpecificOutput"]["permissionDecisionReason"]

    def test_second_edit_same_file_allows(self, tmp_state_dir, gateguard_input):
        gateguard_input({
            "tool_name": "Edit",
            "tool_input": {"file_path": "/x.py"},
            "session_id": "s2",
        })
        import gateguard
        gateguard._active_state_file = None
        rc, out = gateguard_input({
            "tool_name": "Edit",
            "tool_input": {"file_path": "/x.py"},
            "session_id": "s2",
        })
        assert rc == 0
        assert out == ""  # passthrough = allow

    def test_claude_settings_bypassed(self, tmp_state_dir, gateguard_input):
        rc, out = gateguard_input({
            "tool_name": "Write",
            "tool_input": {"file_path": "/u/.claude/settings.json"},
            "session_id": "s3",
        })
        assert out == ""

    def test_subagent_bypassed(self, tmp_state_dir, gateguard_input):
        rc, out = gateguard_input({
            "tool_name": "Edit",
            "tool_input": {"file_path": "/never-marked.py"},
            "session_id": "s4",
            "agent_id": "sub-123",
        })
        assert out == ""

    def test_destructive_bash_denies(self, tmp_state_dir, gateguard_input):
        rc, out = gateguard_input({
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /tmp/foo"},
            "session_id": "s5",
        })
        payload = json.loads(out)
        assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "Destructive command" in payload["hookSpecificOutput"]["permissionDecisionReason"]

    def test_routine_bash_passes_through(self, tmp_state_dir, gateguard_input):
        # Retarget (hb-of7): routine-bash gate dropped — first bash no longer denied.
        rc, out = gateguard_input({
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
            "session_id": "s6",
        })
        assert out == ""

    def test_doc_edit_passes_through(self, tmp_state_dir, gateguard_input):
        # Retarget (hb-of7): doc files exempt from the first-touch fact gate.
        rc, out = gateguard_input({
            "tool_name": "Write",
            "tool_input": {"file_path": "/repo/README.md"},
            "session_id": "s6b",
        })
        assert out == ""

    def test_code_edit_still_denies(self, tmp_state_dir, gateguard_input):
        # Retarget (hb-of7): code files still gated.
        rc, out = gateguard_input({
            "tool_name": "Edit",
            "tool_input": {"file_path": "/repo/app.py"},
            "session_id": "s6c",
        })
        payload = json.loads(out)
        assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_multiedit_mixed_batch_denies_on_code(self, tmp_state_dir, gateguard_input):
        # Retarget (hb-of7): MultiEdit skips the doc edit but still gates the code edit
        # in the same batch. Guards the is_doc_path() check inside the MultiEdit loop.
        rc, out = gateguard_input({
            "tool_name": "MultiEdit",
            "tool_input": {"edits": [
                {"file_path": "/repo/README.md"},
                {"file_path": "/repo/app.py"},
            ]},
            "session_id": "s6d",
        })
        payload = json.loads(out)
        assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_agent_config_md_still_denies(self, tmp_state_dir, gateguard_input):
        # Behavior-bearing config (CLAUDE/AGENTS/GEMINI .md) stays gated.
        rc, out = gateguard_input({
            "tool_name": "Edit",
            "tool_input": {"file_path": "/repo/CLAUDE.md"},
            "session_id": "s6f",
        })
        payload = json.loads(out)
        assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_multiedit_all_docs_passes_through(self, tmp_state_dir, gateguard_input):
        # Retarget (hb-of7): an all-doc MultiEdit batch is fully exempt.
        rc, out = gateguard_input({
            "tool_name": "MultiEdit",
            "tool_input": {"edits": [
                {"file_path": "/repo/a.md"},
                {"file_path": "/repo/b.txt"},
            ]},
            "session_id": "s6e",
        })
        assert out == ""

    def test_non_destructive_bash_passes_through(self, tmp_state_dir, gateguard_input):
        # Retarget (hb-of7): all non-destructive bash passes (routine gate dropped).
        rc, out = gateguard_input({
            "tool_name": "Bash",
            "tool_input": {"command": "git status --porcelain"},
            "session_id": "s7",
        })
        assert out == ""

    def test_disabled_via_env(self, tmp_state_dir, gateguard_input, monkeypatch):
        monkeypatch.setenv("DISCIPLINE_GATEGUARD", "off")
        rc, out = gateguard_input({
            "tool_name": "Edit",
            "tool_input": {"file_path": "/x.py"},
            "session_id": "s8",
        })
        assert out == ""

    def test_invalid_json_input_is_passthrough(self, tmp_state_dir, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO("not-json{{"))
        out_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", out_buf)
        rc = main([])
        assert rc == 0
        assert out_buf.getvalue() == ""


import subprocess


PLUGIN_ROOT = Path(__file__).parent.parent
RUN_WITH_FLAGS = PLUGIN_ROOT / "scripts" / "run_with_flags.py"
GATEGUARD = PLUGIN_ROOT / "scripts" / "gateguard.py"


def _invoke_subprocess(event: dict, env_overrides: dict | None = None) -> tuple[str, int]:
    cmd = [
        sys.executable,
        str(RUN_WITH_FLAGS),
        str(GATEGUARD),
        "discipline:pre-edit:gateguard-fact-force",
        "standard,strict",
    ]
    env_full = dict(os.environ)
    if env_overrides:
        env_full.update(env_overrides)
    proc = subprocess.run(
        cmd,
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env_full,
    )
    return proc.stdout, proc.returncode


class TestIntegration:
    def test_first_touch_denies_via_subprocess(self, tmp_path):
        out, rc = _invoke_subprocess(
            {"tool_name": "Edit", "tool_input": {"file_path": "/x.py"}, "session_id": "int-1"},
            env_overrides={"GATEGUARD_STATE_DIR": str(tmp_path)},
        )
        assert rc == 0
        payload = json.loads(out)
        assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_disabled_via_disable_list(self, tmp_path):
        out, rc = _invoke_subprocess(
            {"tool_name": "Edit", "tool_input": {"file_path": "/y.py"}, "session_id": "int-2"},
            env_overrides={
                "GATEGUARD_STATE_DIR": str(tmp_path),
                "DISCIPLINE_DISABLED_HOOKS": "discipline:pre-edit:gateguard-fact-force",
            },
        )
        assert rc == 0
        assert out == ""

    def test_disabled_via_profile_minimal(self, tmp_path):
        out, rc = _invoke_subprocess(
            {"tool_name": "Edit", "tool_input": {"file_path": "/z.py"}, "session_id": "int-3"},
            env_overrides={
                "GATEGUARD_STATE_DIR": str(tmp_path),
                "DISCIPLINE_HOOK_PROFILE": "minimal",
            },
        )
        assert rc == 0
        assert out == ""
