---
name: plan-completion
description: Use when you think a plan is finished, BEFORE running /plan-retrospective, to verify it is actually complete — checks for a filled-in completion section, no unchecked tasks, addressed verification criteria, and a tracker reference. Reports COMPLETE or a concrete blocker list. Does NOT write the retro.
version: 0.1.0
dependencies: []
---

# Plan Completion

A pre-flight gate that answers one question before you retrospect: **is this plan
actually done?** Run it the moment you believe a plan's work is finished. If it
passes, proceed to `/plan-retrospective`; if not, it hands you a concrete list of
what's still open.

This skill **does not write the retrospective** — that is `/plan-retrospective`'s
job. It only verifies readiness, so the retro captures a genuinely-closed plan
rather than one with half-ticked checkboxes.

## When to use

- You just finished executing a plan and are about to `/plan-retrospective`.
- A SessionStart nag (`plan_completion_check.py`) flagged a pending plan as not
  yet passing completion checks, and you want the full blocker list.

## Interface

```
/plan-completion [<plan-path>]
```

- **`<plan-path>`** — path to the markdown plan. Optional.
- **Default resolution** when omitted:
  1. If `retrospectives/pending/*.marker` exists, read the marker's first line for
     the recorded plan path (fall back to `~/.claude/plans/<slug>.md`).
  2. Otherwise pick the most recent `~/.claude/plans/*.md`.

## Checks (generic — works on any markdown plan)

The same logic the skill applies lives in
[`hooks/plan_completion_check.py`](../../hooks/plan_completion_check.py) as
`check_plan(path) -> CompletionReport`. You can run it directly against a plan:

```bash
uv run --no-project "${CLAUDE_PLUGIN_ROOT}/hooks/plan_completion_check.py" <plan-path>
```

With no argument it runs in SessionStart-nag mode instead (scans pending markers).

The four checks (a blocker is reported when a check fails):

1. **Completion section present + real.** A `## Retrospective` (or `## Completion`
   / `## Done`) section exists and is non-placeholder — not empty, not just
   `TODO`/`TBD`/`<...>`.
2. **No unchecked tasks.** No `- [ ]` (or `* [ ]` / `+ [ ]`) checkboxes remain.
   Every task is ticked, or dropped tasks are removed.
3. **Verification addressed.** If the plan has a `## Verification` section, its
   criteria are resolved — no leftover `TODO`/`TBD`/placeholder markers. (A plan
   with no Verification section is not blocked on this.)
4. **Tracker reference present.** At least one issue/tracker reference exists
   (`#123`, or a beads id like `hb-9yw.4` / `bd-abc1`), tying the plan to tracked
   work.

## Steps

1. Resolve the plan path (argument, pending marker, or most-recent plan).
2. Read the plan and run the four checks. The cheapest way is to call the module:

   ```bash
   uv run --no-project "${CLAUDE_PLUGIN_ROOT}/hooks/plan_completion_check.py" <plan-path>
   ```

   or, in-process, import `check_plan` and read `report.verdict()`.
3. Emit one of:
   - **`COMPLETE -> run /plan-retrospective`** — the plan passes; proceed.
   - **A blocker list** — one line per failed check, each with a concrete fix
     ("3 unchecked tasks remain", "Verification section still contains TODO", …).
4. **Do not** write `retrospectives/done/…` or touch the pending marker. Stop
   here and let the user run `/plan-retrospective` once the blockers clear.

## Output shape

```
COMPLETE -> run /plan-retrospective  (~/.claude/plans/ship-widget.md)
```

or

```
INCOMPLETE (~/.claude/plans/ship-widget.md) — 2 blocker(s):
  - 1 unchecked task remains (`- [ ]`). Tick every checkbox, or remove tasks that were dropped.
  - The Verification section still contains TODO/TBD/placeholder markers. Resolve them.
```

## Relationship to the rest of the plugin

```
ExitPlanMode → retrospectives/pending/<slug>.marker  (exit-plan-mode-marker.sh)
            ↓
   (work happens, commits land)
            ↓
SessionStart → soft nag if a pending plan fails completion checks  (plan_completion_check.py)
            ↓
   /plan-completion → COMPLETE? ──no──► fix blockers, re-run
            │ yes
            ▼
   /plan-retrospective → writes retrospectives/done/<slug>.md, clears marker
```

`plan-completion` runs **before** `plan-retrospective` and never mutates state.

## Workspace-root discovery

The hook resolves the workspace root the same way the rest of the plugin does:
walk upward from the current directory for a `.claude/` directory; fall back to
`git rev-parse --show-toplevel`. This keeps pending-marker scanning consistent
with `exit-plan-mode-marker.sh` and `session-start-retro-nag.sh` even when Claude
is `cd`'d into a nested code repo. Run `/plan-completion` from the workspace root.

## Notes

- **Soft by design.** Neither this skill nor its companion hook ever hard-blocks.
  The checks are advisory — they surface what's open so you don't retrospect a
  half-finished plan.
- **Generic.** The checks make no assumptions about a specific plan template; they
  key off standard markdown structure (headings, task boxes) and tracker syntax.
- Self-contained: the module is pure stdlib and imports nothing from other
  plugins, so the plugin stays independently installable.
