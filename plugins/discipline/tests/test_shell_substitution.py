"""Unit tests for shell_substitution.py — the quote-aware shell-substitution
body extractors used by gateguard's safe-bash detection.

Covers the three public extractors (`extract_command_substitutions`,
`extract_subshell_groups`, `extract_brace_groups`) across the full matrix of
parsing branches: escapes, single/double quote opacity, nested-span skipping,
recursion, and depth tracking. conftest.py puts the plugin's scripts/ dir on
sys.path so these import by bare name.
"""
import pytest
from shell_substitution import (
    extract_command_substitutions,
    extract_subshell_groups,
    extract_brace_groups,
)


# --------------------------------------------------------------------------- #
# extract_command_substitutions
# --------------------------------------------------------------------------- #
class TestExtractCommandSubstitutions:
    def test_dollar_paren(self):
        assert extract_command_substitutions("echo $(rm -rf /tmp)") == ["rm -rf /tmp"]

    def test_backticks(self):
        assert extract_command_substitutions("echo `rm -rf /tmp`") == ["rm -rf /tmp"]

    def test_nested_dollar_paren(self):
        result = extract_command_substitutions("$(outer $(inner))")
        assert "inner" in result
        assert any("outer" in r for r in result)

    def test_no_substitution_returns_empty(self):
        assert extract_command_substitutions("ls -la") == []

    def test_none_input_coerced_to_empty(self):
        # str(text or "") path with falsy input.
        assert extract_command_substitutions(None) == []

    def test_empty_string(self):
        assert extract_command_substitutions("") == []

    def test_escape_outside_single_quote_skips_two_chars(self):
        # Backslash-escaped '$' must NOT start a substitution (line 44-45).
        assert extract_command_substitutions(r"echo \$(not a sub)") == []

    def test_escaped_backtick_not_substitution(self):
        # An escaped backtick is consumed by the escape handler, not a sub.
        assert extract_command_substitutions(r"echo \`literal\`") == []

    def test_single_quotes_make_dollar_paren_literal(self):
        assert extract_command_substitutions("echo '$(rm -rf /)'") == []

    def test_double_quotes_transparent_to_dollar_paren(self):
        assert "rm -rf /tmp" in extract_command_substitutions('echo "$(rm -rf /tmp)"')

    def test_double_quotes_transparent_to_backticks(self):
        assert "ls" in extract_command_substitutions('echo "`ls`"')

    def test_backtick_body_with_escape(self):
        # Escape inside a backtick body is preserved verbatim (lines 71-75).
        result = extract_command_substitutions(r"`echo \` x`")
        assert result and "\\`" in result[0]

    def test_backtick_body_escape_at_eof(self):
        # Trailing backslash inside backticks with no following char: the i+1
        # guard fails so `continue` is skipped, and the trailing `body += inner`
        # appends the backslash a second time. Body is non-empty -> appended.
        result = extract_command_substitutions("`abc\\")
        assert result == ["abc\\\\"]

    def test_empty_backtick_body_skipped(self):
        # Whitespace-only body fails the `.strip()` truthiness check (no append).
        assert extract_command_substitutions("echo ``") == []

    def test_empty_dollar_paren_body_skipped(self):
        assert extract_command_substitutions("echo $()") == []

    def test_dollar_paren_body_escape(self):
        # Escape inside $() body preserved (lines 101-105).
        result = extract_command_substitutions(r'$(echo \) still)')
        assert result and "\\)" in result[0]

    def test_dollar_paren_body_single_quote_protects_paren(self):
        # ')' inside single quotes in the body must not close the sub (line 109).
        result = extract_command_substitutions("$(echo ')')")
        assert result == ["echo ')'"]

    def test_dollar_paren_body_double_quote_toggle(self):
        # Double-quote toggle inside the body (line 111).
        result = extract_command_substitutions('$(echo "a b")')
        assert result == ['echo "a b"']

    def test_dollar_paren_depth_tracking(self):
        # Nested unquoted parens increase/decrease depth (lines 114-119).
        result = extract_command_substitutions("$(echo (sub) done)")
        assert result == ["echo (sub) done"]

    def test_recursion_into_backtick_nested(self):
        result = extract_command_substitutions("`a $(b)`")
        assert "a $(b)" in result
        assert "b" in result


