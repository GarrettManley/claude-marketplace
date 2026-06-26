import io
import json
import os
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).parent.parent / "hooks"
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
for d in (HOOKS_DIR, SCRIPTS_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

import scope_bind  # noqa: E402
from scope_binding import load_scope  # noqa: E402

HOSTS = "name: eng\nhosts:\n  - example.com\n"
PATHS = "name: eng\npath_prefixes:\n  - /eng/\n"


@pytest.fixture
def scope_env(tmp_path, monkeypatch):
    """Strip all EVIDENCE_* env, then let a test install a manifest. Clears the cache."""
    for k in list(os.environ):
        if k.startswith("EVIDENCE_"):
            monkeypatch.delenv(k, raising=False)

    def _set(text):
        # Enforcement is off by default; tests opt in (the env-gate is exercised
        # separately by test_disabled_unless_enforce_env_on).
        monkeypatch.setenv("EVIDENCE_SCOPE_ENFORCE", "on")
        if text is None:
            # point at a nonexistent file so load_scope is deterministically "not loaded"
            monkeypatch.setenv("EVIDENCE_SCOPE_PATH", str(tmp_path / "absent.yaml"))
        else:
            p = tmp_path / "evidence-scope.yaml"
            p.write_text(text, encoding="utf-8")
            monkeypatch.setenv("EVIDENCE_SCOPE_PATH", str(p))
        load_scope.cache_clear()

    yield _set
    load_scope.cache_clear()


def _run(tool_name, tool_input, monkeypatch):
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    return scope_bind.main()


def test_dormant_when_no_manifest(scope_env, monkeypatch):
    scope_env(None)
    assert _run("WebFetch", {"url": "https://anything.com"}, monkeypatch) == 0


def test_webfetch_in_scope_allowed(scope_env, monkeypatch):
    scope_env(HOSTS)
    assert _run("WebFetch", {"url": "https://example.com/x"}, monkeypatch) == 0


def test_webfetch_out_of_scope_blocked(scope_env, monkeypatch):
    scope_env(HOSTS)
    assert _run("WebFetch", {"url": "https://evil.com"}, monkeypatch) == 2


def test_webfetch_ungated_when_manifest_has_no_hosts(scope_env, monkeypatch):
    # C2 fix: a path-only manifest must NOT block all WebFetch.
    scope_env(PATHS)
    assert _run("WebFetch", {"url": "https://anything.com"}, monkeypatch) == 0


def test_write_in_scope_allowed(scope_env, monkeypatch):
    scope_env(PATHS)
    assert _run("Write", {"file_path": "/eng/a.txt", "content": "x"}, monkeypatch) == 0


def test_write_out_of_scope_blocked(scope_env, monkeypatch):
    scope_env(PATHS)
    assert _run("Write", {"file_path": "/etc/passwd", "content": "x"}, monkeypatch) == 2


def test_write_ungated_when_manifest_has_no_path_prefixes(scope_env, monkeypatch):
    # check_path is permissive without path_prefixes: a hosts-only manifest does not gate writes.
    scope_env(HOSTS)
    assert _run("Write", {"file_path": "/anywhere/x.txt", "content": "x"}, monkeypatch) == 0


def test_other_tools_not_gated(scope_env, monkeypatch):
    scope_env(HOSTS)
    assert _run("Bash", {"command": "curl https://evil.com"}, monkeypatch) == 0
    assert _run("WebSearch", {"query": "anything"}, monkeypatch) == 0
    assert _run("Read", {"file_path": "/etc/passwd"}, monkeypatch) == 0


def test_missing_field_not_gated(scope_env, monkeypatch):
    scope_env(HOSTS)
    assert _run("WebFetch", {}, monkeypatch) == 0


def test_malformed_stdin_allowed(scope_env, monkeypatch):
    scope_env(HOSTS)
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    assert scope_bind.main() == 0


def test_override_token_allows_out_of_scope(scope_env, tmp_path, monkeypatch):
    import secrets

    from evidence_hmac import issue_token

    scope_env(HOSTS)
    key = tmp_path / "override-key"
    key.write_text(secrets.token_hex(32), encoding="utf-8")
    monkeypatch.setenv("EVIDENCE_OVERRIDE_KEY", str(key))
    token = issue_token("scope_binding", ttl_seconds=60, max_uses=1, key_path=key)
    monkeypatch.setenv("EVIDENCE_OVERRIDE_TOKEN", token)
    assert _run("WebFetch", {"url": "https://evil.com"}, monkeypatch) == 0


def test_wrong_action_token_does_not_override(scope_env, tmp_path, monkeypatch):
    import secrets

    from evidence_hmac import issue_token

    scope_env(HOSTS)
    key = tmp_path / "override-key"
    key.write_text(secrets.token_hex(32), encoding="utf-8")
    monkeypatch.setenv("EVIDENCE_OVERRIDE_KEY", str(key))
    token = issue_token("secret_scan", ttl_seconds=60, max_uses=1, key_path=key)
    monkeypatch.setenv("EVIDENCE_OVERRIDE_TOKEN", token)
    assert _run("WebFetch", {"url": "https://evil.com"}, monkeypatch) == 2


def test_disabled_unless_enforce_env_on(scope_env, monkeypatch):
    # Off by default: even with a manifest and an out-of-scope op, the hook is a
    # no-op unless EVIDENCE_SCOPE_ENFORCE is on (learning-plugin env-gate idiom).
    scope_env(HOSTS)
    monkeypatch.delenv("EVIDENCE_SCOPE_ENFORCE", raising=False)
    assert _run("WebFetch", {"url": "https://evil.com"}, monkeypatch) == 0
