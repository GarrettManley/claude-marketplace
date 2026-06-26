---
name: prune
description: Decay-prune machine-learned instincts whose confidence has aged below the floor (Phase 3)
---

# /prune

Remove machine-learned instincts that have decayed. Each instinct's confidence falls on a 30-day half-life from its `last_reinforced` time; once the decayed value drops below **0.2** it is pruned. Only machine sources (`auto-*`, `claude-detected`) decay — human-authored and imported instincts are exempt. Re-deriving an instinct (`/instinct-synthesize`, `/instinct-detect`) re-stamps it and resets the decay.

## Implementation

Default is a **dry-run** — list what would be pruned, delete nothing:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/instinct_cli.py" prune --scope project
```

After review, apply. A timestamped snapshot of the instinct stores is taken **before** any deletion (the command prints the restore path):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/instinct_cli.py" prune --scope project --apply
```

Use `--scope global` to prune the global store. To restore, copy the printed snapshot directory's contents back over the data root.
