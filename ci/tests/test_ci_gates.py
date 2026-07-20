"""Tests for the CI gate scripts ci/validate-plugins.py and ci/check-notice.py.

Both are loaded by path (standalone / hyphenated-module style, like test_release.py)
and exercised against synthetic trees via monkeypatched module globals, plus the real
repo for the happy path. A gate that does not itself fail on bad input is worse than no
gate — these tests prove each one actually catches what it claims.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

CI = Path(__file__).resolve().parent.parent
ROOT = CI.parent


def _load(modname: str, filename: str):
    spec = importlib.util.spec_from_file_location(modname, CI / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


vp = _load("validate_plugins", "validate-plugins.py")
cn = _load("check_notice", "check-notice.py")


# --- validate-plugins ---------------------------------------------------------


def _write_plugin(root: Path, dirname: str, manifest: dict) -> None:
    d = root / "plugins" / dirname / ".claude-plugin"
    d.mkdir(parents=True)
    (d / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")


def _write_marketplace(root: Path, entries: list[dict]) -> None:
    d = root / ".claude-plugin"
    d.mkdir(parents=True, exist_ok=True)
    (d / "marketplace.json").write_text(json.dumps({"plugins": entries}), encoding="utf-8")


def _patch_vp(monkeypatch, root: Path) -> None:
    monkeypatch.setattr(vp, "ROOT", root)
    monkeypatch.setattr(vp, "MARKETPLACE", root / ".claude-plugin" / "marketplace.json")
    monkeypatch.setattr(vp, "PLUGINS_DIR", root / "plugins")


def test_validate_plugins_real_repo_is_clean():
    assert vp.main() == 0


def test_validate_plugins_clean_synthetic(tmp_path, monkeypatch):
    _write_plugin(tmp_path, "alpha", {"name": "alpha", "version": "1.0.0", "keywords": ["a"]})
    _write_marketplace(tmp_path, [{"name": "alpha", "source": "./plugins/alpha"}])
    _patch_vp(monkeypatch, tmp_path)
    assert vp.main() == 0


@pytest.mark.parametrize(
    "manifest,entry",
    [
        ({"name": "a", "version": "1.0.0", "agents": ["x"]}, {"name": "a", "source": "./plugins/a"}),
        ({"name": "a", "version": "1.0.0", "hooks": {}}, {"name": "a", "source": "./plugins/a"}),
        ({"name": "a"}, {"name": "a", "source": "./plugins/a"}),
        ({"version": "1.0.0"}, {"name": "a", "source": "./plugins/a"}),
        ({"name": "a", "version": "1.0.0", "commands": "x"}, {"name": "a", "source": "./plugins/a"}),
        ({"name": "b", "version": "1.0.0"}, {"name": "a", "source": "./plugins/a"}),
    ],
    ids=["agents-field", "hooks-field", "no-version", "no-name", "non-array", "name-mismatch"],
)
def test_validate_plugins_catches_violations(tmp_path, monkeypatch, manifest, entry):
    _write_plugin(tmp_path, "a", manifest)
    _write_marketplace(tmp_path, [entry])
    _patch_vp(monkeypatch, tmp_path)
    assert vp.main() != 0


def test_validate_plugins_bad_source_prefix(tmp_path, monkeypatch):
    (tmp_path / "plugins").mkdir()
    _write_marketplace(tmp_path, [{"name": "a", "source": "plugins/a"}])  # missing ./
    _patch_vp(monkeypatch, tmp_path)
    assert vp.main() != 0


def test_validate_plugins_missing_manifest(tmp_path, monkeypatch):
    (tmp_path / "plugins" / "a").mkdir(parents=True)  # dir but no .claude-plugin/plugin.json
    _write_marketplace(tmp_path, [{"name": "a", "source": "./plugins/a"}])
    _patch_vp(monkeypatch, tmp_path)
    assert vp.main() != 0


def test_validate_plugins_orphan_dir(tmp_path, monkeypatch):
    _write_plugin(tmp_path, "a", {"name": "a", "version": "1.0.0"})
    _write_plugin(tmp_path, "orphan", {"name": "orphan", "version": "1.0.0"})
    _write_marketplace(tmp_path, [{"name": "a", "source": "./plugins/a"}])
    _patch_vp(monkeypatch, tmp_path)
    assert vp.main() != 0


def test_validate_plugin_manifest_bad_json(tmp_path, monkeypatch):
    monkeypatch.setattr(vp, "ROOT", tmp_path)
    p = tmp_path / "plugin.json"
    p.write_text("{ not json", encoding="utf-8")
    errors: list[str] = []
    assert vp.validate_plugin_manifest(p, errors) is None
    assert errors


# --- check-notice -------------------------------------------------------------

GOOD_NOTICE = "Some product\n\nMIT License\nCopyright (c) 2026 Affaan Mustafa\n"


def _git_repo_with_trigger(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True, stdin=subprocess.DEVNULL)
    f = tmp_path / "ported.py"
    f.write_text(f"# {cn.TRIGGER}/everything-claude-code @ 4774946d\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "ported.py"], capture_output=True, check=True, stdin=subprocess.DEVNULL)
    return tmp_path


def _patch_cn(monkeypatch, root: Path) -> None:
    monkeypatch.setattr(cn, "ROOT", root)
    monkeypatch.setattr(cn, "NOTICE", root / "NOTICE")


def test_check_notice_real_repo_is_clean():
    assert cn.main() == 0


def test_check_notice_fails_when_missing(tmp_path, monkeypatch):
    _git_repo_with_trigger(tmp_path)
    _patch_cn(monkeypatch, tmp_path)
    assert cn.main() == 1  # trigger present, no NOTICE


def test_check_notice_fails_on_incomplete_notice(tmp_path, monkeypatch):
    _git_repo_with_trigger(tmp_path)
    (tmp_path / "NOTICE").write_text("just a stub\n", encoding="utf-8")
    _patch_cn(monkeypatch, tmp_path)
    assert cn.main() == 1  # NOTICE present but missing the required grant text


def test_check_notice_passes_with_good_notice(tmp_path, monkeypatch):
    _git_repo_with_trigger(tmp_path)
    (tmp_path / "NOTICE").write_text(GOOD_NOTICE, encoding="utf-8")
    _patch_cn(monkeypatch, tmp_path)
    assert cn.main() == 0


def test_check_notice_no_trigger_is_clean(tmp_path, monkeypatch):
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True, stdin=subprocess.DEVNULL)
    f = tmp_path / "plain.py"
    f.write_text("# nothing to attribute here\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "plain.py"], capture_output=True, check=True, stdin=subprocess.DEVNULL)
    _patch_cn(monkeypatch, tmp_path)
    assert cn.main() == 0  # no attribution → NOTICE not required


def test_check_notice_raises_on_git_error(tmp_path, monkeypatch):
    # tmp_path is not a git repo. The dev host home dir is itself git-tracked and
    # %TEMP% sits inside it, so without a ceiling `git grep` would ascend into that
    # ambient repo and exit 0/1. GIT_CEILING_DIRECTORIES=tmp_path.parent stops the
    # upward walk so the "not a git repository" error (exit 128) fires
    # deterministically - the same guard plugins/git/tests/test_init.py uses. The
    # gate must fail loud on that error, not treat it as "no attribution -> pass".
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    _patch_cn(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match="git grep failed"):
        cn.triggering_files()
