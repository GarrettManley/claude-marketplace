# plugins/delivery/tests/test_deliver_contract.py
"""Contract tests for `deliver`'s SKILL.md.

`delivery` ships zero Python -- there is no module to unit-test. What it does ship
is a single long prose document (SKILL.md) that restates the same facts (slot
names, defaults, land-policy verbs, fixed-step names) in several independently
edited places: a table, a YAML example, two echo blocks, and running prose. Those
restatements drift out of sync on routine edits (see the "five fixed steps" /
"Three steps are configurable" bugs fixed alongside this test).

Every assertion here therefore *derives* a fact from >=2 locations in SKILL.md (or
plugin.json) and compares the derived values -- it never hardcodes a literal that
merely repeats what the test author believed the prose said. Sections are located
by heading / fenced-code anchor, never by line number, so routine prose edits that
don't touch the facts being checked can't spuriously fail this file.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

SKILL_PATH = Path(__file__).parents[1] / "skills" / "deliver" / "SKILL.md"
PLUGIN_JSON_PATH = Path(__file__).parents[1] / ".claude-plugin" / "plugin.json"

SKILL_TEXT = SKILL_PATH.read_text(encoding="utf-8")
PLUGIN_JSON = json.loads(PLUGIN_JSON_PATH.read_text(encoding="utf-8"))

FENCE_RE = re.compile(r"```(?:[a-zA-Z]+)?\n(.*?)\n```", re.DOTALL)
BACKTICK_TOKEN_RE = re.compile(r"`([a-zA-Z0-9][a-zA-Z0-9_-]*)`")
PLUGIN_SKILL_SLUG_RE = re.compile(r"`([a-zA-Z0-9_-]+):([a-zA-Z0-9_-]+)`")


def _mask_fenced_blocks(text: str) -> str:
    """Blank out fenced-code interiors (keep length/newlines) so a `#`-prefixed
    comment inside a fenced example (e.g. the Configuration YAML block's
    `# <repo>/.claude/delivery.local.md`) can't be mistaken for a markdown
    heading by `section()`'s heading-boundary search.
    """

    def _blank(match: re.Match) -> str:
        return "".join("\n" if ch == "\n" else " " for ch in match.group(0))

    return re.sub(r"```.*?```", _blank, text, flags=re.DOTALL)


# Index-aligned with SKILL_TEXT (same length, same newline positions) so offsets
# found in one are valid slice bounds into the other.
MASKED_SKILL_TEXT = _mask_fenced_blocks(SKILL_TEXT)


# ---------------------------------------------------------------------------
# Generic anchoring / normalization helpers
# ---------------------------------------------------------------------------


def normalize(raw: str) -> str:
    """Strip markdown decoration and drift-prone trailing qualifiers.

    Backticks and bold/italic asterisks are decoration; "only" and "(Hybrid)" are
    qualifiers that appear next to a value in prose but never in the bare echo
    restatement of that same value, so both must fall away before comparison.
    """
    text = raw.strip()
    text = text.replace("**", "").replace("`", "").replace("*", "")
    text = re.sub(r"\s*\(Hybrid\)\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+only\s*$", "", text, flags=re.IGNORECASE)
    return text.strip()


def section(text: str, heading: str) -> str:
    """Return the body of the section starting at `heading` (exclusive), up to the
    next heading of equal-or-shallower level, anchored on the heading text itself
    rather than a line number.

    Heading boundaries are located in `MASKED_SKILL_TEXT` (fenced-code interiors
    blanked out) so a `#`-prefixed comment inside a fenced example doesn't get
    mistaken for a markdown heading; the returned slice is taken from `text`
    (unmasked) using those same offsets.
    """
    heading_re = re.compile(rf"^{re.escape(heading)}\s*$", re.MULTILINE)
    match = heading_re.search(MASKED_SKILL_TEXT)
    assert match, f"heading not found in SKILL.md: {heading!r}"
    level = len(heading) - len(heading.lstrip("#"))
    next_heading_re = re.compile(rf"^#{{1,{level}}}\s", re.MULTILINE)
    next_match = next_heading_re.search(MASKED_SKILL_TEXT, match.end())
    end = next_match.start() if next_match else len(text)
    return text[match.end() : end]


def fenced_block_containing(text: str, marker: str) -> str:
    """Return the contents of the fenced code block that contains `marker`."""
    for block in FENCE_RE.findall(text):
        if marker in block:
            return block
    raise AssertionError(f"no fenced block in SKILL.md contains {marker!r}")


def parenthetical_after(text: str, marker: str) -> str:
    """Return the contents of the first `(...)` group following `marker`."""
    idx = text.index(marker)
    start = text.index("(", idx)
    end = text.index(")", start)
    return text[start + 1 : end]


# ---------------------------------------------------------------------------
# Fact extraction: Slots table
# ---------------------------------------------------------------------------


def extract_slots_table() -> dict[str, dict[str, str]]:
    """Parse the `| Slot | Generic default | Purpose |` table into
    {slot_name: {"default": ..., "purpose": ...}}, keyed on the normalized slot
    name from the table's own first column.
    """
    header = "| Slot | Generic default | Purpose |"
    start = SKILL_TEXT.index(header)
    lines = SKILL_TEXT[start:].splitlines()
    rows: dict[str, dict[str, str]] = {}
    # lines[0] is the header, lines[1] the `|---|---|---|` separator.
    for line in lines[2:]:
        if not line.strip().startswith("|"):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        assert len(cells) == 3, f"unexpected Slots table row shape: {line!r}"
        slot_name = normalize(cells[0])
        rows[slot_name] = {"default": cells[1], "purpose": cells[2]}
    assert rows, "Slots table parsed to zero rows"
    return rows


# ---------------------------------------------------------------------------
# Fact extraction: Configuration YAML block
# ---------------------------------------------------------------------------


def extract_config_yaml_keys() -> set[str]:
    yaml_block = fenced_block_containing(SKILL_TEXT, "plan-writer: myproject:plan-writer")
    keys = set()
    for line in yaml_block.splitlines():
        line = line.strip()
        if not line or line == "---" or line.startswith("#"):
            continue
        match = re.match(r"^([a-zA-Z0-9_-]+):", line)
        if match:
            keys.add(match.group(1))
    assert keys, "Configuration YAML block parsed to zero keys"
    return keys


# ---------------------------------------------------------------------------
# Fact extraction: resolved-slot echo blocks
# ---------------------------------------------------------------------------


def parse_echo_block(block: str) -> dict[str, str]:
    slots = {}
    for line in block.splitlines():
        match = re.match(r"^\s*([a-zA-Z0-9_-]+)\s*=\s*(.+?)\s*$", line)
        if match:
            slots[match.group(1)] = match.group(2)
    assert slots, "echo block parsed to zero slot=value lines"
    return slots


def extract_with_config_echo() -> dict[str, str]:
    return parse_echo_block(fenced_block_containing(SKILL_TEXT, "resolved slots (myproject)"))


def extract_no_config_echo() -> dict[str, str]:
    return parse_echo_block(fenced_block_containing(SKILL_TEXT, "resolved slots (no delivery.local.md)"))


# ---------------------------------------------------------------------------
# Fact extraction: land-policy verb sets
# ---------------------------------------------------------------------------


def extract_land_policy_verbs_from_table() -> set[str]:
    purpose = extract_slots_table()["land-policy"]["purpose"]
    scope = parenthetical_after(purpose, "a set value")
    return set(BACKTICK_TOKEN_RE.findall(scope))


def extract_land_policy_verbs_from_config_prose() -> set[str]:
    config_section = section(SKILL_TEXT, "## Configuration")
    scope = parenthetical_after(config_section, "accepts a short verb")
    return set(BACKTICK_TOKEN_RE.findall(scope))


def extract_land_policy_verbs_from_landing_section() -> set[str]:
    landing_section = section(SKILL_TEXT, "## Landing policy (Hybrid)")
    scope = parenthetical_after(landing_section, "`land-policy` set**")
    return set(BACKTICK_TOKEN_RE.findall(scope))


# ---------------------------------------------------------------------------
# Fact extraction: fixed steps + Cross-references
# ---------------------------------------------------------------------------


def extract_fixed_step_slugs() -> list[tuple[str, str]]:
    """Extract the `plugin:skill` slugs from the fixed-steps sentence.

    Bounded on a backtick immediately followed by a period (the sentence always
    ends on its last backtick-quoted slug) rather than the next blank line -- a
    paragraph reflow that inserts a blank line mid-list must not silently
    truncate the slug set and leave later slugs unguarded by invariants 4/5.
    """
    marker = "The fixed steps are not configurable"
    start = SKILL_TEXT.index(marker)
    end_match = re.search(r"`\.", SKILL_TEXT[start:])
    assert end_match, "could not find a sentence-terminating '`.' after the fixed-steps marker"
    end = start + end_match.end()
    sentence = SKILL_TEXT[start:end]
    slugs = PLUGIN_SKILL_SLUG_RE.findall(sentence)
    assert slugs, "fixed-steps sentence yielded zero plugin:skill slugs"
    return slugs


def extract_cross_reference_bare_names() -> set[str]:
    cross_refs = section(SKILL_TEXT, "## Cross-references")
    return set(BACKTICK_TOKEN_RE.findall(cross_refs))


# ---------------------------------------------------------------------------
# Invariant 1 -- slot name set identical across all four representations
# ---------------------------------------------------------------------------


class TestSlotNameSetIsIdentical:
    def test_table_yaml_and_both_echoes_agree(self):
        table_slots = set(extract_slots_table().keys())
        yaml_keys = extract_config_yaml_keys()
        with_config_keys = set(extract_with_config_echo().keys())
        no_config_keys = set(extract_no_config_echo().keys())

        assert table_slots == yaml_keys == with_config_keys == no_config_keys


# ---------------------------------------------------------------------------
# Invariant 2 -- each slot's default agrees (no-config echo vs table default)
# ---------------------------------------------------------------------------


class TestSlotDefaultsAgree:
    @pytest.mark.parametrize("slot", sorted(extract_slots_table().keys()))
    def test_default_matches_no_config_echo(self, slot):
        table_default = normalize(extract_slots_table()[slot]["default"])
        echo_default = normalize(extract_no_config_echo()[slot])
        assert table_default == echo_default


# ---------------------------------------------------------------------------
# Invariant 3 -- land-policy verb set identical across all three sections
# ---------------------------------------------------------------------------


class TestLandPolicyVerbSetIsIdentical:
    def test_table_config_and_landing_section_agree(self):
        from_table = extract_land_policy_verbs_from_table()
        from_config = extract_land_policy_verbs_from_config_prose()
        from_landing = extract_land_policy_verbs_from_landing_section()

        assert from_table == from_config == from_landing
        # Guard against a vacuous pass (e.g. an anchor silently matching nothing).
        assert len(from_table) >= 2


# Negative guard: pins out prose already confirmed inaccurate (SKILL.md
# overclaimed "exactly two cases"); this is not the positive-literal antipattern the module
# docstring warns against, since there is no drifting fact being restated here.
class TestLandPolicyOverclaimRemoved:
    def test_overclaim_phrases_are_absent(self):
        landing = section(SKILL_TEXT, "## Landing policy (Hybrid)")
        assert "exactly two cases" not in landing.lower()
        assert "both exhaustive" not in landing.lower()
        assert "unrecognized" in landing.lower()

    def test_slot_table_row_states_the_halt_outcome_too(self):
        """The slot table restates land-policy's behavior independently of the
        Landing policy section prose above -- if only that section were updated
        (as originally happened; caught by whole-branch review), the table would
        silently keep describing a two-outcome model. Assert the table's own
        purpose cell states the halt outcome, not just that the Landing section
        does."""
        purpose = extract_slots_table()["land-policy"]["purpose"]
        assert "halt" in purpose.lower()


# ---------------------------------------------------------------------------
# Invariant 4 -- fixed-step skill names are cross-referenced
# ---------------------------------------------------------------------------


class TestFixedStepsAreCrossReferenced:
    def test_bare_names_appear_in_cross_references(self):
        fixed_step_slugs = extract_fixed_step_slugs()
        cross_ref_names = extract_cross_reference_bare_names()

        bare_names = {name for _prefix, name in fixed_step_slugs}
        assert bare_names, "no bare names derived from the fixed-steps sentence"
        missing = bare_names - cross_ref_names
        assert not missing, f"fixed-step names missing from Cross-references: {missing}"


# ---------------------------------------------------------------------------
# Invariant 5 -- non-external fixed-step plugins are declared dependencies
# ---------------------------------------------------------------------------


class TestNonExternalFixedStepPluginsAreDeclared:
    def test_declared_dependencies_cover_non_external_fixed_steps(self):
        fixed_step_slugs = extract_fixed_step_slugs()
        prefixes = {prefix for prefix, _name in fixed_step_slugs}

        non_external = prefixes - {"superpowers"}
        assert non_external, "expected at least one non-external fixed-step prefix"

        declared = set(PLUGIN_JSON["dependencies"])
        missing = non_external - declared
        assert not missing, f"fixed-step plugins missing from plugin.json dependencies: {missing}"
