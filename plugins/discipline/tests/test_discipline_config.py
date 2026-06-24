"""Unit tests for discipline_config.py — the shared per-project config loader.

Covers the resolution layering (env > .local.md frontmatter > git auto-detect >
default), every scalar/csv/bool/routes parser, the git-detection subprocess
seams (mocked, hermetic + offline), the `has_gh`/`has_bd` PATH probes, and
`normalize_path_to_repo`.

conftest.py puts the plugin's scripts/ dir on sys.path so the module imports by
bare name. `get_config` is `lru_cache`-wrapped, so every test that touches it
clears the cache first (mirroring test_plan_issue_check.py's convention).
"""
import subprocess
from pathlib import Path

import pytest

import discipline_config
from discipline_config import (
    DisciplineConfig,
    _parse_frontmatter,
    _detect_git_root,
    _detect_repo,
    _detect_main_branch,
    _split_csv,
    _parse_bool,
    _parse_routes,
    get_config,
    normalize_path_to_repo,
)


@pytest.fixture(autouse=True)
def _clear_config_cache():
    """get_config is lru_cached for the process; reset between tests."""
    get_config.cache_clear()
    yield
    get_config.cache_clear()


# --------------------------------------------------------------------------- #
# _parse_frontmatter
# --------------------------------------------------------------------------- #
class TestParseFrontmatter:
    def test_empty_text_returns_empty(self):
        assert _parse_frontmatter("") == {}

    def test_no_opening_fence_returns_empty(self):
        assert _parse_frontmatter("# heading\nbody text\n") == {}

    def test_basic_key_value(self):
        out = _parse_frontmatter("---\nrepo: owner/name\n---\nbody")
        assert out == {"repo": "owner/name"}

    def test_closing_fence_stops_parsing(self):
        # `after` is below the closing fence and must be ignored.
        out = _parse_frontmatter("---\nrepo: a/b\n---\nafter: ignored\n")
        assert out == {"repo": "a/b"}

    def test_single_quoted_value_unwrapped(self):
        out = _parse_frontmatter("---\nrepo: 'owner/name'\n---")
        assert out["repo"] == "owner/name"

    def test_double_quoted_value_unwrapped(self):
        out = _parse_frontmatter('---\nrepo: "owner/name"\n---')
        assert out["repo"] == "owner/name"

    def test_comment_line_skipped(self):
        out = _parse_frontmatter("---\n# a comment\nrepo: x/y\n---")
        assert out == {"repo": "x/y"}

    def test_blank_line_skipped(self):
        out = _parse_frontmatter("---\n\nrepo: x/y\n---")
        assert out == {"repo": "x/y"}

    def test_indented_line_skipped(self):
        # Indented lines are nested YAML; the scalar parser skips them.
        out = _parse_frontmatter("---\nparent:\n  child: v\nrepo: x/y\n---")
        assert out == {"parent": "", "repo": "x/y"}

    def test_line_without_colon_skipped(self):
        out = _parse_frontmatter("---\nnocolon here\nrepo: x/y\n---")
        assert out == {"repo": "x/y"}

    def test_value_with_colon_keeps_remainder(self):
        # partition on first ':' keeps later colons in the value.
        out = _parse_frontmatter("---\nurl: http://x/y\n---")
        assert out["url"] == "http://x/y"

    def test_unterminated_frontmatter_within_60_lines(self):
        # No closing fence but keys within the first 60 lines still parse.
        out = _parse_frontmatter("---\nrepo: x/y\nmore: stuff\n")
        assert out == {"repo": "x/y", "more": "stuff"}

    def test_single_char_value_not_treated_as_quote_pair(self):
        # len(value) < 2 guard: a lone quote stays as-is.
        out = _parse_frontmatter("---\nk: '\n---")
        assert out["k"] == "'"


