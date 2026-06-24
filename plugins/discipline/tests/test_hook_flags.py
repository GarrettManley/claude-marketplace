# plugins/discipline/tests/test_hook_flags.py
"""Unit tests for hook_flags.py (canonical copy — covers all vendored copies,
which ci/check-vendored-sync.py keeps byte-identical)."""
from hook_flags import (
    VALID_PROFILES,
    _env_prefix,
    get_hook_profile,
    get_disabled_hook_ids,
    parse_profiles,
    is_hook_enabled,
)

HOOK_ID = "discipline:pre-edit:example"


class TestEnvPrefix:
    def test_namespaced_id(self):
        assert _env_prefix("discipline:pre-edit:example") == "DISCIPLINE"

    def test_other_plugin(self):
        assert _env_prefix("learning:pre-tool:observe") == "LEARNING"

    def test_hyphenated_plugin_name(self):
        assert _env_prefix("my-plugin:stop:check") == "MY_PLUGIN"

    def test_no_namespace_uses_whole_id(self):
        assert _env_prefix("standalone") == "STANDALONE"

    def test_empty_falls_back(self):
        assert _env_prefix("") == "PLUGIN"


class TestGetHookProfile:
    def test_default_is_standard(self, clean_env):
        assert get_hook_profile(HOOK_ID) == "standard"

    def test_minimal(self, clean_env):
        clean_env.setenv("DISCIPLINE_HOOK_PROFILE", "minimal")
        assert get_hook_profile(HOOK_ID) == "minimal"

    def test_strict(self, clean_env):
        clean_env.setenv("DISCIPLINE_HOOK_PROFILE", "strict")
        assert get_hook_profile(HOOK_ID) == "strict"

    def test_invalid_falls_back_to_standard(self, clean_env):
        clean_env.setenv("DISCIPLINE_HOOK_PROFILE", "paranoid")
        assert get_hook_profile(HOOK_ID) == "standard"

    def test_case_insensitive(self, clean_env):
        clean_env.setenv("DISCIPLINE_HOOK_PROFILE", "STRICT")
        assert get_hook_profile(HOOK_ID) == "strict"

    def test_whitespace_stripped(self, clean_env):
        clean_env.setenv("DISCIPLINE_HOOK_PROFILE", "  minimal  ")
        assert get_hook_profile(HOOK_ID) == "minimal"

    def test_prefix_isolation(self, clean_env):
        # Another plugin's profile var must not govern discipline ids.
        clean_env.setenv("LEARNING_HOOK_PROFILE", "minimal")
        assert get_hook_profile(HOOK_ID) == "standard"
        assert get_hook_profile("learning:pre-tool:observe") == "minimal"


class TestGetDisabledHookIds:
    def test_default_is_empty(self, clean_env):
        assert get_disabled_hook_ids(HOOK_ID) == set()

    def test_single_id(self, clean_env):
        clean_env.setenv("DISCIPLINE_DISABLED_HOOKS", "discipline:pre-edit:example")
        assert get_disabled_hook_ids(HOOK_ID) == {"discipline:pre-edit:example"}

    def test_multiple_ids(self, clean_env):
        clean_env.setenv("DISCIPLINE_DISABLED_HOOKS",
                         "discipline:pre-edit:example,discipline:post-edit:frontmatter-lint")
        assert get_disabled_hook_ids(HOOK_ID) == {
            "discipline:pre-edit:example",
            "discipline:post-edit:frontmatter-lint",
        }

    def test_whitespace_trimmed(self, clean_env):
        clean_env.setenv("DISCIPLINE_DISABLED_HOOKS", "  foo:bar  ,  baz:qux  ")
        assert get_disabled_hook_ids(HOOK_ID) == {"foo:bar", "baz:qux"}

    def test_case_insensitive(self, clean_env):
        clean_env.setenv("DISCIPLINE_DISABLED_HOOKS", "DISCIPLINE:Pre-Edit:Example")
        assert get_disabled_hook_ids(HOOK_ID) == {"discipline:pre-edit:example"}

    def test_empty_entries_dropped(self, clean_env):
        clean_env.setenv("DISCIPLINE_DISABLED_HOOKS", "foo,,bar,,,")
        assert get_disabled_hook_ids(HOOK_ID) == {"foo", "bar"}

    def test_whitespace_only_value(self, clean_env):
        clean_env.setenv("DISCIPLINE_DISABLED_HOOKS", "   ")
        assert get_disabled_hook_ids(HOOK_ID) == set()

    def test_prefix_isolation(self, clean_env):
        # Another plugin's disable list must not bleed into discipline lookups.
        clean_env.setenv("LEARNING_DISABLED_HOOKS", "learning:pre-tool:observe")
        assert get_disabled_hook_ids(HOOK_ID) == set()
        assert get_disabled_hook_ids("learning:pre-tool:observe") == {
            "learning:pre-tool:observe"
        }


class TestParseProfiles:
    def test_empty_returns_fallback(self):
        assert parse_profiles("") == ["standard", "strict"]

    def test_none_returns_fallback(self):
        assert parse_profiles(None) == ["standard", "strict"]

    def test_single_profile(self):
        assert parse_profiles("strict") == ["strict"]

    def test_csv(self):
        assert parse_profiles("minimal,standard") == ["minimal", "standard"]

    def test_invalid_filtered_out(self):
        assert parse_profiles("paranoid,strict") == ["strict"]

    def test_all_invalid_returns_fallback(self):
        assert parse_profiles("paranoid,reckless") == ["standard", "strict"]

    def test_whitespace_stripped(self):
        assert parse_profiles("  minimal  ,  strict  ") == ["minimal", "strict"]


class TestIsHookEnabled:
    def test_enabled_when_profile_matches(self, clean_env):
        assert is_hook_enabled("discipline:pre-edit:example", "standard,strict") is True

    def test_disabled_when_in_disabled_list(self, clean_env):
        clean_env.setenv("DISCIPLINE_DISABLED_HOOKS", "discipline:pre-edit:example")
        assert is_hook_enabled("discipline:pre-edit:example", "standard,strict") is False

    def test_disabled_when_profile_excluded(self, clean_env):
        clean_env.setenv("DISCIPLINE_HOOK_PROFILE", "minimal")
        assert is_hook_enabled("discipline:pre-edit:example", "standard,strict") is False

    def test_enabled_when_profile_in_list(self, clean_env):
        clean_env.setenv("DISCIPLINE_HOOK_PROFILE", "strict")
        assert is_hook_enabled("discipline:post-write:spec-companion-check", "strict") is True

    def test_empty_id_returns_true(self, clean_env):
        # Defensive: empty id means "no gate"
        assert is_hook_enabled("", "standard") is True

    def test_disabled_list_case_insensitive(self, clean_env):
        clean_env.setenv("DISCIPLINE_DISABLED_HOOKS", "DISCIPLINE:PRE-EDIT:EXAMPLE")
        assert is_hook_enabled("discipline:pre-edit:example", "standard") is False

    def test_cross_plugin_via_own_prefix(self, clean_env):
        # The same vendored file serves every plugin: learning ids answer to
        # LEARNING_* without any per-plugin edits.
        clean_env.setenv("LEARNING_HOOK_PROFILE", "minimal")
        assert is_hook_enabled("learning:pre-tool:observe", "standard,strict") is False
        assert is_hook_enabled("discipline:pre-edit:example", "standard,strict") is True
