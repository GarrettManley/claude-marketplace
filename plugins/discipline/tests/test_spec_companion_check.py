# plugins/discipline/tests/test_spec_companion_check.py
"""Unit tests for hooks/spec_companion_check.py."""
from __future__ import annotations

import datetime
import io
import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from spec_companion_check import (
    parse_frontmatter,
    strip_frontmatter,
    find_plan,
    days_between,
    slug_prefixes,
    companion_path_exists,
    render_template_paths,
    find_required_section,
    find_acceptance_section,
    find_references_section,
    adr_path,
    emit_block,
    emit_warn,
    check,
    main,
)
from discipline_config import DisciplineConfig


# ---------------------------------------------------------------------------
# parse_frontmatter
# ---------------------------------------------------------------------------

class TestParseFrontmatter:
    def test_valid_frontmatter(self):
        text = "---\nstatus: draft\nauthor: Alice\n---\n# Doc"
        assert parse_frontmatter(text) == {"status": "draft", "author": "Alice"}

    def test_no_opening_fence(self):
        assert parse_frontmatter("# Heading") == {}

    def test_quoted_values_unwrapped(self):
        text = "---\ntitle: 'My Doc'\n---"
        fm = parse_frontmatter(text)
        assert fm["title"] == "My Doc"

    def test_comment_lines_skipped(self):
        text = "---\n# comment\nstatus: active\n---"
        assert parse_frontmatter(text) == {"status": "active"}

    def test_indented_skipped(self):
        text = "---\n  indented: val\nstatus: active\n---"
        fm = parse_frontmatter(text)
        assert "indented" not in fm

    def test_no_closing_fence_parses_leniently(self):
        text = "---\nstatus: draft\n"
        # spec_companion's parser is lenient: a missing closing `---` is not
        # required; fields up to EOF (or line 30) are still parsed.
        assert parse_frontmatter(text) == {"status": "draft"}


# ---------------------------------------------------------------------------
# strip_frontmatter
# ---------------------------------------------------------------------------

class TestStripFrontmatter:
    def test_strips_frontmatter(self):
        text = "---\nstatus: draft\n---\n# Body\ncontent"
        body = strip_frontmatter(text)
        assert body.startswith("# Body")

    def test_no_frontmatter_returns_text(self):
        text = "# No frontmatter\ncontent"
        assert strip_frontmatter(text) == text

    def test_unclosed_frontmatter_returns_original(self):
        text = "---\nstatus: draft\n"
        assert strip_frontmatter(text) == text


# ---------------------------------------------------------------------------
# find_plan
# ---------------------------------------------------------------------------

class TestFindPlan:
    def test_finds_plan_by_number(self, tmp_path):
        plans = tmp_path / "docs" / "engineering" / "plans"
        plans.mkdir(parents=True)
        (plans / "042-my-plan.md").write_text("plan content")
        result = find_plan(tmp_path, "042", "my-plan")
        assert result is not None
        assert result.name == "042-my-plan.md"

    def test_finds_plan_by_slug(self, tmp_path):
        plans = tmp_path / "docs" / "engineering" / "plans"
        plans.mkdir(parents=True)
        (plans / "my-plan.md").write_text("plan content")
        result = find_plan(tmp_path, "042", "my-plan")
        assert result is not None

    def test_returns_none_when_no_plan(self, tmp_path):
        assert find_plan(tmp_path, "042", "my-plan") is None

    def test_skips_non_docs_plans_dirs(self, tmp_path):
        non_docs_plans = tmp_path / "scripts" / "plans"
        non_docs_plans.mkdir(parents=True)
        (non_docs_plans / "042-my-plan.md").write_text("plan content")
        # Not under docs/ so should be skipped
        assert find_plan(tmp_path, "042", "my-plan") is None


# ---------------------------------------------------------------------------
# days_between
# ---------------------------------------------------------------------------

class TestDaysBetween:
    def test_same_date(self):
        assert days_between("2024-01-01", "2024-01-01") == 0

    def test_positive_diff(self):
        assert days_between("2024-01-01", "2024-01-08") == 7

    def test_negative_abs(self):
        assert days_between("2024-01-08", "2024-01-01") == 7

    def test_invalid_date_returns_none(self):
        assert days_between("not-a-date", "2024-01-01") is None

    def test_both_invalid(self):
        assert days_between("bad", "bad") is None


# ---------------------------------------------------------------------------
# slug_prefixes
# ---------------------------------------------------------------------------

