# Contributing

## Post-clone setup

Install the dev toolchain (ruff + pytest + coverage; runtime hooks stay stdlib-only),
then wire the committed pre-commit hook so it runs before every commit:

```bash
python3 -m pip install -r requirements-dev.txt
git config core.hooksPath .githooks
```

The pre-commit hook delegates to `scripts/verify.sh`, so it runs the **exact same
portable gate set as CI** — line-ending/lint hygiene (`lint-no-bare-python`, `ruff`),
manifest integrity (`check-versions --check`, `validate-plugins`), hook runtime
controls, vendored-file sync, frontmatter + skill-index, and the `NOTICE` attribution
gate. The pytest suite and the cross-OS `shellcheck` / `PSScriptAnalyzer` linters run in
CI only (they need the OS-specific tools a committer may not have locally).

## Maintainer pre-merge gate

Before merging any PR, run the verify script from the repo root:

```bash
bash scripts/verify.sh
```

Exit 0 = clean. Exit 1 = failures printed to stdout.

`/deliver` lands via PR by default (`land-policy: pr` in `.claude/delivery.local.md`);
avoid landing with a direct `git push origin main`. A direct push bypasses the required
checks that gate a PR merge — they still run on `main` afterward (`ci.yml` also
triggers on `push: [main]`), but only post-hoc and non-blocking, after the merge
decision has already been made. See `docs/adr/0013-pr-gated-landing.md`.

## Continuous integration

`.github/workflows/ci.yml` is **verification-only — it never tags or publishes**
(releases stay local via `ci/release.py`). It runs a tri-OS matrix (Ubuntu + Windows
required; macOS non-blocking) on Python 3.12 and 3.13. Each leg runs `scripts/verify.sh`,
the per-directory pytest suites with a **≥90% Python line-coverage gate**, plus the
OS-specific linters: `shellcheck -S warning` on Linux and `PSScriptAnalyzer` (per
`PSScriptAnalyzerSettings.psd1`) on Windows. Lint config lives in `pyproject.toml`
(ruff: `E`/`F`/`W`, line-length 120; tests carry per-file-ignores for deliberate
sys.path/seam/fixture patterns).

## Versioning

`plugins/<name>/.claude-plugin/plugin.json` is the **single source of truth** for a
plugin's version (the install cache keys off it). Its entry in
`.claude-plugin/marketplace.json` is a derived duplicate, kept honest automatically:

- `python3 ci/check-versions.py --check` fails on any drift (run by `scripts/verify.sh`
  and the pre-commit hook).
- `python3 ci/check-versions.py --fix` copies plugin.json versions into marketplace.json.
- `python3 ci/release.py` does Conventional-Commit-driven per-plugin bumps, then syncs.

Never hand-edit a version in marketplace.json — bump plugin.json (or let `release.py`
do it) and run `--fix`.

**Changelogs — both root and per-plugin.** The repo keeps a hand-curated root
`CHANGELOG.md` ([Keep a Changelog](https://keepachangelog.com/) format) *and* per-plugin
`plugins/<name>/CHANGELOG.md` files. They are complementary: the root file aggregates
program-level changes (cross-plugin work, repo tooling, governance) with an
`## [Unreleased]` section you append to in your PR; the per-plugin files are written by
`ci/release.py` from Conventional Commits and are authoritative for per-plugin versions.
Update whichever applies — both, when a change is both plugin-scoped and program-level.
See `docs/adr/0008-root-changelog.md`.

Tests for the version tooling: `python3 -m pytest ci/tests/`
(or `uv run --with pytest python -m pytest ci/tests/`).

## Shared patterns and coupling

Cross-plugin conventions to know before editing — this is the whole coupling story,
deliberately kept to one section rather than a spec.

**Vendored hook runtime (discipline → learning, stewardship).**
`scripts/hook_flags.py` and `scripts/run_with_flags.py` are byte-identical across the
three hook-bearing plugins because the install cache delivers each plugin as an
isolated per-version subtree — a repo-level shared lib can never ship. The canonical
copies live in `plugins/discipline/scripts/`; the files are plugin-agnostic (the env
prefix is derived from the hook id namespace, so `learning:*` ids answer to
`LEARNING_*` vars with zero per-plugin patching). Workflow: **edit the canonical copy
only**, run `python3 ci/check-vendored-sync.py --fix` to propagate, and let
`verify.sh`/pre-commit/CI catch anything that drifts. Canonical tests in
`plugins/discipline/tests/` cover all copies — don't re-add per-plugin duplicates
(duplicate test basenames also break repo-root pytest collection).

**Runtime-control env vars.** Every hook routed through `run_with_flags.py` obeys
`<PREFIX>_HOOK_PROFILE=minimal|standard|strict` and `<PREFIX>_DISABLED_HOOKS=<csv>`,
where `<PREFIX>` is the hook id's namespace uppercased. Exception: the retrospective
plugin's two hooks are plain bash, ungated by design.

**Metadata gates.** `ci/lint-frontmatter.py` (presence + parseability of
name/description on every SKILL.md and agent file) and `ci/gen-skill-index.py --check`
(docs/skill-index.md must match frontmatter) both run in `verify.sh`. After adding or
renaming a skill/agent: `python3 ci/gen-skill-index.py --write` and stage the index.

**Repo-marker detection.** aether's hooks resolve their target repo by content
markers (not hardcoded paths), the same style as stewardship's `language_detect.py`.
Prefer that pattern for any new repo-aware hook.

**Context routing — keep machine-specific config out of the repo.** Anything tied to a
particular machine, account, or private project (hardware specs, local model tiers,
identity, secrets) belongs in `~/.claude/context/` or another user-level location — never
committed here. The marketplace ships **generic templates** only (e.g.
`plugins/orchestration/configs/tiers.json` and `context/hardware-profile.template.md` use
`<GPU model>` / `<N> GB VRAM` placeholders; a plugin's `init` scaffolds the real
`~/.claude/context/*.local.*` from them). Before committing, make sure no real machine,
corporate, or identity token leaks into tracked files — the `NOTICE`/secret-scan gates and
the publish-safety review catch the obvious cases, but the rule is: **publishable repo,
private context.** See `docs/adr/0005-context-routing.md`.
