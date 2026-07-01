# discipline@garrettmanley

Generic dev hygiene for Claude Code: TODO+issue enforcement, frontmatter lint, plan validation (issue citation, value justification, retrospective), spec-code drift auditing, a fact-forcing edit gate, git-state checkpoint/snapshot tooling, and three skills (council, finish-and-push, session-handoff). Designed for solo or small-team repos where the agent should be held to the same standards as a human reviewer.

## Install

```
/plugin marketplace add garrettmanley/claude-marketplace
/plugin enable discipline@garrettmanley
```

## Components

### Skills

| Skill | Description |
|-------|-------------|
| `discipline:council` | Convene a four-voice council (Architect/Skeptic/Pragmatist/Critic) for ambiguous go/no-go decisions. Anti-anchoring: the three external voices launch as fresh subagents with only the question, not the full conversation. |
| `discipline:finish-and-push` | Close out a feature branch: fetch, rebase onto main, recheck gates, subagent code review, user sign-off, FF-merge, push, delete branch, prune worktree. User-invocable only (`disable-model-invocation: true`). |
| `discipline:session-handoff` | Write a thorough 8-section end-of-session handoff to `.remember/remember.md`. The heavyweight authoring depth for the same auto-injected file that `remember` writes lightly — reach for it on high-stakes handoffs. |
| `discipline:compact-plan` | Mid-task guided compaction: save an intent note + emit a /compact preservation command; live workflow state re-injects automatically. |

### Commands

| Command | Description |
|---------|-------------|
| `/discipline:checkpoint` | Create, verify, or list git-state checkpoints with delta reporting (files changed, lines +/-, live test pass-count). State lives in `.claude/checkpoints.log`. |

### Agents

| Agent | File | Description |
|-------|------|-------------|
| `spec-code-drift-checker` | `agents/spec-code-drift-checker.agent.md` | Audits a spec doc for drift between cited symbols (file paths, functions, struct fields, response keys, phase labels) and the current codebase. Read-only; uses `Grep`, `Read`, `Glob`. |

### Hooks

| Hook | Type | Default profile | Description |
|------|------|-----------------|-------------|
| `todo_issue_hook.py` | PreToolUse (Edit/Write/MultiEdit) | standard, strict | Blocks bare `TODO`/`FIXME`/`XXX`/`HACK` and informal labels (`heuristic`, `workaround`, `band-aid`) added to source files without a `#NNN` GitHub issue reference. |
| `plan_issue_check.py` | PostToolUse (Write/Edit/MultiEdit) | standard, strict | Validates dated plan files: must cite a GitHub `#N` or a beads id; completed plans need a `Closes/Updates/Follows up` line in the retrospective; optionally auto-closes via `gh`/`bd`. |
| `memory_tracker_check.py` | PostToolUse (Write/Edit/MultiEdit) | standard, strict | Warns (never blocks) when a `type: project` auto-memory file under `.claude/projects/*/memory/` cites no tracker id — beads `hb-`/`bd-` or GitHub `#N`. `MEMORY.md` index and non-`project` types are exempt. |
| `frontmatter_lint.py` | PostToolUse (Write/Edit/MultiEdit) | standard, strict | Validates YAML frontmatter fields on docs matching a configured pattern (off until `require-frontmatter-fields` is set). |
| `spec_companion_check.py` | PostToolUse (Write only) | strict | On new spec docs, enforces issue refs and required sections (`## Goal`, `## Acceptance`); warns on missing companion docs (threat model, runbook, user guide) and missing companion plans. |
| `pitfalls_pointer.py` | PostToolUse (Edit/Write/MultiEdit) | standard, strict | Prints a pointer to an area-specific pitfalls doc when you edit a file in a configured tracked area (off until `pitfalls-routes` is set). |
| `gateguard.py` | PreToolUse (Edit/Write/MultiEdit + Bash) | edit gate: strict; bash gate: standard, strict | Denies the first edit per code file per session until the agent presents investigation facts (importers, public API, schemas, current instruction quoted verbatim). Prose files exempt; `CLAUDE.md`/`AGENTS.md`/`GEMINI.md` stay gated. Also gates destructive Bash (`rm -rf`, `git push --force`, `drop table`, `dd if=`). The edit gate is strict-only as of v0.7.1; the destructive-Bash gate fires under both `standard` and `strict`. |
| `pre_compact_snapshot.py` | PreCompact | standard, strict | Writes a filesystem-state snapshot (branch, HEAD SHA, top-10 recently-modified files) before conversation compaction. |
| `inject_issues.sh` | SessionStart | minimal, standard, strict | Injects open GitHub issues into `additionalContext` when `gh` is on PATH and `origin` resolves to a GitHub repo. |
| `inject_branch_state.sh` | SessionStart | minimal, standard, strict | Warns about stale/unmerged/unpushed branches at session open. |
| `session_resume_context.py` | SessionStart | standard, strict | Reads the latest pre-compact snapshot back at session open and emits it as `additionalContext`. Also renders live workflow state (active plan via SDD ledger or pending retro marker, checkbox progress, pending retros) and the compact-plan intent note (4-hour TTL). |