# --------------------------------------------------------------------------- #
# git detection seams (mocked — hermetic, offline)
# --------------------------------------------------------------------------- #
class TestDetectGitRoot:
    def test_returns_path_on_success(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "check_output", lambda *a, **k: "/repo/root\n"
        )
        assert _detect_git_root() == Path("/repo/root")

    def test_blank_output_returns_none(self, monkeypatch):
        monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: "  \n")
        assert _detect_git_root() is None

    def test_git_missing_returns_none(self, monkeypatch):
        def boom(*a, **k):
            raise FileNotFoundError
        monkeypatch.setattr(subprocess, "check_output", boom)
        assert _detect_git_root() is None

    def test_called_process_error_returns_none(self, monkeypatch):
        def boom(*a, **k):
            raise subprocess.CalledProcessError(128, "git")
        monkeypatch.setattr(subprocess, "check_output", boom)
        assert _detect_git_root() is None

    def test_timeout_returns_none(self, monkeypatch):
        def boom(*a, **k):
            raise subprocess.TimeoutExpired("git", 2)
        monkeypatch.setattr(subprocess, "check_output", boom)
        assert _detect_git_root() is None


class TestDetectRepo:
    def test_ssh_url(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "check_output",
            lambda *a, **k: "git@github.com:owner/repo.git\n",
        )
        assert _detect_repo() == "owner/repo"

    def test_https_url(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "check_output",
            lambda *a, **k: "https://github.com/owner/repo.git\n",
        )
        assert _detect_repo() == "owner/repo"

    def test_url_without_dot_git_suffix(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "check_output",
            lambda *a, **k: "https://github.com/owner/repo\n",
        )
        assert _detect_repo() == "owner/repo"

    def test_url_with_trailing_slash(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "check_output",
            lambda *a, **k: "https://github.com/owner/repo/\n",
        )
        assert _detect_repo() == "owner/repo"

    def test_blank_url_returns_none(self, monkeypatch):
        monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: "\n")
        assert _detect_repo() is None

    def test_unparseable_url_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "check_output", lambda *a, **k: "not-a-url\n"
        )
        assert _detect_repo() is None

    def test_subprocess_error_returns_none(self, monkeypatch):
        def boom(*a, **k):
            raise subprocess.CalledProcessError(1, "git")
        monkeypatch.setattr(subprocess, "check_output", boom)
        assert _detect_repo() is None


class TestDetectMainBranch:
    def test_none_repo_root_returns_main(self):
        assert _detect_main_branch(None) == "main"

    def test_parses_symbolic_ref(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "check_output",
            lambda *a, **k: "refs/remotes/origin/develop\n",
        )
        assert _detect_main_branch(Path("/repo")) == "develop"

    def test_empty_branch_falls_back_to_main(self, monkeypatch):
        # rsplit yields '' for a trailing slash -> `or 'main'`.
        monkeypatch.setattr(
            subprocess, "check_output",
            lambda *a, **k: "refs/remotes/origin/\n",
        )
        assert _detect_main_branch(Path("/repo")) == "main"

    def test_subprocess_error_falls_back_to_main(self, monkeypatch):
        def boom(*a, **k):
            raise subprocess.CalledProcessError(1, "git")
        monkeypatch.setattr(subprocess, "check_output", boom)
        assert _detect_main_branch(Path("/repo")) == "main"


# --------------------------------------------------------------------------- #
# scalar parsers
# --------------------------------------------------------------------------- #
class TestSplitCsv:
    def test_basic(self):
        assert _split_csv("a, b ,c") == ("a", "b", "c")

    def test_drops_empty_parts(self):
        assert _split_csv("a,,b,") == ("a", "b")

    def test_empty_string(self):
        assert _split_csv("") == ()


class TestParseBool:
    @pytest.mark.parametrize("v", ["true", "YES", "1", "On", "  true  "])
    def test_truthy(self, v):
        assert _parse_bool(v, default=False) is True

    @pytest.mark.parametrize("v", ["false", "NO", "0", "Off"])
    def test_falsy(self, v):
        assert _parse_bool(v, default=True) is False

    def test_unrecognized_returns_default(self):
        assert _parse_bool("maybe", default=True) is True
        assert _parse_bool("maybe", default=False) is False


