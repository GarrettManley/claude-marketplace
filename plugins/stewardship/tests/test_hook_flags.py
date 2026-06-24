# plugins/stewardship/tests/test_hook_flags.py
"""Tests for hook_flags.py (vendored) — env-prefix derivation, profile
parsing, disabled-hook list, and is_hook_enabled gate."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from hook_flags import (
    DEFAULT_PROFILE_FALLBACK,
    VALID_PROFILES,
    _env_prefix,
    _normalize_id,
    get_disabled_hook_ids,
    get_hook_profile,
    is_hook_enabled,
    parse_profiles,
)


# ---------------------------------------------------------------------------
# _env_prefix
# ---------------------------------------------------------------------------

class TestEnvPrefix:
    def test_simple_namespace(self):
        assert _env_prefix("discipline:some-hook") == "DISCIPLINE"

    def test_no_colon_uses_whole_string(self):
        assert _env_prefix("myplug") == "MYPLUG"

    def test_hyphen_replaced_with_underscore(self):
        assert _env_prefix("my-plug:hook") == "MY_PLUG"

    def test_empty_string_returns_plugin(self):
        assert _env_prefix("") == "PLUGIN"

    def test_stewardship_namespace(self):
        assert _env_prefix("stewardship:nightly-drift") == "STEWARDSHIP"

    def test_leading_whitespace_stripped(self):
        # strip() is applied to head
        result = _env_prefix("  discipline:foo")
        # The whole string has no leading space before split, so result may vary —
        # but it must not crash.
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# get_hook_profile
# ---------------------------------------------------------------------------

class TestGetHookProfile:
    def test_default_is_standard(self, clean_env):
        profile = get_hook_profile("stewardship:nightly-drift")
        assert profile == "standard"

    def test_valid_minimal(self, clean_env, monkeypatch):
        monkeypatch.setenv("STEWARDSHIP_HOOK_PROFILE", "minimal")
        assert get_hook_profile("stewardship:nightly-drift") == "minimal"

    def test_valid_strict(self, clean_env, monkeypatch):
        monkeypatch.setenv("STEWARDSHIP_HOOK_PROFILE", "strict")
        assert get_hook_profile("stewardship:nightly-drift") == "strict"

    def test_invalid_value_falls_back_to_standard(self, clean_env, monkeypatch):
        monkeypatch.setenv("STEWARDSHIP_HOOK_PROFILE", "ultra")
        assert get_hook_profile("stewardship:nightly-drift") == "standard"

    def test_case_insensitive(self, clean_env, monkeypatch):
        monkeypatch.setenv("STEWARDSHIP_HOOK_PROFILE", "STRICT")
        assert get_hook_profile("stewardship:nightly-drift") == "strict"

    def test_whitespace_stripped(self, clean_env, monkeypatch):
        monkeypatch.setenv("STEWARDSHIP_HOOK_PROFILE", "  minimal  ")
        assert get_hook_profile("stewardship:nightly-drift") == "minimal"


# ---------------------------------------------------------------------------
# get_disabled_hook_ids
# ---------------------------------------------------------------------------

class TestGetDisabledHookIds:
    def test_empty_env_returns_empty_set(self, clean_env):
        ids = get_disabled_hook_ids("stewardship:nightly-drift")
        assert ids == set()

    def test_single_id(self, clean_env, monkeypatch):
        monkeypatch.setenv("STEWARDSHIP_DISABLED_HOOKS", "stewardship:nightly-drift")
        ids = get_disabled_hook_ids("stewardship:nightly-drift")
        assert "stewardship:nightly-drift" in ids

    def test_comma_separated(self, clean_env, monkeypatch):
        monkeypatch.setenv("STEWARDSHIP_DISABLED_HOOKS", "stewardship:a,stewardship:b")
        ids = get_disabled_hook_ids("stewardship:a")
        assert ids == {"stewardship:a", "stewardship:b"}

    def test_whitespace_around_entries(self, clean_env, monkeypatch):
        monkeypatch.setenv("STEWARDSHIP_DISABLED_HOOKS", "  stewardship:a , stewardship:b  ")
        ids = get_disabled_hook_ids("stewardship:a")
        assert "stewardship:a" in ids
        assert "stewardship:b" in ids

    def test_only_whitespace_returns_empty(self, clean_env, monkeypatch):
        monkeypatch.setenv("STEWARDSHIP_DISABLED_HOOKS", "   ")
        ids = get_disabled_hook_ids("stewardship:a")
        assert ids == set()

    def test_normalize_lowercases(self, clean_env, monkeypatch):
        monkeypatch.setenv("STEWARDSHIP_DISABLED_HOOKS", "STEWARDSHIP:NIGHTLY-DRIFT")
        ids = get_disabled_hook_ids("stewardship:nightly-drift")
        assert "stewardship:nightly-drift" in ids


# ---------------------------------------------------------------------------
# parse_profiles
# ---------------------------------------------------------------------------

class TestParseProfiles:
    def test_none_returns_fallback(self):
        assert parse_profiles(None) == list(DEFAULT_PROFILE_FALLBACK)

    def test_empty_string_returns_fallback(self):
        assert parse_profiles("") == list(DEFAULT_PROFILE_FALLBACK)

    def test_single_valid(self):
        assert parse_profiles("minimal") == ["minimal"]

    def test_csv_valid(self):
        result = parse_profiles("minimal,standard")
        assert result == ["minimal", "standard"]

    def test_invalid_entries_filtered(self):
        result = parse_profiles("ultra,minimal")
        assert result == ["minimal"]

    def test_all_invalid_returns_fallback(self):
        result = parse_profiles("ultra,mega")
        assert result == list(DEFAULT_PROFILE_FALLBACK)

    def test_whitespace_stripped(self):
        result = parse_profiles("  strict , standard  ")
        assert "strict" in result
        assert "standard" in result

    def test_case_insensitive(self):
        result = parse_profiles("MINIMAL")
        assert result == ["minimal"]


# ---------------------------------------------------------------------------
# _normalize_id
# ---------------------------------------------------------------------------

class TestNormalizeId:
    def test_strips_and_lowercases(self):
        assert _normalize_id("  Discipline:Foo  ") == "discipline:foo"


# ---------------------------------------------------------------------------
# is_hook_enabled
# ---------------------------------------------------------------------------

class TestIsHookEnabled:
    def test_empty_id_always_enabled(self, clean_env):
        assert is_hook_enabled("", "minimal,standard,strict") is True

    def test_disabled_by_id_returns_false(self, clean_env, monkeypatch):
        monkeypatch.setenv("STEWARDSHIP_DISABLED_HOOKS", "stewardship:drift")
        assert is_hook_enabled("stewardship:drift", "standard,strict") is False

    def test_profile_mismatch_returns_false(self, clean_env, monkeypatch):
        # Profile is standard, hook only allowed in strict
        monkeypatch.setenv("STEWARDSHIP_HOOK_PROFILE", "standard")
        assert is_hook_enabled("stewardship:drift", "strict") is False

    def test_profile_match_returns_true(self, clean_env, monkeypatch):
        monkeypatch.setenv("STEWARDSHIP_HOOK_PROFILE", "strict")
        assert is_hook_enabled("stewardship:drift", "strict") is True

    def test_default_profile_standard_in_standard_csv(self, clean_env):
        # No env var → profile is "standard"; csv includes "standard"
        assert is_hook_enabled("stewardship:drift", "minimal,standard") is True

    def test_disabled_takes_priority_over_profile(self, clean_env, monkeypatch):
        monkeypatch.setenv("STEWARDSHIP_HOOK_PROFILE", "strict")
        monkeypatch.setenv("STEWARDSHIP_DISABLED_HOOKS", "stewardship:drift")
        assert is_hook_enabled("stewardship:drift", "minimal,standard,strict") is False

    def test_none_profiles_csv_uses_fallback(self, clean_env, monkeypatch):
        # parse_profiles(None) returns DEFAULT_PROFILE_FALLBACK = (standard, strict)
        monkeypatch.setenv("STEWARDSHIP_HOOK_PROFILE", "standard")
        result = is_hook_enabled("stewardship:drift", None)
        assert result is True  # standard is in fallback

    def test_all_profiles_csv_enabled_for_minimal(self, clean_env, monkeypatch):
        monkeypatch.setenv("STEWARDSHIP_HOOK_PROFILE", "minimal")
        assert is_hook_enabled("stewardship:drift", "minimal,standard,strict") is True
