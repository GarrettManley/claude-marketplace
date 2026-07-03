---
status: active
author: Garrett Manley
created: 2026-06-23
diataxis: reference
---

# Release process

Releases are **local-only**. A maintainer runs `ci/release.py` on their machine; it
reads Conventional Commits, bumps each plugin's version, writes changelogs, commits, and
creates per-plugin tags. CI (`.github/workflows/ci.yml`) is **verification-only and must
never tag or publish** — it mirrors the local pre-merge gate across a tri-OS matrix and
stops there.

There is no publish step in the traditional sense: the "registry" is this git repo.
Consumers point Claude Code at `garrettmanley/claude-marketplace` and self-heal on
`/plugin marketplace update`, which re-reads `.claude-plugin/marketplace.json` at the
new HEAD.

## Changelogs: root and per-plugin

The repo maintains **two** changelog surfaces:

- **Root `CHANGELOG.md`** — hand-curated, [Keep a Changelog](https://keepachangelog.com/)
  format, program-level. It aggregates cross-plugin work, repo tooling, and governance
  changes, with an `## [Unreleased]` section contributors append to in their PRs. It is
  **not** written by `ci/release.py`.
- **Per-plugin `plugins/<name>/CHANGELOG.md`** — written by `ci/release.py` from
  Conventional Commits, authoritative for each plugin's per-version release notes. The
  canonical form is a **single H1** (e.g., `# <plugin> changelog`), followed by an intro
  block (standard Keep a Changelog preamble), then `## <version>` sections in newest-first
  order. `ci/release.py` preserves this structure by inserting new version sections
  **between** the intro block and the first existing version section, so the newest changes
  always appear first after the intro.

These are complementary, not duplicative (see `docs/adr/0008-root-changelog.md`). When
cutting a release, fold the relevant `## [Unreleased]` entries into a new versioned
section in the root file by hand; `release.py` continues to own the per-plugin files.

## Version source of truth

`plugins/<name>/.claude-plugin/plugin.json` is the **single source of truth** for a
plugin's version — the install cache keys off it.

`.claude-plugin/marketplace.json` carries a copy of each plugin's version in its entry.
That copy is a **derived duplicate**, not an independent value. Never hand-edit a version
there. It is kept honest by `ci/check-versions.py`:

```bash
# Fail (exit 1) on any drift between marketplace.json and plugin.json,
# or any mismatch between the marketplace entry set and the on-disk plugin set.
python3 ci/check-versions.py --check

# Copy each plugin.json version into its marketplace.json entry.
python3 ci/check-versions.py --fix
```

`--check` runs inside `scripts/verify.sh`, so it fires on every pre-commit and in CI; a
drifting marketplace version fails the gate. `--fix` only touches the `version` field of
each entry — description, keywords, and every other field are preserved. `ci/release.py`
reuses `check-versions.py`'s `sync()` so a release leaves the two files consistent by
construction.

## How `ci/release.py` decides the bump

For each plugin on disk (one `plugin.json` per `plugins/<name>/.claude-plugin/`):

1. Find the last tag matching `<name>-v*` (sorted by version). If there is **no** such
   tag at all, the plugin has no baseline: `plan()` skips it (no bump) and the run
   prints a notice to establish the baseline with `--tag` — its current `plugin.json`
   version is the first release (ADR-0012), never bumped over full history.
2. Collect commits in `<last-tag>..HEAD` whose Conventional-Commit **scope equals the
   plugin name**. A commit with no matching scope is ignored for that plugin — scope is
   how a commit is attributed to a plugin.
3. Compute the highest-precedence bump implied by those commits:

   | Commit | Bump |
   |--------|------|
   | `!` after the type/scope, or `BREAKING CHANGE` in the body | major |
   | `feat` | minor |
   | `fix` / `perf` | patch |
   | anything else (`docs`, `chore`, `refactor`, `test`, …) | no bump |

4. If no commit is release-worthy, the plugin is skipped. Otherwise apply the bump to the
   current `plugin.json` version (`major` → `X+1.0.0`, `minor` → `X.Y+1.0`, `patch` →
   `X.Y.Z+1`).

Commit subjects are parsed as `type(scope)!: description`; subjects that don't match
Conventional-Commit form are ignored. The bump is the single strongest signal across all
of a plugin's commits — one `feat` plus three `fix`es is one minor bump, not four
releases.

## Running a release

`--dry-run` is the default and writes nothing — it prints the plan and the changelog
sections that *would* be generated:

```bash
python3 ci/release.py --dry-run
```

When the plan looks right, `--apply` performs the release:

```bash
python3 ci/release.py --apply
```

`--apply`, for every plugin with a release-worthy change:

1. Writes the new version into `plugins/<name>/.claude-plugin/plugin.json`.
2. Inserts a new `## <version>` section (grouped into Breaking / Features / Fixes) into
   `plugins/<name>/CHANGELOG.md` between the file's preamble (H1 + intro) and the first
   existing version section, preserving the intro directly below the H1 and maintaining
   newest-first ordering. Each changelog is validated to contain exactly one H1 via the
   `ci/lint-changelog.py` gate, which runs in the pre-commit gate and in CI.
3. After all plugins are bumped, runs `sync()` to propagate the new versions into
   `.claude-plugin/marketplace.json`.
4. Creates **one** release commit: `chore(release): <name>@<ver>, <name>@<ver>, …`.

`--apply` does **not** tag. Push the branch (no tags yet) and open the PR:

```bash
git push -u origin <branch>
```

After the PR is **squash-merged**, tag on `main` — where the released commit actually
lives, so the tag can never be orphaned by the squash (see
`docs/adr/0012-tag-after-merge.md`):

```bash
git checkout main && git pull
python3 ci/release.py --tag      # tags each untagged current version at HEAD + pushes
```

`--tag` is idempotent (a no-op once every current version is tagged); add `--no-push`
to create the tags without pushing. If `release.py --dry-run`/`--apply` ever reports a
tag is "not an ancestor of HEAD," a squash orphaned it — re-point it before releasing:
`git tag -f <tag> <correct-commit> && git push --force origin <tag>`.

## The v1.0.0 tags are created by hand

`release.py` bumps from a previous version. The initial `1.0.0` for each plugin is the
baseline — it is **tagged by hand**, not produced by the bump logic. Create one annotated
tag per plugin at the v1.0 commit:

```bash
git tag discipline-v1.0.0
git tag evidence-v1.0.0
# … one per plugin
git push --tags
```

After that, those tags become the `<name>-v*` markers `release.py` reads as the
"since" point, and all subsequent bumps are driven by Conventional Commits.

## How consumers get the new version

There is nothing to publish. Once the release commit and tags are on `main`, a consumer
picks up the new versions with:

```
/plugin marketplace update garrettmanley
```

Claude Code re-reads `.claude-plugin/marketplace.json` at the latest HEAD and installs the
listed versions. Because `marketplace.json` is kept in lockstep with each `plugin.json`,
the version a consumer resolves is exactly the one the release wrote.

## Invariants

- **CI never tags or publishes.** `.github/workflows/ci.yml` has `permissions: contents:
  read` and runs only `scripts/verify.sh`, the pytest suites with the ≥90% coverage gate,
  and the OS-specific linters. If you find yourself wanting CI to cut a release, that's a
  design violation — releases stay local.
- **plugin.json leads, marketplace.json follows.** Bump `plugin.json` (or let `release.py`
  do it) and run `check-versions.py --fix`. The reverse never holds.
- **Scope attributes a commit to a plugin.** A commit with the wrong scope (or none) won't
  bump the plugin you expect. Write `feat(<plugin>): …`, not `feat: …`.
