---
name: compact-plan
description: Use when conversation context is nearly full mid-task and the work is governed by a plan, SDD ledger, or delivery run — saves a short intent note to disk and emits a ready-to-paste /compact command with targeted preservation instructions, so the post-compaction session resumes with plan position intact. Not for end-of-session handoffs (use session-handoff) or lightweight breadcrumbs.
version: 0.1.0
dependencies: []
---

# Compact with a Plan

`/compact <instructions>` is user-typed only — no skill or hook can invoke it, and
PreCompact hooks cannot inject text into the summarizer. What CAN be controlled is
(a) what durable state exists on disk and (b) the instruction text the user pastes.
This skill prepares both halves. Plan position, ledger progress, and pending retros
need no saving at all: the discipline SessionStart hook rediscovers them live from
the filesystem after every compaction (manual or auto) and re-injects them. The one
thing the filesystem cannot rediscover is your conversational intent — that is the
note this skill saves.

## When to use

- Mid-task, context pressure building, and the work is governed by a plan file,
  an SDD ledger, or a delivery lifecycle run.
- Before a large exploratory phase (broad code reading, long tool loops) that you
  expect to trigger auto-compaction. The note survives 4 hours; exploration longer
  than that outlives it — re-run the skill to refresh.

Not for: end-of-session handoffs (`discipline:session-handoff` owns the
cross-session `.remember` channel — clobbering it mid-task would destroy the real
handoff) or quick breadcrumbs for a future session.

## Workflow

1. **Save the note** (deterministic — run, don't paraphrase):

   ```
   uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/compact_plan_state.py" --note "<one line: current task + exact next step>"
   ```

   The `--note` line is the single highest-value thing to write: it is the only
   piece of conversation state the filesystem cannot rediscover. Run the command
   from the project root — the note is keyed by the repository the command runs
   in.

2. **Read the digest.** The script prints the discovered active plan, ledger, and
   pending retros. If it printed `no workflow state discovered`, proceed with
   conversation knowledge only.

3. **Read the active plan file** named in the digest and identify the current
   phase/task from its checkboxes.

4. **Emit the paste-ready command** in a fenced block, filled from steps 1-3:

   ```
   /compact Preserve verbatim: (1) the active plan <path> and its current
   position <task/phase>; (2) the exact next step: <step>; (3) decisions made
   this session: <list>; (4) approaches that failed and must not be retried:
   <list>; (5) git branch <branch> @ <short-sha>. Summarize away exploratory
   file reads, resolved errors, and stale tool output.
   ```

5. **Tell the user:** paste the command to compact now; whether compaction is
   manual or automatic, the discipline SessionStart hook re-injects the live
   workflow state and the note afterward.

## What survives compaction, and how

| State | Mechanism |
|---|---|
| Active plan path + checkbox progress | Rediscovered live at every session start (nothing saved) |
| Pending retro markers | Rediscovered live at every session start |
| Your `--note` intent line | Note sidecar, 4-hour TTL, rendered with its timestamp |
| Git branch / HEAD / recent files | Existing PreCompact snapshot (unchanged) |
| Conversation nuance (decisions, failed approaches) | Only via the /compact instruction text — step 4 |

## Related

- `discipline:session-handoff` — end-of-session capture (richer, human-authored,
  different channel and lifetime).
- The discipline snapshot scripts and PreCompact hook — the git-state half of
  resume context; this skill is the mid-task front door for the workflow half.
