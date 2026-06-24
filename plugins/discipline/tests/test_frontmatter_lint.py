# plugins/discipline/tests/test_frontmatter_lint.py
"""Unit tests for hooks/frontmatter_lint.py."""
from __future__ import annotations

import io
import json
import sys
from functools import lru_cache
from pathlib import Path

import pytest

from frontmatter_lint import (
    _validate_status,
    _validate_author,
    _validate_date,
    _validate_diataxis,
    _validate_nonempty,
    _validate_true,
    should_skip,
    parse_frontmatter,
    lint,
    emit_warn,
    main,
)


# ---------------------------------------------------------------------------
# Validator unit tests
# ---------------------------------------------------------------------------

class TestValidateStatus:
    def test_valid_draft(self):
        assert _validate_status("draft") is None

    def test_valid_active(self):
        assert _validate_status("active") is None

    def test_valid_superseded(self):
        assert _validate_status("superseded") is None

    def test_case_insensitive(self):
        assert _validate_status("DRAFT") is None
        assert _validate_status("Active") is None

    def test_invalid_returns_message(self):
        err = _validate_status("pending")
        assert err is not None
        assert "pending" in err

    def test_whitespace_stripped(self):
        assert _validate_status("  draft  ") is None


class TestValidateAuthor:
    def test_non_empty_passes(self):
        assert _validate_author("Alice") is None

    def test_empty_fails(self):
        assert _validate_author("") is not None

    def test_whitespace_only_fails(self):
        assert _validate_author("   ") is not None


class TestValidateDate:
    def test_valid_date(self):
        assert _validate_date("2024-01-15") is None

    def test_invalid_format(self):
        err = _validate_date("01/15/2024")
        assert err is not None
        assert "YYYY-MM-DD" in err

    def test_whitespace_stripped(self):
        assert _validate_date("  2024-01-15  ") is None

    def test_partial_date_fails(self):
        assert _validate_date("2024-01") is not None


class TestValidateDiataxis:
    def test_valid_tutorial(self):
        assert _validate_diataxis("tutorial") is None

    def test_valid_how_to(self):
        assert _validate_diataxis("how-to") is None

    def test_valid_reference(self):
        assert _validate_diataxis("reference") is None

    def test_valid_explanation(self):
        assert _validate_diataxis("explanation") is None

    def test_case_insensitive(self):
        assert _validate_diataxis("TUTORIAL") is None

    def test_invalid_returns_message(self):
        err = _validate_diataxis("guide")
        assert err is not None


class TestValidateNonempty:
    def test_non_empty_passes(self):
        assert _validate_nonempty("any value") is None

    def test_empty_fails(self):
        assert _validate_nonempty("") is not None

    def test_whitespace_only_fails(self):
        assert _validate_nonempty("   ") is not None


class TestValidateTrue:
    def test_true_passes(self):
        assert _validate_true("true") is None

    def test_false_fails(self):
        err = _validate_true("false")
        assert err is not None
        assert "true" in err

    def test_case_insensitive_true(self):
        assert _validate_true("TRUE") is None

    def test_non_true_fails(self):
        assert _validate_true("yes") is not None


# ---------------------------------------------------------------------------
# should_skip
# ---------------------------------------------------------------------------

class TestShouldSkip:
    def test_non_docs_path_skipped(self):
        assert should_skip("src/foo.md", ()) is True

    def test_non_md_skipped(self):
        assert should_skip("docs/foo.txt", ()) is True

    def test_docs_md_not_skipped(self):
        assert should_skip("docs/guide.md", ()) is False

    def test_skip_prefix_applied(self):
        assert should_skip("docs/node_modules/foo.md", ("docs/node_modules/",)) is True

    def test_underscore_name_skipped(self):
        assert should_skip("docs/_draft.md", ()) is True

    def test_nested_docs_path_not_skipped(self):
        assert should_skip("docs/adr/001-decision.md", ()) is False

    def test_default_skip_prefixes(self):
        from frontmatter_lint import should_skip
        assert should_skip("docs/node_modules/x.md", ("node_modules/", "dist/")) is False
        # The prefix check uses the relative path directly
        # node_modules/ prefix only matches when path starts with it
        assert should_skip("node_modules/x.md", ("node_modules/",)) is True

    def test_skip_when_path_starts_with_prefix(self):
        assert should_skip("docs/build/output.md", ("docs/build/",)) is True


# ---------------------------------------------------------------------------
# parse_frontmatter
# ---------------------------------------------------------------------------

