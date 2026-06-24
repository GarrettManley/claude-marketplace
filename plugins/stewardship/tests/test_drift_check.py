# plugins/stewardship/tests/test_drift_check.py
"""Unit tests for drift_check.py — staleness extension + frontmatter parsing."""
from datetime import date

from drift_check import (
    extract_last_verified,
    extract_verification_cmd,
    render_markdown,
    scan_staleness,
)

TODAY = date(2026, 6, 9)


def _ctx(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


class TestExtractLastVerified:
    def test_plain_date(self):
        text = "---\ntopic: x\nlast_verified: 2026-05-09\n---\nbody"
        assert extract_last_verified(text) == date(2026, 5, 9)

    def test_datetime_form(self):
        text = "---\nlast_verified: 2026-03-25 22:58:00\n---\nbody"
        assert extract_last_verified(text) == date(2026, 3, 25)

    def test_quoted(self):
        text = '---\nlast_verified: "2026-01-01"\n---\nbody'
        assert extract_last_verified(text) == date(2026, 1, 1)

    def test_missing_key(self):
        assert extract_last_verified("---\ntopic: x\n---\nbody") is None

    def test_no_frontmatter(self):
        assert extract_last_verified("# just markdown") is None

    def test_key_outside_frontmatter_ignored(self):
        text = "---\ntopic: x\n---\nlast_verified: 2026-01-01\n"
        assert extract_last_verified(text) is None


class TestScanStaleness:
    def test_old_file_flagged(self, tmp_path):
        _ctx(tmp_path, "old.md", "---\nlast_verified: 2026-03-25\n---\nbody")
        stale = scan_staleness(tmp_path, max_age_days=45, today=TODAY)
        assert len(stale) == 1
        assert stale[0].last_verified == "2026-03-25"
        assert stale[0].age_days == 76

    def test_fresh_file_not_flagged(self, tmp_path):
        _ctx(tmp_path, "fresh.md", "---\nlast_verified: 2026-06-09\n---\nbody")
        assert scan_staleness(tmp_path, max_age_days=45, today=TODAY) == []

    def test_boundary_is_exclusive(self, tmp_path):
        _ctx(tmp_path, "edge.md", "---\nlast_verified: 2026-04-25\n---\nbody")  # 45d
        assert scan_staleness(tmp_path, max_age_days=45, today=TODAY) == []

    def test_file_without_last_verified_skipped(self, tmp_path):
        _ctx(tmp_path, "nofm.md", "# no frontmatter at all")
        assert scan_staleness(tmp_path, max_age_days=45, today=TODAY) == []

    def test_zero_disables(self, tmp_path):
        _ctx(tmp_path, "old.md", "---\nlast_verified: 2020-01-01\n---\nbody")
        assert scan_staleness(tmp_path, max_age_days=0, today=TODAY) == []

    def test_readme_skipped(self, tmp_path):
        _ctx(tmp_path, "README.md", "---\nlast_verified: 2020-01-01\n---\nbody")
        assert scan_staleness(tmp_path, max_age_days=45, today=TODAY) == []

    def test_recurses_subdirs(self, tmp_path):
        sub = tmp_path / "orchestration"
        sub.mkdir()
        _ctx(sub, "model-status.md", "---\nlast_verified: 2026-03-25\n---\nbody")
        stale = scan_staleness(tmp_path, max_age_days=45, today=TODAY)
        assert len(stale) == 1

    def test_staleness_independent_of_verification_cmd(self, tmp_path):
        # A file can be stale even if it has no verification_cmd — and a file
        # whose command still passes can still be stale. The two checks are
        # deliberately decoupled.
        body = "---\nlast_verified: 2026-01-01\n---\nbody"
        p = _ctx(tmp_path, "no-cmd.md", body)
        assert extract_verification_cmd(p.read_text(encoding="utf-8")) is None
        assert len(scan_staleness(tmp_path, max_age_days=45, today=TODAY)) == 1


class TestRenderMarkdown:
    def test_stale_section_rendered(self, tmp_path):
        _ctx(tmp_path, "old.md", "---\nlast_verified: 2026-03-25\n---\nbody")
        stale = scan_staleness(tmp_path, max_age_days=45, today=TODAY)
        out = render_markdown([], stale)
        assert "### Stale" in out
        assert "old.md" in out and "76d ago" in out

    def test_no_results_no_stale(self):
        out = render_markdown([], [])
        assert "No verifiable context files" in out

    def test_backward_compatible_without_stale_arg(self):
        # render_markdown([]) must keep working for any existing caller.
        assert "No verifiable context files" in render_markdown([])
