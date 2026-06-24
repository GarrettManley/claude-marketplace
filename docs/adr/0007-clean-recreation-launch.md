---
status: accepted
author: Garrett Manley
created: 2026-06-23
diataxis: reference
---

# 0007. Clean repo recreation for the public v1.0 launch

## Status

Accepted

## Context

The dev repo accumulated a private history: internal path references, draft commit
messages, issue threads, and pull-request bodies that were scoped to a private
context and were never intended to be public. Git-history rewrites (`filter-repo`,
`bfg`) erase commits and blobs, but they cannot remove GitHub-side residue:
closed issues, PR descriptions, `refs/pull/*` refs, and the web-visible event
timeline. Those persist on a renamed or force-pushed repo regardless of what the
local tree contains.

The 12-plugin marketplace is stable at `1.0.0` (tagged per plugin), the CI gate
(`scripts/verify.sh`) is passing across a tri-OS matrix, and test coverage is at or
above the 90% threshold. There is no in-flight work that requires continuity with
the dev history.

## Decision

Ship the public v1.0 via a clean repo recreation:

1. **Rename** the existing private repo to an archive name (e.g.
   `claude-marketplace-dev`). Visibility stays private. All history is preserved
   there for reference.

2. **Create** a new public repo under the same owner/name
   (`GarrettManley/claude-marketplace`). This produces a blank GitHub slate with no
   issues, PRs, or `refs/pull/*`.

3. **Squash** the working tree into a single identity-pinned commit:

   ```bash
   git checkout --orphan public-v1
   git add -A
   git commit --author="Garrett Manley <garrettmanley@gmail.com>" \
     -m "chore: initial public release — v1.0.0"
   git push origin public-v1:main
   ```

4. **Push tags** for each plugin's `1.0.0` baseline to the new remote:

   ```bash
   git push origin --tags
   ```

5. **Update** the install URL in documentation to point at the new repo once it is
   live and the install smoke-test passes.

The single squashed commit is the source-of-truth `HEAD` on the public repo.
Subsequent releases follow the existing `ci/release.py` → `git push --follow-tags`
flow unchanged.

## Consequences

**Positive**

- No private context (commit messages, path fragments, issue text) is reachable
  via the GitHub API, `refs/pull/*`, or the web timeline.
- The public commit graph is minimal; consumers reading history see exactly one
  baseline commit before the first `release.py`-generated tag.
- The dev archive repo remains intact and private; no history is destroyed.

**Negative / mitigations**

- Any bookmarked links to the old repo (issues, PR URLs) become 404s after the
  rename — acceptable given the repo was private.
- `marketplace.json` consumers who pinned the old remote URL must update to
  the new one; the install path (`garrettmanley/claude-marketplace`) is unchanged
  for Claude Code's marketplace resolver, so `/plugin marketplace update
  garrettmanley` continues to work once the new remote is in place.
- Annotated tags must be re-created or re-pushed to the new remote; the
  `release.py` bump logic reads them as the "since" baseline, so they must be
  present before the first post-launch release run.