# --------------------------------------------------------------------------- #
# extract_subshell_groups
# --------------------------------------------------------------------------- #
class TestExtractSubshellGroups:
    def test_paren_group(self):
        assert extract_subshell_groups("(cd /tmp && rm -rf .)") == ["cd /tmp && rm -rf ."]

    def test_distinguishes_from_dollar_paren(self):
        assert extract_subshell_groups("echo $(ls)") == []

    def test_none_input(self):
        assert extract_subshell_groups(None) == []

    def test_escape_outside_single_quote(self):
        # Escaped '(' must not open a subshell (lines 159-161).
        assert extract_subshell_groups(r"echo \(not a group\)") == []

    def test_single_quotes_literal(self):
        # '(' inside single quotes is literal (lines 164, 176-177).
        assert extract_subshell_groups("echo '(literal)'") == []

    def test_double_quotes_literal_for_plain_paren(self):
        # bash does not honor bare (...) inside double quotes (lines 170-177).
        assert extract_subshell_groups('echo "(literal)"') == []

    def test_skip_dollar_paren_then_find_subshell(self):
        # $(...) is skipped (lines 181-207), then a real subshell is found.
        result = extract_subshell_groups("echo $(ls) (cd /x)")
        assert result == ["cd /x"]

    def test_skip_dollar_paren_with_escape(self):
        # Escape inside the skipped $() span (lines 191-193).
        result = extract_subshell_groups(r"$(echo \)) (real)")
        assert result == ["real"]

    def test_skip_dollar_paren_with_quotes(self):
        # Quote toggles inside the skipped $() span (lines 195-198).
        result = extract_subshell_groups("$(echo ')' \"(\" ) (real)")
        assert result == ["real"]

    def test_skip_dollar_paren_nested_depth(self):
        # Nested parens inside skipped $() (lines 200-204).
        result = extract_subshell_groups("$(echo (x)) (real)")
        assert result == ["real"]

    def test_skip_backticks_then_find_subshell(self):
        # Backticks skipped (lines 210-219), then subshell found.
        result = extract_subshell_groups("echo `ls` (cd /y)")
        assert result == ["cd /y"]

    def test_skip_backticks_with_escape(self):
        # Escaped char inside skipped backtick span (lines 213-215).
        result = extract_subshell_groups(r"`echo \`` (real)")
        assert result == ["real"]

    def test_backtick_at_eof_no_close(self):
        # Unterminated backtick: i runs off the end, the `if i < len` is false.
        assert extract_subshell_groups("`unterminated") == []

    def test_subshell_body_escape(self):
        # Escape inside the subshell body (lines 234-239).
        result = extract_subshell_groups(r"(echo \) done)")
        assert result and "\\)" in result[0]

    def test_subshell_body_single_quote_protects_paren(self):
        result = extract_subshell_groups("(echo ')')")
        assert result == ["echo ')'"]

    def test_subshell_body_double_quote_toggle(self):
        result = extract_subshell_groups('(echo "a b")')
        assert result == ['echo "a b"']

    def test_nested_subshell_recursion(self):
        # Depth tracking + recursion (lines 248-261).
        result = extract_subshell_groups("(outer (inner))")
        assert "outer (inner)" in result
        assert "inner" in result

    def test_empty_subshell_body_skipped(self):
        assert extract_subshell_groups("(   )") == []


