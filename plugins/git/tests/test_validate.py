# plugins/git/tests/test_validate.py
"""Unit tests for plugins/git/skills/commit-message/scripts/validate.py.

Coverage strategy:
- _coerce: bool/int/str branches
- load_rules: empty path, missing file, yaml present, yaml absent (ImportError)
- _minimal_yaml_load: full parser branches (nested keys, lists, inline comments,
  quoted strings, bare scalars)
- _find_trailer_start / _extract_trailer_block: direct + via validate()
- validate: happy path, empty message, header pattern, header length,
  body required, trailer required, trailer must_contain
- main(): valid, failed, missing msg_file, bad arg count, bad rules path
"""

import importlib
import pathlib
import sys
import types

import pytest

import validate as v  # resolves via conftest sys.path insert


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CONVENTIONAL_PATTERN = r"^(feat|fix|docs|style|refactor|perf|test|chore|ci|build)(\([^)]+\))?: [A-Z]"

_BASE_RULES = {
    "header": {
        "pattern": CONVENTIONAL_PATTERN,
        "max_length": 72,
    }
}


def _rules_with_body(required=True, min_lines=1):
    return {
        **_BASE_RULES,
        "body": {"required": required, "min_lines_before_trailer": min_lines},
    }


def _rules_with_trailer(name="Tested", required=True, must_contain=None):
    cfg = {"required": required}
    if must_contain:
        cfg["must_contain"] = must_contain
    return {
        **_BASE_RULES,
        "trailers": {name: cfg},
    }


# ---------------------------------------------------------------------------
# _coerce
# ---------------------------------------------------------------------------

class TestCoerce:
    def test_true(self):
        assert v._coerce("true") is True
        assert v._coerce("True") is True

    def test_false(self):
        assert v._coerce("false") is False
        assert v._coerce("FALSE") is False

    def test_integer(self):
        assert v._coerce("42") == 42
        assert isinstance(v._coerce("0"), int)

    def test_string_passthrough(self):
        assert v._coerce("hello") == "hello"
        assert v._coerce("3.14") == "3.14"


# ---------------------------------------------------------------------------
# load_rules — yaml-present path
# ---------------------------------------------------------------------------

class TestLoadRulesYamlPresent:
    def test_empty_string_returns_empty(self):
        assert v.load_rules("") == {}

    def test_missing_file_returns_empty(self, tmp_path):
        assert v.load_rules(str(tmp_path / "nonexistent.yaml")) == {}

    def test_loads_valid_yaml(self, tmp_path):
        rules_file = tmp_path / "rules.yaml"
        rules_file.write_text("header:\n  max_length: 50\n", encoding="utf-8")
        rules = v.load_rules(str(rules_file))
        assert rules["header"]["max_length"] == 50

    def test_empty_yaml_file_returns_empty_dict(self, tmp_path):
        rules_file = tmp_path / "empty.yaml"
        rules_file.write_text("", encoding="utf-8")
        rules = v.load_rules(str(rules_file))
        assert rules == {}


# ---------------------------------------------------------------------------
# load_rules — yaml-absent (ImportError) path via monkeypatch
# ---------------------------------------------------------------------------

class TestLoadRulesYamlAbsent:
    """Force the ImportError branch inside load_rules by hiding yaml from sys.modules."""

    def _block_yaml(self, monkeypatch):
        """Prevent `import yaml` from succeeding inside validate.load_rules."""
        monkeypatch.setitem(sys.modules, "yaml", None)

    def test_falls_back_to_minimal_parser(self, tmp_path, monkeypatch, capsys):
        rules_file = tmp_path / "rules.yaml"
        rules_file.write_text("header:\n  max_length: 72\n", encoding="utf-8")
        self._block_yaml(monkeypatch)
        rules = v.load_rules(str(rules_file))
        assert rules.get("header", {}).get("max_length") == 72
        captured = capsys.readouterr()
        assert "PyYAML not installed" in captured.err

    def test_fallback_warning_message(self, tmp_path, monkeypatch, capsys):
        rules_file = tmp_path / "r.yaml"
        rules_file.write_text("header:\n  pattern: foo\n", encoding="utf-8")
        self._block_yaml(monkeypatch)
        v.load_rules(str(rules_file))
        err = capsys.readouterr().err
        assert "pip install pyyaml" in err

    def test_fallback_parser_error_exits_2(self, tmp_path, monkeypatch):
        """If the minimal parser raises, load_rules calls sys.exit(2)."""
        rules_file = tmp_path / "bad.yaml"
        rules_file.write_text("header:\n  max_length: 72\n", encoding="utf-8")
        self._block_yaml(monkeypatch)

        def boom(p):
            raise RuntimeError("parse failed")

        monkeypatch.setattr(v, "_minimal_yaml_load", boom)
        with pytest.raises(SystemExit) as exc:
            v.load_rules(str(rules_file))
        assert exc.value.code == 2


