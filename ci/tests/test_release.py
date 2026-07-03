"""Unit tests for ci/release.py pure logic and ci/check-versions.py drift/sync.

Run: python3 -m pytest ci/tests/   (or: uv run --with pytest python -m pytest ci/tests/)

Both modules are loaded by path because `check-versions.py` is hyphenated (not a
legal import name) and matches the repo's existing `lint-no-bare-python.py` style.

The git-path coverage (``_last_tag`` / ``_commits_for`` / ``plan`` / ``main``) runs
against a throwaway ``git init`` repo built per-test under ``tmp_path``; the module
globals (``REPO_ROOT`` / ``PLUGINS_DIR``) are repointed at it via ``monkeypatch`` so
they auto-restore and never touch the real tree.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

CI = Path(__file__).resolve().parent.parent


def _load(modname: str, filename: str):
    spec = importlib.util.spec_from_file_location(modname, CI / filename)
    mod = importlib.util.module_from_spec(spec)
    # Register before exec: a module loaded by path is not auto-added to sys.modules,
    # and @dataclass (in release.py) resolves cls.__module__ via sys.modules — without
    # this it gets None and raises AttributeError: 'NoneType' has no attribute '__dict__'.
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


release = _load("release", "release.py")
checkversions = _load("check_versions", "check-versions.py")


# --- parse_commit -------------------------------------------------------------

@pytest.mark.parametrize(
    "subject,expected",
    [
        ("feat(git): add thing", ("feat", "git", False)),
        ("fix(discipline): a bug", ("fix", "discipline", False)),
        ("feat(git)!: breaking", ("feat", "git", True)),
        ("refactor(docs)!: drop x", ("refactor", "docs", True)),
        ("chore: housekeeping", ("chore", None, False)),
        ("not a conventional commit", None),
        ("", None),
    ],
)
def test_parse_commit(subject, expected):
    c = release.parse_commit(subject)
    if expected is None:
        assert c is None
    else:
        assert (c.type, c.scope, c.breaking) == expected


def test_parse_commit_breaking_in_body():
    c = release.parse_commit("feat(git): x", "body\n\nBREAKING CHANGE: removed y")
    assert c is not None and c.breaking is True


# --- bump_for -----------------------------------------------------------------

def _c(type_, scope="git", breaking=False, desc="x"):
    return release.Commit(type_, scope, breaking, desc)


def test_bump_precedence():
    assert release.bump_for([_c("fix"), _c("feat")]) == "minor"
    assert release.bump_for([_c("feat"), _c("fix", breaking=True)]) == "major"
    assert release.bump_for([_c("fix"), _c("perf")]) == "patch"
    assert release.bump_for([_c("chore"), _c("docs")]) is None
    assert release.bump_for([]) is None


@pytest.mark.parametrize(
    "version,kind,expected",
    [
        ("0.2.0", "minor", "0.3.0"),
        ("0.2.0", "patch", "0.2.1"),
        ("0.2.3", "major", "1.0.0"),
        ("1.4.9", "patch", "1.4.10"),
    ],
)
def test_apply_bump(version, kind, expected):
    assert release.apply_bump(version, kind) == expected


def test_render_changelog_groups_and_skips_empty():
    section = release.render_changelog_section(
        "0.3.0", [_c("feat", desc="new flag"), _c("fix", desc="crash")]
    )
    assert "## 0.3.0" in section
    assert "### Features" in section and "- new flag" in section
    assert "### Fixes" in section and "- crash" in section
    assert "### Breaking" not in section


# --- check-versions drift/sync on a synthetic fixture tree --------------------

def _make_tree(tmp_path: Path, plugin_versions: dict, market_versions: dict) -> None:
    (tmp_path / ".claude-plugin").mkdir()
    for name, ver in plugin_versions.items():
        d = tmp_path / "plugins" / name / ".claude-plugin"
        d.mkdir(parents=True)
        (d / "plugin.json").write_text(
            json.dumps({"name": name, "version": ver}, indent=2) + "\n", encoding="utf-8"
        )
    market = {"plugins": [{"name": n, "version": v} for n, v in market_versions.items()]}
    (tmp_path / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(market, indent=2) + "\n", encoding="utf-8"
    )


def _point(tmp_path: Path) -> None:
    checkversions.REPO_ROOT = tmp_path
    checkversions.MARKETPLACE = tmp_path / ".claude-plugin" / "marketplace.json"
    checkversions.PLUGINS_DIR = tmp_path / "plugins"


def test_check_detects_version_drift(tmp_path):
    _make_tree(tmp_path, {"git": "0.2.0"}, {"git": "0.1.0"})
    _point(tmp_path)
    problems = checkversions.check()
    assert any("git" in p and "0.1.0" in p and "0.2.0" in p for p in problems)


def test_sync_fixes_only_drifted_entries(tmp_path):
    _make_tree(
        tmp_path,
        {"git": "0.2.0", "docs": "0.1.0"},
        {"git": "0.1.0", "docs": "0.1.0"},
    )
    _point(tmp_path)
    changed = checkversions.sync()
    assert changed == [("git", "0.1.0", "0.2.0")]
    assert checkversions.check() == []


def test_check_flags_plugin_missing_from_marketplace(tmp_path):
    _make_tree(tmp_path, {"git": "0.2.0", "newbie": "0.1.0"}, {"git": "0.2.0"})
    _point(tmp_path)
    problems = checkversions.check()
    assert any("newbie" in p and "missing from marketplace" in p for p in problems)


def test_check_flags_extra_marketplace_entry(tmp_path):
    # In marketplace.json but no plugins/<name>/.claude-plugin/plugin.json on disk.
    _make_tree(tmp_path, {"git": "0.2.0"}, {"git": "0.2.0", "ghost": "0.1.0"})
    _point(tmp_path)
    problems = checkversions.check()
    assert any("ghost" in p and "no plugins/ghost" in p for p in problems)
    # The extra entry is skipped in the version-compare loop (covers the `continue`),
    # so it is reported exactly once, not also as a version mismatch.
    assert sum("ghost" in p for p in problems) == 1


def test_sync_noop_when_already_in_sync(tmp_path):
    _make_tree(tmp_path, {"git": "0.2.0"}, {"git": "0.2.0"})
    _point(tmp_path)
    assert checkversions.sync() == []


def test_sync_skips_extra_marketplace_entry(tmp_path):
    # An entry not on disk must be left untouched by sync (covers the `continue`).
    _make_tree(tmp_path, {"git": "0.2.0"}, {"git": "0.1.0", "ghost": "9.9.9"})
    _point(tmp_path)
    changed = checkversions.sync()
    assert changed == [("git", "0.1.0", "0.2.0")]
    data = json.loads(
        (tmp_path / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    ghost = next(e for e in data["plugins"] if e["name"] == "ghost")
    assert ghost["version"] == "9.9.9"  # untouched


# --- check-versions main() CLI dispatch ---------------------------------------

def test_checkversions_main_check_clean(tmp_path, capsys):
    _make_tree(tmp_path, {"git": "0.2.0"}, {"git": "0.2.0"})
    _point(tmp_path)
    assert checkversions.main(["check-versions.py"]) == 0
    assert "clean" in capsys.readouterr().out


def test_checkversions_main_check_reports_drift(tmp_path, capsys):
    _make_tree(tmp_path, {"git": "0.2.0"}, {"git": "0.1.0"})
    _point(tmp_path)
    rc = checkversions.main(["check-versions.py", "--check"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "drift problem" in err and "git" in err
    assert "--fix" in err  # the remediation hint


def test_checkversions_main_fix_syncs(tmp_path, capsys):
    _make_tree(tmp_path, {"git": "0.2.0"}, {"git": "0.1.0"})
    _point(tmp_path)
    rc = checkversions.main(["check-versions.py", "--fix"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "synced git 0.1.0 -> 0.2.0" in out
    assert checkversions.check() == []


def test_checkversions_main_fix_already_synced(tmp_path, capsys):
    _make_tree(tmp_path, {"git": "0.2.0"}, {"git": "0.2.0"})
    _point(tmp_path)
    rc = checkversions.main(["check-versions.py", "--fix"])
    assert rc == 0
    assert "already in sync" in capsys.readouterr().out


def test_checkversions_main_bad_mode(capsys):
    rc = checkversions.main(["check-versions.py", "--bogus"])
    assert rc == 2
    assert "usage:" in capsys.readouterr().err


# --- release.py git-path coverage on a throwaway git repo ---------------------


def _git_in(repo: Path, *args: str, allow_fail: bool = False) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=not allow_fail,
    )
    return proc.stdout


def _write_plugin(repo: Path, name: str, version: str) -> None:
    d = repo / "plugins" / name / ".claude-plugin"
    d.mkdir(parents=True, exist_ok=True)
    (d / "plugin.json").write_text(
        json.dumps({"name": name, "version": version}, indent=2) + "\n",
        encoding="utf-8",
    )


def _commit(repo: Path, subject: str, body: str = "") -> None:
    """Create an empty commit with the given subject/body (no working-tree churn)."""
    args = ["commit", "-q", "--allow-empty", "-m", subject]
    if body:
        args += ["-m", body]
    _git_in(repo, *args)


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    """A throwaway git repo with a plugins/ tree, with release.py repointed at it.

    Yields the repo Path. The first commit seeds an empty root so later tags/log
    ranges are well-defined. ``release.REPO_ROOT`` / ``PLUGINS_DIR`` are restored
    automatically by monkeypatch teardown.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_in(repo, "init", "-q", "-b", "main")
    _git_in(repo, "config", "user.name", "Test")
    _git_in(repo, "config", "user.email", "test@example.test")
    _git_in(repo, "config", "commit.gpgsign", "false")
    _git_in(repo, "config", "tag.gpgsign", "false")
    # marketplace.json so _load_sync()'s check-versions can resolve (when used).
    (repo / ".claude-plugin").mkdir()
    (repo / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"plugins": []}, indent=2) + "\n", encoding="utf-8"
    )
    (repo / "plugins").mkdir()
    _commit(repo, "chore: root")  # non-conforming-scope seed commit
    monkeypatch.setattr(release, "REPO_ROOT", repo)
    monkeypatch.setattr(release, "PLUGINS_DIR", repo / "plugins")
    return repo