## Init / Setup

The plugin ships `scripts/init.sh` (Linux/macOS) and `scripts/init.ps1` (Windows, requires PowerShell 7+). Both are idempotent — they copy `examples/discipline.local.md` to `.claude/discipline.local.md` in the current directory and exit 0 if the file already exists.

**Linux/macOS:**

```bash
bash "$(claude plugin path discipline@garrettmanley)/scripts/init.sh"
```

**Windows (PowerShell 7+):**

```powershell
& "$(claude plugin path discipline@garrettmanley)\scripts\init.ps1"
```

Options:

| Flag | Behavior |
|------|----------|
| `--force` / `-Force` | Overwrite an existing `.claude/discipline.local.md` |
| `--quiet` / `-Quiet` | Suppress all output |

The init scripts create `.claude/` if absent, then write the config file. Edit it to enable opt-in features (frontmatter lint, pitfalls pointer, value justification) before the hooks that read them will fire.

## Usage

### Checkpoint a stable point mid-work

```
/discipline:checkpoint create feature-start
/discipline:checkpoint verify
/discipline:checkpoint list
/discipline:checkpoint clear
```

State is recorded in `.claude/checkpoints.log` in the repo root. Verify compares the recorded SHA to `HEAD` and runs the project's test command live.

### Council for ambiguous decisions

```
/discipline:council
```

Invoke when multiple credible paths exist and no obvious winner. Supply the decision question; the skill extracts necessary context, forms its Architect position, dispatches Skeptic/Pragmatist/Critic as parallel subagents, and synthesizes a verdict.

### Session handoff before closing

```
/discipline:session-handoff
```

Writes the 8-section schema to `.remember/remember.md`. The file auto-injects at the next SessionStart so the resumed session picks up with zero re-reading. Use `remember` instead for quick lightweight breadcrumbs.

### Finishing a feature branch

```
/discipline:finish-and-push
```

User-invocable only. Runs rebase → recheck → code review → user sign-off gate → FF-merge → push → branch delete → worktree prune. Does not proceed past any failed gate without an explicit user decision.

### Spec drift audit

Invoke the agent directly with a spec file path:

```
Run the spec-code-drift-checker agent on docs/engineering/specs/001-my-feature.md
```

The agent checks file-path citations, symbol references, response-shape claims, pitfall/decision labels, and phase sub-references, then reports `DRIFT DETECTED` or `No drift detected`.

## Configuration

### Per-project config file

Drop `.claude/discipline.local.md` at the project root to override defaults (run `init.sh`/`init.ps1` to scaffold it):

```markdown
---
repo: your-org/your-repo
main-branch: master
source-extensions: .ts, .tsx, .rs
spec-pattern: ^docs/engineering/\d{3}-[\w-]+\.md$
plan-pattern: ^docs/engineering/plans/\d{4}-\d{2}-\d{2}-.+\.md$
require-value-justification: true
require-frontmatter-fields: status, author, created, diataxis
frontmatter-skip-prefixes: docs/templates/, docs/superpowers/
pitfalls-root: docs/engineering/pitfalls
pitfalls-routes: src/dm.ts=dm-cycle; src/llm/=llm-classifier
inject-issues: true
inject-branch-state: true
---
```

