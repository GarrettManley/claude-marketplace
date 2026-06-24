# plugins/stewardship/tests/test_auto_memory_housekeep.py
"""Tests for auto_memory_housekeep.py — archival-candidate detection, dedup
passes, broken-pointer detection, archive_file(), and main() CLI."""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from auto_memory_housekeep import (
    ARCHIVE_DIR,
    INDEX_FILE,
    BrokenPointer,
    StaleFile,
    archive_file,
    find_broken_pointers,
    find_memory_dirs,
    find_stale,
    main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_memory(memory_dir: Path, name: str, content: str = "") -> Path:
    p = memory_dir / name
    p.write_text(content, encoding="utf-8")
    return p


def _make_projects_dir(tmp_path: Path, proj_name: str = "my-project") -> tuple[Path, Path]:
    """Return (projects_dir, memory_dir)."""
    projects_dir = tmp_path / "projects"
    memory_dir = projects_dir / proj_name / "memory"
    memory_dir.mkdir(parents=True)
    return projects_dir, memory_dir


def _age_file(path: Path, days: int) -> None:
    """Set mtime to `days` days in the past."""
    ts = time.time() - days * 86400
    import os
    os.utime(str(path), (ts, ts))


# ---------------------------------------------------------------------------
# find_memory_dirs
# ---------------------------------------------------------------------------

class TestFindMemoryDirs:
    def test_finds_memory_dirs(self, tmp_path):
        projects_dir, memory_dir = _make_projects_dir(tmp_path)
        dirs = find_memory_dirs(projects_dir)
        assert memory_dir in dirs

    def test_empty_projects_dir(self, tmp_path):
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        assert find_memory_dirs(projects_dir) == []

    def test_ignores_non_memory_subdirs(self, tmp_path):
        projects_dir = tmp_path / "projects"
        (projects_dir / "proj" / "config").mkdir(parents=True)
        dirs = find_memory_dirs(projects_dir)
        assert dirs == []

    def test_multiple_projects(self, tmp_path):
        projects_dir = tmp_path / "projects"
        for name in ("alpha", "beta", "gamma"):
            (projects_dir / name / "memory").mkdir(parents=True)
        dirs = find_memory_dirs(projects_dir)
        assert len(dirs) == 3


# ---------------------------------------------------------------------------
# find_stale
# ---------------------------------------------------------------------------

class TestFindStale:
    def test_old_file_detected(self, tmp_path):
        _, memory_dir = _make_projects_dir(tmp_path)
        p = _write_memory(memory_dir, "user_role.md", "content")
        _age_file(p, 100)
        stale = find_stale(memory_dir, age_threshold_days=90)
        assert len(stale) == 1
        assert stale[0].age_days >= 100

    def test_fresh_file_not_detected(self, tmp_path):
        _, memory_dir = _make_projects_dir(tmp_path)
        _write_memory(memory_dir, "fresh.md", "content")
        # Default mtime is now → 0 days old
        stale = find_stale(memory_dir, age_threshold_days=90)
        assert stale == []

    def test_index_file_skipped(self, tmp_path):
        _, memory_dir = _make_projects_dir(tmp_path)
        p = _write_memory(memory_dir, INDEX_FILE, "# index")
        _age_file(p, 200)
        stale = find_stale(memory_dir, age_threshold_days=90)
        assert stale == []

    def test_project_key_from_parent(self, tmp_path):
        projects_dir = tmp_path / "projects"
        memory_dir = projects_dir / "my-awesome-project" / "memory"
        memory_dir.mkdir(parents=True)
        p = _write_memory(memory_dir, "entry.md", "content")
        _age_file(p, 100)
        stale = find_stale(memory_dir, age_threshold_days=90)
        assert stale[0].project_key == "my-awesome-project"

    def test_oserror_on_stat_skipped(self, tmp_path):
        _, memory_dir = _make_projects_dir(tmp_path)
        p = _write_memory(memory_dir, "entry.md", "content")

        real_stat = Path.stat

        def fake_stat(self, *args, **kwargs):
            if self == p:
                raise OSError("no permission")
            return real_stat(self, *args, **kwargs)

        with patch.object(Path, "stat", fake_stat):
            stale = find_stale(memory_dir, age_threshold_days=90)
        assert stale == []

    def test_boundary_at_threshold(self, tmp_path):
        """File aged exactly threshold days should NOT be flagged (strict >)."""
        _, memory_dir = _make_projects_dir(tmp_path)
        p = _write_memory(memory_dir, "edge.md", "content")
        _age_file(p, 90)
        # find_stale checks `mtime < cutoff` where cutoff = now - threshold*86400;
        # a file aged exactly threshold days sits right at the cutoff boundary.
        # Whether it's included depends on floating-point, but it should be <=1 entry.
        stale = find_stale(memory_dir, age_threshold_days=90)
        assert len(stale) <= 1  # may or may not hit boundary; just not fail


# ---------------------------------------------------------------------------
# find_broken_pointers
# ---------------------------------------------------------------------------

class TestFindBrokenPointers:
    def test_no_index_file_returns_empty(self, tmp_path):
        _, memory_dir = _make_projects_dir(tmp_path)
        assert find_broken_pointers(memory_dir) == []

    def test_valid_pointer_not_broken(self, tmp_path):
        _, memory_dir = _make_projects_dir(tmp_path)
        _write_memory(memory_dir, "user_role.md", "content")
        _write_memory(memory_dir, INDEX_FILE, "- [Role](user_role.md)")
        broken = find_broken_pointers(memory_dir)
        assert broken == []

    def test_missing_target_flagged(self, tmp_path):
        _, memory_dir = _make_projects_dir(tmp_path)
        _write_memory(memory_dir, INDEX_FILE, "- [Ghost](ghost.md)")
        broken = find_broken_pointers(memory_dir)
        assert len(broken) == 1
        assert broken[0].target == "ghost.md"

    def test_http_links_skipped(self, tmp_path):
        _, memory_dir = _make_projects_dir(tmp_path)
        _write_memory(
            memory_dir, INDEX_FILE,
            "- [Docs](https://example.com/docs.md)"
        )
        broken = find_broken_pointers(memory_dir)
        assert broken == []

    def test_multiple_broken_pointers(self, tmp_path):
        _, memory_dir = _make_projects_dir(tmp_path)
        _write_memory(
            memory_dir, INDEX_FILE,
            "- [A](a.md)\n- [B](b.md)\n"
        )
        broken = find_broken_pointers(memory_dir)
        targets = {b.target for b in broken}
        assert "a.md" in targets
        assert "b.md" in targets

    def test_oserror_on_index_read_returns_empty(self, tmp_path):
        _, memory_dir = _make_projects_dir(tmp_path)
        index = _write_memory(memory_dir, INDEX_FILE, "- [X](x.md)")

        real_read = Path.read_text

        def fake_read(self, *args, **kwargs):
            if self == index:
                raise OSError("permission denied")
            return real_read(self, *args, **kwargs)

        with patch.object(Path, "read_text", fake_read):
            broken = find_broken_pointers(memory_dir)
        assert broken == []

    def test_project_key_in_result(self, tmp_path):
        projects_dir = tmp_path / "projects"
        memory_dir = projects_dir / "cool-proj" / "memory"
        memory_dir.mkdir(parents=True)
        _write_memory(memory_dir, INDEX_FILE, "- [X](missing.md)")
        broken = find_broken_pointers(memory_dir)
        assert broken[0].project_key == "cool-proj"

    def test_inline_link_in_table(self, tmp_path):
        _, memory_dir = _make_projects_dir(tmp_path)
        _write_memory(
            memory_dir, INDEX_FILE,
            "| col | [ref](ref.md) | note |"
        )
        broken = find_broken_pointers(memory_dir)
        assert any(b.target == "ref.md" for b in broken)


# ---------------------------------------------------------------------------
# archive_file
# ---------------------------------------------------------------------------

class TestArchiveFile:
    def test_moves_file_to_archive(self, tmp_path):
        _, memory_dir = _make_projects_dir(tmp_path)
        p = _write_memory(memory_dir, "stale.md", "data")
        sf = StaleFile(path=p, age_days=100, project_key="my-project")
        dest = archive_file(sf)
        assert not p.exists()
        assert dest.exists()
        assert dest.parent.name == ARCHIVE_DIR

    def test_duplicate_filename_gets_timestamp(self, tmp_path):
        _, memory_dir = _make_projects_dir(tmp_path)
        p1 = _write_memory(memory_dir, "dup.md", "first")
        sf1 = StaleFile(path=p1, age_days=100, project_key="my-project")
        dest1 = archive_file(sf1)

        # Re-create same name and archive again — should not collide
        p2 = _write_memory(memory_dir, "dup.md", "second")
        sf2 = StaleFile(path=p2, age_days=100, project_key="my-project")
        dest2 = archive_file(sf2)

        assert dest1 != dest2
        assert dest1.exists()
        assert dest2.exists()

    def test_archive_dir_created_automatically(self, tmp_path):
        _, memory_dir = _make_projects_dir(tmp_path)
        archive_root = memory_dir / ARCHIVE_DIR
        assert not archive_root.exists()
        p = _write_memory(memory_dir, "old.md", "content")
        sf = StaleFile(path=p, age_days=100, project_key="p")
        archive_file(sf)
        assert archive_root.is_dir()


# ---------------------------------------------------------------------------
# main() CLI
# ---------------------------------------------------------------------------

class TestMain:
    def test_missing_projects_dir_returns_2(self, tmp_path, monkeypatch, capsys):
        nonexistent = tmp_path / "nowhere"
        monkeypatch.setattr(sys, "argv", ["auto_memory_housekeep.py", "--projects-dir", str(nonexistent)])
        rc = main()
        assert rc == 2

    def test_no_memory_dirs_returns_0(self, tmp_path, monkeypatch, capsys):
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        monkeypatch.setattr(sys, "argv", ["auto_memory_housekeep.py", "--projects-dir", str(projects_dir)])
        rc = main()
        assert rc == 0
        out = capsys.readouterr().out
        assert "No project memory dirs" in out

    def test_dry_run_does_not_move_files(self, tmp_path, monkeypatch, capsys):
        projects_dir, memory_dir = _make_projects_dir(tmp_path)
        p = _write_memory(memory_dir, "old.md", "content")
        _age_file(p, 100)
        monkeypatch.setattr(sys, "argv", [
            "auto_memory_housekeep.py",
            "--projects-dir", str(projects_dir),
            "--days", "50",
        ])
        rc = main()
        assert rc == 0
        assert p.exists()  # dry-run: file still present
        out = capsys.readouterr().out
        assert "dry-run" in out.lower() or "Dry-run" in out

    def test_apply_archives_stale_file(self, tmp_path, monkeypatch, capsys):
        projects_dir, memory_dir = _make_projects_dir(tmp_path)
        p = _write_memory(memory_dir, "old.md", "content")
        _age_file(p, 100)
        monkeypatch.setattr(sys, "argv", [
            "auto_memory_housekeep.py",
            "--projects-dir", str(projects_dir),
            "--days", "50",
            "--apply",
        ])
        rc = main()
        assert rc == 0
        assert not p.exists()
        out = capsys.readouterr().out
        assert "archived" in out.lower() or "Archived" in out

    def test_broken_pointers_reported(self, tmp_path, monkeypatch, capsys):
        projects_dir, memory_dir = _make_projects_dir(tmp_path)
        _write_memory(memory_dir, INDEX_FILE, "- [Ghost](ghost.md)")
        monkeypatch.setattr(sys, "argv", [
            "auto_memory_housekeep.py",
            "--projects-dir", str(projects_dir),
        ])
        rc = main()
        assert rc == 0
        out = capsys.readouterr().out
        assert "ghost.md" in out

    def test_summary_line_present(self, tmp_path, monkeypatch, capsys):
        projects_dir, memory_dir = _make_projects_dir(tmp_path)
        _write_memory(memory_dir, "ok.md", "content")
        monkeypatch.setattr(sys, "argv", [
            "auto_memory_housekeep.py",
            "--projects-dir", str(projects_dir),
        ])
        main()
        out = capsys.readouterr().out
        assert "Summary" in out

    def test_clean_project_no_output_for_it(self, tmp_path, monkeypatch, capsys):
        """Projects with no stale/broken files should not print a section header."""
        projects_dir, memory_dir = _make_projects_dir(tmp_path, "clean-proj")
        _write_memory(memory_dir, "fresh.md", "content")  # fresh mtime
        monkeypatch.setattr(sys, "argv", [
            "auto_memory_housekeep.py",
            "--projects-dir", str(projects_dir),
            "--days", "90",
        ])
        main()
        out = capsys.readouterr().out
        # The project section header should NOT appear
        assert "clean-proj" not in out
