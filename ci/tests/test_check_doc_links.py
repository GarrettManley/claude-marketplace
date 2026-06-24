"""Tests for the ci/check-doc-links.py anti-rot gate.

Loaded by path (hyphenated-module style, like test_ci_gates.py) and exercised
against synthetic git trees via a monkeypatched ROOT. A dead-link gate that does
not itself fail on a dead link is worse than none — these prove it flags broken
references while leaving external URLs, anchors, ${CLAUDE_PLUGIN_ROOT} runtime
refs, and valid sibling `references/…` paths alone. The real repo must be clean.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

CI = Path(__file__).resolve().parent.parent
ROOT = CI.parent


def _load(modname: str, filename: str):
    spec = importlib.util.spec_from_file_location(modname, CI / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


cdl = _load("check_doc_links", "check-doc-links.py")


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init", str(root)], capture_output=True, check=True)


def _add(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", rel], capture_output=True, check=True)
    return p


def _patch(monkeypatch, root: Path) -> None:
    monkeypatch.setattr(cdl, "ROOT", root)


# --- real repo happy path -----------------------------------------------------


def test_real_repo_is_clean():
    assert cdl.main() == 0


# --- synthetic trees ----------------------------------------------------------


def test_valid_markdown_link_passes(tmp_path, monkeypatch):
    _git_init(tmp_path)
    _add(tmp_path, "docs/target.md", "# target\n")
    _add(tmp_path, "docs/index.md", "See [the target](target.md).\n")
    _patch(monkeypatch, tmp_path)
    assert cdl.main() == 0


def test_broken_markdown_link_is_flagged(tmp_path, monkeypatch):
    _git_init(tmp_path)
    _add(tmp_path, "docs/index.md", "See [missing](does-not-exist.md).\n")
    _patch(monkeypatch, tmp_path)
    assert cdl.main() == 1
    problems = cdl.broken_links()
    assert any("does-not-exist.md" in p for p in problems)
    assert problems[0].startswith("docs/index.md:1:")


def test_external_url_is_ignored(tmp_path, monkeypatch):
    _git_init(tmp_path)
    _add(tmp_path, "docs/index.md", "Visit [site](https://example.com/missing.md).\n")
    _patch(monkeypatch, tmp_path)
    assert cdl.main() == 0


def test_anchor_is_ignored(tmp_path, monkeypatch):
    _git_init(tmp_path)
    _add(tmp_path, "docs/index.md", "Jump to [section](#some-heading).\n")
    _patch(monkeypatch, tmp_path)
    assert cdl.main() == 0


def test_plugin_root_runtime_ref_is_ignored(tmp_path, monkeypatch):
    _git_init(tmp_path)
    _add(tmp_path, "docs/index.md", "Run [hook](${CLAUDE_PLUGIN_ROOT}/hooks/x.py).\n")
    _patch(monkeypatch, tmp_path)
    assert cdl.main() == 0


def test_valid_references_path_passes(tmp_path, monkeypatch):
    _git_init(tmp_path)
    _add(tmp_path, "plugins/p/skills/s/references/GUIDE.md", "# guide\n")
    _add(
        tmp_path,
        "plugins/p/skills/s/SKILL.md",
        "See `references/GUIDE.md` for the full treatment.\n",
    )
    _patch(monkeypatch, tmp_path)
    assert cdl.main() == 0


def test_broken_references_path_is_flagged(tmp_path, monkeypatch):
    _git_init(tmp_path)
    _add(tmp_path, "plugins/p/skills/s/SKILL.md", "See `references/GONE.md`.\n")
    _patch(monkeypatch, tmp_path)
    assert cdl.main() == 1
    assert any("references/GONE.md" in p for p in cdl.broken_links())


def test_references_resolves_via_plugin_root(tmp_path, monkeypatch):
    """A README at the plugin root names a skill's references/ tree by its
    plugin-root-relative path — must resolve from the plugin root, not the doc dir."""
    _git_init(tmp_path)
    _add(tmp_path, "plugins/p/skills/s/references/A.md", "# a\n")
    _add(
        tmp_path,
        "plugins/p/README.md",
        "Copy `skills/s/references/A.md` into place.\n",
    )
    _patch(monkeypatch, tmp_path)
    # backticked bare path here is `skills/...` (not references/-prefixed) so it is
    # NOT an inline-path candidate; assert no false positive from prose either way.
    assert cdl.main() == 0


def test_root_relative_prose_path_not_flagged(tmp_path, monkeypatch):
    """A backticked `ci/release.py` in a deep doc is repo-root prose, not a
    doc-relative link — must NOT be flagged even though it won't resolve from the
    doc's own directory."""
    _git_init(tmp_path)
    _add(tmp_path, "docs/deep/notes.md", "The release script is `ci/release.py`.\n")
    _patch(monkeypatch, tmp_path)
    assert cdl.main() == 0


def test_bare_word_link_not_flagged(tmp_path, monkeypatch):
    _git_init(tmp_path)
    # Target has no slash and no known extension -> not clearly a repo path.
    _add(tmp_path, "docs/index.md", "Read [more](Glossary).\n")
    _patch(monkeypatch, tmp_path)
    assert cdl.main() == 0


def test_link_with_anchor_suffix_resolves(tmp_path, monkeypatch):
    _git_init(tmp_path)
    _add(tmp_path, "docs/target.md", "# t\n")
    _add(tmp_path, "docs/index.md", "See [t](target.md#heading).\n")
    _patch(monkeypatch, tmp_path)
    assert cdl.main() == 0


def test_directory_target_resolves(tmp_path, monkeypatch):
    _git_init(tmp_path)
    _add(tmp_path, "docs/adr/0001.md", "# adr\n")
    _add(tmp_path, "docs/index.md", "See [the adrs](adr/).\n")
    _patch(monkeypatch, tmp_path)
    assert cdl.main() == 0


def test_is_external_classifies_schemes():
    assert cdl._is_external("https://x")
    assert cdl._is_external("mailto:a@b")
    assert cdl._is_external("//cdn/x.js")
    assert cdl._is_external("#frag")
    assert cdl._is_external("/abs/path.md")
    assert cdl._is_external("C:/win/path.md")
    assert cdl._is_external("${CLAUDE_PLUGIN_ROOT}/x.md")
    assert cdl._is_external("tel:123")
    assert not cdl._is_external("relative/path.md")
    assert not cdl._is_external("../sibling.md")


def test_looks_repo_relative_heuristic():
    assert cdl._looks_repo_relative("a/b.md")
    assert cdl._looks_repo_relative("README.md")
    assert cdl._looks_repo_relative("references/X.md")
    assert not cdl._looks_repo_relative("Glossary")


def test_strip_suffix_drops_anchor_and_query():
    assert cdl._strip_suffix("a/b.md#x") == "a/b.md"
    assert cdl._strip_suffix("a/b.md?v=1") == "a/b.md"
    assert cdl._strip_suffix("#only-anchor") == ""


def test_plugin_root_for_non_plugin_file_is_none():
    assert cdl._plugin_root_for(ROOT / "README.md") is None
