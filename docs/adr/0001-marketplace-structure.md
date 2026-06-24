---
status: active
author: Garrett Manley
created: 2026-06-23
diataxis: reference
---

# 0001. Per-plugin self-contained subtrees

**Status:** Accepted

## Context

Claude Code installs each plugin as an isolated per-version subtree in the local plugin
cache (`~/.claude/plugins/`). The runtime never merges assets across plugins or across
versions of the same plugin. A shared library placed at the repo root (e.g.,
`lib/hook_utils.py`) would be absent at the install path and therefore silently
unavailable to any hook script at runtime.

The marketplace manifest (`.claude-plugin/marketplace.json`) maps each plugin to a
`./plugins/<name>` source directory. The `ci/validate-plugins.py` gate enforces that
every `source` entry resolves to a `plugins/<name>/.claude-plugin/plugin.json`, and
that every plugin directory with a manifest appears in the manifest — no orphans, no
cross-plugin references.

## Decision

Each plugin under `plugins/<name>/` is fully self-contained: hooks, skills, commands,
agents, scripts, tests, and references all live inside that subtree. No plugin imports
from another plugin's directory at runtime.

When two or more plugins need the same utility file (currently `hook_flags.py` and
`run_with_flags.py`, canonical in `plugins/discipline/scripts/`), the file is vendored
verbatim into each consumer plugin. `ci/check-vendored-sync.py` enforces byte identity
between the canonical copy and all vendored copies; drift fails pre-merge:

```
python3 ci/check-vendored-sync.py        # check
python3 ci/check-vendored-sync.py --fix  # propagate canonical → consumers
```

The edit target for shared logic is always the canonical copy in `discipline`; the fix
command propagates the change. This is documented as the intended workflow, not a
workaround. ADR 0002 covers the vendoring protocol in detail.

## Consequences

**Positive**

- Install isolation is trivially correct: the runtime path for any hook script is
  entirely within the plugin's own subtree.
- Adding or updating a plugin cannot break another plugin's runtime behavior.
- `validate-plugins.py` and `check-vendored-sync.py` make violations visible at CI
  time rather than at consumer install time.

**Negative / tradeoffs**

- Shared utility logic requires coordinated updates: edit canonical, run `--fix`,
  commit all affected files in one PR. Forgetting the fix step produces a CI failure.
- Plugin subtrees grow slightly larger than the minimum when shared files are vendored.
  At the current file sizes this is not material.
