# 0003. Local-LLM Tier Config: Generic Bundle + Machine-Specific Override

**Status:** Accepted

## Context

The `orchestration@garrettmanley` plugin ships tier definitions that the `local-orchestrator` skill reads to select which local GGUF model to load. Those definitions include machine-specific values: the path to `llama-server`, the directory holding GGUF files, the VRAM ceiling, and the GPU model label. Baking real values into a committed file would make the shared marketplace contain one contributor's hardware fingerprint and break setup for anyone with a different machine.

Three options were considered:

1. **Committed file only** — simple, but forces machine-specific values into a public repo.
2. **User-supplied file only** — clean but requires every installer to author the file from scratch with no reference schema.
3. **Generic bundle + local override** — the repo ships a schema-correct file with `<placeholder>` values; an installer-run init script seeds a private copy; the skill reads the private copy if present, else falls back to the bundle.

## Decision

Option 3. `plugins/orchestration/configs/tiers.json` ships with every `runtime` field set to a `<placeholder>` string and `<N> GB VRAM` / `<GPU model>` annotations in human-readable fields. The init scripts (`scripts/init.sh` / `scripts/init.ps1`) copy this file to `~/.claude/context/tiers.local.json` on first run. The `local-orchestrator` skill instructs the model to treat `~/.claude/context/tiers.local.json` as the authoritative source when present, falling back to the bundled `configs/tiers.json` otherwise.

```bash
# After plugin install — seeds ~/.claude/context/tiers.local.json
bash plugins/orchestration/scripts/init.sh
# Then edit the seeded file to replace <placeholder> values with real paths and hardware spec
```

The init scripts are idempotent (no-op if the file already exists) and print `REMINDER:` lines listing every placeholder that needs a real value.

## Consequences

- **Publish safety:** no machine-specific paths, VRAM figures, or GPU labels reach the public repo.
- **Bootstrapping:** a fresh install has a working schema with placeholder values; the model can surface the heuristics and tier table even before the user fills in real paths.
- **Drift risk:** if `configs/tiers.json` adds new fields (e.g. a new tier or a new `runtime` key), existing `tiers.local.json` files will miss them until the user re-runs init with `--force` or manually merges. The `horizon-scanning` skill's monthly review is the intended trigger for that reconciliation.
- **One source of truth per machine:** `~/.claude/context/tiers.local.json` is the single file to edit; there is no per-project config layer for tiers.
