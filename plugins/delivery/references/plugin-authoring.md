# Developing and dev-testing this plugin locally

This doc covers two things: the production flow that actually makes an edit to `delivery` live for a
session, and how to exercise a local change before publishing it. Both were verified empirically
against the `garrettmanley` marketplace; nothing here is hypothetical.

## Part A — the "make-it-live" checklist

A common mistake is treating "I edited the file" as "the session can see the change." It can't, until
four distinct steps run:

1. **Edit the plugin in the dev clone** (`Workspace/claude-marketplace/`, or a worktree of it) — never
   edit the install cache at `~/.claude/plugins/marketplaces/garrettmanley` directly.
2. **Commit, push to `main`.** Direct push works — no PR required (confirmed unprotected as of
   2026-06-30).
3. **`claude plugin marketplace update garrettmanley`** (or `update` with no name to refresh every
   registered marketplace). This pulls from GitHub, **not** the local working tree. This is the
   load-bearing trap: editing the dev clone and pushing does nothing to the live cache until this step
   runs.
4. **`claude plugin install delivery@garrettmanley`** (or `update` if already installed). "Pulled into
   the marketplace checkout" is not "installed" — a plugin can sit in the marketplace checkout and
   still be disabled for every session until this step runs.
5. **Reload the session** (restart Claude Code, or however your environment reloads plugins) to pick
   up the new skill content.

Stated plainly: **making a plugin change available = push to the default branch, then update the
marketplace, then install/update the plugin, then reload.** Four distinct steps, not one — skipping any
of them leaves a stale version live.

## Part B — local dev-test mechanism

You do not need to push and republish to try out a change. Two mechanisms work; only one is
recommended.

### Recommended: `claude --plugin-dir <path>`

Session-scoped, zero registry mutation. `claude --plugin-dir <path-to-plugin-dir>` loads a plugin for
that one session only — it does **not** touch `~/.claude/plugins/known_marketplaces.json`,
`installed_plugins.json`, or any marketplace checkout. This is the safest way to exercise local changes
before publishing. The flag is repeatable: `--plugin-dir A --plugin-dir B`.

A quick "did it even load" smoke check, non-interactive:

```
claude -p --plugin-dir <path-to-plugin-dir> "<prompt>" --output-format json
```

**Confirmed gotcha (load-bearing):** a plugin with a `dependencies` array in its `plugin.json` — as
`delivery` now has: `["docs", "retrospective"]` — **fails to load** via a standalone
`--plugin-dir <delivery-path>`. It surfaces a `dependency-unsatisfied` entry in `plugin_errors`, and
`delivery`'s skills are absent from the session's skill list. To dev-test `delivery` locally, pass
`--plugin-dir` for each declared dependency too:

```
claude --plugin-dir <worktree>/plugins/delivery --plugin-dir <worktree>/plugins/docs --plugin-dir <worktree>/plugins/retrospective
```

(Use the actual worktree path; this repo's plugins live under `plugins/<name>/`.) This needs to be an
**interactive** session to actually exercise `/deliver`'s lifecycle (plan mode, approval gates, etc.) —
the `-p`/`--output-format json` probe above is for the load smoke check, not for running the real
lifecycle. A shell alias/function that bakes in your worktree path and the dependency list is a
reasonable reader-side convenience if you dev-test often; it isn't shipped in this plugin because the
mechanism is already a single command.

### Alternative (works, but actively dangerous if cleaned up carelessly): `marketplace add <path> --scope local`

`claude plugin marketplace add <local-path> --scope local` works and creates a local-scope shadow,
correctly recorded in `<project>/.claude/settings.local.json` under `extraKnownMarketplaces` — this
part is clean and reversible by editing or removing that one file.

**However:** the marketplace's registered name comes from `marketplace.json`'s own `name` field, not
from anything you choose at the CLI — so a local-path add of this repo always registers as
`garrettmanley`, the same name as the live GitHub-sourced marketplace. There is **no way via this CLI
to register the same content under a different alias.**

**Confirmed dangerous (verified empirically, then remediated):** running
`claude plugin marketplace remove garrettmanley --scope local` to "clean up" after such a same-named
local add does **not** safely restore the prior GitHub-sourced registration. It deletes the user-scope
entry from `known_marketplaces.json` entirely, requiring a manual
`claude plugin marketplace add GarrettManley/claude-marketplace` to restore it.

**Do not use this as your primary dev-test path** — it's documented here only as a known-working-but-risky
alternative. If you do use it, you must explicitly re-add the GitHub source afterward and verify with
`claude plugin marketplace list` that the source shows `GitHub (GarrettManley/claude-marketplace)`, not
`Directory (...)`, before trusting the marketplace again.

## Read-only sanity checks

`claude plugin --help` and `claude plugin marketplace --help` are safe, read-only. Do not run
`marketplace add`/`remove` or `plugin install`/`uninstall` against the live `garrettmanley` registration
unless you mean to mutate user-scope state — see the warning above.