# --- _last_tag ----------------------------------------------------------------

def test_last_tag_none_when_no_tags(git_repo):
    _write_plugin(git_repo, "git", "1.0.0")
    assert release._last_tag("git") is None


def test_last_tag_picks_highest_semver(git_repo):
    _write_plugin(git_repo, "git", "1.0.0")
    _commit(git_repo, "chore: a")
    _git_in(git_repo, "tag", "git-v1.0.0")
    _commit(git_repo, "chore: b")
    _git_in(git_repo, "tag", "git-v1.2.0")
    _commit(git_repo, "chore: c")
    _git_in(git_repo, "tag", "git-v1.10.0")  # numeric-aware sort, not lexical
    # An unrelated plugin's tag must not be matched by the "git-v*" glob.
    _git_in(git_repo, "tag", "docs-v9.9.9")
    assert release._last_tag("git") == "git-v1.10.0"


# --- _commits_for -------------------------------------------------------------

def test_commits_for_full_history_when_untagged(git_repo):
    _write_plugin(git_repo, "git", "1.0.0")
    _commit(git_repo, "feat(git): one")
    _commit(git_repo, "fix(docs): unrelated scope")  # filtered: scope != name
    _commit(git_repo, "feat(git): two")
    commits = release._commits_for("git")
    descs = {c.desc for c in commits}
    assert descs == {"one", "two"}
    assert all(c.scope == "git" for c in commits)


