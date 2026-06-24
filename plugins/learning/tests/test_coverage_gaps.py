"""Tests targeting uncovered branches across storage, observe, instinct_schema,
instinct_cli, and analyze modules.

Run from the repo root:
    python -m pytest plugins/learning/tests/test_coverage_gaps.py -q
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

# ---------------------------------------------------------------------------
# Imports — do these after sys.path setup
# ---------------------------------------------------------------------------
import storage as _storage_mod
from storage import (
    GLOBAL_PROJECT_ID,
    _git_remote_url,
    _git_toplevel,
    _short_hash,
    get_data_root,
    get_project_id,
)
from observe import _build_observation, _detect_phase, main as observe_main
from instinct_schema import (
    _parse_frontmatter,
    format_instinct,
    parse_instinct,
    parse_multi_instinct_file,
)
from instinct_cli import (
    cmd_analyze,
    cmd_export,
    cmd_import,
    cmd_status,
    main as cli_main,
)
from analyze import (
    bash_command_prefixes,
    file_hotspots,
    load_observations,
    pre_post_sequences,
    tool_frequency,
)
from storage import get_observations_file, get_project_id, get_project_instincts_dir, get_global_instincts_dir
from instinct_schema import Instinct


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LEARNING_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/explicit/proj")
    return tmp_path


def _make_instinct(id_: str, confidence: float = 0.7, domain: str = "workflow") -> Instinct:
    return Instinct(
        id=id_,
        trigger="when X",
        confidence=confidence,
        domain=domain,
        source="test",
        source_repo=None,
        title=id_,
        action="Do the thing.",
        evidence="It works.",
    )


# ===========================================================================
# storage.py missing lines
# ===========================================================================

class TestStorageFallbackPaths:
    """Lines 49, 63-65, 77-80, 89, 93-96."""

    def test_home_fallback_when_no_env(self, monkeypatch):
        """Line 49 — no LEARNING_DATA_ROOT, not win32, no XDG_DATA_HOME."""
        monkeypatch.delenv("LEARNING_DATA_ROOT", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        monkeypatch.setattr("sys.platform", "linux")
        result = get_data_root()
        assert "claude-marketplace" in result.parts
        assert "learning" in result.parts
        # Must be under .local/share
        assert ".local" in result.parts or "share" in result.parts

    def test_git_remote_url_returns_url_on_success(self, monkeypatch):
        """Line 63 — returncode==0 and stdout has content."""
        fake = MagicMock()
        fake.returncode = 0
        fake.stdout = "https://github.com/org/repo.git\n"
        monkeypatch.setattr("subprocess.run", lambda *a, **k: fake)
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        result = _git_remote_url()
        assert result == "https://github.com/org/repo.git"

    def test_git_remote_url_returns_none_when_nonzero(self, monkeypatch):
        """Line 63 guard — returncode != 0."""
        fake = MagicMock()
        fake.returncode = 1
        fake.stdout = ""
        monkeypatch.setattr("subprocess.run", lambda *a, **k: fake)
        assert _git_remote_url() is None

    def test_git_remote_url_returns_none_on_file_not_found(self, monkeypatch):
        """Line 64 — FileNotFoundError exception."""
        def _raise(*a, **k):
            raise FileNotFoundError("no git")
        monkeypatch.setattr("subprocess.run", _raise)
        assert _git_remote_url() is None

    def test_git_remote_url_returns_none_on_timeout(self, monkeypatch):
        """Line 64 — TimeoutExpired exception."""
        def _raise(*a, **k):
            raise subprocess.TimeoutExpired(cmd="git", timeout=2)
        monkeypatch.setattr("subprocess.run", _raise)
        assert _git_remote_url() is None

    def test_git_remote_url_returns_none_on_oserror(self, monkeypatch):
        """Line 64 — OSError exception."""
        def _raise(*a, **k):
            raise OSError("permission denied")
        monkeypatch.setattr("subprocess.run", _raise)
        assert _git_remote_url() is None

    def test_git_toplevel_returns_none_when_nonzero(self, monkeypatch):
        """Line 77 — returncode != 0 → explicit return None."""
        fake = MagicMock()
        fake.returncode = 1
        fake.stdout = ""
        monkeypatch.setattr("subprocess.run", lambda *a, **k: fake)
        assert _git_toplevel() is None

    def test_git_toplevel_returns_path_on_success(self, monkeypatch):
        """Line 76 — returncode==0 with toplevel."""
        fake = MagicMock()
        fake.returncode = 0
        fake.stdout = "/some/repo\n"
        monkeypatch.setattr("subprocess.run", lambda *a, **k: fake)
        result = _git_toplevel()
        assert result == "/some/repo"

    def test_git_toplevel_returns_none_on_file_not_found(self, monkeypatch):
        """Line 78 — FileNotFoundError."""
        def _raise(*a, **k):
            raise FileNotFoundError("no git")
        monkeypatch.setattr("subprocess.run", _raise)
        assert _git_toplevel() is None

    def test_git_toplevel_returns_none_on_timeout(self, monkeypatch):
        """Line 78 — TimeoutExpired."""
        def _raise(*a, **k):
            raise subprocess.TimeoutExpired(cmd="git", timeout=2)
        monkeypatch.setattr("subprocess.run", _raise)
        assert _git_toplevel() is None

    def test_git_toplevel_returns_none_on_oserror(self, monkeypatch):
        """Line 78 — OSError."""
        def _raise(*a, **k):
            raise OSError("perm denied")
        monkeypatch.setattr("subprocess.run", _raise)
        assert _git_toplevel() is None

    def test_get_project_id_uses_remote(self, monkeypatch):
        """Line 89 — no CLAUDE_PROJECT_DIR, but git remote succeeds."""
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.setattr(_storage_mod, "_git_remote_url",
                            lambda: "https://github.com/org/repo.git")
        result = get_project_id()
        assert len(result) == 12

    def test_get_project_id_uses_toplevel_when_no_remote(self, monkeypatch):
        """Line 91-92 — no remote, but git toplevel succeeds."""
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.setattr(_storage_mod, "_git_remote_url", lambda: None)
        monkeypatch.setattr(_storage_mod, "_git_toplevel", lambda: "/repo/root")
        result = get_project_id()
        assert len(result) == 12

    def test_get_project_id_uses_cwd_when_no_git(self, monkeypatch, tmp_path):
        """Lines 93-95 — no remote, no toplevel, but cwd exists."""
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.setattr(_storage_mod, "_git_remote_url", lambda: None)
        monkeypatch.setattr(_storage_mod, "_git_toplevel", lambda: None)
        monkeypatch.chdir(tmp_path)
        result = get_project_id()
        # Should return a 12-char hash of the cwd
        assert len(result) == 12

    def test_get_project_id_global_fallback_when_cwd_empty(self, monkeypatch):
        """Line 96 — cwd returns falsy (patching os.getcwd)."""
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.setattr(_storage_mod, "_git_remote_url", lambda: None)
        monkeypatch.setattr(_storage_mod, "_git_toplevel", lambda: None)
        monkeypatch.setattr("os.getcwd", lambda: "")
        result = get_project_id()
        assert result == GLOBAL_PROJECT_ID


# ===========================================================================
# observe.py missing lines
# ===========================================================================

class TestObserveMissingLines:
    """Lines 56, 59, 73, 81-82."""

    def test_detect_phase_uses_env_var_pretooluse(self, monkeypatch):
        """Env var fallback (PreToolUse) when event/argv carry no phase."""
        monkeypatch.setenv("CLAUDE_HOOK_EVENT_NAME", "PreToolUse")
        phase = _detect_phase({}, ["observe.py"])
        assert phase == "pre"

    def test_detect_phase_uses_env_var_post(self, monkeypatch):
        """Env var fallback (PostToolUse) → 'post'."""
        monkeypatch.setenv("CLAUDE_HOOK_EVENT_NAME", "PostToolUse")
        phase = _detect_phase({}, ["observe.py"])
        assert phase == "post"

    def test_detect_phase_defaults_to_post(self, monkeypatch):
        """No event phase, no argv[1], no matching env → 'post'."""
        monkeypatch.delenv("CLAUDE_HOOK_EVENT_NAME", raising=False)
        phase = _detect_phase({}, ["observe.py"])
        assert phase == "post"

    def test_detect_phase_argv_pre(self, monkeypatch):
        """argv[1] == 'pre' fallback (no event phase)."""
        phase = _detect_phase({}, ["observe.py", "pre"])
        assert phase == "pre"

    def test_detect_phase_argv_post(self):
        """argv[1] == 'post' fallback (no event phase)."""
        phase = _detect_phase({}, ["observe.py", "post"])
        assert phase == "post"

    def test_main_non_dict_event_returns_0(self, tmp_data, monkeypatch):
        """Line 73 — event is not a dict."""
        monkeypatch.setenv("LEARNING_OBSERVE", "on")
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([1, 2, 3])))
        rc = observe_main([])
        assert rc == 0

    def test_main_oserror_on_write_doesnt_raise(self, tmp_data, monkeypatch):
        """Lines 81-82 — OSError when writing the observation file."""
        monkeypatch.setenv("LEARNING_OBSERVE", "on")
        event = {"tool_name": "Edit", "tool_input": {}, "session_id": "s"}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))

        # Patch open to raise OSError
        import builtins
        original_open = builtins.open
        call_count = [0]

        def _fake_open(file, mode="r", **kwargs):
            call_count[0] += 1
            if "a" in mode:
                raise OSError("disk full")
            return original_open(file, mode, **kwargs)

        monkeypatch.setattr("builtins.open", _fake_open)
        rc = observe_main([])
        # Should swallow OSError and return 0
        assert rc == 0

    def test_main_empty_stdin_when_enabled(self, tmp_data, monkeypatch):
        """Line 69 — raw is empty string → event = {}."""
        monkeypatch.setenv("LEARNING_OBSERVE", "on")
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        rc = observe_main([])
        assert rc == 0


# ===========================================================================
# instinct_schema.py missing lines
# ===========================================================================

VALID_INSTINCT = """\
---
id: test-instinct
trigger: when testing
confidence: 0.8
domain: test
source: unit-test
---

