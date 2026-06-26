# stewardship@garrettmanley

Autonomous maintenance toolkit for Claude Code: runs drift checks against context-file
verification commands, rotates stale auto-memory entries, registers a nightly scheduler,
and applies format + typecheck passes after every session. Keeps your `~/.claude/context/`
facts accurate and your `~/.claude/projects/*/memory/` directories tidy without
manual intervention.

## Install

Enable from the `garrettmanley` marketplace:

```text
/plugin marketplace add garrettmanley/claude-marketplace
/plugin enable stewardship@garrettmanley
```

## Components

### Skills

| Skill | Description |
|-------|-------------|
| `stewardship-overview` | Walks through one-shot scheduler setup and explains how the three core scripts compose into a nightly maintenance job |
| `marketplace-setup` | Detects which enabled plugins are missing per-machine config, runs the right initializer (or the root setup script), and reports a config-status summary |

### Agents

| Agent | Description |
|-------|-------------|
| `harness-optimizer` | Audits plugin manifests, hook configs, enabled-plugin list, and MCP footprint; proposes the top-3 reversible config changes for reliability, cost, or throughput |

### Hooks

| Hook ID | Event | Matcher | Description |
|---------|-------|---------|-------------|
| `stewardship:post-edit:accumulate` | `PostToolUse` | `Edit\|Write\|MultiEdit` | Records every edited path to a per-session tmpfile |
| `stewardship:stop:format-typecheck` | `Stop` | `*` | Reads the accumulator at session end; runs language-appropriate formatter + typechecker once per (language, project root) group |

Both hooks are gated by `STEWARDSHIP_HOOK_PROFILE` and `STEWARDSHIP_DISABLED_HOOKS`.
They fire under `standard` and `strict` profiles; they are off under `minimal`.

### Commands

| Command | Description |
|---------|-------------|
| `/morning-briefing` | Renders today's briefing — drift-check, memory-housekeeping, and horizon-scan status plus rule-based suggested actions — from live data, writing `~/.claude/stewardship/briefing/<date>.md` |

### Scripts

| Script | Purpose |
|--------|---------|
| `scripts/drift_check.py` | Scans `~/.claude/context/` for `verification_cmd:` frontmatter; runs each command; reports pass/fail and staleness |
| `scripts/auto_memory_housekeep.py` | Identifies stale entries (>90d by default) in `~/.claude/projects/*/memory/`; optionally archives them; flags broken `MEMORY.md` pointers |
| `scripts/horizon_scan_schedule.py` | Deterministic cadence tracker — surfaces a "horizon-scan DUE" reminder when the monthly interval elapses. Reminds only; the scan itself (`/orchestration:horizon-scanning`) needs an interactive session |
| `scripts/render_briefing.py` | Fills `templates/morning-briefing.md` from the three sources' `--json` output (status + rule-based actions). Backs `/morning-briefing` and the 4th nightly step |
| `scripts/register_nightly.ps1` | Windows Task Scheduler helper — registers, updates, or removes the `stewardship-nightly-steward` task |
| `scripts/post_edit_accumulator.py` | Backing store for the `PostToolUse` hook |
| `scripts/stop_format_typecheck.py` | Backing store for the `Stop` hook |

### Templates

| Template | Purpose |
|----------|---------|
| `templates/morning-briefing.md` | Daily-briefing template with `{{TOKEN}}` placeholders, filled by `render_briefing.py` (`/morning-briefing` + the nightly steward) from drift-check, housekeep, and horizon-scan data |

## Init / Setup

The plugin ships `scripts/init.ps1` (Windows) and `scripts/init.sh` (Unix / macOS /
Git Bash). Each registers the nightly scheduler for its platform, exits 0 on success
or if already configured, and exits 1 on hard failure.

### Preferred path — root setup script (all plugins at once)

```bash
# Bash (Linux / macOS / Git Bash)
bash <repo-root>/scripts/setup.sh
bash <repo-root>/scripts/setup.sh --force   # re-scaffold
```

```powershell
# PowerShell 7+ (Windows / macOS / Linux)
pwsh <repo-root>/scripts/setup.ps1
pwsh <repo-root>/scripts/setup.ps1 -Force
```

Each plugin's init emits one status line:
`[init:stewardship] <CONFIGURED|already configured|skipped|FAILED> — <detail>`

### Targeted path — stewardship only

```bash
bash <repo-root>/plugins/stewardship/scripts/init.sh
bash <repo-root>/plugins/stewardship/scripts/init.sh --force
```

```powershell
pwsh <repo-root>/plugins/stewardship/scripts/init.ps1
pwsh <repo-root>/plugins/stewardship/scripts/init.ps1 -Force
```

