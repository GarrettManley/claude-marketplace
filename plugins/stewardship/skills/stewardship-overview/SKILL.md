---
name: stewardship-overview
description: Use when the user wants to set up automated maintenance — nightly drift checks against context files, auto-memory housekeeping, scheduled briefings. Walks through the stewardship plugin's three deliverables and how they compose into a one-shot setup.
version: 0.2.0
dependencies: []
---

# Stewardship Overview

Routes the user through one-shot setup of the `stewardship` plugin's nightly maintenance: drift checks against context files, auto-memory housekeeping, and a scheduled job that runs both.

## When to use

- The user wants to set up automated, recurring maintenance of their Claude Code context and memory.
- The user asks how to wire a nightly drift check or memory-housekeeping job, or how to register the scheduled task.
- The user wants to understand what each stewardship script does and how the pieces compose.

## What the plugin gives you

The `stewardship` plugin gives you three composable pieces:

1. **`scripts/drift_check.py`** — scans `~/.claude/context/` (or any dir) for `verification_cmd:` frontmatter, runs each command, reports pass/fail. Catches when documented facts no longer hold.
2. **`scripts/auto_memory_housekeep.py`** — finds stale (>90d default) entries in `~/.claude/projects/*/memory/`, optionally archives them. Also flags broken pointers in `MEMORY.md`.
3. **`scripts/register_nightly.ps1`** — Windows Task Scheduler helper that wires both into a nightly job, logging to `%LOCALAPPDATA%\stewardship-plugin\logs\nightly.log`.

Plus a briefing template (`templates/morning-briefing.md`) for projects that want to render the results into a daily summary.

## Setup (one-shot, per machine)

```powershell
# 1. Decide your time. 03:00 is the default.
$plugin = "$env:USERPROFILE\.claude\plugins\marketplaces\garrettmanley\plugins\stewardship"

# 2. Register the nightly task. Use --apply if you want the housekeep to actually archive.
& "$plugin\scripts\register_nightly.ps1" -At "03:00"
# (re-run with -ApplyHousekeep once you trust the dry-run output)

# 3. Smoke test immediately
Start-ScheduledTask -TaskName stewardship-nightly-steward
Get-Content "$env:LOCALAPPDATA\stewardship-plugin\logs\nightly.log" -Tail 50
```

## When to use each piece on demand (no scheduler needed)

```bash
# Drift-check the user-level context dir (markdown is the default output)
python <plugin>/scripts/drift_check.py

# Drift-check a project-specific context dir
python <plugin>/scripts/drift_check.py --dir C:/Users/<username>/<workspace>/.ai/context --json

# Dry-run memory housekeeping (default: report what would be archived)
python <plugin>/scripts/auto_memory_housekeep.py

# Apply: actually archive stale files into per-project _archive/ subdirs
python <plugin>/scripts/auto_memory_housekeep.py --apply --days 60
```

## Configuration model

This plugin is intentionally **convention over configuration**:

- Drift check looks at `~/.claude/context/` by default. Override with `--dir`.
- Memory housekeep looks at `~/.claude/projects/` by default. Override with `--projects-dir`.
- Scheduler runs both. Edit the generated `run-nightly.ps1` wrapper to add custom steps (e.g., a horizon-scan, a cross-project sync).

If you find yourself wanting more knobs, that's a signal to extend the plugin — open a TODO with `#NN` reference and track it.

## What this plugin deliberately doesn't do (yet)

- **Persona evolution** — out of scope for this plugin (a project-specific `evolve_personas.py` would be too coupled to its persona-matrix format). If you adopt persona-evolution as a cross-project pattern, that's a future plugin or version.
- **Horizon-scan automation** — the `orchestration:horizon-scanning` skill defines the protocol; automating it via this plugin is a future enhancement (would call out to the orchestration skill via the Claude Code CLI).
- **Cross-machine sync** — separate concern; addressed by the marketplace itself being a git repo.