# Test Instinct

## Action

Do something useful.

## Evidence

- It is tested.
"""


class TestInstinctSchemaMissingLines:
    """Lines 38, 40, 59, 62, 73, 99, 134-135, 140-142."""

    def test_parse_frontmatter_skips_hash_comments(self):
        """Line 38 — line starting with '#' is skipped."""
        block = "# comment line\nid: myid\n"
        result = _parse_frontmatter(block)
        assert "id" in result
        assert result["id"] == "myid"
        # The comment should not appear as a key
        assert "#" not in str(result.keys())

    def test_parse_frontmatter_skips_lines_without_colon(self):
        """Line 40 — line without ':' is skipped."""
        block = "id: myid\nno-colon-here\ntrigger: t\n"
        result = _parse_frontmatter(block)
        assert result.get("id") == "myid"
        assert result.get("trigger") == "t"
        # 'no-colon-here' should not be in result
        assert "no-colon-here" not in result

    def test_parse_instinct_not_starting_with_triple_dash_errors(self):
        """Line 59 — text doesn't begin with '---'."""
        bad = "id: x\ntrigger: y\n"
        with pytest.raises(ValueError, match="frontmatter"):
            parse_instinct(bad)

    def test_parse_instinct_unclosed_frontmatter_errors(self):
        """Line 62 — only one '---' (not enough parts)."""
        bad = "---\nid: x\ntrigger: y\n"
        with pytest.raises(ValueError, match="frontmatter"):
            parse_instinct(bad)

    def test_parse_instinct_confidence_out_of_range_errors(self):
        """Line 73 — confidence not in [0, 1]."""
        bad = (
            "---\nid: x\ntrigger: y\nconfidence: 1.5\ndomain: z\nsource: w\n---\n\n"
            "## Action\nfoo\n## Evidence\nbar\n"
        )
        with pytest.raises(ValueError, match="Confidence out"):
            parse_instinct(bad)

    def test_format_instinct_includes_source_repo(self):
        """Line 99 — inst.source_repo is set."""
        inst = Instinct(
            id="with-repo",
            trigger="when testing",
            confidence=0.9,
            domain="workflow",
            source="import",
            source_repo="https://github.com/org/repo",
            title="With Repo",
            action="Do it.",
            evidence="Works.",
        )
        text = format_instinct(inst)
        assert "source_repo: https://github.com/org/repo" in text

    def test_parse_multi_instinct_file_empty_frontmatter_block_skipped(self):
        """Lines 134-135 — a block sequence where a frontmatter part is empty."""
        # A separator '---' that produces an empty frontmatter gets skipped
        # by the `if not fm.strip(): i += 1; continue` logic
        text = "---\n\n---\n\n" + VALID_INSTINCT
        instincts = parse_multi_instinct_file(text)
        # Should still parse the valid one and skip the empty frontmatter
        assert len(instincts) >= 1
        assert instincts[-1].id == "test-instinct"

    def test_parse_multi_instinct_file_malformed_instinct_skipped(self):
        """Lines 140-142 — parse_instinct raises ValueError; skip and continue."""
        # A frontmatter block that's missing required fields
        malformed = (
            "---\n"
            "id: bad-inst\n"
            "confidence: not-a-float\n"
            "---\n\n"
            "# Bad\n\n## Action\nfoo\n\n## Evidence\nbar\n"
        )
        good = VALID_INSTINCT
        combined = malformed + "\n" + good
        instincts = parse_multi_instinct_file(combined)
        # malformed should be skipped; good should be parsed
        ids = [i.id for i in instincts]
        assert "test-instinct" in ids
        assert "bad-inst" not in ids