# ---------------------------------------------------------------------------
# _minimal_yaml_load — parser branch coverage
# ---------------------------------------------------------------------------

class TestMinimalYamlLoad:
    def _load(self, text, tmp_path):
        p = tmp_path / "test.yaml"
        p.write_text(text, encoding="utf-8")
        return v._minimal_yaml_load(p)

    def test_simple_key_value(self, tmp_path):
        result = self._load("key: value\n", tmp_path)
        assert result["key"] == "value"

    def test_integer_coercion(self, tmp_path):
        result = self._load("max_length: 72\n", tmp_path)
        assert result["max_length"] == 72

    def test_bool_coercion(self, tmp_path):
        result = self._load("required: true\n", tmp_path)
        assert result["required"] is True

    def test_nested_keys(self, tmp_path):
        text = "header:\n  max_length: 50\n  pattern: foo\n"
        result = self._load(text, tmp_path)
        assert result["header"]["max_length"] == 50
        assert result["header"]["pattern"] == "foo"

    def test_list_items(self, tmp_path):
        text = "must_contain:\n  - item one\n  - item two\n"
        result = self._load(text, tmp_path)
        assert result["must_contain"] == ["item one", "item two"]

    def test_inline_comment_stripped(self, tmp_path):
        result = self._load("max_length: 72  # chars\n", tmp_path)
        assert result["max_length"] == 72

    def test_blank_and_comment_lines_skipped(self, tmp_path):
        text = "\n# This is a comment\nkey: val\n"
        result = self._load(text, tmp_path)
        assert result["key"] == "val"

    def test_double_quoted_string(self, tmp_path):
        text = 'pattern: "^feat"\n'
        result = self._load(text, tmp_path)
        assert result["pattern"] == "^feat"

    def test_double_quoted_escape_sequences(self, tmp_path):
        text = 'msg: "line1\\nline2"\n'
        result = self._load(text, tmp_path)
        assert result["msg"] == "line1\nline2"

    def test_double_quoted_backslash_escape(self, tmp_path):
        text = r'msg: "a\\b"' + "\n"
        result = self._load(text, tmp_path)
        assert result["msg"] == "a\\b"

    def test_double_quoted_embedded_quote_escape(self, tmp_path):
        text = r'msg: "say \"hi\""' + "\n"
        result = self._load(text, tmp_path)
        assert result["msg"] == 'say "hi"'

    def test_single_quoted_string(self, tmp_path):
        text = "pattern: 'foo bar'\n"
        result = self._load(text, tmp_path)
        assert result["pattern"] == "foo bar"

    def test_nested_list_under_section(self, tmp_path):
        text = "trailers:\n  Tested:\n    must_contain:\n      - '- How:'\n"
        result = self._load(text, tmp_path)
        assert result["trailers"]["Tested"]["must_contain"] == ["- How:"]

    def test_existing_key_not_overwritten_by_section(self, tmp_path):
        # A key that has a value already — opening a section with same name
        # should not overwrite if already set (conditional in parser).
        text = "header:\n  max_length: 72\n"
        result = self._load(text, tmp_path)
        assert "header" in result

    def test_depth_decrease_pops_current(self, tmp_path):
        # Tests line 70: current.pop() fires when indentation decreases (depth < len(current)).
        # Nest deeply then come back to root level.
        text = (
            "section_a:\n"
            "  nested:\n"
            "    deep_key: deep_val\n"
            "section_b:\n"
            "  shallow_key: shallow_val\n"
        )
        result = self._load(text, tmp_path)
        assert result["section_a"]["nested"]["deep_key"] == "deep_val"
        assert result["section_b"]["shallow_key"] == "shallow_val"


# ---------------------------------------------------------------------------
# _find_trailer_start
# ---------------------------------------------------------------------------

