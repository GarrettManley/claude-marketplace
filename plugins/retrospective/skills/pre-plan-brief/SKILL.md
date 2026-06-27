---
name: pre-plan-brief
description: Use BEFORE planning or brainstorming work in an area that has prior retrospectives — surfaces the matching findings (friction, bugs, concrete improvements) from retrospectives/done/ so a known issue does not silently recur in the new plan. Run it at the start of planning, not after.
version: 0.1.0
dependencies: []
---

# Pre-Plan Brief

A retro finding only pays off if it is read *before* the next similar plan. The
SessionStart nag and the accumulated `retrospectives/done/` files do not enforce
that — a finding captured one cycle silently recurs the next because nobody
re-reads the relevant retros while planning. This skill closes that gap: given an
area, it pulls the matching findings from every past retro and puts them in front
of you before you commit to an approach.

## When to use

Run it at the **start** of planning or brainstorming any non-trivial work in an
area that plausibly has history — a plugin, a subsystem, a recurring kind of task
(releases, CI gates, hooks). Especially valuable right before `superpowers:brainstorming`
or `superpowers:writing-plans`.

## How to run

From the workspace root:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/retro_brief.py" "<area-or-keywords>"
```

The `<area>` is one or more keywords — a plugin name (`learning`, `review`), a
subsystem (`release`, `commands lint`), or a theme (`squash tag orphan`). Matching
is recall-biased: a finding is shown when any meaningful keyword appears in its
text or its retro's slug. If the brief looks noisy, narrow the term; if it looks
empty, broaden it.

## How it works

- Resolves the workspace root by walking up for a `.claude/` directory (falling
  back to the git toplevel), the same way the plan-retrospective hooks do — so it
  reads the *workspace's* retros, not a nested code repo's.
- Scans `retrospectives/done/*.md` and extracts bullet items from the
  findings-bearing sections: **Friction / bugs**, **Concrete improvements**, and
  **What worked**.
- Prints the matches grouped by retro, each tagged with its section and a short
  lead, so you can open the source retro for the full root-cause / rule detail.

## How to act on it

Treat each surfaced finding as a question for the new plan: *has this been
addressed, or am I about to repeat it?* Fold the still-open ones into the plan's
scope or its risks. An empty brief is also a signal — you are planning in
genuinely new territory, or the area term was too narrow.

## Notes

- Pure stdlib, self-contained; no cross-plugin imports.
- Read-only: it never writes, so it is safe to run at any point.
