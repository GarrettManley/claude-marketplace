# Retrospective: Harden the hook-runtime-controls CI gate to cover all gated plugins

**Plan:** `~/.claude/plans/delivery-deliver-i-m-looking-to-jazzy-flask.md`
**Commit:** `1cadc2f` (`fix(ci): harden hook-runtime-controls gate against malformed hooks.json`)
**Date:** 2026-06-30

## Outcome

`ci/verify_hook_runtime_controls.py` widened from checking only `discipline`'s
`hooks.json` to checking every plugin that ships the `scripts/run_with_flags.py`
disable-pattern wrapper (`discipline`, `learning`, `stewardship`), via an explicit
`GATED_PLUGINS` list plus a bidirectional consistency assertion against the on-disk
wrapper set. Previously `learning`/`stewardship` hooks could silently bypass their own
disable mechanism and CI would stay green. Landed as 3 commits on `main`
(`ff35831` widen, `9385fee` doc updates, `1cadc2f` harden against malformed input),
fast-forward merged, no push. `TestVerifyHookRuntimeControls` grew from 8 to 15 tests,
100% coverage on the module, `scripts/verify.sh` green throughout. Two non-goals filed as
tracked follow-ups (`hb-w61.8`, `hb-w61.9`) rather than silently dropped.

## What worked

- **Value-probe-before-plan.** Three parallel Explore agents (deferred-work map, retro
  synthesis, cross-plugin quality gaps) surfaced a candidate field in one pass, cross-checked
  against the beads backlog (`hb-w61.*`), letting the target be chosen by evidence rather than
  by picking the first idea. Confirmed `hb-w61.5` (the delivery v0.2.0 epic item) had already
  effectively shipped despite being open in beads — avoided re-planning already-done work.
- **5-agent adversarial plan review caught a real design flaw before code was written.** The
  skeptic agent's case for an explicit `GATED_PLUGINS` list over auto-discovery (auditability:
  a plugin silently gaining the gate should be a reviewed diff, not an implicit side effect)
  was the single highest-value finding of the whole session — it reshaped the design, not just
  polished prose.
- **The feasibility auditor caught a planning error grep should have caught.** My initial plan
  claimed `TestVerifyHookRuntimeControls` didn't exist; it already had 8 tests. My own grep
  during research stopped short of the file's later lines. Caught before an implementer wasted
  a cycle writing a shadowing duplicate class.
- **Wider-scope adversarial-review-code (deliver step 10) found something the narrower SDD
  final review missed.** The silent-failure-hunter's masking finding (a plugin failing the
  consistency check had its actual bypass commands hidden) was real and directly touched code
  this branch introduced — worth fixing even though the other two findings from the same pass
  turned out to be pre-existing, non-silent (crash still exits non-zero) issues.
- **Filing follow-ups as their own tracked beads, not just prose in a closed item's
  description**, made the "confirm deferred work isn't silently dropped" gate checkable rather
  than trust-based — `hb-w61.8`/`hb-w61.9` exist independently of `hb-w61.7`.

## Friction / bugs

- **Plan structure vs. SDD tooling contract.**
  - *What happened:* The approved plan used prose sections (Design / Files to modify /
    Verification), but `subagent-driven-development`'s `task-brief` script requires literal
    `## Task N` markdown headings to extract a brief.
  - *Root cause:* `deliver`'s plan-writer default (`superpowers:writing-plans` only, no bound
    project plan-writer for this repo) doesn't itself mandate task-numbered structure — that's
    an SDD-specific requirement discovered only when Phase B started.
  - *How caught:* Reading `task-brief`'s source before the first dispatch, rather than
    assuming the format would work.
  - *Fix:* Restructured the plan's actionable content into `## Task 1` / `## Task 2` in place
    (content unchanged, headings retrofitted) before dispatching.
  - *Rule:* When a plan will execute via `subagent-driven-development`, write it with `## Task
    N` headings from the start (Phase A step 3), not prose sections retrofitted after
    approval — check `task-brief`'s heading regex before Phase A, not at Phase B.

- **Severity calibration on cross-agent findings needs a controller check, not blind
  aggregation.** The silent-failure-hunter reported 2 of 3 findings as IMPORTANT for code paths
  that were pre-existing (present before this diff) and non-silent (an uncaught exception still
  exits non-zero, so CI still fails-closed). Accepting the severity label at face value would
  have over-scoped the fix pass.
  - *Root cause:* A reviewer agent scoped to "hunt silent failures" will flag any unguarded
    exception path regardless of whether the failure mode is actually silent (exit 0) or loud
    (crash, non-zero exit, still blocks CI).
  - *How caught:* Reading the actual pre-diff file content to confirm the pattern predated
    this change, and reasoning through Python's default exit behavior on an uncaught exception.
  - *Fix:* None needed — fixed anyway since it was cheap and widened the exposure surface
    (1 plugin scanned → 3), but the severity label itself was not taken as ground truth.
  - *Rule:* A CRITICAL/IMPORTANT finding's severity label is a reviewer's claim, not a verified
    fact — verify "does this actually produce a false-clean (exit 0) or just an uglier
    already-blocking failure" before deciding whether to fix now, defer, or downgrade.

## Concrete improvements

- **`hb-w61.8`** — retrofit the `run_with_flags` disable pattern onto the 5 ungated hook
  plugins (or formally document the two-tier design as intentional). Filed, open, P3.
- **`hb-w61.9`** — fix the copy-pasted `DISCIPLINE_HOOK_PROFILE` docstring line in
  `learning`/`stewardship`'s `hook_flags.py`. Filed, open, P4, cosmetic-only.
- **Consider a `deliver` plan-writer note** (or a workspace-level dimension file for
  `adversarial-review-plan`) flagging when a plan destined for `subagent-driven-development`
  lacks `## Task N` headings, so this gets caught during plan review instead of at Phase B
  dispatch time. Not filed as a bead — small enough to just remember for the next `deliver`
  run against this repo.