class TestFindTrailerStart:
    def test_returns_none_when_no_trailers(self):
        rest = ["Some body text.", "More body."]
        assert v._find_trailer_start(rest) is None

    def test_finds_trailer_after_blank_line(self):
        rest = ["Body text.", "", "Tested: yes"]
        idx = v._find_trailer_start(rest)
        assert idx == 2

    def test_ignores_mid_body_note(self):
        # "Note: something" in the body should not be a trailer if it isn't
        # preceded by a blank line at the right place.
        # rest indices: 0="Note: see docs", 1="more body", 2="", 3="Tested: yes"
        # The algorithm finds the blank at index 2 followed by trailer at 3.
        rest = ["Note: see docs", "more body", "", "Tested: yes"]
        idx = v._find_trailer_start(rest)
        assert idx == 3  # points at "Tested: yes" (0-based index into rest)

    def test_none_when_blank_is_last_line(self):
        rest = ["Body", ""]
        assert v._find_trailer_start(rest) is None


# ---------------------------------------------------------------------------
# _extract_trailer_block
# ---------------------------------------------------------------------------

class TestExtractTrailerBlock:
    def test_returns_empty_when_absent(self):
        assert v._extract_trailer_block([], "Tested") == ""

    def test_extracts_single_line_trailer(self):
        rest = ["", "Tested: yes"]
        block = v._extract_trailer_block(rest, "Tested")
        assert "Tested: yes" in block

    def test_extracts_multiline_trailer(self):
        rest = ["", "Tested: something", "- How: manually", "- Hardware: GPU-X"]
        block = v._extract_trailer_block(rest, "Tested")
        assert "- How: manually" in block
        assert "- Hardware: GPU-X" in block

    def test_stops_at_blank_line(self):
        rest = ["", "Tested: something", "- How: manually", "", "Co-authored-by: X"]
        block = v._extract_trailer_block(rest, "Tested")
        assert "Co-authored-by" not in block

    def test_stops_at_next_trailer_key(self):
        rest = ["Tested: yes", "- How: manually", "Co-authored-by: X"]
        block = v._extract_trailer_block(rest, "Tested")
        assert "Co-authored-by" not in block


# ---------------------------------------------------------------------------
# validate — core logic
# ---------------------------------------------------------------------------

class TestValidateEmptyMessage:
    def test_empty_string(self):
        failures = v.validate("HEAD", "", {})
        assert failures == ["empty commit message"]

    def test_whitespace_only(self):
        failures = v.validate("HEAD", "   \n   \n", {})
        assert failures == ["empty commit message"]

    def test_comments_only(self):
        failures = v.validate("HEAD", "# This is a comment\n# another\n", {})
        assert failures == ["empty commit message"]


class TestValidateNoRules:
    """With an empty rules dict, any non-empty message should pass."""

    def test_simple_message_passes(self):
        assert v.validate("HEAD", "chore: something", {}) == []

    def test_multi_line_passes(self):
        msg = "fix: a bug\n\nBody text here.\n\nTested: yes"
        assert v.validate("HEAD", msg, {}) == []


class TestValidateHeaderPattern:
    def test_valid_conventional_commit(self):
        failures = v.validate("HEAD", "feat: Add new feature", _BASE_RULES)
        assert failures == []

    def test_valid_with_scope(self):
        failures = v.validate("HEAD", "fix(auth): Correct token handling", _BASE_RULES)
        assert failures == []

    def test_bad_type_fails(self):
        failures = v.validate("HEAD", "update: Something happened", _BASE_RULES)
        assert any("header-format" in f for f in failures)

    def test_missing_colon_fails(self):
        failures = v.validate("HEAD", "feat Add something", _BASE_RULES)
        assert any("header-format" in f for f in failures)

    def test_lowercase_subject_fails(self):
        failures = v.validate("HEAD", "feat: add something", _BASE_RULES)
        assert any("header-format" in f for f in failures)

    def test_empty_scope_fails(self):
        failures = v.validate("HEAD", "feat(): Add something", _BASE_RULES)
        assert any("header-format" in f for f in failures)

    def test_pattern_in_failure_message(self):
        failures = v.validate("HEAD", "bad message", _BASE_RULES)
        assert any(CONVENTIONAL_PATTERN in f for f in failures)


class TestValidateHeaderLength:
    def test_at_limit_passes(self):
        header = "feat: " + "A" * 66  # 6 + 66 = 72 exactly
        assert v.validate("HEAD", header, _BASE_RULES) == []

    def test_over_limit_fails(self):
        header = "feat: " + "A" * 67  # 73 chars
        failures = v.validate("HEAD", header, _BASE_RULES)
        assert any("header-length" in f for f in failures)

    def test_failure_shows_actual_length(self):
        header = "feat: " + "A" * 67
        failures = v.validate("HEAD", header, _BASE_RULES)
        assert any("73" in f for f in failures)

    def test_zero_max_length_no_length_check(self):
        # max_length: 0 means no length rule
        rules = {"header": {"max_length": 0}}
        long_header = "x" * 200
        failures = v.validate("HEAD", long_header, rules)
        # No header-length failure
        assert not any("header-length" in f for f in failures)


