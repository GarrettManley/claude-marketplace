# aether@garrettmanley

Aether Engine TTRPG/narrative framework support for Claude Code. Packages the hooks, skills, and subagent that a Rust+TypeScript narrative engine project needs to stay disciplined: hash-chain ledger integrity, classifier regression catching, Rust/TS rebuild discipline, and engineering-grade documentation enforcement. Hooks use content-marker detection (`core/Cargo.toml` presence) to identify compatible repos, so the plugin is safe to enable globally — it stays silent everywhere else.

## Install

```
/plugin marketplace add garrettmanley/claude-marketplace
/plugin enable aether@garrettmanley
```

Or add directly to your project's `.claude/settings.local.json`:

```json
{
  "enabledPlugins": {
    "aether@garrettmanley": true
  }
}
```

## Components

### Skills

| Skill | Description |
|---|---|
| `aether-doc-cluster` | Before starting substantial work, walks a trigger taxonomy (spec / ADR / threat model / runbook / user guide / plan / retrospective) to determine which engineering docs must land in the same PR. |
| `aether-edit-checklist` | After a logical chunk of edits and before declaring done: walks the per-edit checklist (diagrams, JSDoc, eval, gameplay harness, TODO format, plan retrospective, final `npm run check`). |
| `aether-plan-writer` | Before writing a plan file under `docs/engineering/plans/`, enforces the three hook-validated rules: `#N` issue cite, `## Value Justification` block with exact regex format, and `## Retrospective` section. |
| `ledger-doctor` | Inspect and repair the SHA-256 hash-linked JSONL campaign ledger. Reports the first broken block, the safe truncation point, and guides the `--fix` truncation + combat-state cleanup sequence. |
| `eval-run` | Run the classifier golden eval suite (38 tests) against the local LLM runtime. Includes an Ollama preflight check that prevents false-green results when the runtime is down. |
| `value-justify` | Generate the exact-format `## Value Justification` block required by `plan_issue_check.py`. Accepts three numbers (`/value-justify <impact> <confidence> <effort>`), computes the score, and emits hook-passing markdown. |

### Hooks

| Hook | Event | Matcher | Behavior |
|---|---|---|---|
| `cd_core_guard.py` | PreToolUse | `Bash` | Blocks `cd core && cargo <subcommand>` commands that leak cwd into subsequent Bash calls. Recommends `--manifest-path` instead. Allows `cd core && cargo build` (documented first-build path). |
| `ledger_truncation_hook.py` | PreToolUse | `Bash` | Warns (blocks) when a Bash command truncates `history.jsonl` without clearing sibling `combat_state.json` / `snapshots/` files that the server loads on boot. |
| `classifier_eval_reminder.py` | PostToolUse | `Edit\|Write\|MultiEdit` | Reminds to run `npm run eval:classifier` after edits to `src/llm/classifier_prompt.ts`, `gemini.ts`, `ollama.ts`, or `schemas.ts`. Never blocks. |
| `gameplay_harness_reminder.py` | PostToolUse | `Edit\|Write\|MultiEdit` | Reminds to run `node scripts/run-gameplay-tests.mjs` after edits to DM-cycle or LLM-pipeline files (`src/dm.ts`, `src/bus.ts`, `src/server.ts`, `src/actor.ts`, `src/roll-proposal.ts`, `src/state-sync.ts`, and the classifier set). Never blocks. |
| `rust_rebuild_reminder.py` | PostToolUse | `Edit\|Write\|MultiEdit` | Reminds to rebuild and retest after edits to `core/src/*.rs`. Checks binary staleness (compares `core.exe` mtime to edited file mtime) and calls out stale-binary risk explicitly. Never blocks. |

All PostToolUse reminder hooks resolve the repo root by walking up to the nearest ancestor containing `core/Cargo.toml`. They no-op when the edited file is outside a matching repo.

### Agent

| Agent | Description |
|---|---|
| `classifier-regression-checker` | Specialist reviewer for classifier changes. Checks enum consistency across `schemas.ts`, `gemini.ts`, and `ollama.ts`; audits LOOK-preference block conflicts against golden tests; runs the eval suite; reports PASS/FAIL per dimension. |

## Usage

### Before starting substantial work

```
/aether:aether-doc-cluster
```

Walk the trigger taxonomy to determine which docs must accompany the PR (spec, ADR, threat model, runbook, user guide, plan, retrospective).

### Before committing

```
/aether:aether-edit-checklist
```

Steps through diagram regen, JSDoc, eval/harness gates, TODO citation, and `npm run check`.

