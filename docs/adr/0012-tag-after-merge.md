---
status: active
author: Garrett Manley
created: 2026-06-25
diataxis: reference
---

# 0012. Release tags are born on `main` after the squash-merge, not on the feature branch

## Status

Accepted

## Context

`ci/release.py --apply` ran on a feature branch and created `<plugin>-v<version>` tags at the
branch commit (ADR-0006: releases are a local maintainer step; CI is verify-only). Release PRs are
**squash-merged**, which creates a *new* commit on `main` and discards the branch commit. The tag
still pointed at the discarded commit, so it was no longer an ancestor of `main`. The next
`release.py` run then computed its `<last-tag>..HEAD` range against that orphaned commit and saw the
squash commit as unreleased — proposing a spurious bump for an already-shipped plugin.

This forced a manual `git tag -f <tag> <squash-commit> && git push --force` reconciliation after
**every** release: five times across the marketplace-completion program (D2, D3, D4, D5, and the D5
hotfix). The toil was predictable and the failure mode (a silent spurious bump) was easy to miss.

## Decision

**Tags are created on `main`, after the merge — never on the feature branch.**

- `release.py --apply` bumps `plugin.json`, prepends the per-plugin CHANGELOG, syncs
  `marketplace.json`, and makes **one** release commit. It no longer creates any tag.
- A new `release.py --tag` mode is run on `main` after the PR squash-merges. It tags each plugin
  whose current `plugin.json` version has no `<plugin>-v<version>` tag, at `HEAD` (the merged
  commit), and pushes the tags. It is idempotent (a no-op once everything is tagged); `--no-push`
  creates without pushing.
- A guard in `--dry-run`/`--apply` refuses (exit 1) when any plugin's last tag is not an ancestor of
  `HEAD` — so a tag orphaned by some other path fails loud with a re-point hint instead of silently
  proposing a spurious bump.

Because the tag is created at the commit that actually lives on `main`, the squash can never orphan
it. The release workflow becomes: branch → `--apply` (no tag) → push branch → squash-merge → on
`main`, `--tag`.

## Consequences

**Positive**

- The squash-orphan is structurally impossible; the recurring manual reconciliation is gone.
- The guard turns any residual orphan (e.g. a reverted workflow, a hand-made tag) into a loud,
  actionable failure rather than a silent re-release.
- `--tag` is idempotent and self-describing, so a missed or repeated run is safe.

**Negative / mitigations**

- One extra command (`release.py --tag` on `main`) in the release runbook. Mitigation: it is a
  single idempotent step documented in `docs/release-process.md`, and it replaces the old
  `git push --follow-tags` step rather than adding net ceremony.
- A brief window between merge and `--tag` where `main` carries an untagged released version; a
  `--dry-run` in that window would propose re-releasing it. Mitigation: the maintainer runs `--tag`
  immediately after merge, and the change is small (the version commit is already on `main`).

This **refines** ADR-0006, it does not reverse it: `--tag` is still a local maintainer step, and CI
still never tags or pushes (`permissions: contents: read`). Cross-reference ADR-0006.