class TestParseFrontmatter:
    def test_empty_file(self):
        fm, err = parse_frontmatter("")
        assert fm is None
        assert "empty" in err

    def test_no_opening_fence(self):
        fm, err = parse_frontmatter("# Heading\ncontent")
        assert fm is None
        assert "---" in err

    def test_no_closing_fence(self):
        text = "---\nstatus: draft\n" + ("x: y\n" * 28)
        fm, err = parse_frontmatter(text)
        assert fm is None
        assert "close" in err

    def test_valid_frontmatter(self):
        text = "---\nstatus: draft\nauthor: Alice\n---\n# Doc"
        fm, err = parse_frontmatter(text)
        assert err is None
        assert fm == {"status": "draft", "author": "Alice"}

    def test_quoted_values_unwrapped(self):
        text = "---\ntitle: 'My Doc'\ndesc: \"hello world\"\n---"
        fm, err = parse_frontmatter(text)
        assert err is None
        assert fm["title"] == "My Doc"
        assert fm["desc"] == "hello world"

    def test_comments_skipped(self):
        text = "---\n# this is a comment\nstatus: active\n---"
        fm, err = parse_frontmatter(text)
        assert err is None
        assert "status" in fm
        assert "#" not in fm

    def test_blank_lines_skipped(self):
        text = "---\n\nstatus: active\n\n---"
        fm, err = parse_frontmatter(text)
        assert err is None
        assert fm == {"status": "active"}

    def test_indented_lines_skipped(self):
        text = "---\nstatus: active\n  indented: value\n---"
        fm, err = parse_frontmatter(text)
        assert err is None
        assert "indented" not in fm

    def test_lines_without_colon_skipped(self):
        text = "---\nstatus: active\nplain-line\n---"
        fm, err = parse_frontmatter(text)
        assert err is None
        assert "plain-line" not in fm

    def test_value_with_colon(self):
        text = "---\nurl: http://example.com\n---"
        fm, err = parse_frontmatter(text)
        assert err is None
        assert fm["url"] == "http://example.com"


# ---------------------------------------------------------------------------
# lint()
# ---------------------------------------------------------------------------

class TestLint:
    def _doc(self, fields: dict[str, str], body: str = "Content.") -> str:
        lines = ["---"]
        for k, v in fields.items():
            lines.append(f"{k}: {v}")
        lines.append("---")
        lines.append(body)
        return "\n".join(lines)

    def test_all_valid_returns_empty(self):
        text = self._doc({
            "status": "active",
            "author": "Bob",
            "created": "2024-01-01",
        })
        errors = lint("docs/guide.md", text, ("status", "author", "created"))
        assert errors == []

    def test_missing_required_field(self):
        text = self._doc({"status": "active"})
        errors = lint("docs/guide.md", text, ("status", "author"))
        assert any("author" in e for e in errors)

    def test_invalid_status_value(self):
        text = self._doc({"status": "wip"})
        errors = lint("docs/guide.md", text, ("status",))
        assert any("status" in e for e in errors)

    def test_invalid_date_value(self):
        text = self._doc({"created": "01-01-2024"})
        errors = lint("docs/guide.md", text, ("created",))
        assert any("created" in e for e in errors)

    def test_parse_error_propagated(self):
        errors = lint("docs/guide.md", "no frontmatter here", ("status",))
        assert len(errors) == 1
        assert "---" in errors[0] or "start" in errors[0]

    def test_unknown_field_uses_nonempty_validator(self):
        text = self._doc({"custom-field": ""})
        errors = lint("docs/guide.md", text, ("custom-field",))
        assert any("custom-field" in e for e in errors)

    def test_unknown_field_with_value_passes(self):
        text = self._doc({"custom-field": "some value"})
        errors = lint("docs/guide.md", text, ("custom-field",))
        assert errors == []

    def test_follows_conventions_must_be_true(self):
        text = self._doc({"follows-conventions": "false"})
        errors = lint("docs/guide.md", text, ("follows-conventions",))
        assert any("follows-conventions" in e for e in errors)

    def test_follows_conventions_true_passes(self):
        text = self._doc({"follows-conventions": "true"})
        errors = lint("docs/guide.md", text, ("follows-conventions",))
        assert errors == []


# ---------------------------------------------------------------------------
# main() / stdin path
# ---------------------------------------------------------------------------

def _make_doc_file(tmp_path: Path, content: str) -> Path:
    """Write a doc file and return its path."""
    doc = tmp_path / "docs" / "guide.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(content, encoding="utf-8")
    return doc


