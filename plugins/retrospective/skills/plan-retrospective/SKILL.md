---
name: plan-retrospective
description: Use after completing a plan to capture what worked, friction, and improvements. Writes retrospectives/done/<slug>.md and clears the pending marker at retrospectives/pending/<slug>.marker.
version: 0.2.0
dependencies: []
---

# Plan Retrospective

Write a retrospective immediately after a plan's execution is done — commit made, user satisfied. The retrospective lives at `retrospectives/done/<slug>.md` in the project root, committed to the repo so findings accumulate over time.

## When to use

Invoke `/plan-retrospective` as soon as the plan work is complete. A marker file in `retrospectives/pending/` signals an outstanding retro; the SessionStart hook (`session-start-retro-nag.sh`) reminds you if one was missed.

## Inputs

- **Plan slug** — the filename stem from `~/.claude/plans/<slug>.md`. Derive it from the pending marker if present: `ls retrospectives/pending/`.
- **Commit SHA** — the final commit that closed the plan work.

## Steps

1. Read `~/.claude/plans/<slug>.md` to recall the plan's goals and scope.
2. Use the template below to write `retrospectives/done/<slug>.md` at the **workspace root** (see [Workspace-root discovery](#workspace-root-discovery) below).
3. Delete `retrospectives/pending/<slug>.marker` once the done file is written.
4. Stage and commit the retro file (standalone commit, message: `docs(retro): Add retrospective for <slug>`).
5. If the workspace has a `.claude/commit-message-rules.yaml` **and** the `git@garrettmanley` plugin
   is installed, validate the retro commit with its `commit-message` validator (best-effort — skip
   this step if the git plugin is not available). Exit 0 = valid; a non-zero exit prints a diagnostic,
   so amend the commit before finishing.

## Template

```markdown
# Retrospective: <Plan Title>

**Plan:** `~/.claude/plans/<slug>.md`
**Commit:** `<SHA>` (`<commit message first line>`)
**Date:** <YYYY-MM-DD>

## Outcome

One paragraph: what changed, what was delivered.

## What worked

- Protocol, tool, or pattern name — one sentence on why it paid off.
- ...

## Friction / bugs

- **<Short name>**
  - *What happened:* ...
  - *Root cause:* ...
  - *How caught:* ...
  - *Fix:* ...
  - *Rule (if generalizable):* ...

## Concrete improvements

- **<Improvement>** — where it lives, status (done / pending / follow-up).
- ...
```

## Prose guidance

If the `docs` plugin is enabled, follow `/tech-writing`. Lead with outcomes, not process. Be specific — vague findings produce nothing actionable. The bugs section is the highest-value part: root cause + how caught + rule is the 3-part structure that actually prevents recurrence.

## Exit protocol

Once `retrospectives/done/<slug>.md` is written and committed, delete the marker. This clears the SessionStart nag.

```bash
rm retrospectives/pending/<slug>.marker
```

## Workspace-root discovery

Both hooks (`exit-plan-mode-marker.sh`, `session-start-retro-nag.sh`) and this skill resolve the workspace root with the helper at `scripts/find_workspace_root.sh`. It walks upward from `$PWD` looking for a `.claude/` directory — that marks the true Claude workspace root. Falls back to `git rev-parse --show-toplevel` for workspaces without `.claude/`.

This matters when Claude is `cd`'d into a nested code repository inside the workspace: `git rev-parse --show-toplevel` would return the nested repo's root and place retro files there, where they would fail CI. The `.claude/` walk finds the correct workspace root regardless of which git repo is currently active.

**Rule:** always invoke `/plan-retrospective` from the workspace root, not from a nested code repo directory. The hooks enforce the workspace root for marker placement automatically.

## Notes

- `retrospectives/done/` is committed. `retrospectives/pending/` should be gitignored — markers are per-machine and per-session, not shared state.
- If the pending marker doesn't exist (manually skipped or first retro), write the done file directly — the marker step is optional.
- For plans with agent sub-tasks, note which agent type produced friction and which produced clean output.

## Gitignore reminder

Add to `.gitignore` once when adopting this plugin:

```
retrospectives/pending/
```