class TestParseRoutes:
    def test_basic(self):
        assert _parse_routes("a=x; b=y") == {"a": "x", "b": "y"}

    def test_skips_pairs_without_equals(self):
        assert _parse_routes("a=x; broken; b=y") == {"a": "x", "b": "y"}

    def test_empty_string(self):
        assert _parse_routes("") == {}

    def test_strips_whitespace(self):
        assert _parse_routes("  a = x  ") == {"a": "x"}


# --------------------------------------------------------------------------- #
# DisciplineConfig.has_gh / has_bd
# --------------------------------------------------------------------------- #
class TestHasGh:
    def test_false_when_no_repo(self):
        assert DisciplineConfig(repo=None).has_gh is False

    def test_true_when_gh_present(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)
        assert DisciplineConfig(repo="o/r").has_gh is True

    def test_false_when_gh_missing(self, monkeypatch):
        def boom(*a, **k):
            raise FileNotFoundError
        monkeypatch.setattr(subprocess, "run", boom)
        assert DisciplineConfig(repo="o/r").has_gh is False

    def test_false_on_called_process_error(self, monkeypatch):
        def boom(*a, **k):
            raise subprocess.CalledProcessError(1, "gh")
        monkeypatch.setattr(subprocess, "run", boom)
        assert DisciplineConfig(repo="o/r").has_gh is False


class TestHasBd:
    def test_false_when_no_ledger(self):
        assert DisciplineConfig(bd_ledger=None).has_bd is False

    def test_true_when_bd_present(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)
        assert DisciplineConfig(bd_ledger="/ledger").has_bd is True

    def test_false_when_bd_missing(self, monkeypatch):
        def boom(*a, **k):
            raise FileNotFoundError
        monkeypatch.setattr(subprocess, "run", boom)
        assert DisciplineConfig(bd_ledger="/ledger").has_bd is False

    def test_false_on_timeout(self, monkeypatch):
        def boom(*a, **k):
            raise subprocess.TimeoutExpired("bd", 2)
        monkeypatch.setattr(subprocess, "run", boom)
        assert DisciplineConfig(bd_ledger="/ledger").has_bd is False


# --------------------------------------------------------------------------- #
# get_config — layering
# --------------------------------------------------------------------------- #
@pytest.fixture
def no_git(monkeypatch):
    """Disable all git auto-detection so config layering is deterministic."""
    monkeypatch.setattr(discipline_config, "_detect_git_root", lambda: None)
    monkeypatch.setattr(discipline_config, "_detect_repo", lambda: None)
    monkeypatch.setattr(
        discipline_config, "_detect_main_branch", lambda root: "main"
    )
    return monkeypatch


@pytest.fixture
def repo_with_local(monkeypatch, tmp_path):
    """Point auto-detection at a tmp repo root and prepare to write a .local.md."""
    monkeypatch.setattr(discipline_config, "_detect_git_root", lambda: tmp_path)
    monkeypatch.setattr(discipline_config, "_detect_repo", lambda: None)
    monkeypatch.setattr(
        discipline_config, "_detect_main_branch", lambda root: "main"
    )

    def _write(frontmatter: str):
        cfg_dir = tmp_path / ".claude"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "discipline.local.md").write_text(frontmatter, encoding="utf-8")
        return tmp_path

    return _write


class TestGetConfigDefaults:
    def test_defaults_when_no_git_no_local(self, clean_env, no_git):
        cfg = get_config()
        assert cfg.repo is None
        assert cfg.main_branch == "main"
        assert cfg.repo_root is None
        assert cfg.inject_issues is True
        assert cfg.require_value_justification is False

    def test_cached_within_process(self, clean_env, no_git):
        assert get_config() is get_config()


