# plugins/discipline/tests/test_pitfalls_pointer.py
"""Unit tests for hooks/pitfalls_pointer.py."""
from __future__ import annotations

import io
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitfalls_pointer import resolve_area, main
from discipline_config import DisciplineConfig


# ---------------------------------------------------------------------------
# resolve_area()
# ---------------------------------------------------------------------------

class TestResolveArea:
    def test_exact_match(self):
        routes = {"src/dm.ts": "dm-cycle", "src/llm/": "llm-classifier"}
        assert resolve_area("src/dm.ts", routes) == "dm-cycle"

    def test_prefix_match(self):
        routes = {"src/llm/": "llm-classifier"}
        assert resolve_area("src/llm/foo.ts", routes) == "llm-classifier"

    def test_no_match_returns_none(self):
        routes = {"src/dm.ts": "dm-cycle"}
        assert resolve_area("src/other.ts", routes) is None

    def test_exact_wins_over_prefix(self):
        routes = {"src/dm.ts": "exact-area", "src/": "prefix-area"}
        assert resolve_area("src/dm.ts", routes) == "exact-area"

    def test_longest_prefix_wins(self):
        routes = {"src/": "short", "src/llm/": "long"}
        assert resolve_area("src/llm/classifier.ts", routes) == "long"

    def test_non_trailing_slash_not_treated_as_prefix(self):
        routes = {"src/dm": "dm-cycle"}
        assert resolve_area("src/dm/foo.ts", routes) is None

    def test_empty_routes_returns_none(self):
        assert resolve_area("src/foo.ts", {}) is None

    def test_empty_path_no_prefix_match(self):
        routes = {"src/": "area"}
        assert resolve_area("", routes) is None

    def test_multiple_prefixes_longest_wins(self):
        routes = {
            "docs/": "docs-area",
            "docs/adr/": "adr-area",
            "docs/adr/decisions/": "decisions-area",
        }
        assert resolve_area("docs/adr/decisions/001.md", routes) == "decisions-area"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cfg(tmp_path: Path, pitfalls_root: str | None = None, routes: dict | None = None):
    """Return a DisciplineConfig with a controlled repo_root."""
    return DisciplineConfig(
        repo_root=tmp_path,
        pitfalls_root=pitfalls_root,
        pitfalls_routes=routes or {},
    )


def _run_main_with_cfg(monkeypatch, payload: dict, cfg: DisciplineConfig, capsys=None) -> int:
    """Patch get_config to return cfg, feed stdin, call main()."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    import pitfalls_pointer
    with patch("pitfalls_pointer.get_config", return_value=cfg):
        return pitfalls_pointer.main()


# ---------------------------------------------------------------------------
# main() / stdin path
# ---------------------------------------------------------------------------

class TestMain:
    def test_malformed_stdin_passes(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
        cfg = _make_cfg(tmp_path)
        import pitfalls_pointer
        with patch("pitfalls_pointer.get_config", return_value=cfg):
            assert pitfalls_pointer.main() == 0

    def test_no_pitfalls_root_configured_silent(self, monkeypatch, tmp_path):
        cfg = _make_cfg(tmp_path, pitfalls_root=None, routes={"src/dm.ts": "dm-cycle"})
        rc = _run_main_with_cfg(monkeypatch, {"tool_input": {"file_path": "src/dm.ts"}}, cfg)
        assert rc == 0

    def test_no_pitfalls_routes_configured_silent(self, monkeypatch, tmp_path):
        cfg = _make_cfg(tmp_path, pitfalls_root="docs/pitfalls", routes={})
        rc = _run_main_with_cfg(monkeypatch, {"tool_input": {"file_path": "src/dm.ts"}}, cfg)
        assert rc == 0

    def test_no_file_path_silent(self, monkeypatch, tmp_path):
        cfg = _make_cfg(tmp_path, pitfalls_root="docs/pitfalls", routes={"src/dm.ts": "dm-cycle"})
        rc = _run_main_with_cfg(monkeypatch, {"tool_input": {}}, cfg)
        assert rc == 0

    def test_no_matching_route_silent(self, monkeypatch, tmp_path, capsys):
        cfg = _make_cfg(tmp_path, pitfalls_root="docs/pitfalls", routes={"src/dm.ts": "dm-cycle"})
        src_file = tmp_path / "src" / "other.ts"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("code", encoding="utf-8")
        rc = _run_main_with_cfg(monkeypatch, {"tool_input": {"file_path": str(src_file)}}, cfg)
        assert rc == 0
        assert capsys.readouterr().out == ""

    def test_matching_exact_route_prints_pointer(self, monkeypatch, tmp_path, capsys):
        cfg = _make_cfg(tmp_path, pitfalls_root="docs/pitfalls", routes={"src/dm.ts": "dm-cycle"})
        src_file = tmp_path / "src" / "dm.ts"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("code", encoding="utf-8")
        rc = _run_main_with_cfg(monkeypatch, {"tool_input": {"file_path": str(src_file)}}, cfg)
        assert rc == 0
        out = capsys.readouterr().out
        assert "[pitfalls]" in out
        assert "dm-cycle.md" in out

    def test_prefix_route_match_prints_pointer(self, monkeypatch, tmp_path, capsys):
        cfg = _make_cfg(tmp_path, pitfalls_root="docs/pitfalls", routes={"src/llm/": "llm-classifier"})
        src_file = tmp_path / "src" / "llm" / "classifier.ts"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("code", encoding="utf-8")
        rc = _run_main_with_cfg(monkeypatch, {"tool_input": {"file_path": str(src_file)}}, cfg)
        assert rc == 0
        out = capsys.readouterr().out
        assert "llm-classifier.md" in out

    def test_pitfalls_root_trailing_slash_stripped(self, monkeypatch, tmp_path, capsys):
        cfg = _make_cfg(tmp_path, pitfalls_root="docs/pitfalls/", routes={"src/dm.ts": "dm-cycle"})
        src_file = tmp_path / "src" / "dm.ts"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("code", encoding="utf-8")
        rc = _run_main_with_cfg(monkeypatch, {"tool_input": {"file_path": str(src_file)}}, cfg)
        assert rc == 0
        out = capsys.readouterr().out
        assert "docs/pitfalls/dm-cycle.md" in out

    def test_tool_response_file_path_used(self, monkeypatch, tmp_path, capsys):
        cfg = _make_cfg(tmp_path, pitfalls_root="docs/pitfalls", routes={"src/dm.ts": "dm-cycle"})
        src_file = tmp_path / "src" / "dm.ts"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("code", encoding="utf-8")
        rc = _run_main_with_cfg(monkeypatch, {"tool_response": {"filePath": str(src_file)}}, cfg)
        assert rc == 0
        out = capsys.readouterr().out
        assert "[pitfalls]" in out

    def test_pointer_line_format(self, monkeypatch, tmp_path, capsys):
        """Full format: [pitfalls] you edited <path>; relevant pitfalls live in <root>/<area>.md"""
        cfg = _make_cfg(tmp_path, pitfalls_root="docs/pitfalls", routes={"src/dm.ts": "dm-cycle"})
        src_file = tmp_path / "src" / "dm.ts"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("code", encoding="utf-8")
        rc = _run_main_with_cfg(monkeypatch, {"tool_input": {"file_path": str(src_file)}}, cfg)
        assert rc == 0
        out = capsys.readouterr().out
        assert "you edited" in out
        assert "relevant pitfalls live in" in out
