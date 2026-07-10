# Adversarial Plan Review — hb-rap hook-error observability

**Plan:** `2026-07-09-hb-rap-hook-error-observability-plan.md`
**Posture:** FULL (6 dimensions + 3 archetypes), because Complexity scored HIGH (cross-plugin, vendored 3×, new cross-plugin JSONL contract) and Phase 0 was skipped.
**Date:** 2026-07-09
**Outcome: HALTED for a user approach-decision** — the review found 2 execution CRITICALs *and* a credible premise challenge (a materially simpler alternative). Resolution is a UX-policy fork that belongs to the user; not resolved unilaterally.

## CRITICAL — execution defects (apply to the log+briefing approach if kept)

- **Test pollution of the real signal** (feasibility + completeness, independently). Existing tests in all three suites (discipline `test_run_with_flags`, stewardship `test_run_with_flags` / `test_render_briefing`, learning `test_coverage_gaps::TestRunWithFlags`) exercise the two swallow points **without** setting `CLAUDE_MARKETPLACE_DATA_ROOT`; no `clean_env` fixture strips it. After landing, every `pytest` run appends synthetic `boom`/`oops` records into the developer's **real** `%LOCALAPPDATA%/claude-marketplace/hooks-errors.jsonl` — the file the live briefing reads. Fix: autouse isolation fixture pointing the root at `tmp_path` in **all** suites that hit the swallow points, not just the 2 new tests.
- **`release.py` bumps by commit SCOPE, not changed files** (feasibility-auditor + clarity + feasibility, `release.py:209` `c.scope == name`). A single `fix(discipline)` commit carrying learning's synced `run_with_flags` never bumps `learning`, so the installed learning copy — the one wrapping `surface.py`, the exact hook this fixes — stays old in the cache. Fix: split the vendored sync into per-plugin commits (`fix(discipline)` + `fix(learning): sync…` + `fix(stewardship): sync…`), each staging its own copy.

## CRITICAL — premise challenge

- **plan-skeptic: the `exit 0` swallow IS the invisibility; `return 1` is the ~2-line fix.** Changing `return 0` → `return 1` at the two swallow points (synced 3×) surfaces the already-printed stderr in-session with no log/env/resolver/briefing/second-plugin. **Verified** against Claude Code docs (`claude-code-guide`): exit 1 shows the first stderr line in the transcript as an error notice (not debug-only), is non-blocking, and does not break the hook chain. Only landmine (exit 2 blocks PreToolUse) is avoided by using 1. The plan asserted the "every-path-returns-0 contract" as sacred but never defended it against exit 1.

## IMPORTANT — over-build consensus (converging across agents)

- **Reuse `learning_data_root()` instead of a new `CLAUDE_MARKETPLACE_DATA_ROOT` env + second resolver** (value-justification, scope-cutter, feasibility-auditor). The marketplace root the plan "introduces" is literally the parent of the existing learning root; the new env var's only real justification is the writer's subprocess test seam.
- **Defer Task 2 (briefing) or justify shipping both** (scope-cut, scope-cutter): the bead says "implement ONE" of log/briefing/doctor; the plan does two + extras.
- **Drop the `derive_actions` rule** (scope-cut, scope-cutter): the `## Hook Errors` section already shows the count; the rule duplicates it and adds threading.
- **`no rotation` contradicts the motivating incident** (risk-rollback, scope-cut): surface.py erroring on *every* SessionStart for weeks falsifies "errors are rare" and echoes the hb-168 large-file/AV-rescan-tax lesson — an append-only log needs a cap, or the approach needs rethinking.
- **Unverified "the briefing is read" premise** (value-justification, plan-skeptic): the read-side depends on the user reading the nightly briefing; discipline's SessionStart-injection is an already-read channel.
- **Concurrent-write interleaving** (risk-rollback): ~20 hook spawns/tool-call appending one file with no lock.

## MINOR (verified, would fix under the log approach)

- `RUN_WITH_FLAGS` is actually named `WRAPPER` (test constant); `derive_actions` needs `len(hook_errors or [])` (a pre-existing test passes no `hook_errors` key); the token test must add `{{HOOK_ERRORS_SECTION}}` to its local template string (not just the sections dict) or it passes vacuously; README/env docs for the new section; the "two swallow points" framing omits a third (`script not found`).

## Disposition

The review's net signal: **the log+briefing subsystem is over-built for a P3**, and a verified, dramatically simpler alternative exists. Whether to surface hook errors **loudly/immediately (exit 1)** or **quietly/persistently (log+briefing)** is a UX policy for the user's own hook system. Halted at the plan gate to get that decision rather than execute a contested, over-built plan or unilaterally change hook-wide behavior.
