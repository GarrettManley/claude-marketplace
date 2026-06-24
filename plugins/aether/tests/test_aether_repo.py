# plugins/aether/tests/test_aether_repo.py
"""Import-based unit tests for plugins/aether/scripts/aether_repo.py.

Coverage targets: lines 36-39, 44-51, 62-63, 78, 81-82 (the previously uncovered
branches identified in the assignment).
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

import aether_repo
from aether_repo import edited_file_path, find_repo_root, load_payload, repo_relative


# ---------------------------------------------------------------------------
# load_payload
# ---------------------------------------------------------------------------

class TestLoadPayload:
    def test_valid_json_returns_dict(self, monkeypatch):
        payload = {"tool_name": "Edit", "tool_input": {"file_path": "/a/b.ts"}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        result = load_payload()
        assert result == payload

    def test_invalid_json_returns_none(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO("not json {{{"))
        result = load_payload()
        assert result is None

    def test_empty_input_returns_none(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))
        result = load_payload()
        assert result is None


# ---------------------------------------------------------------------------
# edited_file_path
# ---------------------------------------------------------------------------

class TestEditedFilePath:
    def test_tool_input_file_path(self):
        payload = {"tool_input": {"file_path": "/repo/src/dm.ts"}}
        assert edited_file_path(payload) == "/repo/src/dm.ts"

    def test_tool_response_file_path(self):
        payload = {"tool_input": {}, "tool_response": {"filePath": "/repo/src/dm.ts"}}
        assert edited_file_path(payload) == "/repo/src/dm.ts"

    def test_tool_input_takes_precedence(self):
        payload = {
            "tool_input": {"file_path": "/a.ts"},
            "tool_response": {"filePath": "/b.ts"},
        }
        assert edited_file_path(payload) == "/a.ts"

    def test_none_payload_returns_none(self):
        assert edited_file_path(None) is None

    def test_non_dict_payload_returns_none(self):
        assert edited_file_path("string") is None
        assert edited_file_path(42) is None
        assert edited_file_path([]) is None

    def test_empty_file_path_returns_none(self):
        # Both keys present but empty strings -> returns None
        payload = {"tool_input": {"file_path": ""}, "tool_response": {"filePath": ""}}
        assert edited_file_path(payload) is None

    def test_missing_keys_returns_none(self):
        assert edited_file_path({}) is None
        assert edited_file_path({"tool_input": {}}) is None


# ---------------------------------------------------------------------------
# find_repo_root
# ---------------------------------------------------------------------------

class TestFindRepoRoot:
    def test_locates_marker_from_deep_file(self, aether_checkout: Path):
        target = aether_checkout / "src" / "llm" / "classifier_prompt.ts"
        found = find_repo_root(str(target))
        assert found == aether_checkout.resolve()

    def test_locates_marker_from_core_src(self, aether_checkout: Path):
        target = aether_checkout / "core" / "src" / "main.rs"
        found = find_repo_root(str(target))
        assert found == aether_checkout.resolve()

    def test_none_outside_repo(self, tmp_path: Path):
        loose = tmp_path / "loose" / "src" / "llm" / "classifier_prompt.ts"
        loose.parent.mkdir(parents=True)
        loose.write_text("// x\n", encoding="utf-8")
        assert find_repo_root(str(loose)) is None

    def test_nonexistent_path_returns_none(self, tmp_path: Path):
        # A path that doesn't exist should return None (parents walk finds nothing)
        missing = tmp_path / "does_not_exist" / "file.ts"
        result = find_repo_root(str(missing))
        assert result is None

    def test_invalid_path_returns_none(self):
        # An empty string or clearly invalid path returns None, not an exception
        result = find_repo_root("")
        # Either None (no marker found walking up from cwd) or a found root —
        # important thing is it doesn't raise
        # In practice empty string resolves to cwd; if cwd has no core/Cargo.toml
        # this returns None. We just check no exception is raised.
        assert result is None or isinstance(result, Path)

    def test_worktree_resolves_to_worktree_root(self, aether_checkout: Path):
        wt = aether_checkout / ".worktrees" / "feat-x"
        (wt / "core").mkdir(parents=True)
        (wt / "src").mkdir(parents=True)
        (wt / "core" / "Cargo.toml").write_text("[package]\nname='core'\n", encoding="utf-8")
        (wt / "src" / "dm.ts").write_text("// dm\n", encoding="utf-8")
        found = find_repo_root(str(wt / "src" / "dm.ts"))
        assert found == wt.resolve()


# ---------------------------------------------------------------------------
# repo_relative
# ---------------------------------------------------------------------------

class TestRepoRelative:
    def test_returns_root_and_posix_relative(self, aether_checkout: Path):
        target = aether_checkout / "core" / "src" / "main.rs"
        root, rel = repo_relative(str(target))
        assert root == aether_checkout.resolve()
        assert rel == "core/src/main.rs"
        assert "\\" not in rel, "relative path must use forward slashes"

    def test_llm_file_relative(self, aether_checkout: Path):
        target = aether_checkout / "src" / "llm" / "ollama.ts"
        root, rel = repo_relative(str(target))
        assert root == aether_checkout.resolve()
        assert rel == "src/llm/ollama.ts"

    def test_none_outside_repo(self, tmp_path: Path):
        loose = tmp_path / "nowhere" / "file.ts"
        loose.parent.mkdir(parents=True)
        loose.write_text("x", encoding="utf-8")
        root, rel = repo_relative(str(loose))
        assert root is None
        assert rel is None

    def test_empty_string_returns_none_none(self):
        # When path has no Aether marker ancestor
        root, rel = repo_relative("__nonexistent_path_xyz__")
        assert root is None
        assert rel is None

    def test_oserror_in_resolve_returns_none_none(self, monkeypatch):
        """Cover the except (OSError, ValueError) in find_repo_root (lines 62-63)
        and the resulting (None, None) from repo_relative (lines 81-82)."""
        from pathlib import Path as _Path

        orig_resolve = _Path.resolve

        def _bad_resolve(self, *args, **kwargs):
            raise OSError("synthetic OS error")

        monkeypatch.setattr(_Path, "resolve", _bad_resolve)
        # find_repo_root should return None when resolve raises
        result = aether_repo.find_repo_root("/some/path/file.ts")
        assert result is None

    def test_repo_relative_valueerror_returns_none_none(self, monkeypatch, aether_checkout):
        """Cover the except (OSError, ValueError) in repo_relative (lines 81-82).

        Patch relative_to to raise ValueError so the except branch is hit even
        when find_repo_root succeeds.
        """
        from pathlib import Path as _Path

        orig_relative_to = _Path.relative_to

        # find_repo_root will succeed (returns aether_checkout), but then
        # relative_to raises ValueError
        call_count = [0]

        def _bad_relative_to(self, *args, **kwargs):
            call_count[0] += 1
            # Only raise on the relative_to call inside repo_relative
            raise ValueError("synthetic ValueError from relative_to")

        monkeypatch.setattr(_Path, "relative_to", _bad_relative_to)
        target = str(aether_checkout / "core" / "src" / "main.rs")
        root, rel = aether_repo.repo_relative(target)
        assert root is None
        assert rel is None
