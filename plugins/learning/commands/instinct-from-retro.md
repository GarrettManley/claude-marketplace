---
name: instinct-from-retro
description: Mine retrospectives' recurring friction Rules into retro-mined instincts (Phase 2d)
---

# /instinct-from-retro

Close the write-only retrospective loop. Retros accumulate structured friction — each `## Friction / bugs` entry ends in a `*Rule:*` (a human-synthesized, ready-made instinct action) — but nothing re-ingests them. This command mines the **recurring** rules into `retro-mined` instincts that `surface.py` injects at SessionStart. The intelligence here is *yours*: the script parses + dumps friction deterministically; you cluster recurring patterns and author candidates.

Mirrors `/instinct-detect` (Path A, Claude-driven). The cluster/dedup judgment cannot be made by frequency synthesis.

## Implementation

**1. Dump the friction summary** (one JSON entry per rule-bearing friction item, plus a `parsed_empty` count for visibility into template drift):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/instinct_cli.py" retro-mine --dump-retros \
  --retros-dir "<path-to>/retrospectives/done" --scope project
```

`--retros-dir` defaults to `retrospectives/done` (cwd-relative); pass it explicitly when the cwd isn't the repo that owns the retros.

**2. Reason over it.** Read the JSON and:
- **Cluster recurring friction** by root-cause class. **Keep only patterns that appear in ≥2 retros** — one-off friction is dropped (it doesn't generalize). Collapse each kept cluster into ONE instinct; union the evidence and cite the source retro slugs.
- **Dedup against existing instincts** — run `/instinct-status` and skip a candidate whose normalized trigger + title already exists.
- **Generalize the Rule lightly** for the `action`: drop a one-off file path or PR number, keep the transferable instruction.

**3. Author candidates** as a multi-instinct YAML file (same shape `/instinct-import` accepts). Each candidate needs the **full** frontmatter or `parse_instinct` silently drops it: `id` (use a `retro-<slug>` namespace so it can never collide with an `auto-*`/`claude-detected` file), `trigger`, `confidence`, `domain`, `source`, then `# title`, `## Action`, `## Evidence`. Set evidence to "Derived from N retro friction entries: <slugs>". Source and confidence are normalized for you (forced to `retro-mined`, capped at 0.80). Write it to a temp path, e.g. `"$TMPDIR/retro-candidates.yaml"`.

**4. Review (dry-run), then persist:**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/instinct_cli.py" retro-mine --ingest "$TMPDIR/retro-candidates.yaml" --scope project
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/instinct_cli.py" retro-mine --ingest "$TMPDIR/retro-candidates.yaml" --scope project --apply
```

## Notes

- **Surfacing must be on** for the loop to actually close: `export LEARNING_HOOK_PROFILE=strict; export LEARNING_SURFACE=on`. Without it, retro-mined instincts are stored but never injected.
- **Re-run periodically.** Retro instincts are reinforced (`last_reinforced` re-stamped) only when this command re-applies them. Because there's no processed-ledger, re-running re-mines the whole corpus and re-stamps surviving patterns — otherwise `/prune`'s 30-day half-life will decay them while the source retros still exist.
- Retro instincts land in the scope's `personal/` store and are evolved/decayed like other machine instincts; run `/instinct-status` to review.
