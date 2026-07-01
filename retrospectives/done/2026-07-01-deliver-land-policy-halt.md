# Retrospective: fail-closed land-policy halt for `/deliver`

**Tracker:** hb-w61.11, under epic hb-w61.
**Commits:** see `git log main..worktree-deliver-land-policy-halt` for the exact, current hash
list — not pinned here by hash, since this branch was rebased onto `main` in a follow-up
`/deliver` session (rebase rewrites hashes; see the companion `run_with_flags` retro's "Update"
section for the same lesson learned in this session).
**Date:** 2026-07-01

## Outcome

Hardened `deliver`'s Landing-policy resolution (`plugins/delivery/skills/deliver/SKILL.md`) from
an undefined-on-unrecognized-value gap into a fail-closed three-way split: `land-policy` unset →
`finishing-a-development-branch`'s menu; set to a recognized verb (`ff-only`/`pr`/`direct`/`ask`)
→ honored inline; anything else (typo, unsupported verb, empty/whitespace-only) → halt and surface
the literal configured value, never landing. Previously an unrecognized value had no defined
behavior in the prose spec, meaning a future agent executing `deliver` could plausibly default to
either path silently rather than refusing to land — a silent-fallthrough risk this closes.

Also closed, in a subsequent `/deliver` session's whole-branch adversarial code review (before PR
landing): the slot table's `land-policy` row still described only the old two-outcome model,
contradicting the "## Landing policy (Hybrid)" section's new three-way split a few paragraphs
below — an agent skimming just the table could still land on a misconfigured value. Reconciled the
table row and Configuration section, and added a derived-fact test
(`test_slot_table_row_states_the_halt_outcome_too`) asserting the table's own purpose cell states
the halt outcome, so this exact class of drift is CI-caught rather than requiring a human to
notice it again.

## What worked

- **The existing contract-test module's "derive facts from >=2 locations, never hardcode" design**
  (`test_deliver_contract.py`'s own docstring) made the whole-branch review's finding actionable
  immediately — the fix wasn't "add an assertion," it was "extend the existing derivation pattern
  to a location it hadn't reached yet," which kept the new test consistent with the file's stated
  philosophy instead of adding a one-off literal check.
- **Verifying a review finding against the actual extraction helpers before editing** caught a
  self-inflicted regression before it landed: the first draft of the slot-table fix reworded "a set
  value" to "a recognized value," which broke `extract_land_policy_verbs_from_table`'s literal
  string anchor (`text.index("a set value")` raises `ValueError` on no match) — caught by running
  the test suite immediately after the edit, before committing, rather than assuming a prose
  rewording was safe.
- **Disjoint-file landing alongside a second unrelated branch** (`worktree-fix-run-with-flags-spawn-bugs`,
  touching only `plugins/{discipline,learning,stewardship}/`) — no cross-branch conflict, both
  rebased and reviewed independently in the same session with zero coordination overhead.

## Friction / bugs

- **A prose-rewording edit broke a test that anchors on an exact substring.** The contract test
  suite's derivation helpers (`parenthetical_after`, etc.) intentionally anchor on literal phrases
  in the prose to extract facts — which means any edit to that exact phrase, even a
  meaning-preserving paraphrase, is a breaking change to the test, not just to the prose. This is a
  known and accepted tradeoff of the module's own design (documented in its docstring), not a new
  bug, but it's worth flagging as a standing hazard for future SKILL.md edits: **grep the target
  phrase in `test_deliver_contract.py` before rewording anything in a table row or section this
  suite anchors on.**
  - *Rule:* before editing prose in `plugins/delivery/skills/deliver/SKILL.md`, check whether
    `test_deliver_contract.py` anchors on the exact substring being changed
    (`grep -n "<phrase>" plugins/delivery/tests/test_deliver_contract.py`); if so, either preserve
    the anchor phrase verbatim or update the helper's marker string in the same commit.

## Concrete improvements

- **hb-w61.11 is closed** — the fail-closed halt behavior is implemented, tested, and (pending PR
  merge) about to ship.
- **Follow-up, not filed as a new tracker item (low priority, optional):** the Configuration
  section's `land-policy` sentence and the slot table both now state the halt outcome briefly; a
  future edit could go further and add a fourth bullet-style outcome row to the table itself
  instead of a purpose-cell footnote, if the prose ever gets dense enough to warrant it. Not done
  here — out of scope for this fix.
