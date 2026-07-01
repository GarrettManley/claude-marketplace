---
status: accepted
author: Garrett Manley
created: 2026-06-23
diataxis: reference
---

# 0002. Vendored hook runtime with CI-enforced byte-identity sync

**Status:** Accepted

## Context

`discipline`, `learning`, and `stewardship` all need the same two runtime-control
files: `hook_flags.py` (profile + disable-list logic) and `run_with_flags.py`
(the wrapper that gates each hook via `is_hook_enabled`). Sharing them as a
cross-plugin library is not viable — Claude Code installs each plugin as an
isolated per-version subtree in the user's plugin cache, so there is no location
a shared library can reliably occupy at install time (ADR 0001). The files are
plugin-agnostic by construction: the env-var prefix (`DISCIPLINE_*`, `LEARNING_*`,
`STEWARDSHIP_*`) is derived at runtime from the hook id namespace, not hardcoded,
so the same bytes work unchanged in every plugin.

## Decision

`plugins/discipline/scripts/` holds the canonical copies of both files.
`plugins/learning/scripts/` and `plugins/stewardship/scripts/` carry verbatim
vendored copies. `ci/check-vendored-sync.py` detects any byte-level divergence:

```bash
python3 ci/check-vendored-sync.py          # check; exit 1 on drift
python3 ci/check-vendored-sync.py --fix    # overwrite consumers from canonical
```

The fix direction is one-way: edit the canonical copy in `discipline`, then
propagate with `--fix`. Editing a consumer copy directly will cause CI to fail
on the next `scripts/verify.sh` run, which gates every pre-merge.

`ci/verify_hook_runtime_controls.py` enforces a complementary invariant: every
command in the gated plugins' (`discipline`, `learning`, `stewardship`)
`hooks.json` files must invoke `scripts/run_with_flags.py`, so env-var disables
(`*_DISABLED_HOOKS`) apply uniformly to all hooks in each gated plugin.

## Consequences

- **Single edit point.** All behavioral changes go to the canonical `discipline`
  copies; consumers are updated mechanically.
- **Drift is caught immediately.** `check-vendored-sync` runs in `scripts/verify.sh`
  (pre-merge gate) and CI, so a stale consumer never ships in a release.
- **New consumers are cheap to add.** Add the plugin name to `CONSUMER_PLUGINS`
  in `ci/check-vendored-sync.py` and run `--fix`; no other wiring needed.
- **No runtime overhead.** The vendored files are imported in-process by
  `run_with_flags.py` via `importlib`; there is no subprocess cold-start per hook
  invocation for Python hooks.
