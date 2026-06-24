import pytest
from pathlib import Path
import sys

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from instinct_schema import (
    Instinct,
    parse_instinct,
    format_instinct,
    parse_multi_instinct_file,
    INSTINCT_FRONTMATTER_FIELDS,
)


SINGLE_INSTINCT = """---
id: grep-before-edit
trigger: when modifying code
confidence: 0.7
domain: workflow
source: import
---

# Grep before edit

## Action

Run Grep on the symbol before editing any source file.

## Evidence

- Reduces incorrect edits where the symbol has multiple definitions.
"""


def test_parse_instinct_basic():
    inst = parse_instinct(SINGLE_INSTINCT)
    assert inst.id == "grep-before-edit"
    assert inst.confidence == 0.7
    assert inst.domain == "workflow"
    assert inst.trigger == "when modifying code"
    assert "Run Grep" in inst.action
    assert "incorrect edits" in inst.evidence


def test_parse_instinct_missing_required_field_errors():
    bad = "---\nid: x\nconfidence: 0.5\n---\n\n## Action\nfoo"
    with pytest.raises(ValueError):
        parse_instinct(bad)


def test_parse_instinct_invalid_confidence_errors():
    bad = "---\nid: x\ntrigger: y\nconfidence: high\ndomain: z\nsource: w\n---\n\n## Action\nfoo"
    with pytest.raises(ValueError):
        parse_instinct(bad)


def test_format_instinct_roundtrip():
    inst = parse_instinct(SINGLE_INSTINCT)
    text = format_instinct(inst)
    inst2 = parse_instinct(text)
    assert inst2.id == inst.id
    assert inst2.confidence == inst.confidence
    assert inst2.action.strip() == inst.action.strip()


def test_parse_multi_instinct_file_two_instincts():
    # Two complete instincts back to back with EVERYTHING (frontmatter+body) for each
    multi = SINGLE_INSTINCT + "\n" + """---
id: two
trigger: when something
confidence: 0.8
domain: workflow
source: import
---

# Two

## Action

Do other thing.

## Evidence

- It works.
"""
    instincts = parse_multi_instinct_file(multi)
    assert len(instincts) == 2
    assert {i.id for i in instincts} == {"grep-before-edit", "two"}


def test_parse_multi_instinct_file_single():
    instincts = parse_multi_instinct_file(SINGLE_INSTINCT)
    assert len(instincts) == 1
    assert instincts[0].id == "grep-before-edit"


def test_required_fields_constant():
    assert "id" in INSTINCT_FRONTMATTER_FIELDS
    assert "confidence" in INSTINCT_FRONTMATTER_FIELDS
    assert "domain" in INSTINCT_FRONTMATTER_FIELDS
    assert "trigger" in INSTINCT_FRONTMATTER_FIELDS
    assert "source" in INSTINCT_FRONTMATTER_FIELDS
