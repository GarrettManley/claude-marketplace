# retrospective@garrettmanley

Plan retrospective discipline: a self-contained cycle of marker-drop (on plan approval), session-start
reminders, a plan-completion pre-check, and a retro-authoring skill. Forces a structured pause after
every approved plan to capture what worked, what surprised you, and concrete improvements — before the
next plan starts. A completion gate verifies a plan is *actually done* before you retrospect it.

Intended for engineers who run Claude Code in plan mode and want learning to accumulate across plans
rather than evaporate between sessions.

## Install

```
/plugin marketplace add garrettmanley/claude-marketplace
/plugin install retrospective@garrettmanley
```

No init scripts. No further setup required beyond the one-time `.gitignore` entry described in
[Usage](#usage).

## Components

| Component | Type | Trigger / Purpose |
|-----------|------|-------------------|
| `exit-plan-mode-marker.sh` | PostToolUse hook (`ExitPlanMode`) | Drops a `.marker` file in `retrospectives/pending/` referencing the most recently approved plan. |
| `session-start-retro-nag.sh` | SessionStart hook | Lists outstanding pending markers at the start of every session. |
| `plan_completion_check.py` | SessionStart hook | Soft completion-gate nag: scans pending markers, runs completion checks against each plan, and lists any that are **not yet done**. Never blocks. |
| `plan-completion` | Skill | Pre-check before retrospecting — verifies a plan is actually complete (filled-in retro section, no unchecked tasks, addressed verification, tracker reference) and reports COMPLETE or a blocker list. Does **not** write the retro. |
| `plan-retrospective` | Skill | Authoring flow — reads the plan, writes `retrospectives/done/<slug>.md`, deletes the pending marker. |

The plugin registers **three hooks**: two `bash` commands with a **5-second timeout** and one Python
hook (`plan_completion_check.py`) invoked via `uv run --no-project` with a **15-second timeout** (see
`hooks/hooks.json`). The Python hook requires [`uv`](https://github.com/astral-sh/uv) on `PATH`; it is
pure stdlib otherwise. None of the hooks honor `*_HOOK_PROFILE` env vars or other disable frameworks —
enabling the plugin means the hooks are on. Failures are non-blocking; a hook error never interrupts
the session.

## Usage

### One-time project setup

Add to your project's `.gitignore` so per-machine markers are not committed:

```
retrospectives/pending/
```

`retrospectives/done/` stays tracked — that directory is where findings accumulate over time.

### Normal flow

```
ExitPlanMode → marker dropped in retrospectives/pending/<slug>.marker
            ↓
   (work happens, commits land)
            ↓
SessionStart → nag: "Outstanding retros: <slug>, ..."
            → completion nag: pending plans NOT yet complete (soft)
            ↓
   /plan-completion → COMPLETE? ──no──► fix blockers, re-run
            │ yes
            ↓
   /plan-retrospective → writes retrospectives/done/<slug>.md
                          deletes retrospectives/pending/<slug>.marker
```

### Verifying completion before retrospecting

Run `/plan-completion` once you think a plan is finished — **before**
`/plan-retrospective`:

```
/plan-completion [<plan-path>]
```

It pre-checks the plan (generic; works on any markdown plan) and reports either
`COMPLETE -> run /plan-retrospective` or a concrete blocker list:

1. A `## Retrospective` / `## Completion` section exists and is non-placeholder.
2. No unchecked task checkboxes (`- [ ]`) remain.
3. The `## Verification` section's criteria are addressed (no leftover TODO/TBD).
4. At least one issue/tracker reference is present (`#123`, `hb-9yw.4`, `bd-abc1`).

It **does not** write the retrospective or touch the marker — that stays
`/plan-retrospective`'s job. The same checks run automatically as the SessionStart
soft nag (`plan_completion_check.py`), which lists any pending plan that does not
yet pass. The check logic lives in `hooks/plan_completion_check.py` and is also
runnable directly:

```
uv run --no-project "${CLAUDE_PLUGIN_ROOT}/hooks/plan_completion_check.py" <plan-path>
```

### Running the skill

Invoke the skill after a plan's work is complete — commit made, user satisfied:

```
/plan-retrospective
```

The skill:

1. Reads `~/.claude/plans/<slug>.md` to recall the plan's goals and scope.
2. Derives the slug from the pending marker (`ls retrospectives/pending/`) or prompts for it.
3. Writes `retrospectives/done/<slug>.md` using the structured template below.
4. Deletes the pending marker.
5. Stages and commits the retro file with message `docs(retro): Add retrospective for <slug>`.
6. If `.claude/commit-message-rules.yaml` exists in the workspace, validates the commit message and
   prompts to amend before finishing.

### Retro template

```markdown
# Retrospective: <Plan Title>

**Plan:** `~/.claude/plans/<slug>.md`
**Commit:** `<SHA>` (`<commit message first line>`)
**Date:** <YYYY-MM-DD>

## Outcome

One paragraph: what changed, what was delivered.

## What worked

- Protocol, tool, or pattern name — one sentence on why it paid off.

## Friction / bugs

- **<Short name>**
  - *What happened:* ...
  - *Root cause:* ...
  - *How caught:* ...
  - *Fix:* ...
  - *Rule (if generalizable):* ...

## Concrete improvements

- **<Improvement>** — where it lives, status (done / pending / follow-up).
```

The bugs section is the highest-value part. Root cause + how caught + rule is the 3-part structure
that prevents recurrence rather than just logging the event.

If the `docs` plugin is enabled, follow `/tech-writing` when authoring prose. Lead with outcomes,
not process.

## Configuration

This plugin has no env vars or local config files. All behavior is unconditional once the plugin is
enabled.

The only per-project decision is the `.gitignore` entry above. Everything else — file paths,
directory names, commit message format — is fixed.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Markers are never dropped automatically after plan approval | The `ExitPlanMode` PostToolUse matcher may not fire in every Claude Code version. Invoke `/plan-retrospective` manually — the skill works without a marker. |
| `session-start-retro-nag.sh` exits with "cannot locate workspace root" | The hook could not find a `.claude/` directory walking upward from `$PWD`, and `git rev-parse --show-toplevel` also failed. Run Claude from inside a git repo or a directory with a `.claude/` folder. |
| `exit-plan-mode-marker.sh` dropped a marker with the wrong slug | If two plan files were modified within the same second, the hook may pick the wrong one (it takes the most recently modified `.md` under `~/.claude/plans/`). Delete the wrong marker and invoke `/plan-retrospective` with the correct slug. |
| Retro file lands in the wrong repo (nested project) | Invoke `/plan-retrospective` from the workspace root, not from a nested code repository. The hooks always resolve to the correct workspace root; the skill requires correct `$PWD`. |

## Workspace-root discovery

Both hooks and the skill resolve the workspace root with
`skills/plan-retrospective/scripts/find_workspace_root.sh`. The script walks upward from `$PWD`
looking for a `.claude/` directory — that marks the true Claude workspace root. Falls back to
`git rev-parse --show-toplevel` for workspaces without `.claude/`.

This matters when Claude is invoked from inside a nested code repository: `git rev-parse` would
return that repo's root and place retro files there (wrong). The `.claude/` walk finds the outer
workspace root regardless of which git repo is active.

## Cross-platform

The hooks are `bash` scripts and run on macOS and Linux without modification. On Windows they require
Git Bash, WSL, or another POSIX-compatible shell that Claude Code is configured to invoke for hook
commands. The skill itself is platform-agnostic (Claude handles the authoring steps).

## What this is not

- **Not session handoff.** The `discipline:session-handoff` skill and the `remember` flow write
  `.remember/remember.md` for state transfer between sessions. A retrospective is learning capture
  after a plan closes — not the same thing.
- **Not a work tracker.** Pending markers are reminders, not tasks. Track follow-up work in your
  issue tracker; record only findings in `retrospectives/done/`.