def test_commits_for_only_since_last_tag(git_repo):
    _write_plugin(git_repo, "git", "1.0.0")
    _commit(git_repo, "feat(git): pre-tag")
    _git_in(git_repo, "tag", "git-v1.1.0")
    _commit(git_repo, "fix(git): post-tag")
    commits = release._commits_for("git")
    assert [c.desc for c in commits] == ["post-tag"]  # pre-tag excluded by range


def test_commits_for_picks_up_breaking_from_body(git_repo):
    _write_plugin(git_repo, "git", "1.0.0")
    _commit(git_repo, "feat(git): big", "BREAKING CHANGE: drops the old API")
    commits = release._commits_for("git")
    assert len(commits) == 1 and commits[0].breaking is True


# --- plan ---------------------------------------------------------------------

def test_plan_nothing_to_do_at_tag_head(git_repo):
    # (a) tag at HEAD with no newer commits => no bump.
    _write_plugin(git_repo, "git", "1.0.0")
    _commit(git_repo, "feat(git): shipped")
    _git_in(git_repo, "tag", "git-v1.0.0")  # HEAD == tag, nothing after
    assert release.plan() == []


def test_plan_feat_proposes_minor(git_repo):
    # (b) one feat after the tag => minor bump.
    _write_plugin(git_repo, "git", "1.0.0")
    _commit(git_repo, "feat(git): base")
    _git_in(git_repo, "tag", "git-v1.0.0")
    _commit(git_repo, "feat(git): shiny new flag")
    plans = release.plan()
    assert len(plans) == 1
    name, old, new, commits = plans[0]
    assert (name, old, new) == ("git", "1.0.0", "1.1.0")
    assert [c.desc for c in commits] == ["shiny new flag"]