class TestSlugPrefixes:
    def test_single_word(self):
        assert slug_prefixes("foo") == ["foo"]

    def test_hyphenated(self):
        result = slug_prefixes("foo-bar-baz")
        # Should be ordered from longest to shortest
        assert result == ["foo-bar-baz", "foo-bar", "foo"]

    def test_two_parts(self):
        assert slug_prefixes("a-b") == ["a-b", "a"]


# ---------------------------------------------------------------------------
# companion_path_exists
# ---------------------------------------------------------------------------

class TestCompanionPathExists:
    def test_exact_path_exists(self, tmp_path):
        target = tmp_path / "docs" / "security" / "my-feature-threat-model.md"
        target.parent.mkdir(parents=True)
        target.write_text("threat model")
        templates = ["docs/security/{slug}-threat-model.md"]
        assert companion_path_exists(tmp_path, templates, "my-feature", "042") is True

    def test_exact_path_missing(self, tmp_path):
        templates = ["docs/security/{slug}-threat-model.md"]
        assert companion_path_exists(tmp_path, templates, "my-feature", "042") is False

    def test_fallback_dir_scan(self, tmp_path):
        # No exact match but a file in the dir starts with the slug prefix
        sec_dir = tmp_path / "docs" / "security"
        sec_dir.mkdir(parents=True)
        (sec_dir / "my-threat-model.md").write_text("tm")
        templates = ["docs/security/{slug}-threat-model.md"]
        assert companion_path_exists(tmp_path, templates, "my", "042") is True

    def test_empty_templates(self, tmp_path):
        assert companion_path_exists(tmp_path, [], "slug", "042") is False


# ---------------------------------------------------------------------------
# render_template_paths
# ---------------------------------------------------------------------------

class TestRenderTemplatePaths:
    def test_single_template(self):
        result = render_template_paths(["docs/{slug}-tm.md"], "my-feature", "042")
        assert result == "docs/my-feature-tm.md"

    def test_multiple_templates(self):
        result = render_template_paths(
            ["docs/{slug}-tm.md", "docs/{number}-{slug}-tm.md"],
            "feat", "042",
        )
        assert "docs/feat-tm.md" in result
        assert "docs/042-feat-tm.md" in result


# ---------------------------------------------------------------------------
# find_required_section
# ---------------------------------------------------------------------------

class TestFindRequiredSection:
    def test_finds_goal_section(self):
        body = "## Goal\nsome content"
        assert find_required_section(body, "Goal") is True

    def test_finds_numbered_goal(self):
        body = "## 1. Goal\nsome content"
        assert find_required_section(body, "Goal") is True

    def test_goal_h1(self):
        body = "# Goal\ncontent"
        assert find_required_section(body, "Goal") is True

    def test_no_goal(self):
        body = "## Introduction\ncontent"
        assert find_required_section(body, "Goal") is False

    def test_case_insensitive_match(self):
        body = "## goal\ncontent"
        # find_required_section uses the (?im) flags — heading matching is
        # case-insensitive, so "## goal" satisfies a "Goal" requirement.
        assert find_required_section(body, "Goal") is True


# ---------------------------------------------------------------------------
# find_acceptance_section
# ---------------------------------------------------------------------------

class TestFindAcceptanceSection:
    def test_finds_acceptance_criteria(self):
        body = "## Acceptance Criteria\ncontent"
        assert find_acceptance_section(body) is True

    def test_finds_acceptance_tests(self):
        body = "## Acceptance Tests\ncontent"
        assert find_acceptance_section(body) is True

    def test_no_acceptance(self):
        body = "## Overview\ncontent"
        assert find_acceptance_section(body) is False

    def test_case_insensitive(self):
        body = "## ACCEPTANCE CRITERIA\ncontent"
        assert find_acceptance_section(body) is True


# ---------------------------------------------------------------------------
# find_references_section
# ---------------------------------------------------------------------------

class TestFindReferencesSection:
    def test_finds_references(self):
        assert find_references_section("## References\ncontent") is True

    def test_references_h1(self):
        assert find_references_section("# References\ncontent") is True

    def test_no_references(self):
        assert find_references_section("## Overview\ncontent") is False


# ---------------------------------------------------------------------------
# adr_path
# ---------------------------------------------------------------------------