Both honor `--force`/`-Force` (re-register even if already configured) and
`--quiet`/`-Quiet` (suppress the status line). Re-running without `--force` is
always safe — it reports `already configured` and exits 0.

## Usage

### Invoke the setup skill

```text
/stewardship-overview
```

Walks through one-shot setup, explains each script, and shows smoke-test commands.

### Run drift-check on demand

```bash
# Default: scan ~/.claude/context/, markdown output
python <plugin>/scripts/drift_check.py

# JSON output (pipe to other tools)
python <plugin>/scripts/drift_check.py --json

# Custom context directory
python <plugin>/scripts/drift_check.py --dir /path/to/project/.ai/context

# Adjust staleness threshold (default: 45 days)
python <plugin>/scripts/drift_check.py --max-age-days 30
```

### Run memory housekeeping on demand

```bash
# Dry-run (report only, no files moved)
python <plugin>/scripts/auto_memory_housekeep.py

# Apply: archive stale files into per-project _archive/ subdirs
python <plugin>/scripts/auto_memory_housekeep.py --apply

# Custom threshold and projects directory
python <plugin>/scripts/auto_memory_housekeep.py --apply --days 60 --projects-dir /custom/path

# Structured JSON report (report-only; ignores --apply) — consumed by the briefing renderer
python <plugin>/scripts/auto_memory_housekeep.py --json
```

### Check the horizon-scan cadence on demand

The nightly steward's third step tracks when an `orchestration:horizon-scanning` sweep is due. It is a **reminder, not an executor**: horizon-scanning web-searches benchmarks, weighs the 8 GB VRAM ceiling, and runs load tests, so it requires an interactive Claude session and cannot run headless. The steward surfaces a DUE notice; you run the scan interactively, then reset the clock.

```bash
# Is a scan due? (markdown body; default interval 30 days)
python <plugin>/scripts/horizon_scan_schedule.py

# Machine-readable output (for a briefing renderer)
python <plugin>/scripts/horizon_scan_schedule.py --json

# Custom cadence
python <plugin>/scripts/horizon_scan_schedule.py --interval-days 45

# After completing an interactive scan, reset the clock (also invoked by the skill's closing step)
python <plugin>/scripts/horizon_scan_schedule.py --mark-done
```

State lives at `~/.claude/stewardship/horizon-scan-state.json` (a `last_scan` timestamp). A missing or unreadable state file is treated as never-scanned → DUE. The nightly run logs a `## horizon_scan` section to `nightly.log`, and the `{{HORIZON_SCAN_SECTION}}` token in `templates/morning-briefing.md` gives a briefing renderer a slot to surface it. See `docs/adr/0010-horizon-scan-cadence-reminder.md` for why the steward reminds rather than executes.

### Generate the morning briefing on demand

`render_briefing.py` fills `templates/morning-briefing.md` from live data: it invokes the three source scripts with `--json`, derives the status line + rule-based suggested actions, and substitutes the six `{{TOKEN}}` placeholders. The same subprocess `--json` contract is each script's single source of truth for its structured output — the renderer is a thin composer (see `docs/adr/0011-morning-briefing-renderer.md`). A source whose subprocess fails degrades to an `_(… unavailable)_` section rather than crashing the briefing.

```bash
# Render today's briefing to ~/.claude/stewardship/briefing/<date>.md and print it
python <plugin>/scripts/render_briefing.py --stdout

# Tune the drift / horizon thresholds, or point at non-default dirs (test-injection seams)
python <plugin>/scripts/render_briefing.py --max-age-days 30 --interval-days 45
```

The nightly steward also pre-renders one at 03:00 (its 4th step). When the nightly runs with `-ApplyHousekeep`, step 2 archives stale memory *before* the briefing re-scans, so the briefing reflects the post-archival state ("what still needs attention").

### Register the nightly task (Windows, manual)

```powershell
# Register at 03:00 daily (dry-run housekeep)
.\scripts\register_nightly.ps1

# Custom time
.\scripts\register_nightly.ps1 -At "02:30"

# Enable archival mode in the scheduled run
.\scripts\register_nightly.ps1 -ApplyHousekeep

# Smoke test
Start-ScheduledTask -TaskName "stewardship-nightly-steward"
Get-Content "$env:LOCALAPPDATA\stewardship-plugin\logs\nightly.log" -Tail 40

# Remove
.\scripts\register_nightly.ps1 -Unregister
```

### Invoke the harness optimizer

```text
/harness-optimizer
```

Reads your current `~/.claude/settings.json` (plugins, hooks, MCP), then proposes
the top-3 reversible config changes. Never edits files without explicit approval.

## Configuration

### Hook profile

`STEWARDSHIP_HOOK_PROFILE=minimal|standard|strict` (default: `standard`)

