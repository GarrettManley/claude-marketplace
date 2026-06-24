# CLAUDE.md — claude-marketplace

Dev clone of the `garrettmanley` plugin marketplace. Edit here, push, then the user
runs `/plugin` to reinstall — this repo is **separate** from the live plugin cache at
`~/.claude/plugins/marketplaces/garrettmanley` (never edit the cache directly).

## Gotchas
- **Stage files explicitly per commit (never `git add -A`).** This clone has
  historically carried untracked orphans (the old `docs/`/`templates/` exclusions are
  resolved — both are tracked now), and explicit staging keeps release scopes honest
  for `release.py`.
- **Versions: `plugins/<name>/.claude-plugin/plugin.json` is the single source of truth**
  (the install cache keys off it). `.claude-plugin/marketplace.json` is a derived
  duplicate — never hand-edit its versions; run `python3 ci/check-versions.py --fix`.
  `python3 ci/release.py --dry-run|--apply` does conventional-commit per-plugin bumps.
- **`git fetch --tags` before any `release.py` run.** `release.py` derives each
  plugin's commit range from the last *local* `<name>-v*` tag. This dir doubles as
  the install cache and nothing routinely fetches it, so its tags drift behind the
  remote — a stale clone makes a healthy plugin look like it has unreleased breaking
  changes and `--dry-run` proposes a spurious major bump. If a bump looks wrong,
  suspect stale tags first: `git fetch --tags` and re-run `--dry-run`.
- **`release.py` bumps only on `feat`/`fix`/`perf`/breaking.** `refactor`/`docs`/`test`
  commits are not release-worthy, so they reach the install cache only when the plugin's
  next feat/fix release ships them. Don't fake a `fix:` to force a release — if the change
  is behavior-neutral, deferred shipping is correct.
- **Pre-merge gate:** `bash scripts/verify.sh` (lint + version drift + hook-runtime checks).
  CI tests: `python3 -m pytest ci/tests/`. Hyphenated `ci/check-versions.py` is loaded
  via importlib, not imported.
- Conventional Commits with per-plugin scopes, e.g. `feat(discipline):`, `fix(ci):`.