def test_plan_fix_proposes_patch(git_repo):
    # (c) fix => patch.
    _write_plugin(git_repo, "git", "1.2.3")
    _git_in(git_repo, "tag", "git-v1.2.3")
    _commit(git_repo, "fix(git): off-by-one")
    plans = release.plan()
    assert plans[0][:3] == ("git", "1.2.3", "1.2.4")


def test_plan_scopeless_chore_is_skipped(git_repo):
    # (c) a scopeless `chore:` (the squash-subject case) yields no bump.
    _write_plugin(git_repo, "git", "1.0.0")
    _git_in(git_repo, "tag", "git-v1.0.0")
    _commit(git_repo, "chore: squashed subject with no scope")
    # parse_commit returns a Commit (chore/None scope) but scope != name, so it is
    # filtered out of _commits_for and bump_for sees nothing => no plan entry.
    assert release._commits_for("git") == []
    assert release.plan() == []


def test_plan_breaking_proposes_major(git_repo):
    # (d) breaking-change marker => major.
    _write_plugin(git_repo, "git", "1.4.2")
    _git_in(git_repo, "tag", "git-v1.4.2")
    _commit(git_repo, "feat(git)!: rip out legacy")
    plans = release.plan()
    assert plans[0][:3] == ("git", "1.4.2", "2.0.0")


def test_plan_spans_multiple_plugins(git_repo):
    _write_plugin(git_repo, "git", "1.0.0")
    _write_plugin(git_repo, "docs", "0.5.0")
    _git_in(git_repo, "tag", "git-v1.0.0")
    _git_in(git_repo, "tag", "docs-v0.5.0")
    _commit(git_repo, "fix(git): patch it")
    _commit(git_repo, "feat(docs): new section")
    plans = {p[0]: p[1:3] for p in release.plan()}
    # fix(git) => patch (1.0.1); feat(docs) => minor (0.6.0).
    assert plans == {"git": ("1.0.0", "1.0.1"), "docs": ("0.5.0", "0.6.0")}


# --- _set_version / _prepend_changelog ----------------------------------------

def test_set_version_rewrites_plugin_json(git_repo):
    _write_plugin(git_repo, "git", "1.0.0")
    release._set_version("git", "1.1.0")
    data = json.loads(
        (git_repo / "plugins" / "git" / ".claude-plugin" / "plugin.json").read_text(
            encoding="utf-8"
        )
    )
    assert data["version"] == "1.1.0"


def test_prepend_changelog_creates_then_prepends(git_repo):
    _write_plugin(git_repo, "git", "1.0.0")
    release._prepend_changelog("git", "## 1.0.0\n\n### Fixes\n- a\n")
    path = git_repo / "plugins" / "git" / "CHANGELOG.md"
    first = path.read_text(encoding="utf-8")
    assert first == "# git changelog\n\n## 1.0.0\n\n### Fixes\n- a\n"
    # Simulate a hand-authored intro paragraph sitting between the H1 and the
    # version list (this is the shape that exposed the double-H1 / wedged-intro bug).
    path.write_text(
        "# git changelog\n\n"
        "All notable changes to the **git** plugin are documented here.\n\n"
        "## 1.0.0\n\n### Fixes\n- a\n",
        encoding="utf-8",
    )
    # Second release inserts below the preamble/intro, above the prior `## ` section
    # — the intro must stay put and the header must not be duplicated.
    release._prepend_changelog("git", "## 1.1.0\n\n### Features\n- b\n")
    second = path.read_text(encoding="utf-8")
    assert second == (
        "# git changelog\n\n"
        "All notable changes to the **git** plugin are documented here.\n\n"
        "## 1.1.0\n\n### Features\n- b\n\n"
        "## 1.0.0\n\n### Fixes\n- a\n"
    )
    assert second.count("# git changelog") == 1


