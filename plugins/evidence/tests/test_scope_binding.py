# plugins/evidence/tests/test_scope_binding.py
"""Unit tests for scope_binding.py — scope manifest loading and URL/path checks."""
import importlib
import sys
from pathlib import Path

import pytest

# conftest.py already inserts scripts/ onto sys.path; import by bare name.
import scope_binding
from scope_binding import (
    DEFAULT_SCOPE_PATH,
    Scope,
    _detect_repo_root,
    _host_matches,
    _parse_simple_yaml,
    check_path,
    check_url,
    load_scope,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scope(tmp_path, content: str, *, path: str | None = None) -> Path:
    """Write a YAML manifest into tmp_path and return its path."""
    manifest = tmp_path / (path or "evidence-scope.yaml")
    manifest.write_text(content, encoding="utf-8")
    return manifest


def _fresh_scope(manifest_path: str) -> Scope:
    """Call load_scope bypassing the lru_cache."""
    load_scope.cache_clear()
    try:
        return load_scope(scope_path=str(manifest_path))
    finally:
        load_scope.cache_clear()


# ---------------------------------------------------------------------------
# _parse_simple_yaml
# ---------------------------------------------------------------------------

class TestParseSimpleYaml:
    def test_scalar_values(self):
        text = "name: my-engagement\n"
        result = _parse_simple_yaml(text)
        assert result["name"] == "my-engagement"

    def test_quoted_scalar(self):
        result = _parse_simple_yaml('name: "quoted-value"\n')
        assert result["name"] == "quoted-value"

    def test_single_quoted_scalar(self):
        result = _parse_simple_yaml("name: 'single-quoted'\n")
        assert result["name"] == "single-quoted"

    def test_list_entries(self):
        text = "hosts:\n  - example.com\n  - api.example.com\n"
        result = _parse_simple_yaml(text)
        assert result["hosts"] == ["example.com", "api.example.com"]

    def test_quoted_list_entry(self):
        text = 'hosts:\n  - "*.example.com"\n'
        result = _parse_simple_yaml(text)
        assert result["hosts"] == ["*.example.com"]

    def test_comments_ignored(self):
        text = "# comment line\nname: foo  # inline\n"
        result = _parse_simple_yaml(text)
        # Comment lines are skipped; inline #-after-value is kept (not stripped)
        assert "name" in result

    def test_empty_text(self):
        assert _parse_simple_yaml("") == {}

    def test_blank_lines_skipped(self):
        text = "\n\nname: bar\n\n"
        result = _parse_simple_yaml(text)
        assert result["name"] == "bar"

    def test_unhandled_indentation_skipped(self):
        # Indented non-list line is skipped silently
        text = "name: test\n  nested_key: value\n"
        result = _parse_simple_yaml(text)
        assert result["name"] == "test"
        assert "nested_key" not in result

    def test_tab_indented_list(self):
        text = "hosts:\n\t- example.com\n"
        result = _parse_simple_yaml(text)
        assert result["hosts"] == ["example.com"]


# ---------------------------------------------------------------------------
# _host_matches
# ---------------------------------------------------------------------------

class TestHostMatches:
    def test_exact_match(self):
        assert _host_matches("example.com", "example.com")

    def test_exact_mismatch(self):
        assert not _host_matches("other.com", "example.com")

    def test_wildcard_subdomain_matches(self):
        assert _host_matches("sub.example.com", "*.example.com")

    def test_wildcard_does_not_match_root(self):
        # *.foo.com should NOT match foo.com itself
        assert not _host_matches("example.com", "*.example.com")

    def test_wildcard_case_insensitive(self):
        assert _host_matches("SUB.EXAMPLE.COM", "*.example.com")

    def test_exact_case_insensitive(self):
        assert _host_matches("EXAMPLE.COM", "example.com")

    def test_wildcard_deep_subdomain(self):
        assert _host_matches("a.b.example.com", "*.example.com")


# ---------------------------------------------------------------------------
# load_scope
# ---------------------------------------------------------------------------

class TestLoadScope:
    def test_permissive_when_no_manifest(self, tmp_path, monkeypatch):
        monkeypatch.delenv("EVIDENCE_SCOPE_PATH", raising=False)
        load_scope.cache_clear()
        try:
            sc = load_scope(scope_path=str(tmp_path / "nonexistent.yaml"))
        finally:
            load_scope.cache_clear()
        assert not sc.is_loaded

    def test_permissive_when_env_points_to_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EVIDENCE_SCOPE_PATH", str(tmp_path / "missing.yaml"))
        load_scope.cache_clear()
        try:
            sc = load_scope()
        finally:
            load_scope.cache_clear()
        assert not sc.is_loaded

    def test_loads_manifest_via_explicit_path(self, tmp_path):
        manifest = _make_scope(
            tmp_path,
            "name: test-scope\nhosts:\n  - example.com\n",
        )
        sc = _fresh_scope(manifest)
        assert sc.is_loaded
        assert sc.name == "test-scope"
        assert "example.com" in sc.hosts

    def test_loads_via_env_var(self, tmp_path, monkeypatch):
        manifest = _make_scope(tmp_path, "name: env-scope\nhosts:\n  - env.example.com\n")
        monkeypatch.setenv("EVIDENCE_SCOPE_PATH", str(manifest))
        load_scope.cache_clear()
        try:
            sc = load_scope()
        finally:
            load_scope.cache_clear()
        assert sc.is_loaded
        assert sc.name == "env-scope"

    def test_deny_hosts_loaded(self, tmp_path):
        manifest = _make_scope(
            tmp_path,
            "name: s\nhosts:\n  - example.com\ndeny_hosts:\n  - bad.example.com\n",
        )
        sc = _fresh_scope(manifest)
        assert "bad.example.com" in sc.deny_hosts

    def test_path_prefixes_loaded(self, tmp_path):
        manifest = _make_scope(
            tmp_path,
            "name: s\npath_prefixes:\n  - /opt/data/\n",
        )
        sc = _fresh_scope(manifest)
        assert "/opt/data/" in sc.path_prefixes


# ---------------------------------------------------------------------------
# check_url — permissive (no manifest loaded)
# ---------------------------------------------------------------------------

class TestCheckUrlPermissive:
    """When scope has no manifest, every URL is in-scope."""

    def test_any_url_passes_when_no_manifest(self):
        sc = Scope()  # not loaded
        ok, reason = check_url("https://attacker.com/evil", scope=sc)
        assert ok
        assert "permissive" in reason


# ---------------------------------------------------------------------------
# check_url — with a loaded scope
# ---------------------------------------------------------------------------

FULL_YAML = """\
name: my-test
hosts:
  - example.com
  - "*.example.com"
deny_hosts:
  - internal.example.com
"""


@pytest.fixture
def loaded_scope(tmp_path) -> Scope:
    manifest = _make_scope(tmp_path, FULL_YAML)
    return _fresh_scope(manifest)


class TestCheckUrl:
    def test_exact_host_allowed(self, loaded_scope):
        ok, _ = check_url("https://example.com/path", scope=loaded_scope)
        assert ok

    def test_wildcard_subdomain_allowed(self, loaded_scope):
        ok, _ = check_url("https://sub.example.com/api", scope=loaded_scope)
        assert ok

    def test_denied_host_blocked(self, loaded_scope):
        ok, reason = check_url("https://internal.example.com/", scope=loaded_scope)
        assert not ok
        assert "explicitly denied" in reason

    def test_out_of_scope_host_blocked(self, loaded_scope):
        ok, reason = check_url("https://outsider.com/", scope=loaded_scope)
        assert not ok
        assert "not in allow-list" in reason

    def test_unparseable_url_blocked(self, loaded_scope):
        ok, reason = check_url("not-a-url", scope=loaded_scope)
        assert not ok
        assert "could not parse host" in reason

    def test_no_hosts_in_scope_rejects_all(self, tmp_path):
        manifest = _make_scope(tmp_path, "name: empty-hosts\nhosts:\n")
        sc = _fresh_scope(manifest)
        ok, reason = check_url("https://anything.com/", scope=sc)
        assert not ok
        assert "no allowed hosts" in reason


# ---------------------------------------------------------------------------
# check_path — permissive (no manifest loaded)
# ---------------------------------------------------------------------------

class TestCheckPathPermissive:
    def test_any_path_passes_when_no_manifest(self):
        sc = Scope()
        ok, reason = check_path("/etc/passwd", scope=sc)
        assert ok
        assert "permissive" in reason


# ---------------------------------------------------------------------------
# check_path — with a loaded scope
# ---------------------------------------------------------------------------

class TestCheckPath:
    def test_matching_prefix_allowed(self, tmp_path):
        data_dir = tmp_path / "engagement"
        data_dir.mkdir()
        manifest = _make_scope(
            tmp_path,
            f"name: s\npath_prefixes:\n  - {str(data_dir)}\n",
        )
        sc = _fresh_scope(manifest)
        target = data_dir / "report.txt"
        target.write_text("x")
        ok, _ = check_path(str(target), scope=sc)
        assert ok

    def test_non_matching_prefix_blocked(self, tmp_path):
        manifest = _make_scope(
            tmp_path,
            "name: s\npath_prefixes:\n  - /opt/data/\n",
        )
        sc = _fresh_scope(manifest)
        ok, reason = check_path("/tmp/evil.txt", scope=sc)
        assert not ok
        assert "outside path_prefixes" in reason

    def test_no_path_prefixes_allows_all(self, tmp_path):
        # A loaded scope with empty path_prefixes is permissive on paths
        manifest = _make_scope(tmp_path, "name: s\nhosts:\n  - example.com\n")
        sc = _fresh_scope(manifest)
        ok, reason = check_path("/any/path", scope=sc)
        assert ok
        assert "no path restrictions" in reason

    def test_nonexistent_path_uses_raw_string(self, tmp_path):
        # Path does not exist → raw string used (no resolve())
        manifest = _make_scope(
            tmp_path,
            "name: s\npath_prefixes:\n  - /opt/data/\n",
        )
        sc = _fresh_scope(manifest)
        ok, reason = check_path("/opt/data/report.txt", scope=sc)
        assert ok

    def test_check_path_rejects_parent_traversal_escape(self, tmp_path):
        # A non-existent path that climbs out of the prefix with ../ must be rejected,
        # even though its raw string starts with the prefix. Path()/".." keeps this
        # native-separator on each OS so the guard is exercised on both CI legs.
        inside = tmp_path / "engagement"
        inside.mkdir()
        manifest = _make_scope(tmp_path, f"name: s\npath_prefixes:\n  - {str(inside)}\n")
        sc = _fresh_scope(manifest)
        escape = str(inside / ".." / "secret.txt")  # a ../ escape out of the prefix
        ok, reason = check_path(escape, scope=sc)
        assert not ok
        assert "traversal" in reason.lower()


# ---------------------------------------------------------------------------
# _detect_repo_root — lines 90-98
# ---------------------------------------------------------------------------

class TestDetectRepoRoot:
    def test_success_returns_path(self, monkeypatch):
        """Lines 90-96: subprocess.check_output succeeds -> returns Path."""
        import subprocess as sp

        def _fake_check_output(cmd, **kwargs):
            return "/fake/repo/root\n"

        monkeypatch.setattr(sp, "check_output", _fake_check_output)

        # Import subprocess inside the function at call time, so we need to
        # patch via the scope_binding module's use of subprocess.
        import importlib
        import sys

        # Reload to get a fresh function scope that will call our patched subprocess
        # Actually _detect_repo_root imports subprocess inside the function body,
        # so monkeypatching sys.modules["subprocess"] is the correct seam.
        real_subprocess = sys.modules.get("subprocess")
        import subprocess as real_sp
        monkeypatch.setattr(real_sp, "check_output", _fake_check_output)

        result = _detect_repo_root()
        assert result == Path("/fake/repo/root")

    def test_empty_output_returns_none(self, monkeypatch):
        """Lines 90-96: empty git output -> returns None."""
        import subprocess as real_sp

        monkeypatch.setattr(real_sp, "check_output", lambda *a, **kw: "")
        result = _detect_repo_root()
        assert result is None

    def test_file_not_found_returns_none(self, monkeypatch):
        """Line 97-98: FileNotFoundError (git not on PATH) -> returns None."""
        import subprocess as real_sp

        def _raise(*a, **kw):
            raise FileNotFoundError("git not found")

        monkeypatch.setattr(real_sp, "check_output", _raise)
        result = _detect_repo_root()
        assert result is None

    def test_called_process_error_returns_none(self, monkeypatch):
        """Line 97-98: CalledProcessError (not in a git repo) -> returns None."""
        import subprocess as real_sp

        def _raise(*a, **kw):
            raise real_sp.CalledProcessError(128, "git")

        monkeypatch.setattr(real_sp, "check_output", _raise)
        result = _detect_repo_root()
        assert result is None

    def test_timeout_returns_none(self, monkeypatch):
        """Line 97-98: TimeoutExpired -> returns None."""
        import subprocess as real_sp

        def _raise(*a, **kw):
            raise real_sp.TimeoutExpired("git", 2)

        monkeypatch.setattr(real_sp, "check_output", _raise)
        result = _detect_repo_root()
        assert result is None


# ---------------------------------------------------------------------------
# load_scope: lines 113-117 — _detect_repo_root path
# and lines 124-125 — OSError on read_text
# ---------------------------------------------------------------------------

class TestLoadScopeRepoPaths:
    def test_finds_manifest_via_detect_repo_root(self, tmp_path, monkeypatch):
        """Lines 113-117: no explicit path or env var; _detect_repo_root returns
        a root where .claude/evidence-scope.yaml exists."""
        scope_dir = tmp_path / ".claude"
        scope_dir.mkdir()
        manifest = scope_dir / "evidence-scope.yaml"
        manifest.write_text("name: auto-detected\nhosts:\n  - auto.example.com\n", encoding="utf-8")

        import subprocess as real_sp
        monkeypatch.setattr(real_sp, "check_output", lambda *a, **kw: str(tmp_path) + "\n")
        monkeypatch.delenv("EVIDENCE_SCOPE_PATH", raising=False)

        load_scope.cache_clear()
        try:
            sc = load_scope()
        finally:
            load_scope.cache_clear()

        assert sc.is_loaded
        assert sc.name == "auto-detected"

    def test_oserror_on_read_returns_empty_scope(self, tmp_path, monkeypatch):
        """Lines 124-125: OSError when reading the manifest file -> returns empty Scope."""
        manifest = tmp_path / "scope.yaml"
        manifest.write_text("name: x\n", encoding="utf-8")

        original_read_text = Path.read_text

        def _failing_read_text(self, *args, **kwargs):
            if self == manifest:
                raise OSError("permission denied")
            return original_read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", _failing_read_text)

        load_scope.cache_clear()
        try:
            sc = load_scope(scope_path=str(manifest))
        finally:
            load_scope.cache_clear()

        assert not sc.is_loaded
