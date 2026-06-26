import pytest

import persona

_VALID = """---
name: security-auditor
description: |
  Use when reviewing trust boundaries.
tools: Read, Grep, Glob, Bash
---

# Security Auditor

- **Pushback triggers:**
  - Permissions broader than needed
- **NOT covered:** business logic.
- **Severity rubric:**
  - `blocker` — exploitable without auth
- **Last updated:** 0.1.0 — initial archetype.
"""


def test_split_frontmatter_returns_fm_and_body():
    fm, body = persona.split_frontmatter(_VALID)
    assert "name: security-auditor" in fm
    assert "# Security Auditor" in body


def test_split_frontmatter_raises_without_frontmatter():
    with pytest.raises(ValueError):
        persona.split_frontmatter("# no frontmatter here")


def test_extract_name():
    fm, _ = persona.split_frontmatter(_VALID)
    assert persona.extract_name(fm) == "security-auditor"


def test_extract_name_returns_none_without_name_key():
    assert persona.extract_name("description: x\ntools: Read\n") is None


def test_validate_persona_accepts_well_formed():
    assert persona.validate_persona(_VALID, "security-auditor") == []


def test_validate_persona_flags_name_mismatch():
    errs = persona.validate_persona(_VALID, "data-architect")
    assert any("name" in e.lower() for e in errs)


def test_validate_persona_flags_missing_section():
    text = _VALID.replace("- **Severity rubric:**", "- **Notes:**")
    errs = persona.validate_persona(text, "security-auditor")
    assert any("Severity rubric" in e for e in errs)


def test_validate_persona_flags_missing_frontmatter_key():
    text = _VALID.replace("tools: Read, Grep, Glob, Bash\n", "")
    errs = persona.validate_persona(text, "security-auditor")
    assert any("tools" in e for e in errs)


def test_validate_persona_flags_absent_frontmatter():
    errs = persona.validate_persona("# no frontmatter", "security-auditor")
    assert errs and "frontmatter" in errs[0].lower()


def test_last_updated_line():
    assert "0.1.0" in persona.last_updated_line(_VALID)


def test_last_updated_line_none_without_marker():
    assert persona.last_updated_line("no marker here") is None


def test_render_diff_shows_change():
    d = persona.render_diff("a\n", "b\n", "x.md")
    assert "-a" in d and "+b" in d


def test_atomic_write_roundtrip(tmp_path):
    p = tmp_path / "out.md"
    persona.atomic_write(p, "hello")
    assert p.read_text(encoding="utf-8") == "hello"
