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


def extract_step5_body() -> str:
    """Return step 5's full body: from its list marker up to (not including) step 6.

    Step 5 is a numbered list item inside "### Phase A", not its own markdown
    heading, so `section()` (heading-anchored) doesn't apply -- anchor on the list
    marker text itself instead, the same text-anchoring convention already used by
    `parenthetical_after` / `extract_fixed_step_slugs` above.
    """
    phase_a = section(SKILL_TEXT, "### Phase A — Plan (in plan mode)")
    start = phase_a.index("5. **Adversarial plan review")
    end = phase_a.index("6. **Approval", start)
    return phase_a[start:end]


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


# ---------------------------------------------------------------------------
# Invariant 6 -- every composed skill with its own auto-hand-off is suppressed
# ---------------------------------------------------------------------------


class TestComposedHandoffsAreSuppressed:
    """deliver's spine invariant: each composed skill that documents its own
    downstream auto-hand-off must be given an explicit stop-instruction, in its
    own phase, so deliver keeps control of the lifecycle. Three seams carry this:
    brainstorming (Phase 0), writing-plans (Phase A), subagent-driven-development
    (Phase B). A future edit that adds/strengthens one but drops another silently
    reintroduces a double-hand-off bug. Structural guard, not a restatement of a
    drifting fact -- cf. TestLandPolicyOverclaimRemoved.
    """

    # (suppressed skill, exact phase heading whose body must contain its stop-instruction)
    SEAMS = [
        ("brainstorming", "### Phase 0 — Design (optional)"),
        ("writing-plans", "### Phase A — Plan (in plan mode)"),
        ("subagent-driven-development", "### Phase B — Execute"),
    ]

    @pytest.mark.parametrize("skill,phase_heading", SEAMS)
    def test_seam_carries_stop_instruction_in_its_phase(self, skill, phase_heading):
        body = section(SKILL_TEXT, phase_heading)
        assert skill in body, f"{skill!r} not named in {phase_heading!r}"
        assert re.search(r"\bStop\b", body), f"{phase_heading!r} lacks a 'Stop' instruction"
        assert re.search(r"hand-?off", body, re.IGNORECASE), (
            f"{phase_heading!r} lacks a 'hand-off' suppression instruction"
        )


# ---------------------------------------------------------------------------
# Invariant 7 -- the plan-review triage is named and wired
# ---------------------------------------------------------------------------


class TestReviewTriage:
    """Step 5's adversarial-plan-review dispatch is triaged (SKIP/SCALED/FULL), not
    an unconditional full review -- a future edit that simplifies step 5 back to a
    flat invocation must not silently drop the triage this plugin exists to add.
    """

    def test_step_5_names_all_three_postures(self):
        body = extract_step5_body()
        for posture in ("SKIP", "SCALED", "FULL"):
            assert posture in body, f"step 5 does not name the {posture!r} posture"

    def test_skip_is_conditioned_on_the_format_self_check(self):
        body = extract_step5_body()
        skip_bullet = body[body.index("**`SKIP`**"): body.index("**`FULL`**")]
        # Collapse markdown's hard-wrapped whitespace/newlines before the substring
        # check -- prose reflow must not break this invariant.
        collapsed = re.sub(r"\s+", " ", skip_bullet)
        assert "format self-check" in collapsed, (
            "the SKIP posture's own bullet must condition on the format self-check, "
            "not just mention it elsewhere in step 5"
        )

    def test_phase_0_signal_is_wired_to_scaled(self):
        body = extract_step5_body()
        scaled_bullet = body[body.index("**`SCALED`**"):]
        assert "Phase 0" in scaled_bullet, (
            "the SCALED posture's own bullet must reference Phase 0 -- this is the "
            "brainstorming-as-gate mechanism the whole feature exists to wire up"
        )

    def test_an_artifact_is_committed_on_every_posture(self):
        body = extract_step5_body()
        skip_bullet = body[body.index("**`SKIP`**"): body.index("**`FULL`**")]
        assert "commit" in skip_bullet.lower(), (
            "SKIP must still leave a committed record -- the 'findings file committed' "
            "invariant must hold on every posture, not just SCALED/FULL"
        )

    def test_plan_review_policy_key_is_in_all_four_slot_representations(self):
        """plan-review-policy must ride the same four-representation invariant
        TestSlotNameSetIsIdentical already enforces for every slot -- assert it
        explicitly here so reviewing this feature's diff doesn't require
        cross-referencing that unrelated test class to know it's covered."""
        assert "plan-review-policy" in extract_slots_table()
        assert "plan-review-policy" in extract_config_yaml_keys()
        assert "plan-review-policy" in extract_with_config_echo()
        assert "plan-review-policy" in extract_no_config_echo()


# ---------------------------------------------------------------------------
# Invariant 8 -- Phase B dispatch carries a cwd/worktree confirmation guardrail
# ---------------------------------------------------------------------------


def extract_step7_body() -> str:
    """Return step 7's body: from its list marker up to (not including) step 8.

    Step 7 is a numbered list item inside "### Phase B", not its own markdown
    heading, so section() (heading-anchored) doesn't apply -- anchor on the list
    marker text itself, mirroring extract_step5_body above.
    """
    phase_b = section(SKILL_TEXT, "### Phase B — Execute")
    start = phase_b.index("7. **Subagent-driven execution")
    end = phase_b.index("8. **Edit checklist", start)
    return phase_b[start:end]


class TestImplementerCwdGuardrail:
    """Step 7 must instruct dispatched implementers to confirm their working
    directory/branch before editing -- a prose 'Work from: <path>' is not an
    enforced cwd (claude-marketplace PR #26: an implementer silently edited the
    main checkout instead of its worktree, self-reporting a plausible test
    transcript). Structural guard, not a restatement of a drifting fact --
    cf. TestReviewTriage / TestComposedHandoffsAreSuppressed.
    """

    def test_step_7_names_the_cwd_confirmation_commands(self):
        body = extract_step7_body()
        assert "git rev-parse" in body, "step 7 must tell the subagent to run git rev-parse"
        assert "git branch" in body, "step 7 must tell the subagent to run git branch"

    def test_step_7_requires_confirming_before_editing(self):
        body = extract_step7_body()
        collapsed = re.sub(r"\s+", " ", body).lower()
        assert "confirm" in collapsed, "step 7 must require the subagent to confirm its cwd"
        assert re.search(r"before (touch|edit)", collapsed), (
            "the guardrail must require confirmation BEFORE touching/editing a file"
        )

    def test_step_7_cites_the_mislocation_counterexample(self):
        # Non-vacuous anchor: tie the guardrail to its documented incident so a
        # future edit can't reduce it to a bare one-liner and still pass.
        body = extract_step7_body()
        assert "Work from" in body or "#26" in body, (
            "the guardrail must cite the enforced-cwd rationale / PR #26 counter-example"
        )
