---
name: evolve
description: Cluster near-duplicate machine instincts and merge each cluster into its strongest member (Phase 3)
---

# /evolve

Consolidate redundancy in the instinct store. Machine-learned instincts whose `trigger + title` are ≥80% similar are clustered; each cluster of two or more merges into its highest-confidence member (their evidence is unioned), and the merged-away instincts are archived into the `evolved/` directory rather than deleted. Human-authored and imported instincts are never merged.

## Implementation

Default is a **dry-run** — show the clusters and the merge target, change nothing:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/instinct_cli.py" evolve --scope project
```

After review, apply. A snapshot is taken before merging; archived sources move to the scope's `evolved/` directory:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/instinct_cli.py" evolve --scope project --apply
```

Use `--scope global` to consolidate the global store. To undo, restore from the printed snapshot directory.