# --------------------------------------------------------------------------- #
# extract_brace_groups
# --------------------------------------------------------------------------- #
class TestExtractBraceGroups:
    def test_brace_group(self):
        assert extract_brace_groups("{ cd /tmp; rm -rf .; }") == ["cd /tmp; rm -rf ."]

    def test_no_brace_returns_empty(self):
        assert extract_brace_groups("ls -la") == []

    def test_none_input(self):
        assert extract_brace_groups(None) == []

    def test_brace_requires_following_whitespace(self):
        # `{x` is not a reserved-word brace group (no space after `{`).
        assert extract_brace_groups("echo {x}") == []

    def test_brace_requires_boundary_before(self):
        # `a{ ... }` — `{` preceded by a non-boundary char is not reserved
        # (lines 395-397: prev_is_boundary False -> i+=1; continue).
        assert extract_brace_groups("a{ echo hi; }") == []

    def test_escape_outside_single_quote(self):
        # Top-level escape handling (lines 297-299).
        assert extract_brace_groups(r"echo \{ literal") == []

    def test_single_quotes_literal_top_level(self):
        # `{` inside single quotes is literal (lines 302, 314).
        assert extract_brace_groups("echo '{ x; }'") == []

    def test_double_quotes_literal_top_level(self):
        assert extract_brace_groups('echo "{ x; }"') == []

    def test_skip_dollar_paren_top_level(self):
        # $() skipped at the top level (lines 319-345), then brace found.
        result = extract_brace_groups("echo $(ls) { cd /x; }")
        assert result == ["cd /x"]

    def test_skip_dollar_paren_top_level_escape(self):
        # Escape inside skipped $() span (lines 329-331).
        result = extract_brace_groups(r"$(echo \)) { real; }")
        assert result == ["real"]

    def test_skip_dollar_paren_top_level_quotes(self):
        # Quote toggles inside skipped $() span (lines 333-336).
        result = extract_brace_groups("$(echo ')' \"x\") { real; }")
        assert result == ["real"]

    def test_skip_dollar_paren_top_level_nested(self):
        # Nested parens in skipped $() (lines 338-341).
        result = extract_brace_groups("$(a (b)) { real; }")
        assert result == ["real"]

    def test_skip_backticks_top_level(self):
        # Backticks skipped (lines 348-357), then brace found.
        result = extract_brace_groups("echo `ls` { cd /y; }")
        assert result == ["cd /y"]

    def test_skip_backticks_top_level_escape(self):
        # Escaped char inside skipped top-level backtick span (lines 351-353).
        result = extract_brace_groups(r"`echo \`` { real; }")
        assert result == ["real"]

    def test_skip_plain_subshell_top_level(self):
        # Plain (...) skipped at the top level (lines 360-386), then brace found.
        result = extract_brace_groups("(cd /tmp) { echo done; }")
        assert result == ["echo done"]

    def test_skip_plain_subshell_top_level_escape(self):
        # Escape inside skipped top-level subshell (lines 370-371).
        result = extract_brace_groups(r"(echo \)) { real; }")
        assert result == ["real"]

    def test_skip_plain_subshell_top_level_quotes(self):
        # Quote toggles inside skipped top-level subshell (lines 374-377).
        result = extract_brace_groups("(echo ')' \"x\") { real; }")
        assert result == ["real"]

    def test_skip_plain_subshell_top_level_nested(self):
        # Nested parens inside skipped subshell (lines 379-383).
        result = extract_brace_groups("(a (b)) { real; }")
        assert result == ["real"]

    # ---- brace BODY inner-loop branches (the bulk: 411-540) ---- #
    def test_body_escape(self):
        # Escape inside brace body (lines 410-415).
        result = extract_brace_groups(r"{ echo \}; }")
        assert result and "\\}" in result[0]

    def test_body_single_quote_span(self):
        # Single-quote span inside body protects `}` (lines 418-422).
        result = extract_brace_groups("{ echo '}'; }")
        assert result == ["echo '}'"]

    def test_body_double_quote_span(self):
        # Double-quote span inside body (lines 425-429).
        result = extract_brace_groups('{ echo "} not close"; }')
        assert result == ['echo "} not close"']

    def test_body_inside_quotes_accumulate(self):
        # Chars inside an open quote span just accumulate (lines 432-435).
        result = extract_brace_groups("{ echo 'a b c'; }")
        assert result == ["echo 'a b c'"]

    def test_body_dollar_paren_span(self):
        # $() span inside brace body is skipped intact (lines 438-467).
        result = extract_brace_groups("{ echo $(ls -la); }")
        assert result == ["echo $(ls -la)"]

    def test_body_dollar_paren_span_escape(self):
        # Escape inside the in-body $() span (lines 450-453).
        result = extract_brace_groups(r"{ echo $(printf \)); }")
        assert result and "$(printf" in result[0]

    def test_body_dollar_paren_span_quotes(self):
        # Quote toggles inside the in-body $() span (lines 455-458).
        result = extract_brace_groups("{ echo $(printf ')' \"x\"); }")
        assert result and "$(printf" in result[0]

    def test_body_dollar_paren_span_nested(self):
        # Nested parens inside the in-body $() span (lines 460-463).
        result = extract_brace_groups("{ echo $(a (b)); }")
        assert result == ["echo $(a (b))"]

    def test_body_backtick_span(self):
        # Backtick span inside brace body (lines 470-486).
        result = extract_brace_groups("{ echo `ls`; }")
        assert result == ["echo `ls`"]

    def test_body_backtick_span_escape(self):
        # Escaped char inside the in-body backtick span (lines 475-478).
        result = extract_brace_groups(r"{ echo `printf \``; }")
        assert result and "`printf" in result[0]

    def test_body_plain_subshell_span(self):
        # Plain (...) span inside brace body (lines 489-518).
        result = extract_brace_groups("{ (cd /tmp && ls); }")
        assert result == ["(cd /tmp && ls)"]

    def test_body_plain_subshell_span_escape(self):
        # Escape inside the in-body subshell span (lines 501-505).
        result = extract_brace_groups(r"{ (printf \)); }")
        assert result and "(printf" in result[0]

    def test_body_plain_subshell_span_quotes(self):
        # Quote toggles inside the in-body subshell span (lines 506-509).
        result = extract_brace_groups("{ (printf ')' \"x\"); }")
        assert result and "(printf" in result[0]

    def test_body_plain_subshell_span_nested(self):
        # Nested parens inside the in-body subshell span (lines 511-513).
        result = extract_brace_groups("{ (a (b)); }")
        assert result == ["(a (b))"]

    def test_nested_brace_group(self):
        # Nested { ...; } increments depth and recurses (lines 521-524, 539-540).
        result = extract_brace_groups("{ { echo inner; }; }")
        # Outer body keeps the inner braces; recursion surfaces the inner body.
        assert any("echo inner" in r for r in result)
        assert len(result) >= 2

    def test_closing_brace_after_semicolon(self):
        # `}` preceded by ';' closes (lines 527-530).
        assert extract_brace_groups("{ echo hi; }") == ["echo hi"]

    def test_closing_brace_after_space(self):
        # `}` preceded by whitespace also closes.
        assert extract_brace_groups("{ echo hi ; }") == ["echo hi"]

    def test_empty_brace_body_skipped(self):
        # Whitespace-only body fails the truthiness check (no append).
        assert extract_brace_groups("{  }") == []

    def test_trailing_semicolons_stripped(self):
        # Cleaned body strips trailing ';' (line 537).
        result = extract_brace_groups("{ echo hi;; }")
        assert result == ["echo hi"]
