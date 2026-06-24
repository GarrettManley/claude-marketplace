---
name: instinct-export
description: Export instincts to a YAML file (global or project scope)
argument-hint: <output-path>
---

# /instinct-export

Export the union of `personal/` and `inherited/` instincts from a scope to a single concatenated YAML file.

## Implementation

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/instinct_cli.py" export "$OUTPUT" --scope=<global|project>
```

Show the output verbatim. The exported file can be re-imported on another machine via `/instinct-import`.