def test_prepend_changelog_tolerates_headerless_existing(git_repo):
    _write_plugin(git_repo, "git", "1.0.0")
    path = git_repo / "plugins" / "git" / "CHANGELOG.md"
    path.write_text("legacy content with no header\n", encoding="utf-8")
    release._prepend_changelog("git", "## 1.1.0\n\n### Fixes\n- z\n")
    text = path.read_text(encoding="utf-8")
    # Case 2 (headerless existing): the legacy body is the preamble and is preserved
    # verbatim — no H1 is fabricated — with the new section appended after it.
    assert text == "legacy content with no header\n\n## 1.1.0\n\n### Fixes\n- z\n"
    assert "legacy content with no header" in text
    assert text.index("legacy content with no header") < text.index("## 1.1.0")


def test_prepend_changelog_file_absent_creates_header_and_section(git_repo):
    _write_plugin(git_repo, "git", "1.0.0")
    path = git_repo / "plugins" / "git" / "CHANGELOG.md"
    assert not path.exists()
    release._prepend_changelog("git", "## 1.0.0\n\n### Fixes\n- a\n")
    text = path.read_text(encoding="utf-8")
    assert text == "# git changelog\n\n## 1.0.0\n\n### Fixes\n- a\n"


def test_prepend_changelog_ignores_version_heading_inside_fenced_code_block(git_repo):
    _write_plugin(git_repo, "git", "1.0.0")
    path = git_repo / "plugins" / "git" / "CHANGELOG.md"
    # A Keep-a-Changelog-style usage example embeds a `## ` line inside a fenced
    # code block in the intro prose. The naive first-match regex used to wedge the
    # new section right there instead of before the real first version heading.
    path.write_text(
        "# git changelog\n\n"
        "Example usage:\n\n"
        "```\n"
        "## 9.9.9\n"
        "```\n\n"
        "## 1.0.0\n\n### Fixes\n- a\n",
        encoding="utf-8",
    )
    release._prepend_changelog("git", "## 1.1.0\n\n### Features\n- b\n")
    text = path.read_text(encoding="utf-8")
    assert text == (
        "# git changelog\n\n"
        "Example usage:\n\n"
        "```\n"
        "## 9.9.9\n"
        "```\n\n"
        "## 1.1.0\n\n### Features\n- b\n\n"
        "## 1.0.0\n\n### Fixes\n- a\n"
    )
    assert text.count("# git changelog") == 1
    # The fenced example heading must remain inside the fence, untouched, and
    # before the newly-inserted real section.
    assert text.index("```\n## 9.9.9\n```") < text.index("## 1.1.0")


def test_prepend_changelog_inserts_between_preamble_and_first_section(git_repo):
    _write_plugin(git_repo, "git", "1.0.0")
    path = git_repo / "plugins" / "git" / "CHANGELOG.md"
    path.write_text(
        "# git changelog\n\n"
        "All notable changes to the **git** plugin are documented here.\n\n"
        "## 1.0.0\n\n### Fixes\n- a\n",
        encoding="utf-8",
    )
    release._prepend_changelog("git", "## 1.1.0\n\n### Features\n- b\n")
    text = path.read_text(encoding="utf-8")
    assert text == (
        "# git changelog\n\n"
        "All notable changes to the **git** plugin are documented here.\n\n"
        "## 1.1.0\n\n### Features\n- b\n\n"
        "## 1.0.0\n\n### Fixes\n- a\n"
    )
    assert text.count("# git changelog") == 1
    assert text.index("All notable changes") < text.index("## 1.1.0")
    assert text.index("## 1.1.0") < text.index("## 1.0.0")


# --- _current_version / _ondisk_plugins ---------------------------------------

def test_current_version_and_ondisk_plugins(git_repo):
    _write_plugin(git_repo, "git", "1.0.0")
    _write_plugin(git_repo, "docs", "0.5.0")
    assert release._current_version("git") == "1.0.0"
    assert release._ondisk_plugins() == ["docs", "git"]  # sorted


# --- _load_sync ---------------------------------------------------------------

