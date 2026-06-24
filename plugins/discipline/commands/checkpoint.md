---
description: Create, verify, or list git-state checkpoints with delta reporting (files changed, lines +/-, live test pass-count). Use to mark stable points mid-work so you can compare current state to a known-good baseline.
---

> Adapted from `affaan-m/everything-claude-code` at commit [`4774946d`](https://github.com/affaan-m/everything-claude-code/blob/4774946db57a072f9b878f233a80f2ec6f5ac342/commands/checkpoint.md) (MIT licensed). State lives at project-local `.claude/checkpoints.log`; no backing JS lifted.

# Checkpoint

Create or verify a git-state checkpoint in the current project.

## Usage

```
/discipline:checkpoint create <name>             # mark current state as checkpoint <name>
/discipline:checkpoint verify [<name>]           # compare current state to checkpoint (default: latest)
/discipline:checkpoint list                      # show all checkpoints
/discipline:checkpoint clear                     # remove old checkpoints (keep last 5)
```

State file: `.claude/checkpoints.log` in the current project's repo root (or working directory if not in a repo).

## create <name>

When asked to create a checkpoint named `<name>`:

1. Ensure `.claude/` exists in the repo root:
   ```bash
   mkdir -p .claude
   ```
2. Capture current state:
   ```bash
   TIMESTAMP=$(date +%Y-%m-%d-%H:%M)
   SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "no-git")
   DIRTY=$(git status --porcelain 2>/dev/null | wc -l)
   ```
3. (No test pass-count or coverage is stored in the log. Those are computed live during `verify` instead — see below.)
4. Append a line to `.claude/checkpoints.log`:
   ```bash
   echo "$TIMESTAMP | <name> | $SHA | dirty=$DIRTY" >> .claude/checkpoints.log
   ```
5. Report:
   ```
   Checkpoint created: <name>
   Timestamp: $TIMESTAMP
   SHA: $SHA
   Working tree: <clean | $DIRTY uncommitted change(s)>
   ```

## verify [<name>]

When asked to verify against a checkpoint (default: latest entry in `.claude/checkpoints.log`):

1. Read `.claude/checkpoints.log`. If missing or empty, report:
   ```
   No checkpoints found in .claude/checkpoints.log.
   Run /discipline:checkpoint create <name> first.
   ```
   and stop.
2. Find the target checkpoint:
   - Default: latest entry in the log
   - With `<name>` argument: exact-match by name; if multiple entries share the name, use the most recent one
3. Compare current state to the checkpoint:
   - `git diff --stat <checkpoint-sha>..HEAD` — files changed
   - `git diff <checkpoint-sha>..HEAD --shortstat` — lines added/removed
   - If a test command is available: run it once and capture current pass-count
4. Report in this exact format:
   ```
   CHECKPOINT COMPARISON: <name>
   ============================
   Checkpoint SHA: <sha>     ($TIMESTAMP)
   Current SHA:    <sha>     ($(date +%Y-%m-%d-%H:%M))

   Files changed: <N>
   Lines: +<X> / -<Y>
   Tests: <current pass-count> (run live; no baseline stored)
   Working tree: <clean | $DIRTY uncommitted change(s)>
   ```

## list

Read `.claude/checkpoints.log` and print one row per checkpoint:

```
2026-05-15-09:30 | feature-start    | a1b2c3d | dirty=0
2026-05-15-10:45 | core-done        | e4f5g6h | dirty=2
2026-05-15-11:20 | tests-passing    | i7j8k9l | dirty=0
```

If file missing or empty: "No checkpoints recorded for this project."

## clear

Keep the last 5 checkpoint lines, archive the rest:

```bash
if [ -f .claude/checkpoints.log ]; then
  total=$(wc -l < .claude/checkpoints.log)
  if [ "$total" -gt 5 ]; then
    keep=$(tail -n 5 .claude/checkpoints.log)
    mv .claude/checkpoints.log .claude/checkpoints.log.$(date +%Y%m%d-%H%M%S).archive
    echo "$keep" > .claude/checkpoints.log
    echo "Kept last 5 checkpoints. Older entries archived."
  else
    echo "Only $total checkpoints; nothing to clear."
  fi
else
  echo "No checkpoints.log to clear."
fi
```

## Typical Workflow

```
[Start of feature]   /discipline:checkpoint create feature-start
       │
[Implement core]     /discipline:checkpoint create core-done
       │
[Run tests]          /discipline:checkpoint verify core-done
       │
[Refactor]           /discipline:checkpoint create refactor-done
       │
[Pre-PR]             /discipline:checkpoint verify feature-start
```

## Notes

- Checkpoints are project-local (`.claude/checkpoints.log` lives in the repo). Different projects have independent histories.
- The log file is plain text; safe to commit OR gitignore depending on project preference. This marketplace gitignores `.claude/` by convention; for repos that gitignore it, checkpoints are private to the developer.
- This command does **not** snapshot working-tree state (no `git stash`). It records the SHA + dirty count and reports deltas. If you want to snapshot uncommitted changes, run `git stash push -m "checkpoint:<name>"` separately.
- Test pass-count and coverage are best-effort. If no test command is configured for the project, those fields are omitted from the report rather than inventing values.