### Writing a plan file

```
/aether:aether-plan-writer
```

Then, to generate the hook-validated Value Justification block:

```
/value-justify 4 5 8
```

This produces the exact `## Value Justification` format that `plan_issue_check.py` accepts.

### Inspecting a broken ledger

```
/aether:ledger-doctor
```

Provide the campaign ID. The skill runs `npx ts-node scripts/ledger-doctor.ts <campaign_id>` to scan the hash chain, identifies the first broken block and nearest prior snapshot, then optionally runs with `--fix` to back up and truncate.

### Running the classifier eval

```
/aether:eval-run
```

Verifies Ollama is reachable first, then runs the 38-test suite. Reports regressions by name, received type, and expected type.

### Reviewing classifier changes

The `classifier-regression-checker` agent triggers on changes to `src/llm/classifier_prompt.ts`, `src/llm/gemini.ts`, `src/llm/ollama.ts`, or `src/llm/schemas.ts`. It runs automatically via the `classifier_eval_reminder.py` hook reminder; invoke it directly when you want the full three-part review (enum check + LOOK-preference conflicts + eval run).

## Configuration

The hooks read no external config files and expose no env vars of their own. Repo detection is fully automatic via the `core/Cargo.toml` root marker — no path configuration required.

To disable the plugin's hooks without disabling the plugin itself, use `settings.local.json` hook overrides in the project. The hooks carry no profile or disable mechanism of their own (unlike `discipline@garrettmanley`).

The `eval-run` skill reads `OLLAMA_URL` (default `http://localhost:11434`) and `OLLAMA_CLASSIFIER_MODEL` (default `gemma3:4b`) from the environment.

```bash
# Override classifier model for the eval
OLLAMA_CLASSIFIER_MODEL=qwen2.5:7b /aether:eval-run
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Hooks fire in an unrelated repo that happens to have a `core/` directory | The Rust-rebuild and classifier/harness reminders require `core/Cargo.toml` to exist, not just a `core/` dir. The `cd_core_guard` is intentionally broader (it catches the same cwd-leak anti-pattern in any Rust project). No false-positive for non-Rust repos. |
| `eval-run` reports 0 tests or all passing after an Ollama outage | The eval silently skips when Ollama is unreachable. The skill includes a preflight `curl` check that stops execution before the eval runs. If the preflight passes but fewer than 38 tests run, Ollama disconnected mid-run — restart it and re-run. |
| `ledger_truncation_hook.py` fires on a `--body` string that mentions `history.jsonl` | The hook strips `--body`, `--message`, and `--comment` flag arguments before pattern-matching, so mentions inside flag values should not trigger. If it does fire, the command likely contains an unquoted path token that the strip regex missed — wrap the argument in quotes. |
| `plan_issue_check.py` rejects a plan's Value Justification block | The regex requires `**Field** (label): N`, not `**Field: N**`. Use `/value-justify` to emit a guaranteed-passing block, or check that asterisks close before the colon on each line. |

## Cross-platform notes

The hooks run under `python3` via `${CLAUDE_PLUGIN_ROOT}` resolution, which works on Windows, macOS, and Linux as long as Python 3 is on PATH. The Rust-rebuild reminder checks `core/target/release/core.exe` for staleness; on macOS/Linux the binary will be `core` (no `.exe`) and the staleness probe will hit an `OSError` and skip the stale-binary warning — the reminder message still fires. No other platform-specific behavior.

The plugin ships no `init.sh` / `init.ps1` — no scaffolding step is required.

## Migration from per-project hooks

If you have these hooks already in a project's `.claude/`:

1. Enable `aether@garrettmanley` in the project's `.claude/settings.local.json`.
2. Remove the migrated hooks (`cd_core_guard.py`, `ledger_truncation_hook.py`, `classifier_eval_reminder.py`, `gameplay_harness_reminder.py`, `rust_rebuild_reminder.py`) and their entries from `settings.local.json`.
3. Remove the migrated skills (`aether-doc-cluster`, `aether-edit-checklist`, `aether-plan-writer`, `ledger-doctor`, `eval-run`, `value-justify`) and the `classifier-regression-checker` agent.
4. Generic discipline hooks (`todo_issue_hook.py`, `plan_issue_check.py`, `frontmatter_lint.py`, etc.) are covered by `discipline@garrettmanley` — migrate those separately with a `.claude/discipline.local.md`.
5. Smoke-test: attempt a `cd core && cargo test` command and edit a classifier file to confirm the hooks fire.

The migration is opportunistic — do it when next working in the project, not as a one-shot rip-out.