def test_load_sync_returns_callable_sync():
    # Loads the real ci/check-versions.py by path (Path(__file__)-relative) and
    # hands back its sync(). Pure import + attribute fetch — no filesystem mutation,
    # so it's safe to call here without monkeypatching the repo tree.
    sync = release._load_sync()
    assert callable(sync)
    assert sync.__name__ == "sync"


# --- main() -------------------------------------------------------------------

def test_main_bad_mode_returns_2(capsys):
    rc = release.main(["release.py", "--bogus"])
    assert rc == 2
    assert "usage:" in capsys.readouterr().err


def test_main_nothing_to_do(git_repo, capsys):
    _write_plugin(git_repo, "git", "1.0.0")
    _commit(git_repo, "feat(git): shipped")
    _git_in(git_repo, "tag", "git-v1.0.0")  # HEAD == tag
    rc = release.main(["release.py"])  # default dry-run
    out = capsys.readouterr().out
    assert rc == 0
    assert "nothing to do" in out


def test_main_dry_run_prints_plan_writes_nothing(git_repo, capsys):
    _write_plugin(git_repo, "git", "1.0.0")
    _git_in(git_repo, "tag", "git-v1.0.0")
    _commit(git_repo, "feat(git): a brand new thing")
    pj = git_repo / "plugins" / "git" / ".claude-plugin" / "plugin.json"
    before = pj.read_text(encoding="utf-8")
    rc = release.main(["release.py", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "git 1.0.0 -> 1.1.0" in out
    assert "a brand new thing" in out  # changelog body rendered in dry-run
    assert "dry-run" in out
    assert pj.read_text(encoding="utf-8") == before  # nothing written


def test_main_apply_writes_commits_no_tag(git_repo, monkeypatch, capsys):
    _write_plugin(git_repo, "git", "1.0.0")
    _git_in(git_repo, "tag", "git-v1.0.0")
    _commit(git_repo, "feat(git): land the feature")

    # _load_sync() re-execs check-versions.py from its real on-disk location, which
    # would point at the real repo. Stub it to a no-op so --apply stays hermetic.
    monkeypatch.setattr(release, "_load_sync", lambda: (lambda: []))

    rc = release.main(["release.py", "--apply"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "git@1.1.0" in out
    assert "--tag" in out  # apply now defers tagging to the post-merge --tag step

    # plugin.json bumped on disk.
    pj = git_repo / "plugins" / "git" / ".claude-plugin" / "plugin.json"
    assert json.loads(pj.read_text(encoding="utf-8"))["version"] == "1.1.0"
    # CHANGELOG.md created.
    assert (git_repo / "plugins" / "git" / "CHANGELOG.md").exists()
    # A release commit landed, but NO tag was created on the branch.
    assert "chore(release): git@1.1.0" in _git_in(git_repo, "log", "--format=%s")
    assert "git-v1.1.0" not in _git_in(git_repo, "tag", "--list")
    # Working tree is clean (everything was committed by main()).
    assert _git_in(git_repo, "status", "--porcelain").strip() == ""


def test_main_apply_aborts_before_commit_on_invalid_h1_count(git_repo, monkeypatch, capsys):
    # Force case-2/headerless output from _prepend_changelog: an existing
    # CHANGELOG.md with zero `# ` headings stays at zero H1s after the new
    # `## ` section is appended (the section itself never adds an H1). The
    # post-write guard must catch this and abort --apply before any commit.
    _write_plugin(git_repo, "git", "1.0.0")
    _git_in(git_repo, "tag", "git-v1.0.0")
    _commit(git_repo, "feat(git): land the feature")
    changelog = git_repo / "plugins" / "git" / "CHANGELOG.md"
    changelog.write_text("legacy content with no header\n", encoding="utf-8")

    monkeypatch.setattr(release, "_load_sync", lambda: (lambda: []))
    commit_calls = []
    orig_git = release._git

    def spy_git(*args):
        if args and args[0] == "commit":
            commit_calls.append(args)
        return orig_git(*args)

    monkeypatch.setattr(release, "_git", spy_git)

    rc = release.main(["release.py", "--apply"])
    err = capsys.readouterr().err

    assert rc != 0
    assert commit_calls == []  # the tool must never commit a bad H1 count
    assert "git" in err and "CHANGELOG.md" in err
    # No release commit landed.
    assert "chore(release):" not in _git_in(git_repo, "log", "--format=%s")


def test_main_apply_is_atomic_across_plugins_on_h1_abort(git_repo, monkeypatch, capsys):
    # Two release-worthy plugins. The second (alphabetically later => processed
    # second) has a headerless CHANGELOG that yields H1==0 and must abort the run.
    # The FIRST plugin must be left completely unwritten -- no partial mutation (#33).
    _write_plugin(git_repo, "aaa", "1.0.0")
    _write_plugin(git_repo, "zzz", "1.0.0")
    _git_in(git_repo, "tag", "aaa-v1.0.0")
    _git_in(git_repo, "tag", "zzz-v1.0.0")
    _commit(git_repo, "feat(aaa): good change")
    _commit(git_repo, "feat(zzz): bad changelog shape")
    (git_repo / "plugins" / "zzz" / "CHANGELOG.md").write_text(
        "legacy content with no header\n", encoding="utf-8")
    aaa_pj = git_repo / "plugins" / "aaa" / ".claude-plugin" / "plugin.json"
    before = aaa_pj.read_text(encoding="utf-8")

    monkeypatch.setattr(release, "_load_sync", lambda: (lambda: []))
    rc = release.main(["release.py", "--apply"])

    assert rc != 0
    assert aaa_pj.read_text(encoding="utf-8") == before  # untouched -- the #33 proof
    assert not (git_repo / "plugins" / "aaa" / "CHANGELOG.md").exists()  # #33 proof
    assert "chore(release):" not in _git_in(git_repo, "log", "--format=%s")  # belt-and-suspenders


# --- D6: orphan guard + --tag mode --------------------------------------------

def test_is_ancestor_true_and_false(git_repo):
    _commit(git_repo, "chore: a")
    _git_in(git_repo, "tag", "anchor")
    _commit(git_repo, "chore: b")
    assert release._is_ancestor("anchor") is True
    head = _git_in(git_repo, "rev-parse", "HEAD").strip()
    _git_in(git_repo, "reset", "--hard", "anchor")
    _commit(git_repo, "chore: divergent")
    assert release._is_ancestor(head) is False


def test_main_refuses_orphaned_tag(git_repo, capsys):
    _write_plugin(git_repo, "git", "1.0.0")
    _commit(git_repo, "feat(git): shipped")
    _git_in(git_repo, "tag", "git-v1.0.0")            # tag at this commit
    _git_in(git_repo, "reset", "--hard", "HEAD~1")    # back before it
    _commit(git_repo, "feat(git): divergent")         # tag no longer an ancestor
    rc = release.main(["release.py", "--dry-run"])
    err = capsys.readouterr().err
    assert rc == 1 and "git-v1.0.0" in err and "ancestor" in err.lower()


def test_main_tag_creates_untagged_at_head(git_repo, capsys):
    _write_plugin(git_repo, "git", "1.1.0")
    _commit(git_repo, "chore(release): git@1.1.0")
    rc = release.main(["release.py", "--tag", "--no-push"])
    out = capsys.readouterr().out
    assert rc == 0 and "git-v1.1.0" in out
    assert "git-v1.1.0" in _git_in(git_repo, "tag", "--list")
    head = _git_in(git_repo, "rev-parse", "HEAD").strip()
    assert _git_in(git_repo, "rev-list", "-n1", "git-v1.1.0").strip() == head


def test_main_tag_noop_when_all_tagged(git_repo, capsys):
    _write_plugin(git_repo, "git", "1.1.0")
    _git_in(git_repo, "tag", "git-v1.1.0")
    rc = release.main(["release.py", "--tag", "--no-push"])
    assert rc == 0 and "already tagged" in capsys.readouterr().out


def test_main_tag_pushes_to_origin(git_repo, tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    _git_in(git_repo, "remote", "add", "origin", str(origin))
    _git_in(git_repo, "push", "-q", "-u", "origin", "main")
    _write_plugin(git_repo, "git", "1.1.0")
    _commit(git_repo, "chore(release): git@1.1.0")
    rc = release.main(["release.py", "--tag"])  # default: push
    assert rc == 0
    pushed = subprocess.run(
        ["git", "-C", str(origin), "tag", "--list"], capture_output=True, text=True).stdout
    assert "git-v1.1.0" in pushed