| Hook ID | minimal | standard | strict |
|---------|---------|----------|--------|
| `stewardship:post-edit:accumulate` | | ✓ | ✓ |
| `stewardship:stop:format-typecheck` | | ✓ | ✓ |

### Per-hook disable

`STEWARDSHIP_DISABLED_HOOKS=<id>[,<id>…]` — comma-separated list of hook IDs to
silence without changing the profile. Whitespace trimmed; case-insensitive.

```bash
# Disable the Stop-time format pass for one session
STEWARDSHIP_DISABLED_HOOKS=stewardship:stop:format-typecheck claude
```

### Format/typecheck tuning

| Env var | Default | Effect |
|---------|---------|--------|
| `STEWARDSHIP_FORMAT_TIMEOUT_S` | `90` | Per-batch timeout cap in seconds |

Total budget across all batches is capped at 270 s (under the 300 s Stop hook ceiling).
Missing tools (e.g., no `cargo` on PATH) are silently skipped — the hook always exits 0.

### Language detection markers

| Language | Project-root markers | Format | Typecheck |
|----------|---------------------|--------|-----------|
| TypeScript / JavaScript | `tsconfig.json`, `package.json` | `npx prettier --write <files>` | `npx tsc --noEmit` (`.ts`/`.tsx`/`.mts`/`.cts` only) |
| Python | `pyproject.toml`, `setup.py`, `setup.cfg` | `ruff format <files>` | `ruff check <files>` |
| Rust | `Cargo.toml` | `cargo fmt` | `cargo check` |

### Drift-check frontmatter

To make a context file verifiable, add `verification_cmd:` to its YAML frontmatter:

```markdown
---
topic: local runtime
verification_cmd: "python3 --version"
last_verified: "2025-11-01"
---
```

`drift_check.py` runs the command in the context directory (exit 0 = pass). The
`last_verified` field is checked against `--max-age-days` (default 45) independently
of whether the command passes.

### Convention over configuration

| Default path | Override |
|-------------|----------|
| `~/.claude/context/` (drift check) | `--dir PATH` |
| `~/.claude/projects/` (housekeep) | `--projects-dir PATH` |
| 90-day staleness threshold (housekeep) | `--days N` |
| 45-day staleness threshold (drift check) | `--max-age-days N` |
| Dry-run mode (housekeep) | `--apply` to enable archival |
| 30-day horizon-scan cadence | `--interval-days N` |
| `~/.claude/stewardship/horizon-scan-state.json` (scan state) | managed by `--mark-done` |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `stewardship-nightly-steward` task not found after init | Run `init.ps1` from an elevated PowerShell prompt, or verify `register_nightly.ps1` is on the expected path relative to `$PSScriptRoot` |
| Drift-check finds no files | Confirm context files start with `---` and contain a `verification_cmd:` line inside the frontmatter block |
| Stop hook runs formatters on unrelated files | The accumulator is SHA-keyed on `CLAUDE_SESSION_ID`; a stale accumulator from a prior session can survive if the session key didn't change. Delete `${TMPDIR}/stewardship-edited-<session-key>.txt` manually |
| `ruff` / `cargo` / `npx` not found — silent skip | Install the missing tool and ensure it is on PATH at session launch time; the hook logs tool-not-found to stderr only |

## Cross-platform notes

| Concern | Windows | macOS | Linux / Git Bash |
|---------|---------|-------|------------------|
| Nightly scheduler | Windows Task Scheduler via `register_nightly.ps1`; task named `stewardship-nightly-steward`; logs to `%LOCALAPPDATA%\stewardship-plugin\logs\nightly.log` | launchd LaunchAgent via `com.claude.stewardship.nightly.plist.template`; logs to `~/Library/Logs/stewardship-plugin/nightly.log` | cron via `nightly-scheduler.cron.template`; logs to `~/.local/share/stewardship-plugin/logs/nightly.log` |
| `init` script | `scripts/init.ps1` (PowerShell 7+) | `scripts/init.sh` (Bash) — installs cron entry | `scripts/init.sh` (Bash) — installs cron entry |
| Python launcher | `register_nightly.ps1` resolves `python3` → `python` → `py` at registration time and bakes the path into the wrapper | `python3` assumed on PATH | `python3` assumed on PATH |
| Missed runs | Task Scheduler catches up on wake (`-StartWhenAvailable`) | launchd skips missed runs; no catch-up | cron skips missed runs; no catch-up |
| Log rotation | Not automatic; manually manage `nightly.log` | Use `newsyslog` | Use `logrotate` |

The three Python maintenance scripts (`drift_check.py`, `auto_memory_housekeep.py`,
`horizon_scan_schedule.py`) are pure Python 3 and run identically on all platforms. Only
the scheduler wiring differs.