class TestValidateBodyRequired:
    def test_body_present_passes(self):
        msg = "feat: Add thing\n\nThis is a body line."
        failures = v.validate("HEAD", msg, _rules_with_body())
        # Filter to only body failures
        body_failures = [f for f in failures if "missing-body" in f]
        assert body_failures == []

    def test_body_missing_fails(self):
        msg = "feat: Add thing"
        failures = v.validate("HEAD", msg, _rules_with_body())
        assert any("missing-body" in f for f in failures)

    def test_body_with_min_lines(self):
        # min_lines=2, only 1 body line → fail
        msg = "feat: Add thing\n\nOne line."
        failures = v.validate("HEAD", msg, _rules_with_body(min_lines=2))
        assert any("missing-body" in f for f in failures)

    def test_body_with_min_lines_satisfied(self):
        msg = "feat: Add thing\n\nLine one.\nLine two."
        failures = v.validate("HEAD", msg, _rules_with_body(min_lines=2))
        body_failures = [f for f in failures if "missing-body" in f]
        assert body_failures == []

    def test_body_not_required_no_check(self):
        msg = "feat: Add thing"
        rules = {**_BASE_RULES, "body": {"required": False}}
        body_failures = [f for f in v.validate("HEAD", msg, rules) if "missing-body" in f]
        assert body_failures == []

    def test_blank_lines_before_trailer_not_counted_as_body(self):
        # Body section is empty lines only; trailer follows → body is empty
        msg = "feat: Add thing\n\n\nTested: yes"
        failures = v.validate("HEAD", msg, _rules_with_body())
        assert any("missing-body" in f for f in failures)


class TestValidateTrailerRequired:
    def test_trailer_present_passes(self):
        msg = "feat: Add thing\n\nBody.\n\nTested: yes"
        failures = v.validate("HEAD", msg, _rules_with_trailer())
        trailer_failures = [f for f in failures if "missing-trailer" in f]
        assert trailer_failures == []

    def test_trailer_absent_fails(self):
        msg = "feat: Add thing\n\nBody text."
        failures = v.validate("HEAD", msg, _rules_with_trailer())
        assert any("missing-trailer" in f for f in failures)

    def test_trailer_not_required_no_check(self):
        msg = "feat: Add thing"
        rules = _rules_with_trailer(required=False)
        trailer_failures = [f for f in v.validate("HEAD", msg, rules) if "missing-trailer" in f]
        assert trailer_failures == []

    def test_trailer_name_in_failure_message(self):
        msg = "feat: Add thing"
        failures = v.validate("HEAD", msg, _rules_with_trailer(name="Reviewed-by"))
        assert any("Reviewed-by" in f for f in failures)


class TestValidateTrailerMustContain:
    def test_must_contain_present_passes(self):
        msg = "feat: Add thing\n\n\nTested: yes\n- How: manually"
        rules = _rules_with_trailer(must_contain=["- How:"])
        must_failures = [f for f in v.validate("HEAD", msg, rules) if "trailer-missing-field" in f]
        assert must_failures == []

    def test_must_contain_absent_fails(self):
        msg = "feat: Add thing\n\n\nTested: yes"
        rules = _rules_with_trailer(must_contain=["- How:"])
        failures = v.validate("HEAD", msg, rules)
        assert any("trailer-missing-field" in f and "- How:" in f for f in failures)

    def test_multiple_must_contain(self):
        msg = "feat: Add thing\n\n\nTested: yes\n- How: manual"
        rules = _rules_with_trailer(must_contain=["- How:", "- Hardware:"])
        failures = v.validate("HEAD", msg, rules)
        assert any("- Hardware:" in f for f in failures)
        # "- How:" was present, so no failure for it
        assert not any("trailer-missing-field" in f and "- How:" in f for f in failures)

    def test_trailer_non_dict_cfg_skipped(self):
        """Non-dict trailer config must not crash (defensive branch)."""
        rules = {**_BASE_RULES, "trailers": {"Tested": "just-a-string"}}
        msg = "feat: Add thing"
        # Should not raise
        failures = v.validate("HEAD", msg, rules)
        assert isinstance(failures, list)