class TestGetConfigLocalMd:
    def test_reads_every_scalar_key(self, clean_env, repo_with_local):
        repo_with_local(
            "---\n"
            "repo: owner/proj\n"
            "main-branch: develop\n"
            "source-extensions: .py, .rs\n"
            "spec-pattern: ^spec/.*\\.md$\n"
            "plan-pattern: ^plan/.*\\.md$\n"
            "bd-id-pattern: zz-[0-9]+\n"
            "bd-ledger: .beads\n"
            "require-value-justification: true\n"
            "require-frontmatter-fields: title, status\n"
            "frontmatter-skip-prefixes: tmp/, out/\n"
            "pitfalls-root: docs/pitfalls\n"
            "pitfalls-routes: a=x; b=y\n"
            "inject-issues: false\n"
            "inject-branch-state: false\n"
            "---\n"
        )
        cfg = get_config()
        assert cfg.repo == "owner/proj"
        assert cfg.main_branch == "develop"
        assert cfg.source_extensions == (".py", ".rs")
        assert cfg.spec_pattern == r"^spec/.*\.md$"
        assert cfg.plan_pattern == r"^plan/.*\.md$"
        assert cfg.bd_id_pattern == "zz-[0-9]+"
        assert cfg.bd_ledger == ".beads"
        assert cfg.require_value_justification is True
        assert cfg.require_frontmatter_fields == ("title", "status")
        assert cfg.frontmatter_skip_prefixes == ("tmp/", "out/")
        assert cfg.pitfalls_root == "docs/pitfalls"
        assert cfg.pitfalls_routes == {"a": "x", "b": "y"}
        assert cfg.inject_issues is False
        assert cfg.inject_branch_state is False

    def test_empty_local_md_keeps_defaults(self, clean_env, repo_with_local):
        repo_with_local("---\n---\n")
        cfg = get_config()
        assert cfg.repo is None
        assert cfg.main_branch == "main"

    def test_local_md_read_error_is_swallowed(self, clean_env, repo_with_local, monkeypatch):
        repo_with_local("---\nrepo: x/y\n---\n")

        # Force read_text to raise OSError -> fields_out = {} (lines 246-247).
        orig_read = Path.read_text

        def flaky(self, *a, **k):
            if self.name == "discipline.local.md":
                raise OSError("boom")
            return orig_read(self, *a, **k)

        monkeypatch.setattr(Path, "read_text", flaky)
        cfg = get_config()
        # No keys applied; defaults survive.
        assert cfg.repo is None

    def test_missing_local_md_file_skipped(self, clean_env, monkeypatch, tmp_path):
        # repo_root set but no .claude/discipline.local.md -> is_file() False.
        monkeypatch.setattr(discipline_config, "_detect_git_root", lambda: tmp_path)
        monkeypatch.setattr(discipline_config, "_detect_repo", lambda: None)
        monkeypatch.setattr(
            discipline_config, "_detect_main_branch", lambda root: "main"
        )
        cfg = get_config()
        assert cfg.repo is None
        assert cfg.repo_root == tmp_path


