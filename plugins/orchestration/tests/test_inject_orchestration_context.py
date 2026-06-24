# plugins/orchestration/tests/test_inject_orchestration_context.py
"""Unit tests for the inject_orchestration_context SessionStart hook.

The module is imported directly so coverage counts every executed line.
All tests are hermetic — they do not require network access or external
processes.
"""
import importlib
import io
import json
import sys
from pathlib import Path

import pytest

import inject_orchestration_context as ioc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REAL_CONTEXT_FILE = (
    Path(__file__).resolve().parent.parent / "context" / "agent-orchestration.md"
)


def _run_main_captured(monkeypatch) -> tuple[int, str]:
    """Run main(), capturing stdout; return (exit_code, stdout_text)."""
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    rc = ioc.main()
    return rc, buf.getvalue()


# ---------------------------------------------------------------------------
# strip_frontmatter
# ---------------------------------------------------------------------------


class TestStripFrontmatter:
    def test_no_frontmatter_returned_as_is(self):
        text = "# Hello\n\nsome body"
        assert ioc.strip_frontmatter(text) == text

    def test_frontmatter_removed(self):
        text = "---\ntitle: foo\nalways: true\n---\n# Body\n\ncontent"
        result = ioc.strip_frontmatter(text)
        assert result == "# Body\n\ncontent"
        assert "title: foo" not in result

    def test_frontmatter_with_leading_newlines_stripped(self):
        text = "---\nkey: val\n---\n\n\n# Real content"
        result = ioc.strip_frontmatter(text)
        assert result == "# Real content"

    def test_unclosed_frontmatter_returned_as_is(self):
        # Opening --- but no closing --- -> treated as plain text
        text = "---\ntitle: foo\nno closing delimiter"
        assert ioc.strip_frontmatter(text) == text

    def test_empty_frontmatter_block(self):
        text = "---\n---\n# After"
        result = ioc.strip_frontmatter(text)
        assert "After" in result
        assert "---" not in result

    def test_non_frontmatter_starting_with_dashes(self):
        # Only lines that *start* with --- at position 0 are treated as frontmatter
        text = "Some text\n---\n# After"
        assert ioc.strip_frontmatter(text) == text


# ---------------------------------------------------------------------------
# main() — happy path with the real bundled context file
# ---------------------------------------------------------------------------


class TestMainHappyPath:
    def test_returns_zero(self, monkeypatch):
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        rc = ioc.main()
        assert rc == 0

    def test_emits_valid_json(self, monkeypatch):
        rc, out = _run_main_captured(monkeypatch)
        assert rc == 0
        data = json.loads(out)  # must not raise
        assert "hookSpecificOutput" in data

    def test_hook_event_name_is_session_start(self, monkeypatch):
        _, out = _run_main_captured(monkeypatch)
        data = json.loads(out)
        assert data["hookSpecificOutput"]["hookEventName"] == "SessionStart"

    def test_additional_context_is_non_empty(self, monkeypatch):
        _, out = _run_main_captured(monkeypatch)
        data = json.loads(out)
        body = data["hookSpecificOutput"]["additionalContext"]
        assert body.strip() != ""

    def test_additional_context_contains_orchestration_content(self, monkeypatch):
        _, out = _run_main_captured(monkeypatch)
        data = json.loads(out)
        body = data["hookSpecificOutput"]["additionalContext"]
        # The bundled context file discusses agent/workflow orchestration
        assert "Workflow" in body or "workflow" in body or "agent" in body.lower()

    def test_output_has_no_trailing_whitespace_from_strip(self, monkeypatch):
        _, out = _run_main_captured(monkeypatch)
        data = json.loads(out)
        body = data["hookSpecificOutput"]["additionalContext"]
        # main() calls .strip() so no leading/trailing whitespace
        assert body == body.strip()


# ---------------------------------------------------------------------------
# main() — missing context file (OSError path)
# ---------------------------------------------------------------------------


class TestMainMissingFile:
    def test_missing_file_returns_zero(self, monkeypatch, tmp_path):
        missing = tmp_path / "nonexistent.md"
        monkeypatch.setattr(ioc, "CONTEXT_FILE", missing)
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        rc = ioc.main()
        assert rc == 0

    def test_missing_file_emits_nothing(self, monkeypatch, tmp_path):
        missing = tmp_path / "nonexistent.md"
        monkeypatch.setattr(ioc, "CONTEXT_FILE", missing)
        rc, out = _run_main_captured(monkeypatch)
        assert out == ""


# ---------------------------------------------------------------------------
# main() — empty / blank context file
# ---------------------------------------------------------------------------


class TestMainEmptyFile:
    def test_empty_file_returns_zero(self, monkeypatch, tmp_path):
        empty = tmp_path / "empty.md"
        empty.write_text("", encoding="utf-8")
        monkeypatch.setattr(ioc, "CONTEXT_FILE", empty)
        rc, out = _run_main_captured(monkeypatch)
        assert rc == 0

    def test_empty_file_emits_nothing(self, monkeypatch, tmp_path):
        empty = tmp_path / "empty.md"
        empty.write_text("", encoding="utf-8")
        monkeypatch.setattr(ioc, "CONTEXT_FILE", empty)
        _, out = _run_main_captured(monkeypatch)
        assert out == ""

    def test_whitespace_only_file_emits_nothing(self, monkeypatch, tmp_path):
        blank = tmp_path / "blank.md"
        blank.write_text("   \n\n  \n", encoding="utf-8")
        monkeypatch.setattr(ioc, "CONTEXT_FILE", blank)
        _, out = _run_main_captured(monkeypatch)
        assert out == ""


# ---------------------------------------------------------------------------
# main() — custom context file with frontmatter
# ---------------------------------------------------------------------------


class TestMainCustomContent:
    def test_frontmatter_is_stripped_before_injection(self, monkeypatch, tmp_path):
        ctx = tmp_path / "ctx.md"
        ctx.write_text(
            "---\nalways: true\ntitle: Orch\n---\n# Policy\n\nDelegate by default.",
            encoding="utf-8",
        )
        monkeypatch.setattr(ioc, "CONTEXT_FILE", ctx)
        _, out = _run_main_captured(monkeypatch)
        data = json.loads(out)
        body = data["hookSpecificOutput"]["additionalContext"]
        assert "always: true" not in body
        assert "Policy" in body
        assert "Delegate by default." in body

    def test_plain_content_passes_through_unchanged(self, monkeypatch, tmp_path):
        ctx = tmp_path / "ctx.md"
        ctx.write_text("Just some policy text.", encoding="utf-8")
        monkeypatch.setattr(ioc, "CONTEXT_FILE", ctx)
        _, out = _run_main_captured(monkeypatch)
        data = json.loads(out)
        body = data["hookSpecificOutput"]["additionalContext"]
        assert body == "Just some policy text."

    def test_output_schema_matches_contract(self, monkeypatch, tmp_path):
        """Validate the exact JSON schema the hook promises."""
        ctx = tmp_path / "ctx.md"
        ctx.write_text("policy content", encoding="utf-8")
        monkeypatch.setattr(ioc, "CONTEXT_FILE", ctx)
        _, out = _run_main_captured(monkeypatch)
        data = json.loads(out)
        hso = data["hookSpecificOutput"]
        assert set(hso.keys()) == {"hookEventName", "additionalContext"}
        assert hso["hookEventName"] == "SessionStart"
        assert hso["additionalContext"] == "policy content"