class TestValidateCommentStripping:
    def test_git_comment_lines_ignored(self):
        msg = "# This is a git-added comment\nfeat: Add thing\n# another comment"
        assert v.validate("HEAD", msg, _BASE_RULES) == []

    def test_leading_blank_lines_stripped(self):
        msg = "\n\nfeat: Add thing\n"
        assert v.validate("HEAD", msg, _BASE_RULES) == []

    def test_trailing_blank_lines_stripped(self):
        # Exercises line 149: lines.pop() for trailing blanks
        msg = "feat: Add thing\n\n\n"
        assert v.validate("HEAD", msg, _BASE_RULES) == []


class TestValidateMultipleFailures:
    def test_pattern_and_length_both_reported(self):
        header = "bad: " + "x" * 100  # bad type AND too long (over 72 default)
        failures = v.validate("HEAD", header, _BASE_RULES)
        assert any("header-format" in f for f in failures)
        assert any("header-length" in f for f in failures)


# ---------------------------------------------------------------------------
# main() — integration via argv / tmp files
# ---------------------------------------------------------------------------

class TestMain:
    def _run(self, monkeypatch, args, msg_content, rules_content=None, tmp_path=None):
        """Wire sys.argv and temp files, call main(), return exit code."""
        msg_file = tmp_path / "COMMIT_EDITMSG"
        msg_file.write_text(msg_content, encoding="utf-8")

        argv = ["validate.py", "HEAD", str(msg_file)]
        if rules_content is not None:
            rules_file = tmp_path / "rules.yaml"
            rules_file.write_text(rules_content, encoding="utf-8")
            argv.append(str(rules_file))

        monkeypatch.setattr(sys, "argv", argv)
        return v.main()

    def test_valid_message_no_rules_returns_0(self, monkeypatch, tmp_path, capsys):
        rc = self._run(monkeypatch, [], "feat: Add feature\n", tmp_path=tmp_path)
        assert rc == 0
        assert "OK" in capsys.readouterr().out

    def test_valid_message_with_rules_returns_0(self, monkeypatch, tmp_path, capsys):
        rules_yaml = "header:\n  pattern: '^feat'\n  max_length: 72\n"
        rc = self._run(monkeypatch, [], "feat: Add feature\n", rules_content=rules_yaml, tmp_path=tmp_path)
        assert rc == 0

    def test_invalid_message_returns_1(self, monkeypatch, tmp_path, capsys):
        rules_yaml = "header:\n  pattern: '^(feat|fix)'\n"
        rc = self._run(monkeypatch, [], "bad type: something\n", rules_content=rules_yaml, tmp_path=tmp_path)
        assert rc == 1
        err = capsys.readouterr().err
        assert "FAILED" in err
        assert "FAIL" in err

    def test_missing_msg_file_returns_2(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(sys, "argv", ["validate.py", "HEAD", str(tmp_path / "nope.txt")])
        rc = v.main()
        assert rc == 2
        assert "cannot read" in capsys.readouterr().err

    def test_too_few_args_returns_2(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["validate.py", "HEAD"])
        rc = v.main()
        assert rc == 2
        assert "Usage" in capsys.readouterr().err

    def test_rules_file_arg_empty_string_is_no_rules(self, monkeypatch, tmp_path):
        msg_file = tmp_path / "msg.txt"
        msg_file.write_text("docs: Update readme\n", encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["validate.py", "HEAD", str(msg_file), ""])
        rc = v.main()
        assert rc == 0

    def test_ref_in_output(self, monkeypatch, tmp_path, capsys):
        msg_file = tmp_path / "msg.txt"
        msg_file.write_text("feat: Something\n", encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["validate.py", "my-branch", str(msg_file)])
        v.main()
        assert "my-branch" in capsys.readouterr().out

    def test_main_with_yaml_absent(self, monkeypatch, tmp_path, capsys):
        """main() still succeeds via fallback parser when yaml is blocked."""
        rules_yaml = "header:\n  max_length: 72\n"
        rules_file = tmp_path / "rules.yaml"
        rules_file.write_text(rules_yaml, encoding="utf-8")
        msg_file = tmp_path / "msg.txt"
        msg_file.write_text("feat: Short message\n", encoding="utf-8")
        monkeypatch.setitem(sys.modules, "yaml", None)
        monkeypatch.setattr(sys, "argv", ["validate.py", "HEAD", str(msg_file), str(rules_file)])
        rc = v.main()
        assert rc == 0
        capsys.readouterr()  # consume output
