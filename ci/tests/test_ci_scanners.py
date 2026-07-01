"""Tests for the five zero-coverage CI scanner scripts.

Loaded via importlib.util.spec_from_file_location (hyphenated filenames need it).
All tests are hermetic — no network, no git, no gh calls needed for these modules.

Run: python3 -m pytest ci/tests/test_ci_scanners.py -q
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from io import StringIO

import pytest

CI = Path(__file__).resolve().parent.parent
REPO_ROOT = CI.parent


def _load(modname: str, filename: str):
    """Load a CI script (possibly hyphenated) by absolute path."""
    spec = importlib.util.spec_from_file_location(modname, CI / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


# Module-level loads — executed once at import time.
lint_bare = _load("lint_no_bare_python", "lint-no-bare-python.py")
lint_fm = _load("lint_frontmatter", "lint-frontmatter.py")
gen_index = _load("gen_skill_index", "gen-skill-index.py")
check_vendor = _load("check_vendored_sync", "check-vendored-sync.py")
verify_hooks = _load("verify_hook_runtime_controls", "verify_hook_runtime_controls.py")


# ===========================================================================
# lint-no-bare-python.py
# ===========================================================================

class TestLintNoBareP:
    """Tests for lint-no-bare-python: scan_file / should_scan / main."""

    def _write(self, tmp_path: Path, name: str, content: str) -> Path:
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        return p

    # --- scan_file -----------------------------------------------------------

    def test_scan_file_clean_sh(self, tmp_path):
        p = self._write(tmp_path, "run.sh", "#!/bin/bash\npython3 script.py\n")
        hits = lint_bare.scan_file(p)
        assert hits == []

    def test_scan_file_bare_python(self, tmp_path):
        p = self._write(tmp_path, "run.sh", "#!/bin/bash\npython script.py\n")
        hits = lint_bare.scan_file(p)
        assert len(hits) == 1
        assert hits[0][0] == 2  # line number
        assert "python script.py" in hits[0][1]

    def test_scan_file_bare_python2(self, tmp_path):
        p = self._write(tmp_path, "run.sh", "python2 -c 'print 1'\n")
        hits = lint_bare.scan_file(p)
        assert len(hits) == 1

    def test_scan_file_hyphen_name_not_flagged(self, tmp_path):
        # A token like 'lint-no-bare-python' must NOT match (hyphen guard).
        p = self._write(tmp_path, "run.sh", "# called from lint-no-bare-python\npython3 ok.py\n")
        hits = lint_bare.scan_file(p)
        assert hits == []

    def test_scan_file_python3_not_flagged(self, tmp_path):
        p = self._write(tmp_path, "run.sh", "python3 run.py\npython3.11 run.py\n")
        hits = lint_bare.scan_file(p)
        assert hits == []

    def test_scan_file_multiple_hits(self, tmp_path):
        p = self._write(tmp_path, "a.sh", "python a.py\npython b.py\n")
        hits = lint_bare.scan_file(p)
        assert len(hits) == 2

    def test_scan_file_json_bare_python(self, tmp_path):
        content = json.dumps({"command": "python script.py"})
        p = self._write(tmp_path, "hooks.json", content)
        hits = lint_bare.scan_file(p)
        assert len(hits) == 1

    def test_scan_file_json_python3_clean(self, tmp_path):
        content = json.dumps({"command": "python3 script.py"})
        p = self._write(tmp_path, "hooks.json", content)
        hits = lint_bare.scan_file(p)
        assert hits == []

    # --- should_scan -----------------------------------------------------------
    # should_scan calls is_exempt, which calls path.relative_to(REPO_ROOT).
    # For tmp_path files we must monkeypatch REPO_ROOT to tmp_path so the
    # relative_to() call does not raise ValueError.

    def test_should_scan_sh(self, tmp_path, monkeypatch):
        monkeypatch.setattr(lint_bare, "REPO_ROOT", tmp_path)
        p = self._write(tmp_path, "run.sh", "")
        assert lint_bare.should_scan(p) is True

    def test_should_scan_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(lint_bare, "REPO_ROOT", tmp_path)
        p = self._write(tmp_path, "hooks.json", "{}")
        assert lint_bare.should_scan(p) is True

    def test_should_scan_py_excluded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(lint_bare, "REPO_ROOT", tmp_path)
        p = self._write(tmp_path, "helper.py", "")
        # .py suffix not in SCAN_EXTENSIONS → False (suffix check before is_exempt)
        assert lint_bare.should_scan(p) is False

    def test_should_scan_md_excluded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(lint_bare, "REPO_ROOT", tmp_path)
        p = self._write(tmp_path, "README.md", "")
        assert lint_bare.should_scan(p) is False

    def test_should_scan_not_a_file(self, tmp_path):
        assert lint_bare.should_scan(tmp_path / "nonexistent.sh") is False

    def test_should_scan_yaml_excluded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(lint_bare, "REPO_ROOT", tmp_path)
        p = self._write(tmp_path, "ci.yml", "")
        assert lint_bare.should_scan(p) is False

    def test_should_scan_skips_git_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(lint_bare, "REPO_ROOT", tmp_path)
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        p = git_dir / "config.sh"
        p.write_text("python script.py\n", encoding="utf-8")
        assert lint_bare.should_scan(p) is False

    # --- main -----------------------------------------------------------------
    # main() calls iter_files → should_scan → is_exempt → path.relative_to(REPO_ROOT).
    # For tmp_path targets we must monkeypatch REPO_ROOT.

    def test_main_clean_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(lint_bare, "REPO_ROOT", tmp_path)
        (tmp_path / "run.sh").write_text("python3 ok.py\n", encoding="utf-8")
        rc = lint_bare.main(["lint-no-bare-python.py", str(tmp_path)])
        assert rc == 0

    def test_main_reports_bare_python(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(lint_bare, "REPO_ROOT", tmp_path)
        (tmp_path / "run.sh").write_text("python run.py\n", encoding="utf-8")
        rc = lint_bare.main(["lint-no-bare-python.py", str(tmp_path)])
        assert rc == 1
        out = capsys.readouterr().out
        assert "bare-python" in out

    def test_main_no_args_uses_repo_root(self):
        # With no extra args main() scans REPO_ROOT — just verify it returns 0|1 without
        # crashing.  The actual return code depends on whether the repo has any hits.
        rc = lint_bare.main(["lint-no-bare-python.py"])
        assert rc in (0, 1)

    def test_main_direct_file_arg(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(lint_bare, "REPO_ROOT", tmp_path)
        p = tmp_path / "a.sh"
        p.write_text("python2 script.py\n", encoding="utf-8")
        rc = lint_bare.main(["lint-no-bare-python.py", str(p)])
        assert rc == 1
        out = capsys.readouterr().out
        assert "1 bare-python" in out

    def test_main_skip_non_scan_extension(self, tmp_path, monkeypatch):
        monkeypatch.setattr(lint_bare, "REPO_ROOT", tmp_path)
        (tmp_path / "notes.py").write_text("python script.py\n", encoding="utf-8")
        rc = lint_bare.main(["lint-no-bare-python.py", str(tmp_path)])
        assert rc == 0  # .py is excluded

    def test_should_scan_bash_extension(self, tmp_path, monkeypatch):
        monkeypatch.setattr(lint_bare, "REPO_ROOT", tmp_path)
        p = self._write(tmp_path, "run.bash", "")
        assert lint_bare.should_scan(p) is True

    def test_should_scan_zsh_extension(self, tmp_path, monkeypatch):
        monkeypatch.setattr(lint_bare, "REPO_ROOT", tmp_path)
        p = self._write(tmp_path, "run.zsh", "")
        assert lint_bare.should_scan(p) is True

    def test_main_multiple_files_with_hits(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(lint_bare, "REPO_ROOT", tmp_path)
        (tmp_path / "a.sh").write_text("python run.py\n", encoding="utf-8")
        (tmp_path / "b.json").write_text('{"cmd": "python foo.py"}', encoding="utf-8")
        rc = lint_bare.main(["lint-no-bare-python.py", str(tmp_path)])
        assert rc == 1
        out = capsys.readouterr().out
        assert "2 bare-python" in out

    def test_is_exempt_exempt_paths(self, tmp_path, monkeypatch):
        # Cover the EXEMPT_PATHS branch (line 64): add the file's relative path to the set.
        monkeypatch.setattr(lint_bare, "REPO_ROOT", tmp_path)
        p = tmp_path / "run.sh"
        p.write_text("python run.py\n", encoding="utf-8")
        rel = str(p.relative_to(tmp_path))
        monkeypatch.setattr(lint_bare, "EXEMPT_PATHS", {rel})
        assert lint_bare.is_exempt(p) is True
        # should_scan must also return False for exempt file
        assert lint_bare.should_scan(p) is False

    def test_scan_file_unreadable(self, tmp_path, monkeypatch):
        # Cover the except branch in scan_file (lines 97-98) by monkeypatching read_text.
        p = tmp_path / "run.sh"
        p.write_text("python run.py\n", encoding="utf-8")

        original_read_text = Path.read_text

        def failing_read_text(self, *args, **kwargs):
            if self == p:
                raise PermissionError("access denied")
            return original_read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", failing_read_text)
        hits = lint_bare.scan_file(p)
        assert len(hits) == 1
        assert hits[0][0] == 0
        assert "could not read file" in hits[0][1]


# ===========================================================================
# lint-frontmatter.py
# ===========================================================================

class TestLintFrontmatter:
    """Tests for lint-frontmatter: extract_frontmatter / key_value / lint_file / main."""

    # --- extract_frontmatter -------------------------------------------------

    def test_extract_valid(self):
        text = "---\nname: foo\ndescription: bar\n---\nBody"
        block = lint_fm.extract_frontmatter(text)
        assert block is not None
        assert "name: foo" in block

    def test_extract_none_if_no_leading_dashes(self):
        assert lint_fm.extract_frontmatter("# Heading\n") is None

    def test_extract_none_if_unterminated(self):
        assert lint_fm.extract_frontmatter("---\nname: foo\n") is None

    # --- key_value -----------------------------------------------------------

    def test_key_value_simple(self):
        block = "\nname: my-skill\ndescription: does stuff\n"
        assert lint_fm.key_value(block, "name") == "my-skill"
        assert lint_fm.key_value(block, "description") == "does stuff"

    def test_key_value_missing(self):
        assert lint_fm.key_value("\nname: foo\n", "description") is None

    def test_key_value_block_scalar(self):
        block = "\nname: foo\ndescription: >\n  Some long\n  description here\n"
        val = lint_fm.key_value(block, "description")
        assert val is not None and "Some long" in val

    def test_key_value_strips_quotes(self):
        block = "\nname: 'quoted-name'\n"
        assert lint_fm.key_value(block, "name") == "quoted-name"

    # --- lint_file -----------------------------------------------------------

    def _skill(self, tmp_path: Path, content: str) -> Path:
        p = tmp_path / "SKILL.md"
        p.write_text(content, encoding="utf-8")
        return p

    def test_lint_file_valid(self, tmp_path):
        p = self._skill(tmp_path, "---\nname: my-skill\ndescription: does things\n---\nBody\n")
        assert lint_fm.lint_file(p) == []

    def test_lint_file_missing_frontmatter(self, tmp_path):
        p = self._skill(tmp_path, "# No frontmatter\n")
        problems = lint_fm.lint_file(p)
        assert any("missing" in pr.lower() or "unterminated" in pr.lower() for pr in problems)

    def test_lint_file_missing_name(self, tmp_path):
        p = self._skill(tmp_path, "---\ndescription: does things\n---\nBody\n")
        problems = lint_fm.lint_file(p)
        assert any("name" in pr for pr in problems)

    def test_lint_file_missing_description(self, tmp_path):
        p = self._skill(tmp_path, "---\nname: my-skill\n---\nBody\n")
        problems = lint_fm.lint_file(p)
        assert any("description" in pr for pr in problems)

    def test_lint_file_empty_name(self, tmp_path):
        # Use YAML block scalar form `|` with empty content so key_value returns "".
        p = self._skill(tmp_path, "---\nname: |\n  \ndescription: does things\n---\n")
        problems = lint_fm.lint_file(p)
        assert any("empty" in pr and "name" in pr for pr in problems)

    def test_lint_file_description_too_long(self, tmp_path):
        long_desc = "x" * (lint_fm.MAX_DESCRIPTION_CHARS + 1)
        p = self._skill(tmp_path, f"---\nname: foo\ndescription: {long_desc}\n---\n")
        problems = lint_fm.lint_file(p)
        assert any("too long" in pr for pr in problems)

    def test_lint_file_unreadable(self, tmp_path):
        # Pass a directory as a path — reading it raises OSError.
        problems = lint_fm.lint_file(tmp_path)
        assert any("unreadable" in pr for pr in problems)

    # --- main (patched ROOT) -------------------------------------------------

    def test_main_clean(self, tmp_path, monkeypatch, capsys):
        # Build a mini plugin tree
        skill_dir = tmp_path / "plugins" / "myplugin" / "skills" / "myskill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: myskill\ndescription: does things\n---\n", encoding="utf-8"
        )
        monkeypatch.setattr(lint_fm, "ROOT", tmp_path)
        rc = lint_fm.main()
        assert rc == 0
        out = capsys.readouterr().out
        assert "clean" in out

    def test_main_with_invalid_skill(self, tmp_path, monkeypatch, capsys):
        skill_dir = tmp_path / "plugins" / "myplugin" / "skills" / "badskill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# No frontmatter\n", encoding="utf-8")
        monkeypatch.setattr(lint_fm, "ROOT", tmp_path)
        rc = lint_fm.main()
        assert rc == 1
        out = capsys.readouterr().out
        assert "lint-frontmatter:" in out

    def test_main_no_targets(self, tmp_path, monkeypatch, capsys):
        # Empty root → no targets found
        monkeypatch.setattr(lint_fm, "ROOT", tmp_path)
        rc = lint_fm.main()
        assert rc == 1
        err = capsys.readouterr().err
        assert "no skill/agent" in err

    def test_main_agent_file(self, tmp_path, monkeypatch, capsys):
        agents_dir = tmp_path / "plugins" / "myplugin" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "my-agent.md").write_text(
            "---\nname: my-agent\ndescription: An agent\n---\nBody\n", encoding="utf-8"
        )
        monkeypatch.setattr(lint_fm, "ROOT", tmp_path)
        rc = lint_fm.main()
        assert rc == 0

    def test_main_multiple_failures(self, tmp_path, monkeypatch, capsys):
        for i in range(3):
            skill_dir = tmp_path / "plugins" / "p" / "skills" / f"s{i}"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("# no fm\n", encoding="utf-8")
        monkeypatch.setattr(lint_fm, "ROOT", tmp_path)
        rc = lint_fm.main()
        assert rc == 1
        out = capsys.readouterr().out
        assert "3 problem(s)" in out

    # --- command files (per-type schema) -------------------------------------

    def _command(self, tmp_path: Path, stem: str, content: str) -> Path:
        d = tmp_path / "commands"
        d.mkdir(exist_ok=True)
        p = d / f"{stem}.md"
        p.write_text(content, encoding="utf-8")
        return p

    def test_lint_command_description_only_valid(self, tmp_path):
        # Commands derive their name from the filename; `name` is optional.
        p = self._command(tmp_path, "checkpoint", "---\ndescription: does things\n---\nBody\n")
        assert lint_fm.lint_file(p) == []

    def test_lint_command_missing_description(self, tmp_path):
        p = self._command(tmp_path, "foo", "---\nargument-hint: <x>\n---\n")
        problems = lint_fm.lint_file(p)
        assert any("description" in pr for pr in problems)

    def test_lint_command_name_not_required(self, tmp_path):
        # Absent `name` on a command must NOT be reported (unlike skills/agents).
        p = self._command(tmp_path, "foo", "---\ndescription: d\n---\n")
        problems = lint_fm.lint_file(p)
        assert not any("name" in pr for pr in problems)

    def test_lint_command_name_parity_ok(self, tmp_path):
        p = self._command(tmp_path, "evolve", "---\nname: evolve\ndescription: d\n---\n")
        assert lint_fm.lint_file(p) == []

    def test_lint_command_name_parity_mismatch(self, tmp_path):
        # A declared name that disagrees with the filename stem is the real defect class.
        p = self._command(tmp_path, "evolve", "---\nname: wrong\ndescription: d\n---\n")
        problems = lint_fm.lint_file(p)
        assert any("stem" in pr or "match" in pr for pr in problems)

    def test_main_picks_up_command_file(self, tmp_path, monkeypatch, capsys):
        cmd_dir = tmp_path / "plugins" / "myplugin" / "commands"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "do-thing.md").write_text(
            "---\ndescription: does a thing\n---\n", encoding="utf-8"
        )
        monkeypatch.setattr(lint_fm, "ROOT", tmp_path)
        rc = lint_fm.main()
        assert rc == 0


# ===========================================================================
# gen-skill-index.py
# ===========================================================================

class TestGenSkillIndex:
    """Tests for gen-skill-index: _describe / _rows / generate / main."""

    def _make_skill(self, tmp_path: Path, plugin: str, skill: str, name: str, desc: str) -> Path:
        d = tmp_path / "plugins" / plugin / "skills" / skill
        d.mkdir(parents=True)
        p = d / "SKILL.md"
        p.write_text(f"---\nname: {name}\ndescription: {desc}\n---\n", encoding="utf-8")
        return p

    def _make_agent(self, tmp_path: Path, plugin: str, agent_file: str, name: str, desc: str) -> Path:
        d = tmp_path / "plugins" / plugin / "agents"
        d.mkdir(parents=True)
        p = d / agent_file
        p.write_text(f"---\nname: {name}\ndescription: {desc}\n---\n", encoding="utf-8")
        return p

    def _point(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr(gen_index, "ROOT", tmp_path)
        monkeypatch.setattr(gen_index, "INDEX_PATH", tmp_path / "docs" / "skill-index.md")

    # --- _describe -----------------------------------------------------------

    def test_describe_extracts_name_and_desc(self, tmp_path):
        p = self._make_skill(tmp_path, "myplugin", "myskill", "my-skill", "Does things")
        name, desc = gen_index._describe(p)
        assert name == "my-skill"
        assert desc == "Does things"

    def test_describe_truncates_long_desc(self, tmp_path):
        long = "word " * 50  # definitely > MAX_DESC
        p = self._make_skill(tmp_path, "p", "s", "foo", long.strip())
        name, desc = gen_index._describe(p)
        assert len(desc) <= gen_index.MAX_DESC
        assert desc.endswith("…")

    def test_describe_pipe_escaped(self, tmp_path):
        p = self._make_skill(tmp_path, "p", "s", "foo", "a|b")
        _, desc = gen_index._describe(p)
        assert "\\|" in desc

    def test_describe_fallback_name(self, tmp_path):
        # No 'name' key in frontmatter → falls back to parent dir name.
        d = tmp_path / "plugins" / "p" / "skills" / "fallback-skill"
        d.mkdir(parents=True)
        p = d / "SKILL.md"
        p.write_text("---\ndescription: desc\n---\n", encoding="utf-8")
        name, _ = gen_index._describe(p)
        assert name == "fallback-skill"

    def _make_command(self, tmp_path: Path, plugin: str, stem: str, name: str | None, desc: str) -> Path:
        d = tmp_path / "plugins" / plugin / "commands"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{stem}.md"
        fm = (
            f"---\nname: {name}\ndescription: {desc}\n---\n"
            if name
            else f"---\ndescription: {desc}\n---\n"
        )
        p.write_text(fm, encoding="utf-8")
        return p

    def test_describe_command_fallback_to_stem(self, tmp_path):
        # A nameless command falls back to the filename stem, not the parent dir ("commands").
        p = self._make_command(tmp_path, "p", "checkpoint", None, "desc")
        name, _ = gen_index._describe(p)
        assert name == "checkpoint"

    # --- generate / main --write / --check -----------------------------------

    def test_generate_contains_header(self, tmp_path, monkeypatch):
        self._point(monkeypatch, tmp_path)
        self._make_skill(tmp_path, "myplugin", "myskill", "my-skill", "Does things")
        content = gen_index.generate()
        assert "# Skill, Agent & Command Index" in content
        assert "## Skills" in content
        assert "## Agents" in content

    def test_generate_includes_skill_row(self, tmp_path, monkeypatch):
        self._point(monkeypatch, tmp_path)
        self._make_skill(tmp_path, "myplugin", "myskill", "my-skill", "Does things")
        content = gen_index.generate()
        assert "myplugin" in content
        assert "`my-skill`" in content

    def test_generate_includes_agent_row(self, tmp_path, monkeypatch):
        self._point(monkeypatch, tmp_path)
        self._make_agent(tmp_path, "myplugin", "my-agent.md", "my-agent", "An agent")
        content = gen_index.generate()
        assert "`my-agent`" in content

    def test_generate_includes_command_section(self, tmp_path, monkeypatch):
        self._point(monkeypatch, tmp_path)
        self._make_command(tmp_path, "myplugin", "do-thing", "do-thing", "Does a thing")
        content = gen_index.generate()
        assert "## Commands" in content
        assert "`do-thing`" in content

    def test_main_write_creates_file(self, tmp_path, monkeypatch, capsys):
        self._point(monkeypatch, tmp_path)
        self._make_skill(tmp_path, "p", "s", "s-name", "s-desc")
        rc = gen_index.main(["--write"])
        assert rc == 0
        index_path = tmp_path / "docs" / "skill-index.md"
        assert index_path.is_file()
        assert "# Skill, Agent & Command Index" in index_path.read_text(encoding="utf-8")
        out = capsys.readouterr().out
        assert "gen-skill-index: wrote" in out

    def test_main_check_up_to_date(self, tmp_path, monkeypatch, capsys):
        self._point(monkeypatch, tmp_path)
        self._make_skill(tmp_path, "p", "s", "s-name", "s-desc")
        # First write
        gen_index.main(["--write"])
        # Then check — should be clean
        rc = gen_index.main(["--check"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "up to date" in out

    def test_main_check_detects_drift(self, tmp_path, monkeypatch, capsys):
        self._point(monkeypatch, tmp_path)
        self._make_skill(tmp_path, "p", "s", "s-name", "s-desc")
        # Write stale content
        index_path = tmp_path / "docs" / "skill-index.md"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text("stale content", encoding="utf-8")
        rc = gen_index.main(["--check"])
        assert rc == 1
        out = capsys.readouterr().out
        assert "out of date" in out

    def test_main_check_missing_file(self, tmp_path, monkeypatch, capsys):
        self._point(monkeypatch, tmp_path)
        self._make_skill(tmp_path, "p", "s", "s-name", "s-desc")
        # No index file at all
        rc = gen_index.main(["--check"])
        assert rc == 1

    def test_main_default_is_check(self, tmp_path, monkeypatch):
        self._point(monkeypatch, tmp_path)
        self._make_skill(tmp_path, "p", "s", "s-name", "s-desc")
        # No args → --check behaviour → missing file → exit 1
        rc = gen_index.main([])
        assert rc == 1


# ===========================================================================
# check-vendored-sync.py
# ===========================================================================

class TestCheckVendoredSync:
    """Tests for check-vendored-sync: main on a synthetic plugin tree."""

    _CANONICAL = "discipline"
    _CONSUMERS = ("learning", "stewardship")
    _FILES = ("scripts/hook_flags.py", "scripts/run_with_flags.py")
    _CONTENT = "# canonical\ndef example(): pass\n"
    _ALT_CONTENT = "# diverged\ndef example(): return 1\n"

    def _build_tree(self, tmp_path: Path, consumer_content: dict | None = None) -> None:
        """
        consumer_content: maps 'learning/scripts/hook_flags.py' -> text.
        Omitted keys → match canonical.
        Missing from consumer_content explicitly → consumer file absent.
        Pass None to match all.
        """
        for rel in self._FILES:
            canon = tmp_path / "plugins" / self._CANONICAL / rel
            canon.parent.mkdir(parents=True, exist_ok=True)
            canon.write_text(self._CONTENT, encoding="utf-8")
        for consumer in self._CONSUMERS:
            for rel in self._FILES:
                key = f"{consumer}/{rel}"
                text = None
                if consumer_content is None:
                    text = self._CONTENT  # match canonical
                elif key in consumer_content:
                    text = consumer_content[key]
                if text is not None:
                    target = tmp_path / "plugins" / consumer / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(text, encoding="utf-8")

    def _point(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr(check_vendor, "ROOT", tmp_path)
        monkeypatch.setattr(check_vendor, "CANONICAL_PLUGIN", self._CANONICAL)
        monkeypatch.setattr(check_vendor, "CONSUMER_PLUGINS", self._CONSUMERS)
        monkeypatch.setattr(check_vendor, "VENDORED_FILES", self._FILES)

    # --- clean cases -----------------------------------------------------------

    def test_clean_when_all_match(self, tmp_path, monkeypatch, capsys):
        self._build_tree(tmp_path)  # all match
        self._point(monkeypatch, tmp_path)
        rc = check_vendor.main([])
        assert rc == 0
        out = capsys.readouterr().out
        assert "clean" in out

    # --- drift cases ----------------------------------------------------------

    def test_detects_content_drift(self, tmp_path, monkeypatch, capsys):
        self._build_tree(tmp_path, {"learning/scripts/hook_flags.py": self._ALT_CONTENT,
                                    "learning/scripts/run_with_flags.py": self._CONTENT,
                                    "stewardship/scripts/hook_flags.py": self._CONTENT,
                                    "stewardship/scripts/run_with_flags.py": self._CONTENT})
        self._point(monkeypatch, tmp_path)
        rc = check_vendor.main([])
        assert rc == 1
        out = capsys.readouterr().out
        assert "DRIFT" in out
        assert "learning/scripts/hook_flags.py" in out

    def test_detects_missing_consumer_file(self, tmp_path, monkeypatch, capsys):
        # Consumer file absent → counted as drift
        consumer_content = {
            "learning/scripts/run_with_flags.py": self._CONTENT,
            "stewardship/scripts/hook_flags.py": self._CONTENT,
            "stewardship/scripts/run_with_flags.py": self._CONTENT,
        }
        # learning/scripts/hook_flags.py intentionally absent from dict
        self._build_tree(tmp_path, consumer_content)
        self._point(monkeypatch, tmp_path)
        rc = check_vendor.main([])
        assert rc == 1

    def test_canonical_missing_returns_1(self, tmp_path, monkeypatch, capsys):
        # Don't create canonical at all
        self._point(monkeypatch, tmp_path)
        rc = check_vendor.main([])
        assert rc == 1
        err = capsys.readouterr().err
        assert "canonical missing" in err

    # --- --fix mode -----------------------------------------------------------

    def test_fix_copies_canonical_over_diverged(self, tmp_path, monkeypatch, capsys):
        self._build_tree(tmp_path, {"learning/scripts/hook_flags.py": self._ALT_CONTENT,
                                    "learning/scripts/run_with_flags.py": self._CONTENT,
                                    "stewardship/scripts/hook_flags.py": self._CONTENT,
                                    "stewardship/scripts/run_with_flags.py": self._CONTENT})
        self._point(monkeypatch, tmp_path)
        rc = check_vendor.main(["--fix"])
        assert rc == 0
        fixed = (tmp_path / "plugins" / "learning" / "scripts" / "hook_flags.py")
        assert fixed.read_text(encoding="utf-8") == self._CONTENT
        out = capsys.readouterr().out
        assert "fixed" in out

    def test_fix_creates_missing_consumer_file(self, tmp_path, monkeypatch, capsys):
        consumer_content = {
            "learning/scripts/run_with_flags.py": self._CONTENT,
            "stewardship/scripts/hook_flags.py": self._CONTENT,
            "stewardship/scripts/run_with_flags.py": self._CONTENT,
        }
        self._build_tree(tmp_path, consumer_content)
        self._point(monkeypatch, tmp_path)
        rc = check_vendor.main(["--fix"])
        assert rc == 0
        created = tmp_path / "plugins" / "learning" / "scripts" / "hook_flags.py"
        assert created.is_file()
        assert created.read_text(encoding="utf-8") == self._CONTENT

    def test_fix_clean_tree_is_noop(self, tmp_path, monkeypatch, capsys):
        self._build_tree(tmp_path)  # all match
        self._point(monkeypatch, tmp_path)
        rc = check_vendor.main(["--fix"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "clean" in out


# ===========================================================================
# verify_hook_runtime_controls.py
# ===========================================================================

class TestVerifyHookRuntimeControls:
    """Tests for verify_hook_runtime_controls: main on a synthetic plugins/ tree."""

    _WRAPPER = "scripts/run_with_flags.py"

    def _make_plugin(
        self,
        tmp_path: Path,
        name: str,
        hooks_data: dict,
        with_wrapper: bool = True,
    ) -> None:
        plugin_dir = tmp_path / "plugins" / name
        hooks_dir = plugin_dir / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "hooks.json").write_text(json.dumps(hooks_data), encoding="utf-8")
        if with_wrapper:
            scripts_dir = plugin_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            (scripts_dir / "run_with_flags.py").touch()

    # --- clean / no-op -------------------------------------------------------

    def test_clean_all_hooks_use_wrapper(self, tmp_path, monkeypatch, capsys):
        data = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Edit",
                        "hooks": [
                            {"type": "command",
                             "command": f"python3 ${{CLAUDE_PLUGIN_ROOT}}/{self._WRAPPER} todo.py"}
                        ],
                    }
                ]
            }
        }
        self._make_plugin(tmp_path, "discipline", data)
        monkeypatch.setattr(verify_hooks, "GATED_PLUGINS", ("discipline",))
        rc = verify_hooks.main(root=tmp_path)
        assert rc == 0
        out = capsys.readouterr().out
        assert "clean" in out

    def test_empty_hooks_section_is_clean(self, tmp_path, monkeypatch, capsys):
        data = {"hooks": {}}
        self._make_plugin(tmp_path, "discipline", data)
        monkeypatch.setattr(verify_hooks, "GATED_PLUGINS", ("discipline",))
        rc = verify_hooks.main(root=tmp_path)
        assert rc == 0

    def test_no_hooks_key_is_clean(self, tmp_path, monkeypatch, capsys):
        data = {}
        self._make_plugin(tmp_path, "discipline", data)
        monkeypatch.setattr(verify_hooks, "GATED_PLUGINS", ("discipline",))
        rc = verify_hooks.main(root=tmp_path)
        assert rc == 0

    # --- violations ----------------------------------------------------------

    def test_violation_detected(self, tmp_path, monkeypatch, capsys):
        data = {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {"type": "command", "command": "python3 scripts/naked.py"}
                        ],
                    }
                ]
            }
        }
        self._make_plugin(tmp_path, "discipline", data)
        monkeypatch.setattr(verify_hooks, "GATED_PLUGINS", ("discipline",))
        rc = verify_hooks.main(root=tmp_path)
        assert rc == 1
        err = capsys.readouterr().err
        assert "bypass" in err.lower() or "run_with_flags" in err

    def test_multiple_violations_all_reported(self, tmp_path, monkeypatch, capsys):
        data = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Edit",
                        "hooks": [
                            {"type": "command", "command": "python3 scripts/a.py"},
                            {"type": "command", "command": "python3 scripts/b.py"},
                        ],
                    }
                ]
            }
        }
        self._make_plugin(tmp_path, "discipline", data)
        monkeypatch.setattr(verify_hooks, "GATED_PLUGINS", ("discipline",))
        rc = verify_hooks.main(root=tmp_path)
        assert rc == 1
        err = capsys.readouterr().err
        assert "scripts/a.py" in err
        assert "scripts/b.py" in err

    def test_mixed_clean_and_violation(self, tmp_path, monkeypatch, capsys):
        data = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Edit",
                        "hooks": [
                            {"type": "command",
                             "command": f"python3 ${{PLUGIN}}/{self._WRAPPER} ok.py"},
                            {"type": "command", "command": "python3 scripts/bad.py"},
                        ],
                    }
                ]
            }
        }
        self._make_plugin(tmp_path, "discipline", data)
        monkeypatch.setattr(verify_hooks, "GATED_PLUGINS", ("discipline",))
        rc = verify_hooks.main(root=tmp_path)
        assert rc == 1

    # --- error handling -------------------------------------------------------

    def test_missing_hooks_json(self, tmp_path, monkeypatch, capsys):
        plugin_dir = tmp_path / "plugins" / "discipline"
        scripts_dir = plugin_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "run_with_flags.py").touch()
        monkeypatch.setattr(verify_hooks, "GATED_PLUGINS", ("discipline",))
        rc = verify_hooks.main(root=tmp_path)
        assert rc == 1
        err = capsys.readouterr().err
        assert "missing" in err

    def test_invalid_json(self, tmp_path, monkeypatch, capsys):
        plugin_dir = tmp_path / "plugins" / "discipline"
        hooks_dir = plugin_dir / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "hooks.json").write_text("{broken json", encoding="utf-8")
        scripts_dir = plugin_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "run_with_flags.py").touch()
        monkeypatch.setattr(verify_hooks, "GATED_PLUGINS", ("discipline",))
        rc = verify_hooks.main(root=tmp_path)
        assert rc == 1
        err = capsys.readouterr().err
        assert "invalid JSON" in err

    # --- consistency assertion -------------------------------------------------

    def test_wrapper_present_but_plugin_not_gated_is_violation(
        self, tmp_path, monkeypatch, capsys
    ):
        data = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Edit",
                        "hooks": [
                            {"type": "command",
                             "command": f"python3 ${{CLAUDE_PLUGIN_ROOT}}/{self._WRAPPER} todo.py"}
                        ],
                    }
                ]
            }
        }
        self._make_plugin(tmp_path, "learning", data, with_wrapper=True)
        monkeypatch.setattr(verify_hooks, "GATED_PLUGINS", ())
        rc = verify_hooks.main(root=tmp_path)
        assert rc == 1
        err = capsys.readouterr().err
        assert "learning" in err

    def test_gated_plugin_without_wrapper_is_violation(self, tmp_path, monkeypatch, capsys):
        data = {"hooks": {}}
        self._make_plugin(tmp_path, "discipline", data, with_wrapper=False)
        monkeypatch.setattr(verify_hooks, "GATED_PLUGINS", ("discipline",))
        rc = verify_hooks.main(root=tmp_path)
        assert rc == 1
        err = capsys.readouterr().err
        assert "discipline" in err

    def test_multi_plugin_violation_names_offending_plugin(
        self, tmp_path, monkeypatch, capsys
    ):
        clean_data = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Edit",
                        "hooks": [
                            {"type": "command",
                             "command": f"python3 ${{CLAUDE_PLUGIN_ROOT}}/{self._WRAPPER} todo.py"}
                        ],
                    }
                ]
            }
        }
        bypassing_data = {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {"type": "command", "command": "python3 scripts/naked.py"}
                        ],
                    }
                ]
            }
        }
        self._make_plugin(tmp_path, "discipline", clean_data)
        self._make_plugin(tmp_path, "learning", bypassing_data)
        monkeypatch.setattr(verify_hooks, "GATED_PLUGINS", ("discipline", "learning"))
        rc = verify_hooks.main(root=tmp_path)
        assert rc == 1
        err = capsys.readouterr().err
        assert "learning" in err
        assert "scripts/naked.py" in err
        assert "discipline:" not in err