class TestAdrPath:
    def test_finds_adr_file(self, tmp_path):
        adrs = tmp_path / "docs" / "engineering" / "adrs"
        adrs.mkdir(parents=True)
        (adrs / "ADR-001-some-decision.md").write_text("adr content")
        result = adr_path(tmp_path, "001")
        assert result is not None
        assert result.name == "ADR-001-some-decision.md"

    def test_returns_none_when_missing(self, tmp_path):
        assert adr_path(tmp_path, "001") is None

    def test_skips_non_docs_adrs(self, tmp_path):
        adrs = tmp_path / "scripts" / "adrs"
        adrs.mkdir(parents=True)
        (adrs / "ADR-001-foo.md").write_text("adr")
        assert adr_path(tmp_path, "001") is None


# ---------------------------------------------------------------------------
# emit_block / emit_warn
# ---------------------------------------------------------------------------

class TestEmitBlockAndWarn:
    def test_emit_block_outputs_decision_block(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            emit_block("test reason")
        assert exc_info.value.code == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["decision"] == "block"
        assert out["reason"] == "test reason"

    def test_emit_warn_outputs_system_message(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            emit_warn("test warning")
        assert exc_info.value.code == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["systemMessage"] == "test warning"


# ---------------------------------------------------------------------------
# check() — core validation logic
# ---------------------------------------------------------------------------

_SPEC_RE = re.compile(r"^docs/.*\d{3,4}-[\w-]+\.md$")

_GOOD_BODY = (
    "Tracks #42.\n\n"
    "## Goal\n\nBuild the thing.\n\n"
    "## Acceptance Criteria\n\nAll tests pass.\n\n"
    "## References\n\nSee #42.\n"
)


def _make_spec(
    tmp_path: Path,
    path: str = "docs/engineering/042-my-feature.md",
    body: str = _GOOD_BODY,
    fields: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Write a spec file and return (rel_path, text)."""
    fields = fields or {"status": "active", "created": "2024-01-01"}
    lines = ["---"]
    for k, v in fields.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append(body)
    text = "\n".join(lines)
    full = tmp_path / Path(path)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(text, encoding="utf-8")
    return path, text


class TestCheck:
    def test_good_spec_returns_no_errors_no_warnings(self, tmp_path):
        rel_path, text = _make_spec(tmp_path)
        # Create a plan file to suppress plan warning
        plans = tmp_path / "docs" / "engineering" / "plans"
        plans.mkdir(parents=True)
        (plans / "042-my-feature-plan.md").write_text("plan")
        errors, warnings = check(rel_path, text, tmp_path, _SPEC_RE)
        assert errors == []
        assert warnings == []

    def test_non_matching_path_returns_empty(self, tmp_path):
        errors, warnings = check(
            "src/util.ts", "some content", tmp_path, _SPEC_RE,
        )
        assert errors == []
        assert warnings == []

    def test_missing_issue_reference_is_error(self, tmp_path):
        body = "## Goal\n\nDo stuff.\n\n## Acceptance Criteria\n\nPass.\n"
        rel_path, text = _make_spec(tmp_path, body=body)
        errors, _ = check(rel_path, text, tmp_path, _SPEC_RE)
        assert any("#" in e for e in errors)

    def test_missing_goal_section_is_error(self, tmp_path):
        body = "Tracks #42.\n\n## Acceptance Criteria\n\nPass.\n"
        rel_path, text = _make_spec(tmp_path, body=body)
        errors, _ = check(rel_path, text, tmp_path, _SPEC_RE)
        assert any("Goal" in e for e in errors)

    def test_missing_acceptance_section_is_error(self, tmp_path):
        body = "Tracks #42.\n\n## Goal\n\nBuild.\n"
        rel_path, text = _make_spec(tmp_path, body=body)
        errors, _ = check(rel_path, text, tmp_path, _SPEC_RE)
        assert any("Acceptance" in e for e in errors)

    def test_missing_references_section_is_warning(self, tmp_path):
        body = "Tracks #42.\n\n## Goal\n\nBuild.\n\n## Acceptance Criteria\n\nPass.\n"
        rel_path, text = _make_spec(tmp_path, body=body)
        _, warnings = check(rel_path, text, tmp_path, _SPEC_RE)
        assert any("References" in w for w in warnings)

    def test_security_keywords_trigger_threat_model_warning(self, tmp_path):
        body = (
            "Tracks #42.\n\n## Goal\n\nAuth flow.\n\n"
            "## Acceptance Criteria\n\nPass.\n\n"
            "## References\n\nSee #42.\n\n"
            "Uses OIDC and TLS for auth.\n"
        )
        rel_path, text = _make_spec(tmp_path, body=body)
        _, warnings = check(rel_path, text, tmp_path, _SPEC_RE)
        assert any("threat model" in w for w in warnings)

    def test_runbook_keywords_trigger_warning(self, tmp_path):
        body = (
            "Tracks #42.\n\n## Goal\n\nDeploy.\n\n"
            "## Acceptance Criteria\n\nPass.\n\n"
            "## References\n\nSee #42.\n\n"
            "Runbook needed for operator.\n"
        )
        rel_path, text = _make_spec(tmp_path, body=body)
        _, warnings = check(rel_path, text, tmp_path, _SPEC_RE)
        assert any("runbook" in w for w in warnings)

    def test_referenced_adr_missing_is_error(self, tmp_path):
        body = (
            "Tracks #42.\n\n## Goal\n\nBuild.\n\n"
            "## Acceptance Criteria\n\nPass.\n\n"
            "## References\n\nSee ADR-001.\n"
        )
        rel_path, text = _make_spec(tmp_path, body=body)
        errors, _ = check(rel_path, text, tmp_path, _SPEC_RE)
        assert any("ADR-001" in e for e in errors)

    def test_referenced_adr_present_no_error(self, tmp_path):
        adrs = tmp_path / "docs" / "engineering" / "adrs"
        adrs.mkdir(parents=True)
        (adrs / "ADR-001-my-decision.md").write_text("adr")
        body = (
            "Tracks #42.\n\n## Goal\n\nBuild.\n\n"
            "## Acceptance Criteria\n\nPass.\n\n"
            "## References\n\nSee ADR-001.\n"
        )
        rel_path, text = _make_spec(tmp_path, body=body)
        errors, _ = check(rel_path, text, tmp_path, _SPEC_RE)
        assert not any("ADR-001" in e for e in errors)

    def test_missing_plan_within_7_days_no_warning(self, tmp_path):
        """If created date is within 7 days, no plan warning."""
        body = _GOOD_BODY
        today = datetime.date.today()
        created = (today - datetime.timedelta(days=3)).isoformat()
        rel_path, text = _make_spec(tmp_path, fields={"created": created})
        _, warnings = check(rel_path, text, tmp_path, _SPEC_RE, today=today)
        assert not any("plan" in w for w in warnings)

    def test_missing_plan_after_7_days_is_warning(self, tmp_path):
        body = _GOOD_BODY
        today = datetime.date.today()
        created = (today - datetime.timedelta(days=10)).isoformat()
        rel_path, text = _make_spec(tmp_path, fields={"created": created})
        _, warnings = check(rel_path, text, tmp_path, _SPEC_RE, today=today)
        assert any("plan" in w for w in warnings)

    def test_spec_without_number_no_plan_check(self, tmp_path):
        # Path doesn't match number-slug pattern
        body = _GOOD_BODY
        rel_path = "docs/engineering/spec-no-number.md"
        text = "---\nstatus: active\n---\n" + body
        full = tmp_path / Path(rel_path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(text, encoding="utf-8")
        spec_re = re.compile(r"^docs/.*[\w-]+\.md$")
        errors, warnings = check(rel_path, text, tmp_path, spec_re)
        # No plan warning since no number
        assert not any("plan" in w for w in warnings)

    def test_no_created_field_plan_warning_issued(self, tmp_path):
        """Missing created field with no plan -> warning (gap=None -> gap>7 branch)."""
        body = _GOOD_BODY
        rel_path, text = _make_spec(tmp_path, fields={})  # no 'created'
        _, warnings = check(rel_path, text, tmp_path, _SPEC_RE)
        assert any("plan" in w for w in warnings)

    def test_user_guide_keywords_trigger_warning(self, tmp_path):
        body = (
            "Tracks #42.\n\n## Goal\n\nUser guide.\n\n"
            "## Acceptance Criteria\n\nPass.\n\n"
            "## References\n\nSee #42.\n\n"
            "This is an operator manual for users.\n"
        )
        rel_path, text = _make_spec(tmp_path, body=body)
        _, warnings = check(rel_path, text, tmp_path, _SPEC_RE)
        assert any("user guide" in w for w in warnings)


# ---------------------------------------------------------------------------
# main() / stdin path
# ---------------------------------------------------------------------------

def _make_cfg(tmp_path: Path) -> DisciplineConfig:
    return DisciplineConfig(
        repo_root=tmp_path,
        spec_pattern=r"^docs/.*\d{3,4}-[\w-]+\.md$",
    )


def _run_main_with_cfg(monkeypatch, payload: dict, cfg: DisciplineConfig) -> int:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    import spec_companion_check
    with patch("spec_companion_check.get_config", return_value=cfg):
        return spec_companion_check.main()


class TestMainSpecCheck:
    def test_malformed_stdin_passes(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
        cfg = _make_cfg(tmp_path)
        import spec_companion_check
        with patch("spec_companion_check.get_config", return_value=cfg):
            assert spec_companion_check.main() == 0

    def test_non_write_tool_ignored(self, monkeypatch, tmp_path):
        cfg = _make_cfg(tmp_path)
        rc = _run_main_with_cfg(
            monkeypatch,
            {"tool_name": "Edit", "tool_input": {"file_path": "docs/engineering/042-foo.md"}},
            cfg,
        )
        assert rc == 0

    def test_no_repo_root_returns_0(self, monkeypatch, tmp_path):
        cfg = DisciplineConfig(repo_root=None)
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_name": "Write"})))
        import spec_companion_check
        with patch("spec_companion_check.get_config", return_value=cfg):
            assert spec_companion_check.main() == 0

    def test_no_file_path_passes(self, monkeypatch, tmp_path):
        cfg = _make_cfg(tmp_path)
        rc = _run_main_with_cfg(monkeypatch, {"tool_name": "Write", "tool_input": {}}, cfg)
        assert rc == 0

    def test_non_spec_path_passes(self, monkeypatch, tmp_path):
        cfg = _make_cfg(tmp_path)
        rc = _run_main_with_cfg(
            monkeypatch,
            {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "src" / "foo.ts")}},
            cfg,
        )
        assert rc == 0

    def test_valid_spec_passes(self, monkeypatch, tmp_path, capsys):
        cfg = _make_cfg(tmp_path)
        plans = tmp_path / "docs" / "engineering" / "plans"
        plans.mkdir(parents=True)
        (plans / "042-my-feature.md").write_text("plan")
        spec_file = tmp_path / "docs" / "engineering" / "042-my-feature.md"
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        spec_file.write_text(
            "---\nstatus: active\ncreated: 2024-01-01\n---\n" + _GOOD_BODY,
            encoding="utf-8",
        )
        rc = _run_main_with_cfg(
            monkeypatch,
            {"tool_name": "Write", "tool_input": {"file_path": str(spec_file)}},
            cfg,
        )
        assert rc == 0

    def test_errors_cause_block(self, monkeypatch, tmp_path, capsys):
        cfg = _make_cfg(tmp_path)
        spec_file = tmp_path / "docs" / "engineering" / "042-my-feature.md"
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        # Missing issue reference + Goal + Acceptance
        spec_file.write_text("---\nstatus: active\n---\n# No required sections\n", encoding="utf-8")
        with pytest.raises(SystemExit) as exc_info:
            _run_main_with_cfg(
                monkeypatch,
                {"tool_name": "Write", "tool_input": {"file_path": str(spec_file)}},
                cfg,
            )
        assert exc_info.value.code == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["decision"] == "block"

    def test_warnings_cause_warn_when_no_errors(self, monkeypatch, tmp_path, capsys):
        cfg = _make_cfg(tmp_path)
        spec_file = tmp_path / "docs" / "engineering" / "042-my-feature.md"
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        # Valid spec but missing References section -> warning only
        body = (
            "Tracks #42.\n\n## Goal\n\nBuild.\n\n"
            "## Acceptance Criteria\n\nPass.\n"
        )
        spec_file.write_text("---\nstatus: active\ncreated: 2024-01-01\n---\n" + body, encoding="utf-8")
        # Create plan to avoid plan warning
        plans = tmp_path / "docs" / "engineering" / "plans"
        plans.mkdir(parents=True)
        (plans / "042-my-feature.md").write_text("plan")
        with pytest.raises(SystemExit) as exc_info:
            _run_main_with_cfg(
                monkeypatch,
                {"tool_name": "Write", "tool_input": {"file_path": str(spec_file)}},
                cfg,
            )
        assert exc_info.value.code == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["systemMessage"] is not None

    def test_unreadable_spec_passes(self, monkeypatch, tmp_path):
        cfg = _make_cfg(tmp_path)
        rc = _run_main_with_cfg(
            monkeypatch,
            {"tool_name": "Write", "tool_input": {
                "file_path": str(tmp_path / "docs" / "engineering" / "042-missing.md")
            }},
            cfg,
        )
        assert rc == 0