def _run_main(monkeypatch, payload: dict, env_overrides: dict | None = None) -> int:
    """Feed payload as stdin and call main(); returns exit code."""
    if env_overrides:
        for k, v in env_overrides.items():
            monkeypatch.setenv(k, v)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    import frontmatter_lint
    import discipline_config
    discipline_config.get_config.cache_clear()
    return frontmatter_lint.main()


class TestMain:
    def test_malformed_stdin_passes(self, monkeypatch, clean_env):
        monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
        import frontmatter_lint
        assert frontmatter_lint.main() == 0

    def test_lint_disabled_by_default(self, monkeypatch, clean_env, tmp_path):
        # Without DISCIPLINE_REQUIRE_FRONTMATTER_FIELDS, lint is off
        doc = _make_doc_file(tmp_path, "# No frontmatter")
        rc = _run_main(monkeypatch, {
            "tool_input": {"file_path": str(doc)},
        })
        assert rc == 0

    def test_no_file_path_passes(self, monkeypatch, clean_env):
        rc = _run_main(monkeypatch, {"tool_input": {}},
                       env_overrides={"DISCIPLINE_REQUIRE_FRONTMATTER_FIELDS": "status"})
        assert rc == 0

    def test_non_docs_file_skipped(self, monkeypatch, clean_env, tmp_path):
        # Set DISCIPLINE_REPO_ROOT so normalize_path works properly
        src_file = tmp_path / "src" / "file.md"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("# No frontmatter", encoding="utf-8")
        import discipline_config
        discipline_config.get_config.cache_clear()
        rc = _run_main(
            monkeypatch,
            {"tool_input": {"file_path": str(src_file)}},
            env_overrides={"DISCIPLINE_REQUIRE_FRONTMATTER_FIELDS": "status"},
        )
        assert rc == 0

    def test_valid_frontmatter_passes(self, monkeypatch, clean_env, tmp_path):
        doc = _make_doc_file(tmp_path, "---\nstatus: active\n---\n# Doc\n")
        import discipline_config
        discipline_config.get_config.cache_clear()
        rc = _run_main(
            monkeypatch,
            {"tool_input": {"file_path": str(doc)}},
            env_overrides={
                "DISCIPLINE_REQUIRE_FRONTMATTER_FIELDS": "status",
                "DISCIPLINE_REPO_ROOT": str(tmp_path),
            },
        )
        assert rc == 0

    def test_emit_block_called_on_error(self, monkeypatch, clean_env, tmp_path, capsys):
        doc = _make_doc_file(tmp_path, "---\nstatus: wip\n---\n# Doc\n")
        import discipline_config
        discipline_config.get_config.cache_clear()
        with pytest.raises(SystemExit) as exc_info:
            _run_main(
                monkeypatch,
                {"tool_input": {"file_path": str(doc)}},
                env_overrides={
                    "DISCIPLINE_REQUIRE_FRONTMATTER_FIELDS": "status",
                    "DISCIPLINE_REPO_ROOT": str(tmp_path),
                },
            )
        assert exc_info.value.code == 0  # emit_block does sys.exit(0)
        out = capsys.readouterr().out
        parsed = json.loads(out.strip())
        assert parsed["decision"] == "block"
        assert "frontmatter_lint" in parsed["reason"]

    def test_tool_response_file_path_used(self, monkeypatch, clean_env, tmp_path):
        doc = _make_doc_file(tmp_path, "---\nstatus: active\n---\n# Doc\n")
        import discipline_config
        discipline_config.get_config.cache_clear()
        rc = _run_main(
            monkeypatch,
            {"tool_response": {"filePath": str(doc)}},
            env_overrides={
                "DISCIPLINE_REQUIRE_FRONTMATTER_FIELDS": "status",
                "DISCIPLINE_REPO_ROOT": str(tmp_path),
            },
        )
        assert rc == 0

    def test_emit_warn_outputs_system_message(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            emit_warn("test warning")
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        parsed = json.loads(out.strip())
        assert parsed["systemMessage"] == "test warning"

    def test_unreadable_file_passes(self, monkeypatch, clean_env, tmp_path):
        import discipline_config
        discipline_config.get_config.cache_clear()
        rc = _run_main(
            monkeypatch,
            {"tool_input": {"file_path": str(tmp_path / "docs" / "nonexistent.md")}},
            env_overrides={
                "DISCIPLINE_REQUIRE_FRONTMATTER_FIELDS": "status",
                "DISCIPLINE_REPO_ROOT": str(tmp_path),
            },
        )
        assert rc == 0
