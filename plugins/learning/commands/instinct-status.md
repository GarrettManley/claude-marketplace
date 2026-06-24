---
name: instinct-status
description: Show learned instincts (project + global) with confidence
---

# /instinct-status

Show all instincts for the current project plus global instincts, grouped by domain.

## Implementation

Run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/instinct_cli.py" status
```

Show the output verbatim to the user. No further synthesis required.
