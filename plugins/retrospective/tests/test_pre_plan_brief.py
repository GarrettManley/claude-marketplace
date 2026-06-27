"""Tests for retro_brief: section extraction, item/finding parsing, matching, brief.

The parsing/matching functions are pure (text in, structured out); the CLI is
exercised via main() with a patched workspace root.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

# retro_brief lives under the plugin-root scripts/ (like learning's instinct_cli).
_SCRIPT = Path(__file__).parent.parent / "scripts" / "retro_brief.py"
_spec = importlib.util.spec_from_file_location("retro_brief", _SCRIPT)
rb = importlib.util.module_from_spec(_spec)
# Register before exec so @dataclass can resolve the module (Python 3.14).
sys.modules["retro_brief"] = rb
_spec.loader.exec_module(rb)


SAMPLE = """\
# Retrospective: Demo

**Date:** 2026-06-26

## Outcome

Did a thing with the release tooling.

## What worked

- The `release.py` tag-after-merge flow paid off.

## Friction / bugs

- **Commands not linted.** The lint globbed only skills and agents, so command
  files shipped unvalidated — recurred across cycles.
- **Observation privacy caveat.** tool_input recorded verbatim; guardrail deferred.

## Concrete improvements

- **release reconciliation** — done, shipped.
"""


# --- section_body ----------------------------------------------------------

def test_section_body_extracts_named_section():
    body = rb.section_body(SAMPLE, "Friction / bugs")
    assert body is not None
    assert "Commands not linted" in body
    assert "Outcome" not in body  # stops at the next header

def test_section_body_prefix_match():
    text = "## What worked (harness-level)\n- it worked\n## Next\n"
    body = rb.section_body(text, "What worked")
    assert body is not None and "it worked" in body

def test_section_body_missing_returns_none():
    assert rb.section_body(SAMPLE, "Nonexistent Section") is None


# --- extract_items ---------------------------------------------------------

def test_extract_items_splits_top_level_bullets():
    body = rb.section_body(SAMPLE, "Friction / bugs")
    items = rb.extract_items(body)
    assert len(items) == 2
    assert "Commands not linted" in items[0]
    assert "privacy caveat" in items[1].lower()

def test_extract_items_keeps_multiline_continuation():
    body = rb.section_body(SAMPLE, "Friction / bugs")
    items = rb.extract_items(body)
    assert "shipped unvalidated" in items[0]  # wrapped continuation line folded in


# --- lead_of ---------------------------------------------------------------

def test_lead_of_uses_bold_lead():
    assert rb.lead_of("- **Commands not linted.** rest of the text") == "Commands not linted."

def test_lead_of_falls_back_to_first_words():
    lead = rb.lead_of("- a plain finding with no bold lead at all here indeed")
    assert lead.startswith("a plain finding")


# --- extract_findings ------------------------------------------------------

def test_extract_findings_covers_findings_sections():
    findings = rb.extract_findings(SAMPLE, "demo")
    sections = {f.section for f in findings}
    assert "Friction / bugs" in sections
    assert "Concrete improvements" in sections
    assert all(f.slug == "demo" for f in findings)


# --- query / matching ------------------------------------------------------

def test_query_tokens_drops_short_and_stopwords():
    toks = rb.query_tokens("the commands lint a plugin")
    assert "commands" in toks and "lint" in toks
    assert "the" not in toks and "plugin" not in toks  # stopword + noise

def test_matches_on_any_token():
    f = rb.Finding(slug="demo", section="Friction / bugs", lead="x", text="command files shipped unvalidated")
    assert rb.matches(f, ["lint", "command"])
    assert not rb.matches(f, ["postgres"])

def test_matches_on_slug():
    f = rb.Finding(slug="learning-loop", section="x", lead="y", text="unrelated body")
    assert rb.matches(f, ["learning"])


# --- brief / format --------------------------------------------------------

def _write_retro(root: Path, slug: str, content: str) -> None:
    d = root / "retrospectives" / "done"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.md").write_text(content, encoding="utf-8")

def test_brief_finds_matches(tmp_path):
    _write_retro(tmp_path, "demo", SAMPLE)
    found = rb.brief(tmp_path, "commands")
    assert found and any("Commands not linted" in f.lead for f in found)

def test_brief_no_matches(tmp_path):
    _write_retro(tmp_path, "demo", SAMPLE)
    assert rb.brief(tmp_path, "kubernetes") == []

def test_iter_retro_files_sorted(tmp_path):
    _write_retro(tmp_path, "b", SAMPLE)
    _write_retro(tmp_path, "a", SAMPLE)
    files = rb.iter_retro_files(tmp_path)
    assert [p.stem for p in files] == ["a", "b"]

def test_format_brief_groups_by_retro():
    out = rb.format_brief("commands", [rb.Finding("demo", "Friction / bugs", "Commands not linted.", "...")])
    assert "demo" in out and "Commands not linted." in out and "Friction / bugs" in out

def test_format_brief_no_matches_message():
    out = rb.format_brief("kubernetes", [])
    assert "no matching" in out.lower()


# --- find_workspace_root ---------------------------------------------------

def test_find_workspace_root_finds_dot_claude(tmp_path):
    (tmp_path / ".claude").mkdir()
    sub = tmp_path / "nested" / "deep"
    sub.mkdir(parents=True)
    assert rb.find_workspace_root(sub) == tmp_path


# --- main (CLI) ------------------------------------------------------------

def test_main_prints_findings(tmp_path, monkeypatch, capsys):
    _write_retro(tmp_path, "demo", SAMPLE)
    monkeypatch.setattr(rb, "find_workspace_root", lambda *a, **k: tmp_path)
    rc = rb.main(["commands"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Commands not linted." in out

def test_main_no_query_returns_2(capsys):
    rc = rb.main([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "usage" in err.lower()

def test_main_no_workspace_root_is_soft(monkeypatch, capsys):
    monkeypatch.setattr(rb, "find_workspace_root", lambda *a, **k: None)
    rc = rb.main(["commands"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "workspace root" in out.lower()

def test_force_utf8_is_safe():
    rb._force_utf8()  # must never raise, even where streams can't be reconfigured

def test_force_utf8_swallows_missing_reconfigure(monkeypatch):
    import io
    monkeypatch.setattr(rb.sys, "stdout", io.StringIO())  # no .reconfigure -> AttributeError
    monkeypatch.setattr(rb.sys, "stderr", io.StringIO())
    rb._force_utf8()  # swallowed, no raise


# --- additional branch coverage --------------------------------------------

def test_extract_items_blank_line_separates():
    body = "- first item\n\n- second item\n"
    assert rb.extract_items(body) == ["- first item", "- second item"]

def test_extract_findings_skips_missing_sections():
    # A retro with no findings-bearing sections yields nothing.
    assert rb.extract_findings("# Retro\n\n## Outcome\n\nplain.\n", "x") == []

def test_lead_of_truncates_long_item():
    item = "- " + " ".join(f"w{i}" for i in range(20))
    lead = rb.lead_of(item)
    assert lead.endswith("…")

def test_brief_empty_query_returns_empty(tmp_path):
    _write_retro(tmp_path, "demo", SAMPLE)
    assert rb.brief(tmp_path, "the a") == []  # all stopword/short -> no tokens

def test_brief_skips_unreadable_file(tmp_path, monkeypatch):
    import pathlib
    _write_retro(tmp_path, "demo", SAMPLE)
    monkeypatch.setattr(pathlib.Path, "read_text", lambda self, *a, **k: (_ for _ in ()).throw(OSError()))
    assert rb.brief(tmp_path, "commands") == []

def test_find_workspace_root_git_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(rb.Path, "is_dir", lambda self: False)  # no .claude anywhere
    monkeypatch.setattr(rb.subprocess, "check_output", lambda *a, **k: f"{tmp_path}\n")
    assert rb.find_workspace_root(tmp_path) == tmp_path

def test_find_workspace_root_git_empty_output_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(rb.Path, "is_dir", lambda self: False)
    monkeypatch.setattr(rb.subprocess, "check_output", lambda *a, **k: "\n")
    assert rb.find_workspace_root(tmp_path) is None

def test_find_workspace_root_git_error_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(rb.Path, "is_dir", lambda self: False)
    def boom(*a, **k):
        raise rb.subprocess.CalledProcessError(1, "git")
    monkeypatch.setattr(rb.subprocess, "check_output", boom)
    assert rb.find_workspace_root(tmp_path) is None

def test_main_handles_non_cp1252_content(tmp_path, monkeypatch):
    # Retro content with an arrow + checkmark must not crash rendering.
    _write_retro(tmp_path, "demo", SAMPLE.replace("done, shipped", "done → shipped ✓"))
    monkeypatch.setattr(rb, "find_workspace_root", lambda *a, **k: tmp_path)
    assert rb.main(["release"]) == 0
