---
name: marketplace-setup
description: Use when setting up this marketplace on a new machine, when a plugin reports missing machine/user config, or when the user asks to initialize/configure/bootstrap the garrettmanley plugins. Detects which enabled plugins are missing per-machine config, runs the right init (or the root setup script), and reports a config-status summary.
version: 0.1.0
dependencies: []
---

# Marketplace Setup

Brings a freshly installed `garrettmanley` marketplace to a working state by running each plugin's machine/user initializer, idempotently. Most plugins work the moment they're enabled; a few need a one-time per-machine step (a generated key, a context template, a scheduled task). This skill finds those, runs the right initializer, and reports what changed.

## When to use

- Setting up the marketplace on a **new machine** for the first time.
- A plugin **reports missing config** (e.g. evidence can't find its override key, orchestration has no `tiers.local.json`, stewardship's nightly task isn't registered).
- The user asks to **initialize / configure / bootstrap / re-scaffold** the plugins.
- After a `--force` re-install where local config may need regenerating.

## Which plugins need per-machine init

These five ship a `scripts/init.sh` + `scripts/init.ps1` under the same contract:

| Plugin | What its init configures | Scope |
| --- | --- | --- |
| `evidence` | HMAC override key at `~/.claude/evidence-override-key` (CSPRNG, 0600) | user-level, machine |
| `orchestration` | `~/.claude/context/tiers.local.json` + `hardware-profile.md` from templates | user-level, machine |
| `stewardship` | nightly steward scheduled task / cron entry | user-level, machine |
| `discipline` | project-local `./.claude/discipline.local.md` from example | per-repo (run in the repo) |
| `git` | project-local `./.claude/commit-message-rules.yaml` from example | per-repo (run in the repo) |

The other plugins (`docs`, `review`, `retrospective`, `learning`, `windows`, `aether`, `agentic`) are pure skills/agents/hooks and need no per-machine config.

## Preferred path: the root setup script

The one-command setup runs all five inits in order and prints a status table. Resolve the repo root from wherever the marketplace is checked out (dev clone under `source/repos/claude-marketplace`, or the install cache under `~/.claude/plugins/marketplaces/garrettmanley`).

```bash
# Bash (Linux / macOS / Git-Bash). --force re-scaffolds; --quiet hides per-plugin lines.
bash <repo-root>/scripts/setup.sh
bash <repo-root>/scripts/setup.sh --force
```

```powershell
# PowerShell 7+ (Windows / macOS / Linux)
pwsh <repo-root>/scripts/setup.ps1
pwsh <repo-root>/scripts/setup.ps1 -Force
```

Each init prints one status line in the form `[init:<plugin>] <CONFIGURED|already configured|skipped|FAILED> — <detail>`, and `setup` collects them into a summary table. `setup` exits non-zero only if a plugin's init **hard-fails** — `already configured` and `skipped` are success.

Note the per-repo scope: `discipline` and `git` scaffold into the **current** repo's `.claude/`. The root script runs them against whatever directory it's invoked from. To scaffold a *different* project, run those two inits from inside that project (see below).

## Targeted path: run a single plugin's init

When only one plugin reports missing config, skip the orchestrator and run just that init. Use the variant matching the platform; both honor `--force`/`-Force` and `--quiet`/`-Quiet`.

```bash
bash <repo-root>/plugins/evidence/scripts/init.sh
```

```powershell
pwsh <repo-root>/plugins/orchestration/scripts/init.ps1
```

For the two per-repo plugins, `cd` into the target project first so the scaffold lands in that repo:

```bash
cd <target-project> && bash <repo-root>/plugins/discipline/scripts/init.sh
cd <target-project> && bash <repo-root>/plugins/git/scripts/init.sh
```

## Procedure for Claude

1. **Locate the marketplace root.** Prefer a dev clone if one exists (`source/repos/claude-marketplace`); otherwise the install cache `~/.claude/plugins/marketplaces/garrettmanley`. Confirm `scripts/setup.sh` and `scripts/setup.ps1` are present.
2. **Detect what's missing** (optional but informative). Check the user-level artifacts before running anything, so the report is meaningful:
   - `~/.claude/evidence-override-key` exists? (evidence)
   - `~/.claude/context/tiers.local.json` + `hardware-profile.md` exist? (orchestration)
   - the `stewardship-nightly-steward` task / cron entry exists? (stewardship)
3. **Run setup.** Pick the platform variant (`setup.ps1` on Windows, `setup.sh` on Unix/Git-Bash). Pass `--force`/`-Force` only if the user explicitly wants a re-scaffold — the inits are idempotent and a bare run is the safe default.
4. **Read the summary table.** Report each plugin's state. Flag any `FAILED` row with its detail and the remediation hint (e.g. evidence's `FAILED — python3 not found` means install Python 3 and re-run).
5. **Surface the post-config reminders.** `orchestration` emits `REMINDER:` lines telling the user to fill placeholders in `tiers.local.json` / `hardware-profile.md` — relay those; they are not auto-filled.
6. **Handle the per-repo plugins deliberately.** If the user wants `discipline`/`git` scaffolds in a specific project, run those two inits from inside that project rather than relying on the root script's working directory.

## Idempotency contract

Re-running is always safe: an init that finds its config in place reports `already configured` and exits 0 without touching the existing file. Nothing is overwritten unless the user passes `--force`. Treat a non-zero exit from `setup` as a genuine hard failure worth investigating, not as "needs re-running."