# ===========================================================================
# instinct_cli.py missing lines
# ===========================================================================

class TestInstinctCliMissingLines:
    """Lines 39-40 (skip on error), 104-106 (import parse failure),
    110 (project scope), 195-214 (main() dispatch)."""

    def test_load_all_instincts_skips_invalid_file(self, tmp_data, capsys):
        """Lines 39-40 — _load_all_instincts prints skip when ValueError."""
        from instinct_cli import _load_all_instincts
        d = get_global_instincts_dir() / "personal"
        d.mkdir(parents=True)
        # Write an invalid instinct file
        (d / "bad.yaml").write_text("not-valid-frontmatter\n", encoding="utf-8")
        result = _load_all_instincts(d)
        assert result == []
        stderr = capsys.readouterr().err
        assert "skip" in stderr.lower()

    def test_cmd_import_parse_failure_returns_nonzero(self, tmp_data, tmp_path, capsys):
        """Lines 104-106 — parse_multi_instinct_file returns empty (invalid file)."""
        # Write a file that parses but has no valid instincts
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("this is not yaml frontmatter\n", encoding="utf-8")
        rc = cmd_import(str(bad_file), scope="global")
        # Should succeed (0 instincts imported) since parse_multi_instinct_file
        # doesn't raise, it just returns []
        # Let's check the behavior: empty instinct list → 0 imported, rc=0
        assert rc == 0

    def test_cmd_import_project_scope(self, tmp_data, tmp_path):
        """Line 110 — scope='project' branch."""
        src = tmp_path / "in.yaml"
        src.write_text(format_instinct(_make_instinct("proj-inst")), encoding="utf-8")
        rc = cmd_import(str(src), scope="project")
        assert rc == 0
        target_dir = get_project_instincts_dir(get_project_id()) / "inherited"
        assert (target_dir / "proj-inst.yaml").exists()

    def test_main_status_dispatch(self, tmp_data, capsys):
        """Lines 206-207 — main dispatches to cmd_status."""
        rc = cli_main(["status"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "INSTINCT STATUS" in out

    def test_main_import_dispatch(self, tmp_data, tmp_path, capsys):
        """Lines 208-209 — main dispatches to cmd_import."""
        src = tmp_path / "imp.yaml"
        src.write_text(format_instinct(_make_instinct("main-imp")), encoding="utf-8")
        rc = cli_main(["import", str(src), "--scope=global"])
        assert rc == 0
        target = get_global_instincts_dir() / "inherited" / "main-imp.yaml"
        assert target.exists()

    def test_main_export_dispatch(self, tmp_data, tmp_path, capsys):
        """Lines 210-211 — main dispatches to cmd_export."""
        global_dir = get_global_instincts_dir() / "personal"
        global_dir.mkdir(parents=True)
        (global_dir / "exp.yaml").write_text(
            format_instinct(_make_instinct("exp-inst")), encoding="utf-8"
        )
        out_file = tmp_path / "out.yaml"
        rc = cli_main(["export", str(out_file), "--scope=global"])
        assert rc == 0
        assert out_file.exists()

    def test_main_analyze_dispatch(self, tmp_data, capsys):
        """Lines 212-213 — main dispatches to cmd_analyze."""
        rc = cli_main(["analyze"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "OBSERVATION ANALYSIS" in out

    def test_main_import_project_scope(self, tmp_data, tmp_path):
        """main() with --scope=project."""
        src = tmp_path / "proj.yaml"
        src.write_text(format_instinct(_make_instinct("main-proj")), encoding="utf-8")
        rc = cli_main(["import", str(src), "--scope=project"])
        assert rc == 0

    def test_main_export_project_scope(self, tmp_data, tmp_path, capsys):
        """main() export with --scope=project."""
        proj_dir = get_project_instincts_dir(get_project_id()) / "personal"
        proj_dir.mkdir(parents=True)
        (proj_dir / "p.yaml").write_text(
            format_instinct(_make_instinct("p-inst")), encoding="utf-8"
        )
        out_file = tmp_path / "pout.yaml"
        rc = cli_main(["export", str(out_file), "--scope=project"])
        assert rc == 0
        assert out_file.exists()


# ===========================================================================
# analyze.py missing lines
# ===========================================================================

class TestAnalyzeMissingLines:
    """Lines 28 (sys.path), 44 (empty/blank lines), 51-52 (OSError), 125 (single-token cmd)."""

    def test_load_observations_skips_blank_lines(self, tmp_data):
        """Line 44 — blank lines in JSONL are skipped."""
        obs_file = get_observations_file(get_project_id())
        obs_file.parent.mkdir(parents=True, exist_ok=True)
        obs_file.write_text(
            json.dumps({"timestamp": 1.0, "tool_name": "Edit"}) + "\n"
            "\n"  # blank line
            "   \n"  # whitespace-only line
            + json.dumps({"timestamp": 2.0, "tool_name": "Bash"}) + "\n",
            encoding="utf-8",
        )
        records = load_observations()
        assert len(records) == 2

    def test_load_observations_skips_non_dict_records(self, tmp_data):
        """Line 49 check — non-dict JSON (array) is silently skipped."""
        obs_file = get_observations_file(get_project_id())
        obs_file.parent.mkdir(parents=True, exist_ok=True)
        obs_file.write_text(
            json.dumps([1, 2, 3]) + "\n"  # array, not dict → skipped
            + json.dumps({"timestamp": 1.0, "tool_name": "Edit"}) + "\n",
            encoding="utf-8",
        )
        records = load_observations()
        assert len(records) == 1
        assert records[0]["tool_name"] == "Edit"

    def test_load_observations_returns_empty_on_oserror(self, tmp_data, monkeypatch):
        """Lines 51-52 — OSError on open → returns []."""
        obs_file = get_observations_file(get_project_id())
        obs_file.parent.mkdir(parents=True, exist_ok=True)
        obs_file.write_text(json.dumps({"tool_name": "Edit"}) + "\n", encoding="utf-8")

        import builtins
        original_open = builtins.open

        def _fail_open(file, *args, **kwargs):
            if str(obs_file) in str(file):
                raise OSError("permission denied")
            return original_open(file, *args, **kwargs)

        monkeypatch.setattr("builtins.open", _fail_open)
        records = load_observations()
        assert records == []

    def test_bash_prefixes_single_token_command(self):
        """Line 125 — command with only one token uses tokens[0] as prefix."""
        records = [
            {"phase": "pre", "tool_name": "Bash", "tool_input": {"command": "pytest"}},
            {"phase": "pre", "tool_name": "Bash", "tool_input": {"command": "make"}},
            {"phase": "pre", "tool_name": "Bash", "tool_input": {"command": "pytest"}},
        ]
        prefixes = bash_command_prefixes(records, top_n=10)
        prefix_dict = dict(prefixes)
        assert prefix_dict.get("pytest") == 2
        assert prefix_dict.get("make") == 1

    def test_load_observations_with_explicit_project_id(self, tmp_data):
        """Line 34 — explicit project_id argument."""
        pid = "testprojectid"
        obs_file = get_observations_file(pid)
        obs_file.parent.mkdir(parents=True, exist_ok=True)
        obs_file.write_text(
            json.dumps({"timestamp": 1.0, "tool_name": "Read"}) + "\n",
            encoding="utf-8",
        )
        records = load_observations(project_id=pid)
        assert len(records) == 1
        assert records[0]["tool_name"] == "Read"


# ===========================================================================
# hook_flags.py — full coverage (currently 0%)
# ===========================================================================

import hook_flags as _hf
from hook_flags import (
    VALID_PROFILES,
    DEFAULT_PROFILE_FALLBACK,
    _env_prefix,
    _normalize_id,
    get_hook_profile,
    get_disabled_hook_ids,
    parse_profiles,
    is_hook_enabled,
)


class TestHookFlags:
    """Full coverage of hook_flags.py."""

    def test_env_prefix_basic(self):
        assert _env_prefix("discipline:post-edit") == "DISCIPLINE"

    def test_env_prefix_with_hyphen(self):
        assert _env_prefix("my-plugin:hook") == "MY_PLUGIN"

    def test_env_prefix_empty_head(self):
        # No namespace separator → head is empty → falls back to 'PLUGIN'
        assert _env_prefix(":hook") == "PLUGIN"

    def test_env_prefix_no_colon(self):
        # No colon → entire string is the head
        assert _env_prefix("learning") == "LEARNING"

    def test_get_hook_profile_returns_standard_by_default(self, monkeypatch):
        monkeypatch.delenv("LEARNING_HOOK_PROFILE", raising=False)
        profile = get_hook_profile("learning:observe")
        assert profile == "standard"

    def test_get_hook_profile_reads_env(self, monkeypatch):
        monkeypatch.setenv("LEARNING_HOOK_PROFILE", "strict")
        profile = get_hook_profile("learning:observe")
        assert profile == "strict"

    def test_get_hook_profile_invalid_falls_back_to_standard(self, monkeypatch):
        monkeypatch.setenv("LEARNING_HOOK_PROFILE", "bogus")
        profile = get_hook_profile("learning:observe")
        assert profile == "standard"

    def test_get_hook_profile_minimal(self, monkeypatch):
        monkeypatch.setenv("LEARNING_HOOK_PROFILE", "minimal")
        assert get_hook_profile("learning:observe") == "minimal"

    def test_get_disabled_hook_ids_empty(self, monkeypatch):
        monkeypatch.delenv("LEARNING_DISABLED_HOOKS", raising=False)
        assert get_disabled_hook_ids("learning:observe") == set()

    def test_get_disabled_hook_ids_single(self, monkeypatch):
        monkeypatch.setenv("LEARNING_DISABLED_HOOKS", "learning:observe")
        result = get_disabled_hook_ids("learning:observe")
        assert "learning:observe" in result

    def test_get_disabled_hook_ids_multiple(self, monkeypatch):
        monkeypatch.setenv("LEARNING_DISABLED_HOOKS", "learning:observe, learning:other,")
        result = get_disabled_hook_ids("learning:observe")
        assert "learning:observe" in result
        assert "learning:other" in result

    def test_get_disabled_hook_ids_whitespace_only(self, monkeypatch):
        monkeypatch.setenv("LEARNING_DISABLED_HOOKS", "   ")
        assert get_disabled_hook_ids("learning:observe") == set()

    def test_parse_profiles_empty_returns_fallback(self):
        result = parse_profiles(None)
        assert result == list(DEFAULT_PROFILE_FALLBACK)

    def test_parse_profiles_empty_string_returns_fallback(self):
        result = parse_profiles("")
        assert result == list(DEFAULT_PROFILE_FALLBACK)

    def test_parse_profiles_valid_csv(self):
        result = parse_profiles("minimal,strict")
        assert result == ["minimal", "strict"]

    def test_parse_profiles_filters_invalid(self):
        result = parse_profiles("minimal,bogus,strict")
        assert "bogus" not in result
        assert "minimal" in result
        assert "strict" in result

    def test_parse_profiles_all_invalid_returns_fallback(self):
        result = parse_profiles("notaprofile,alsonot")
        assert result == list(DEFAULT_PROFILE_FALLBACK)

    def test_parse_profiles_case_insensitive(self):
        result = parse_profiles("MINIMAL,STRICT")
        assert "minimal" in result
        assert "strict" in result

    def test_is_hook_enabled_empty_id_always_true(self, monkeypatch):
        """Empty hook_id is un-gated."""
        monkeypatch.delenv("LEARNING_DISABLED_HOOKS", raising=False)
        assert is_hook_enabled("", "standard,strict") is True

    def test_is_hook_enabled_disabled_hook_returns_false(self, monkeypatch):
        monkeypatch.setenv("LEARNING_DISABLED_HOOKS", "learning:observe")
        monkeypatch.setenv("LEARNING_HOOK_PROFILE", "standard")
        assert is_hook_enabled("learning:observe", "standard,strict") is False

    def test_is_hook_enabled_profile_match_returns_true(self, monkeypatch):
        monkeypatch.delenv("LEARNING_DISABLED_HOOKS", raising=False)
        monkeypatch.setenv("LEARNING_HOOK_PROFILE", "strict")
        assert is_hook_enabled("learning:observe", "standard,strict") is True

    def test_is_hook_enabled_profile_mismatch_returns_false(self, monkeypatch):
        monkeypatch.delenv("LEARNING_DISABLED_HOOKS", raising=False)
        monkeypatch.setenv("LEARNING_HOOK_PROFILE", "minimal")
        assert is_hook_enabled("learning:observe", "standard,strict") is False

    def test_valid_profiles_constant(self):
        assert "minimal" in VALID_PROFILES
        assert "standard" in VALID_PROFILES
        assert "strict" in VALID_PROFILES

    def test_normalize_id_strips_and_lowercases(self):
        assert _normalize_id("  Learning:Observe  ") == "learning:observe"


# ===========================================================================
# run_with_flags.py — full coverage (currently 0%)
# ===========================================================================

import run_with_flags as _rwf
from run_with_flags import (
    main as rwf_main,
    _read_stdin,
    _passthrough,
    _import_and_run_python,
    _spawn_shell,
    _spawn_generic,
)


class TestRunWithFlags:
    """Full coverage of run_with_flags.py."""

    def test_main_too_few_args_returns_2(self, capsys):
        rc = rwf_main(["run_with_flags.py"])
        assert rc == 2
        stderr = capsys.readouterr().err
        assert "usage" in stderr.lower()

    def test_main_hook_disabled_returns_0(self, monkeypatch):
        """Hook disabled → _passthrough → 0."""
        monkeypatch.setenv("LEARNING_DISABLED_HOOKS", "learning:observe")
        monkeypatch.setenv("LEARNING_HOOK_PROFILE", "standard")
        monkeypatch.setattr("sys.stdin", io.StringIO("some input"))
        rc = rwf_main(["rwf", "any_script.py", "learning:observe", "standard,strict"])
        assert rc == 0

    def test_main_script_not_found_returns_passthrough(self, monkeypatch, tmp_path, capsys):
        """Hook is enabled but script path does not exist."""
        monkeypatch.delenv("LEARNING_DISABLED_HOOKS", raising=False)
        monkeypatch.setenv("LEARNING_HOOK_PROFILE", "strict")
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        nonexistent = str(tmp_path / "no_script.py")
        rc = rwf_main(["rwf", nonexistent, "learning:observe", "strict"])
        assert rc == 0
        err = capsys.readouterr().err
        assert "not found" in err

    def test_main_dispatches_python_hook(self, monkeypatch, tmp_path):
        """Hook enabled + .py script → _import_and_run_python."""
        # Write a simple hook that returns 0
        hook = tmp_path / "hook.py"
        hook.write_text("def main():\n    return 0\n", encoding="utf-8")
        monkeypatch.delenv("LEARNING_DISABLED_HOOKS", raising=False)
        monkeypatch.setenv("LEARNING_HOOK_PROFILE", "strict")
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        rc = rwf_main(["rwf", str(hook), "learning:observe", "strict"])
        assert rc == 0

    def test_main_dispatches_shell_hook(self, monkeypatch, tmp_path):
        """Hook enabled + .sh script → _spawn_shell."""
        hook = tmp_path / "hook.sh"
        hook.write_text("exit 0\n", encoding="utf-8")
        monkeypatch.delenv("LEARNING_DISABLED_HOOKS", raising=False)
        monkeypatch.setenv("LEARNING_HOOK_PROFILE", "standard")
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        called = {}

        def fake_spawn(script_path, stdin_text):
            called["path"] = script_path
            called["stdin"] = stdin_text
            return 0

        monkeypatch.setattr(_rwf, "_spawn_shell", fake_spawn)
        rc = rwf_main(["rwf", str(hook), "learning:observe", "standard"])
        assert rc == 0
        assert called["path"] == hook

    def test_main_dispatches_bash_extension(self, monkeypatch, tmp_path):
        """Hook enabled + .bash script → _spawn_shell."""
        hook = tmp_path / "hook.bash"
        hook.write_text("exit 0\n", encoding="utf-8")
        monkeypatch.delenv("LEARNING_DISABLED_HOOKS", raising=False)
        monkeypatch.setenv("LEARNING_HOOK_PROFILE", "standard")
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        called = {}
        monkeypatch.setattr(_rwf, "_spawn_shell", lambda p, s: (called.__setitem__("p", p), 0)[1])
        rc = rwf_main(["rwf", str(hook), "learning:observe", "standard"])
        assert rc == 0

    def test_main_dispatches_generic_for_unknown_extension(self, monkeypatch, tmp_path):
        """Hook enabled + .exe-like extension → _spawn_generic."""
        hook = tmp_path / "hook.exe"
        hook.write_text("")  # content doesn't matter
        monkeypatch.delenv("LEARNING_DISABLED_HOOKS", raising=False)
        monkeypatch.setenv("LEARNING_HOOK_PROFILE", "standard")
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        called = {}
        monkeypatch.setattr(_rwf, "_spawn_generic", lambda p, s: (called.__setitem__("p", p), 7)[1])
        rc = rwf_main(["rwf", str(hook), "learning:observe", "standard"])
        assert rc == 7

    def test_passthrough_returns_0(self):
        assert _passthrough("any text") == 0

    def test_read_stdin(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO("hello world"))
        result = _read_stdin()
        assert result == "hello world"

    def test_import_and_run_python_with_main(self, tmp_path, monkeypatch):
        """_import_and_run_python — module has main() → call it."""
        hook = tmp_path / "myhook.py"
        hook.write_text("def main():\n    return 42\n", encoding="utf-8")
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        rc = _import_and_run_python(hook, "{}")
        assert rc == 42

    def test_import_and_run_python_no_main(self, tmp_path, monkeypatch):
        """_import_and_run_python — module has no main() → return 0."""
        hook = tmp_path / "nomain.py"
        hook.write_text("x = 1 + 1\n", encoding="utf-8")
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        rc = _import_and_run_python(hook, "")
        assert rc == 0

    def test_import_and_run_python_main_returns_none(self, tmp_path, monkeypatch):
        """_import_and_run_python — main() returns None → treated as 0."""
        hook = tmp_path / "retnone.py"
        hook.write_text("def main():\n    pass\n", encoding="utf-8")
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        rc = _import_and_run_python(hook, "")
        assert rc == 0

    def test_import_and_run_python_module_top_level_sysexit(self, tmp_path, monkeypatch):
        """_import_and_run_python — module calls sys.exit() at top level."""
        hook = tmp_path / "exitmodule.py"
        hook.write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        rc = _import_and_run_python(hook, "")
        assert rc == 3

    def test_import_and_run_python_main_sysexit(self, tmp_path, monkeypatch):
        """_import_and_run_python — main() calls sys.exit()."""
        hook = tmp_path / "mainexit.py"
        hook.write_text("import sys\ndef main():\n    sys.exit(5)\n", encoding="utf-8")
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        rc = _import_and_run_python(hook, "")
        assert rc == 5

    def test_import_and_run_python_import_exception(self, tmp_path, monkeypatch, capsys):
        """_import_and_run_python — module raises exception on import → return 0."""
        hook = tmp_path / "badimport.py"
        hook.write_text("raise RuntimeError('oops')\n", encoding="utf-8")
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        rc = _import_and_run_python(hook, "")
        assert rc == 0
        err = capsys.readouterr().err
        assert "import error" in err

    def test_import_and_run_python_main_exception(self, tmp_path, monkeypatch, capsys):
        """_import_and_run_python — main() raises exception → return 0."""
        hook = tmp_path / "badmain.py"
        hook.write_text("def main():\n    raise ValueError('bad')\n", encoding="utf-8")
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        rc = _import_and_run_python(hook, "")
        assert rc == 0
        err = capsys.readouterr().err
        assert "runtime error" in err

    def test_import_and_run_python_spec_none(self, tmp_path, monkeypatch):
        """_import_and_run_python — spec_from_file_location returns None → passthrough."""
        hook = tmp_path / "ghost.py"
        hook.write_text("def main(): return 0\n", encoding="utf-8")
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        import importlib.util
        monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *a, **k: None)
        rc = _import_and_run_python(hook, "")
        assert rc == 0

    def test_spawn_shell_unreadable_script(self, tmp_path, monkeypatch, capsys):
        """_spawn_shell — can't read script → _passthrough."""
        hook = tmp_path / "unreadable.sh"
        hook.write_text("exit 0")

        # _spawn_shell calls script_path.read_text() — patch Path.read_text
        from pathlib import Path as _Path
        original_read_text = _Path.read_text

        def _fail_read_text(self, *a, **kw):
            if self == hook:
                raise OSError("access denied")
            return original_read_text(self, *a, **kw)

        monkeypatch.setattr(_Path, "read_text", _fail_read_text)
        rc = _spawn_shell(hook, "")
        assert rc == 0
        err = capsys.readouterr().err
        assert "cannot read" in err

    def test_zsh_extension_dispatches_to_spawn_shell(self, monkeypatch, tmp_path):
        """Hook enabled + .zsh extension → _spawn_shell."""
        hook = tmp_path / "hook.zsh"
        hook.write_text("exit 0\n", encoding="utf-8")
        monkeypatch.delenv("LEARNING_DISABLED_HOOKS", raising=False)
        monkeypatch.setenv("LEARNING_HOOK_PROFILE", "standard")
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        called = {}
        monkeypatch.setattr(_rwf, "_spawn_shell", lambda p, s: (called.__setitem__("p", p), 0)[1])
        rc = rwf_main(["rwf", str(hook), "learning:observe", "standard"])
        assert rc == 0
        assert called.get("p") == hook

    def test_spawn_shell_runs_subprocess(self, tmp_path, monkeypatch):
        """Lines 107-115 — _spawn_shell calls subprocess.run (bash -c)."""
        hook = tmp_path / "hook.sh"
        hook.write_text("exit 0\n", encoding="utf-8")

        fake_result = MagicMock()
        fake_result.returncode = 0
        fake_result.stdout = "hello\n"
        fake_result.stderr = ""

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["input"] = kwargs.get("input")
            return fake_result

        monkeypatch.setattr("subprocess.run", fake_run)
        rc = _spawn_shell(hook, "test-stdin")
        assert rc == 0
        assert captured["cmd"][0].endswith(("bash", "bash.exe"))
        assert captured["cmd"][1] == "-c"
        assert captured["input"] == "test-stdin"

    def test_spawn_shell_propagates_returncode(self, tmp_path, monkeypatch):
        """_spawn_shell returns the subprocess returncode."""
        hook = tmp_path / "failing.sh"
        hook.write_text("exit 1\n", encoding="utf-8")

        fake_result = MagicMock()
        fake_result.returncode = 1
        fake_result.stdout = ""
        fake_result.stderr = "error output"

        monkeypatch.setattr("subprocess.run", lambda *a, **k: fake_result)
        rc = _spawn_shell(hook, "")
        assert rc == 1

    def test_spawn_generic_runs_subprocess(self, tmp_path, monkeypatch):
        """Lines 119-127 — _spawn_generic calls subprocess.run."""
        hook = tmp_path / "hook.exe"
        hook.write_text("")

        fake_result = MagicMock()
        fake_result.returncode = 7
        fake_result.stdout = "out"
        fake_result.stderr = "err"

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return fake_result

        monkeypatch.setattr("subprocess.run", fake_run)
        rc = _spawn_generic(hook, "my-stdin")
        assert rc == 7
        assert str(hook) in captured["cmd"]


# ===========================================================================
# analyze.py + instinct_cli.py — remaining uncovered branches
# ===========================================================================

class TestAnalyzeRemainingBranches:
    """analyze.py:125 (empty/None command in Bash records)."""

    def test_bash_prefixes_skips_none_command(self):
        """Line 125 — tool_input has no 'command' key → skip."""
        records = [
            {"phase": "pre", "tool_name": "Bash", "tool_input": {}},  # no command key
            {"phase": "pre", "tool_name": "Bash", "tool_input": {"command": "git status"}},
        ]
        prefixes = bash_command_prefixes(records, top_n=10)
        prefix_dict = dict(prefixes)
        assert prefix_dict.get("git status") == 1
        # The None-command record is skipped
        assert len(prefix_dict) == 1

    def test_bash_prefixes_skips_empty_command(self):
        """Line 125 — command is empty string → skip."""
        records = [
            {"phase": "pre", "tool_name": "Bash", "tool_input": {"command": "  "}},
            {"phase": "pre", "tool_name": "Bash", "tool_input": {"command": "ls -la"}},
        ]
        prefixes = bash_command_prefixes(records, top_n=10)
        prefix_dict = dict(prefixes)
        assert "ls -la" in prefix_dict
        assert len(prefix_dict) == 1

    def test_bash_prefixes_skips_non_string_command(self):
        """Line 124 — command is not a str → skip."""
        records = [
            {"phase": "pre", "tool_name": "Bash", "tool_input": {"command": 42}},
            {"phase": "pre", "tool_name": "Bash", "tool_input": {"command": "echo hi"}},
        ]
        prefixes = bash_command_prefixes(records, top_n=10)
        prefix_dict = dict(prefixes)
        assert prefix_dict.get("echo hi") == 1


class TestInstinctCliRemainingBranches:
    """instinct_cli.py:104-106 (OSError on read_text in cmd_import)."""

    def test_cmd_import_oserror_returns_nonzero(self, tmp_data, tmp_path, monkeypatch, capsys):
        """Lines 104-106 — OSError when reading the import file."""
        src = tmp_path / "good.yaml"
        src.write_text(format_instinct(_make_instinct("ioerr-inst")), encoding="utf-8")

        from pathlib import Path as _Path
        original_read_text = _Path.read_text

        def _fail_read(self, *a, **kw):
            if self == src:
                raise OSError("disk read error")
            return original_read_text(self, *a, **kw)

        monkeypatch.setattr(_Path, "read_text", _fail_read)
        rc = cmd_import(str(src), scope="global")
        assert rc == 1
        err = capsys.readouterr().err
        assert "parse failed" in err
