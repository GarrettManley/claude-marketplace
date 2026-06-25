---
name: instinct-synthesize
description: Auto-create instincts from frequency patterns in observations.jsonl (Phase 2b)
---

# /instinct-synthesize

Convert frequency patterns in the current project's `observations.jsonl` into instincts automatically, written to the scope's `personal/` directory. This is the automated successor to the manual `/analyze-observations` → hand-write YAML → `/instinct-import` loop.

Two pattern families become instincts:
- **workflow** — tool-pair sequences (B frequently follows A), scored by support × consistency.
- **tooling** — frequently-used Bash command prefixes.

Confidence is auto-derived and capped below the band reserved for human-authored instincts; auto-created instincts carry `source: auto-frequency`. Re-running updates `auto-*` files in place (idempotent) and never overwrites a manually-promoted instinct of the same id.

## Implementation

Default is a **dry-run** — show candidates, write nothing:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/instinct_cli.py" synthesize --scope project
```

Show the output verbatim. After the user reviews the candidates, persist them with:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/instinct_cli.py" synthesize --scope project --write
```

Optional flags: `--min-support N` (default 5), `--min-consistency F` (default 0.5), `--scope global|project` (default project).

## Notes

If the report says "0 candidates" with "no observations recorded", enable capture first and run some sessions:

```bash
export LEARNING_HOOK_PROFILE=strict
export LEARNING_OBSERVE=on
```

After writing, run `/instinct-status` to see the new instincts, and set `LEARNING_SURFACE=on` to have high-confidence instincts injected into future sessions.
