# vendored: plugins/<plugin>/scripts/hook_flags.py — canonical copy lives in
# plugins/discipline/scripts/; ci/check-vendored-sync.py keeps all copies byte-identical.
"""Shared runtime controls for plugin hooks.

The env-var prefix is derived from the hook id's namespace, so this same file
works in every plugin: a hook id `discipline:post-edit:frontmatter-lint` is
governed by DISCIPLINE_HOOK_PROFILE / DISCIPLINE_DISABLED_HOOKS, a `learning:…`
id by LEARNING_*, a `stewardship:…` id by STEWARDSHIP_*, and so on.

Controls (per plugin <PREFIX>):
- <PREFIX>_HOOK_PROFILE=minimal|standard|strict (default: standard)
- <PREFIX>_DISABLED_HOOKS=comma,separated,hook,ids (default: empty)

Adapted from affaan-m/everything-claude-code @ 4774946d, scripts/lib/hook-flags.js.
"""
from __future__ import annotations

import os

VALID_PROFILES: frozenset[str] = frozenset({"minimal", "standard", "strict"})

DEFAULT_PROFILE_FALLBACK = ("standard", "strict")


def _env_prefix(hook_id: str) -> str:
    """Derive the env prefix from a namespaced hook id ('discipline:…' -> 'DISCIPLINE')."""
    head = hook_id.split(":", 1)[0].strip()
    return head.upper().replace("-", "_") if head else "PLUGIN"


def get_hook_profile(hook_id: str) -> str:
    """Return the active profile name. Invalid values fall back to 'standard'."""
    raw = (
        os.environ.get(f"{_env_prefix(hook_id)}_HOOK_PROFILE", "standard")
        .strip()
        .lower()
    )
    return raw if raw in VALID_PROFILES else "standard"


def _normalize_id(value: str) -> str:
    return value.strip().lower()


def get_disabled_hook_ids(hook_id: str) -> set[str]:
    """Return the set of disabled hook IDs from <PREFIX>_DISABLED_HOOKS."""
    raw = os.environ.get(f"{_env_prefix(hook_id)}_DISABLED_HOOKS", "")
    if not raw.strip():
        return set()
    return {
        _normalize_id(part)
        for part in raw.split(",")
        if part.strip()
    }


def parse_profiles(raw: str | None) -> list[str]:
    """Parse a profile CSV. Invalid entries are filtered. Empty input -> fallback."""
    if not raw:
        return list(DEFAULT_PROFILE_FALLBACK)
    parsed = [
        p.strip().lower()
        for p in raw.split(",")
        if p.strip()
    ]
    valid = [p for p in parsed if p in VALID_PROFILES]
    return valid if valid else list(DEFAULT_PROFILE_FALLBACK)


def is_hook_enabled(hook_id: str, allowed_profiles_csv: str | None) -> bool:
    """Return True iff this hook is enabled in the current environment.

    A hook is enabled when:
    1. Its id is not in <PREFIX>_DISABLED_HOOKS
    2. The current <PREFIX>_HOOK_PROFILE is in the hook's allowed_profiles_csv

    An empty hook_id is treated as un-gated (returns True).
    """
    id_norm = _normalize_id(hook_id)
    if not id_norm:
        return True
    if id_norm in get_disabled_hook_ids(hook_id):
        return False
    allowed = parse_profiles(allowed_profiles_csv)
    return get_hook_profile(hook_id) in allowed
