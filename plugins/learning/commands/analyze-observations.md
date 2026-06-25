---
name: analyze-observations
description: Report tool-use patterns from learning's observations.jsonl
---

# /analyze-observations

Report tool-use frequency, common tool-pair sequences, top Bash command prefixes, and file hotspots from the current project's `observations.jsonl` (written by the opt-in `learning:pre-tool:observe` + `learning:post-tool:observe` hooks).

This is the manual-review report. To turn these patterns into instincts automatically, use `/instinct-synthesize` (Phase 2b). For full hand control, read the report, decide which patterns warrant an instinct, then create the YAML file and import via `/instinct-import`.

## Implementation

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/instinct_cli.py" analyze
```

Show the output verbatim.

## Notes

If the report says "0 records", enable observation capture first:

```bash
export LEARNING_HOOK_PROFILE=strict
export LEARNING_OBSERVE=on
```

Both gates must be open for `observe.py` to write anything.
