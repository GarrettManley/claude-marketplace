---
generated_by: stewardship plugin
date: {{DATE}}
---

# Morning Briefing — {{DATE}}

Skeleton briefing for the garrettmanley `stewardship` plugin. A project renders this by substituting the `{{TOKEN}}` placeholders below with drift-check, housekeeping, and horizon-scan output. Nothing in the plugin auto-populates it yet — the nightly job (`drift_check.py` + `auto_memory_housekeep.py` + `horizon_scan_schedule.py`) logs to `nightly.log`; wire your own renderer to fill this template.

## Drift Check Status

**Result**: {{AUDIT_STATUS}}

{{DRIFT_SECTION}}

## Memory Housekeeping

{{HOUSEKEEPING_SECTION}}

## Horizon Scan

{{HORIZON_SCAN_SECTION}}

## Suggested Actions

{{ACTIONS_SECTION}}

---

_Scripts and templates live at `~/.claude/plugins/marketplaces/garrettmanley/plugins/stewardship/`. Re-run the nightly job manually with `Start-ScheduledTask -TaskName stewardship-nightly-steward` (registered by `scripts/register_nightly.ps1`)._
