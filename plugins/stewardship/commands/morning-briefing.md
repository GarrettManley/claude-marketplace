---
name: morning-briefing
description: Render today's stewardship morning briefing — drift-check, memory-housekeeping, and horizon-scan status with suggested actions — from live data.
---

# /morning-briefing

Generate today's briefing by filling `templates/morning-briefing.md` from fresh source data (drift check, memory housekeeping, horizon-scan cadence).

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/render_briefing.py" --stdout
```

Writes `~/.claude/stewardship/briefing/<date>.md` and prints it. The briefing reflects the moment you run it; the nightly steward also pre-renders one at 03:00.