### Environment variables

All config file settings have env var equivalents (highest priority):

| Variable | Maps to |
|----------|---------|
| `DISCIPLINE_REPO` | `repo` |
| `DISCIPLINE_MAIN_BRANCH` | `main-branch` |
| `DISCIPLINE_SOURCE_EXTENSIONS` | `source-extensions` (comma-separated) |
| `DISCIPLINE_SPEC_PATTERN` | `spec-pattern` |
| `DISCIPLINE_PLAN_PATTERN` | `plan-pattern` |
| `DISCIPLINE_REQUIRE_VALUE_JUSTIFICATION` | `require-value-justification` |
| `DISCIPLINE_REQUIRE_FRONTMATTER_FIELDS` | `require-frontmatter-fields` |
| `DISCIPLINE_FRONTMATTER_SKIP_PREFIXES` | `frontmatter-skip-prefixes` |
| `DISCIPLINE_PITFALLS_ROOT` | `pitfalls-root` |
| `DISCIPLINE_PITFALLS_ROUTES` | `pitfalls-routes` |
| `DISCIPLINE_INJECT_ISSUES` | `inject-issues` (true/false) |
| `DISCIPLINE_INJECT_BRANCH_STATE` | `inject-branch-state` (true/false) |

### Hook profiles

`DISCIPLINE_HOOK_PROFILE` selects which hooks fire. Values: `minimal` | `standard` (default) | `strict`.

| Hook id | minimal | standard | strict |
|---------|---------|----------|--------|
| `discipline:session-start:inject-issues` | ✓ | ✓ | ✓ |
| `discipline:session-start:inject-branch-state` | ✓ | ✓ | ✓ |
| `discipline:pre-edit:todo-issue` | | ✓ | ✓ |
| `discipline:post-edit:plan-issue-check` | | ✓ | ✓ |
| `discipline:post-edit:memory-tracker-check` | | ✓ | ✓ |
| `discipline:post-edit:frontmatter-lint` | | ✓ | ✓ |
| `discipline:post-edit:pitfalls-pointer` | | ✓ | ✓ |
| `discipline:pre-edit:gateguard-fact-force` | | | ✓ |
| `discipline:pre-bash:gateguard-fact-force` | | ✓ | ✓ |
| `discipline:pre-compact:snapshot` | | ✓ | ✓ |
| `discipline:session-start:resume-context` | | ✓ | ✓ |
| `discipline:post-write:spec-companion-check` | | | ✓ |

### Disabling individual hooks

```bash
# Disable the TODO check for one session
DISCIPLINE_DISABLED_HOOKS=discipline:pre-edit:todo-issue claude

# Run with only SessionStart injections; skip all edit-time discipline
DISCIPLINE_HOOK_PROFILE=minimal claude

# Maximum strictness (includes spec-companion-check)
DISCIPLINE_HOOK_PROFILE=strict claude

# Disable two specific hooks
DISCIPLINE_DISABLED_HOOKS=discipline:post-edit:pitfalls-pointer,discipline:post-edit:frontmatter-lint claude
```

`DISCIPLINE_DISABLED_HOOKS` accepts a comma-separated list of hook ids (case-insensitive, whitespace trimmed). A disabled hook exits 0 silently — the hook chain continues.

### Gateguard-specific controls

```bash
# Disable both gateguard hooks at once
export DISCIPLINE_GATEGUARD=off

# Disable only the file gate (keep destructive-Bash gate)
export DISCIPLINE_DISABLED_HOOKS=discipline:pre-edit:gateguard-fact-force

# Override state directory (useful in tests)
export GATEGUARD_STATE_DIR=/path/to/state
```

Gateguard session state lives at `~/.claude/discipline/gateguard/state-<session-key>.json` with a 30-minute inactivity TTL.

### Snapshot storage

