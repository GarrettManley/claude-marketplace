---
name: pre-plan-brief
description: Surface prior retrospective findings for an area before planning, so a known issue does not silently recur.
argument-hint: <area-or-keywords>
---

# /pre-plan-brief

Before planning work in **$ARGUMENTS**, surface the matching findings from past
retrospectives so nothing recurs that a prior cycle already learned.

## Implementation

Run from the workspace root:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/retro_brief.py" "$ARGUMENTS"
```

Show the brief to the user, then — for each surfaced finding — state whether the
upcoming plan already addresses it or needs to. If the brief is empty, say so:
the area has no prior retro findings, so plan with a clear slate.

See the `pre-plan-brief` skill for matching behavior and how to widen/narrow the
area term.