class TestGetConfigEnvOverrides:
    def test_every_env_var_overrides(self, clean_env, repo_with_local, monkeypatch):
        # local.md sets baseline values; env must win over all of them.
        repo_with_local(
            "---\nrepo: local/repo\nmain-branch: localbranch\n"
            "inject-issues: false\n---\n"
        )
        monkeypatch.setenv("DISCIPLINE_REPO", "env/repo")
        monkeypatch.setenv("DISCIPLINE_MAIN_BRANCH", "envbranch")
        monkeypatch.setenv("DISCIPLINE_SOURCE_EXTENSIONS", ".env1,.env2")
        monkeypatch.setenv("DISCIPLINE_SPEC_PATTERN", "ENVSPEC")
        monkeypatch.setenv("DISCIPLINE_PLAN_PATTERN", "ENVPLAN")
        monkeypatch.setenv("DISCIPLINE_BD_ID_PATTERN", "ENVID")
        monkeypatch.setenv("DISCIPLINE_BD_LEDGER", "envledger")
        monkeypatch.setenv("DISCIPLINE_REQUIRE_VALUE_JUSTIFICATION", "true")
        monkeypatch.setenv("DISCIPLINE_REQUIRE_FRONTMATTER_FIELDS", "ef1,ef2")
        monkeypatch.setenv("DISCIPLINE_FRONTMATTER_SKIP_PREFIXES", "ep1/,ep2/")
        monkeypatch.setenv("DISCIPLINE_PITFALLS_ROOT", "envroot")
        monkeypatch.setenv("DISCIPLINE_PITFALLS_ROUTES", "k=v")
        monkeypatch.setenv("DISCIPLINE_INJECT_ISSUES", "true")
        monkeypatch.setenv("DISCIPLINE_INJECT_BRANCH_STATE", "false")

        cfg = get_config()
        assert cfg.repo == "env/repo"
        assert cfg.main_branch == "envbranch"
        assert cfg.source_extensions == (".env1", ".env2")
        assert cfg.spec_pattern == "ENVSPEC"
        assert cfg.plan_pattern == "ENVPLAN"
        assert cfg.bd_id_pattern == "ENVID"
        assert cfg.bd_ledger == "envledger"
        assert cfg.require_value_justification is True
        assert cfg.require_frontmatter_fields == ("ef1", "ef2")
        assert cfg.frontmatter_skip_prefixes == ("ep1/", "ep2/")
        assert cfg.pitfalls_root == "envroot"
        assert cfg.pitfalls_routes == {"k": "v"}
        assert cfg.inject_issues is True
        assert cfg.inject_branch_state is False

    def test_env_overrides_apply_without_git(self, clean_env, no_git, monkeypatch):
        monkeypatch.setenv("DISCIPLINE_REPO", "env/only")
        cfg = get_config()
        assert cfg.repo == "env/only"


# --------------------------------------------------------------------------- #
# normalize_path_to_repo
# --------------------------------------------------------------------------- #
class TestNormalizePathToRepo:
    def test_backslashes_to_posix(self):
        # No repo_root, no worktree, no /docs/ -> returns posix form unchanged.
        assert normalize_path_to_repo(r"C:\a\b\c.py", None) == "C:/a/b/c.py"

    def test_worktree_strip_with_subpath(self):
        raw = "/x/.worktrees/feature/src/app.py"
        assert normalize_path_to_repo(raw, None) == "src/app.py"

    def test_worktree_strip_branch_only(self):
        # tail has no '/' -> returns the tail as-is.
        raw = "/x/.worktrees/feature"
        assert normalize_path_to_repo(raw, None) == "feature"

    def test_relative_to_repo_root(self, tmp_path):
        f = tmp_path / "src" / "main.py"
        f.parent.mkdir(parents=True)
        f.write_text("x", encoding="utf-8")
        assert normalize_path_to_repo(str(f), tmp_path) == "src/main.py"

    def test_outside_repo_root_falls_through(self, tmp_path):
        # A path outside repo_root raises ValueError in relative_to -> fall through.
        outside = "/totally/elsewhere/file.py"
        assert normalize_path_to_repo(outside, tmp_path) == "/totally/elsewhere/file.py"

    def test_docs_substring_fallback(self):
        raw = "/home/user/project/docs/spec.md"
        assert normalize_path_to_repo(raw, None) == "docs/spec.md"

    def test_docs_prefix_returned_as_is(self):
        assert normalize_path_to_repo("docs/plan.md", None) == "docs/plan.md"

    def test_plain_path_returned(self):
        assert normalize_path_to_repo("/no/docs/here/x.py".replace("docs", "src"), None) == "/no/src/here/x.py"