Pre-compact snapshots are stored at `~/.claude/discipline/snapshots/<project-key>.json` (one file per project, latest overwrites). Override with `DISCIPLINE_SNAPSHOT_DIR`. The compact-plan skill additionally writes `<root-key>.note.json` into the snapshot directory — a `{text, timestamp}` intent note with a 4-hour TTL, keyed by the resolved project root (deliberately not the snapshot's own project key, so hook and CLI contexts converge); expired or malformed notes are ignored.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `todo_issue_hook.py` blocks a file type you don't want gated | Set `DISCIPLINE_SOURCE_EXTENSIONS` (or `source-extensions` in `.claude/discipline.local.md`) to only the extensions you care about. |
| Gateguard fires on every `.md` edit | Prose files (`.md`, `.txt`, `.rst`) are exempt by default — check that the file doesn't have the `.md` extension on one of the behavior-bearing config trio (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`), which stay gated intentionally. |
| Plan check fails with "no tracker id" on a file you didn't intend as a plan | The default plan pattern matches `docs/**/plans/YYYY-MM-DD-*.md` and `.claude/plans/**`. Set a narrower `plan-pattern` in `.claude/discipline.local.md` if your layout differs. |
| `inject_issues.sh` produces nothing | Confirm `uv` and `gh` are on PATH, `gh` is authenticated (`gh auth status`), and `git remote get-url origin` resolves to a GitHub repo. The hook is a no-op when any condition is false (the Python helper runs via `uv run --no-project`, so missing `uv` silently disables it). |

## Cross-platform

- `init.sh` requires Bash; `init.ps1` requires PowerShell 7+ (`pwsh`). Both are functionally equivalent — run whichever matches your shell.
- `inject_issues.sh` and `inject_branch_state.sh` are Bash scripts. On Windows they run under Git Bash (bundled with Git for Windows) or WSL. No PowerShell equivalent is needed because Claude Code's hook runner invokes them via the system shell. `inject_issues.sh` runs its Python helper through `uv run --no-project` (matching the rest of `hooks.json`), so it needs `uv` on PATH rather than a bare `python3` — the latter is absent on a stock Windows + Git Bash install. `inject_branch_state.sh` is pure Bash + git and needs only `gh`.
- Gateguard worktree cleanup uses a PowerShell fallback (`Remove-Item -Recurse -Force`) when `git worktree remove` fails with a permission error on Windows.
- Path separators in `.claude/discipline.local.md` values should use forward slashes; the config reader normalizes them on Windows.

## Migration notes

**0.1.0 → 0.2.0:** `spec-companion-check` moved to `strict` profile only. Set `DISCIPLINE_HOOK_PROFILE=strict` to restore the prior behavior.

**0.2.0 → 0.3.0:** Adds `gateguard`. Originally default-on under `standard`; the edit gate was later narrowed to `strict` only (see the 0.7.0 → 0.7.1 note). To opt out entirely: `DISCIPLINE_HOOK_PROFILE=minimal` or add both gateguard ids to `DISCIPLINE_DISABLED_HOOKS`.

**0.3.0 → 0.4.0:** Adds `pre-compact:snapshot` + `session-start:resume-context` (default-on under `standard`). Disable via `DISCIPLINE_HOOK_PROFILE=minimal` or the hook ids.

**0.5.0 → 0.6.0:** Gateguard file gate narrowed to code files — prose (`.md`/`.txt`/`.rst`) is now exempt except `CLAUDE.md`/`AGENTS.md`/`GEMINI.md`. Routine-Bash gate removed entirely. Destructive-Bash detection unchanged.

**0.7.0 → 0.7.1:** Gateguard edit gate narrowed to the `strict` profile only (`discipline:pre-edit:gateguard-fact-force` no longer fires under `standard`). The destructive-Bash gate (`discipline:pre-bash:gateguard-fact-force`) still fires under both `standard` and `strict`. To restore the fact-forcing edit gate, run with `DISCIPLINE_HOOK_PROFILE=strict`.

**1.1.0 → 1.2.0:** Adds the `compact-plan` skill, live workflow-state rendering in resume context, and the intent-note sidecar. No hooks.json changes; no action needed.

If you previously maintained these hooks at the project level:

1. Enable `discipline@garrettmanley` in `.claude/settings.local.json`.
2. Add `.claude/discipline.local.md` with project-specific overrides.
3. Remove the migrated `.claude/hooks/*.py` files and their hook bindings from `settings.local.json`.
4. Verify gating still fires by attempting a known violation in a throwaway file.
