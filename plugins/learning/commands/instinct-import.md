---
name: instinct-import
description: Import instincts from a YAML file into global or project scope
argument-hint: <file-path>
---

# /instinct-import

Import instincts from a YAML file into the `inherited/` directory of either the global or current-project scope.

## Implementation

Determine the file path from the user's argument. Default scope is `global` unless the user specifies `--project`. Run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/instinct_cli.py" import "$FILE" --scope=<global|project>
```

Show the output verbatim.

## Notes

Imported instincts land in `inherited/` (vs `personal/`, reserved for Phase 2 auto-creation). Use this to seed instincts from another machine, a teammate's curated file, or your own backup.
