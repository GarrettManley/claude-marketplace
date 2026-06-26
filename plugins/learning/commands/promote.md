---
name: promote
description: Promote a project-scoped instinct to the global store, explicitly or auto by cross-project evidence (Phase 3)
---

# /promote

Move an instinct that has proven general from a project's `personal/` store to the global store, so it applies everywhere. Promotion is copy-verify-delete (the global copy is parsed back before the project copy is removed) and the original `source` / `source_repo` are preserved. A snapshot is taken before any change.

## Implementation

**Explicit** — promote one instinct by id from the current project (dry-run first):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/instinct_cli.py" promote <instinct-id> --scope project
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/instinct_cli.py" promote <instinct-id> --scope project --apply
```

**Auto** — promote instincts that appear in ≥2 project stores with a (decayed) confidence ≥ 0.80:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/instinct_cli.py" promote --auto
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/instinct_cli.py" promote --auto --apply
```

`--auto` removes the promoted instinct from every project store it appeared in (it now lives globally). Run `/instinct-status` afterward to confirm.
