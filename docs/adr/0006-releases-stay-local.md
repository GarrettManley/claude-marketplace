# 0006. Releases stay local; CI is verify-only

**Status:** Accepted

## Context

`ci/release.py` is the only tool that bumps plugin versions, writes changelogs, creates the release
commit, and applies per-plugin tags (e.g. `discipline-v1.2.0`). The CI workflow
(`.github/workflows/ci.yml`) mirrors the local pre-merge gate (`scripts/verify.sh`) across a
tri-OS matrix and adds pytest with a ≥90% coverage gate. That is the full scope of what CI does.

The workflow file's opening comment makes this explicit:

```
# Verification-only CI: mirrors the local pre-merge gate (scripts/verify.sh) plus
# the pytest suites + coverage gate, across a tri-OS matrix. Releases stay local via
# ci/release.py — this workflow must never tag or publish (release flow is local-only).
```

The workflow is granted only `permissions: contents: read`. It has no write access to refs
and no credentials for any registry. Granting write access to automate tagging would remove the
human review step between "CI passed" and "version shipped" — acceptable for a multi-maintainer
project with approval workflows, not for a solo-maintained repo where the maintainer is also the
only reviewer.

The reopen condition for this decision is **multi-maintainer operation**: if the repo gains
co-maintainers with code-review authority, a gated release workflow (manual `workflow_dispatch`
trigger, restricted to maintainers) becomes worth the added complexity.

## Decision

`ci/release.py --apply` runs locally by the maintainer. CI does not run `release.py` and must
never be granted the permissions required to do so.

## Consequences

- The release workflow is one local command followed by `git push --follow-tags`. The
  single release commit and its tags are visible in the PR history before they reach consumers.
- There is no risk of an automated job creating a tag for a commit that has not passed a human
  judgment step.
- A contributor cannot trigger a release by merging a PR — releases remain intentional, not
  incidental.
- If the maintainer's local environment is broken (e.g., a missing dependency in
  `requirements-dev.txt`), a release is blocked until that is fixed. This is an acceptable
  tradeoff; `scripts/verify.sh` should catch toolchain gaps before they reach the release step.
