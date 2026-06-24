---
status: active
author: Garrett Manley
created: 2026-06-23
diataxis: explanation
---

# Architecture

How `garrettmanley/claude-marketplace` is laid out and why. This is the
maintainer-and-contributor map: the install model that drives the structure, plugin
anatomy, the vendored hook runtime and the gate that keeps it honest, runtime-control
env vars, context routing, and the verify-only CI posture.

For per-plugin behaviour, read each plugin's own `README.md`. For manifest validator
gotchas, read [`plugin-schema-gotchas.md`](plugin-schema-gotchas.md). This doc covers
the cross-plugin structure those don't.

## Repository shape

```
.claude-plugin/marketplace.json   # the marketplace manifest — lists every plugin
plugins/<name>/                    # one self-contained subtree per plugin (12 of them)
ci/                                # verification + release tooling (Python, stdlib-only gates)
scripts/verify.sh                  # the portable gate set (CI + pre-commit run this)
templates/                         # per-project settings.local.json archetype snippets
docs/                              # skill-index, schema gotchas, this file
.githooks/                         # committed pre-commit hook (opt in via core.hooksPath)
```

The marketplace installs over GitHub. A consumer runs:

```
/plugin marketplace add garrettmanley/claude-marketplace
/plugin install discipline@garrettmanley
```

`garrettmanley` is the marketplace install name (from `marketplace.json`'s `name`
field); `<plugin>@garrettmanley` is how a plugin is addressed once the marketplace is
added.

## The install model drives the structure

The single most load-bearing fact about this repo: **Claude Code's plugin cache
delivers each plugin as an isolated, per-version subtree.** When a consumer installs
`discipline@garrettmanley`, they get a verbatim copy of `plugins/discipline/` at a
pinned version — nothing above it, nothing beside it. Other plugins in the marketplace
are not present in that install.

Two consequences follow, and they explain almost every structural decision below:

1. **A plugin must be self-contained.** Everything a plugin needs at runtime —
   skills, hooks, scripts, config — lives under `plugins/<name>/`. There is no
   repo-level shared library a plugin can import, because the repo root is not part of
   the install.
2. **Cross-plugin code reuse means vendoring, not importing.** When two plugins need
   the same runtime helper, the file is copied into each subtree byte-for-byte. A CI
   gate enforces that the copies stay identical (see
   [Vendored hook runtime](#vendored-hook-runtime)).

`plugins/<name>/.claude-plugin/plugin.json` is the source of truth for a plugin's
version, because the install cache keys off it. The matching entry in
`marketplace.json` is a derived duplicate, kept in sync by tooling — never hand-edited
(see [Versioning and release](#versioning-and-release)).

## Plugin anatomy

A plugin subtree uses Claude Code's standard layout. Not every plugin has every
directory; components are auto-discovered by their directory, so presence is what
enables them.

```
plugins/<name>/
  .claude-plugin/plugin.json   # manifest: name, version, description, keywords (required: name + version)
  skills/<skill>/SKILL.md      # skills (frontmatter: name, description) + supporting files
  commands/*.md                # slash commands
  agents/*.agent.md            # subagents (frontmatter: name, description)
  hooks/hooks.json             # hook bindings (event -> matcher -> command)
  hooks/*.py, *.sh             # hook implementations
  scripts/*.py                 # shared/helper scripts the hooks call
  context/*.md                 # context files + *.template.md generic templates
  configs/*.json               # reference data (e.g. orchestration tiers)
  README.md, CHANGELOG.md      # per-plugin docs + release history
  tests/                       # pytest suite (CI-only; not shipped to consumers' runtime)
```

`plugin.json` carries `name` and `version` (both mandatory) plus description, author,
repository, license, and keywords. It must **not** declare `agents` or `hooks` — those
are auto-discovered from their directories, and declaring them errors at install time.
`commands`, `skills`, and `keywords` must be arrays when present. `ci/validate-plugins.py`
enforces all of this pre-merge so a malformed manifest fails here rather than with a
vague "Invalid input" at a consumer's install.

Inside a hook command, `${CLAUDE_PLUGIN_ROOT}` resolves to the installed plugin's root,
so hooks reference their own scripts by relative path:

```json
{
  "type": "command",
  "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/run_with_flags.py\" \"${CLAUDE_PLUGIN_ROOT}/hooks/inject_issues.sh\" discipline:session-start:inject-issues minimal,standard,strict"
}
```

The three positional arguments after the wrapper are the hook script, the hook id, and
the profile CSV — the inputs to the runtime-control system below.

## Vendored hook runtime

Three plugins carry hooks gated by the same runtime-control system: `discipline`
(canonical), `learning`, and `stewardship`. They share two files:

- `scripts/hook_flags.py` — profile/disable-list logic.
- `scripts/run_with_flags.py` — the wrapper every gated hook command invokes.

These files are **byte-identical** across the three plugins. They have to be vendored
rather than imported from a shared location, because — per the install model — no
repo-level shared lib ships with a plugin. The canonical copies live in
`plugins/discipline/scripts/`; the other two carry verbatim copies.

The files are written **plugin-agnostic** so byte identity is achievable with zero
per-plugin patching. The env-var prefix is derived at runtime from the hook id's
namespace, not hardcoded:

```python
def _env_prefix(hook_id: str) -> str:
    head = hook_id.split(":", 1)[0].strip()
    return head.upper().replace("-", "_") if head else "PLUGIN"
```

So `discipline:post-edit:frontmatter-lint` answers to `DISCIPLINE_*` vars, a
`learning:*` id to `LEARNING_*`, a `stewardship:*` id to `STEWARDSHIP_*` — the same
bytes, different behaviour, decided entirely by the id passed on the command line.

`run_with_flags.py` reads stdin once (capped at 1 MiB), checks whether the hook is
enabled, and if so dispatches it. Python hooks are run via `importlib` (no second
interpreter cold-start); shell hooks are spawned via `bash -c` with the script content
inlined (to dodge Windows path-mangling). It fails open: import or runtime errors in a
hook print to stderr and return 0, so a broken hook never breaks the hook chain. When a
hook is disabled, the wrapper exits 0 **without writing stdout** — important because
SessionStart treats stdout as `additionalContext`, and echoing the raw event JSON would
leak `session_id` / `transcript_path` into the model's context.

### The gate that keeps copies identical

`ci/check-vendored-sync.py` byte-compares each vendored file in `learning` and
`stewardship` against the canonical copy in `discipline` and fails on any divergence:

```bash
python3 ci/check-vendored-sync.py          # check; exit 1 on drift
python3 ci/check-vendored-sync.py --fix    # copy canonical over the consumers
```

The workflow is therefore: **edit the canonical copy only**, run `--fix` to propagate,
and let `verify.sh` / pre-commit / CI catch anything that drifted. Canonical tests in
`plugins/discipline/tests/` cover all copies — don't re-add per-plugin duplicate tests
(duplicate test basenames also break repo-root pytest collection).

A second gate, `ci/verify_hook_runtime_controls.py`, asserts that **every** command in
`discipline`'s `hooks.json` routes through `run_with_flags.py`. Without it, a
contributor could add a hook that silently bypasses the disable list for itself; CI
rejection on first review is the cheapest fix.

## Runtime-control env vars

Every hook routed through `run_with_flags.py` obeys two environment variables, where
`<PREFIX>` is the hook id's namespace uppercased (`DISCIPLINE`, `LEARNING`,
`STEWARDSHIP`). They toggle hooks per-session, per-shell, or per-CI-job without editing
`hooks.json`.

### `<PREFIX>_HOOK_PROFILE`

Selects which hooks fire at all. Values: `minimal` | `standard` (default) | `strict`.
Each hook's command line carries the profile CSV it's enabled under, so a hook only
fires when the active profile is in its list. Invalid values fall back to `standard`.

```bash
# Only SessionStart injections; skip all edit-time discipline
DISCIPLINE_HOOK_PROFILE=minimal claude

# Maximum strictness (e.g. discipline's spec-companion-check is strict-only)
DISCIPLINE_HOOK_PROFILE=strict claude
```

### `<PREFIX>_DISABLED_HOOKS`

Comma-separated list of hook ids to silently disable regardless of profile.
Case-insensitive, whitespace-trimmed.

```bash
# Disable one hook for a session
DISCIPLINE_DISABLED_HOOKS=discipline:pre-edit:todo-issue claude
```

A disabled hook's wrapper exits 0 with no stdout — the hook chain continues as if it had
succeeded.

The `retrospective` plugin is the documented exception: its two hooks are plain bash and
ungated by design, so they aren't covered by this system.

See the per-plugin README (e.g. `plugins/discipline/README.md`) for the full hook-id
table and per-profile matrix.

## Context routing

Some plugins want to inform a session about the machine it's running on — local-model
tiers, hardware ceilings, orchestration defaults. The rule that keeps the repo
publishable is a split between generic and machine-specific:

- **Generic, ships in-repo.** Templates and defaults that are safe to publish live under
  the plugin, e.g. `plugins/orchestration/context/hardware-profile.template.md` and
  `plugins/orchestration/configs/tiers.json` (placeholder paths, generic VRAM ceilings).
  These are reference data a skill reads — no hook parses them at runtime.

- **Machine-specific, lives in `~/.claude/context/`, never in the repo.** Real binary
  paths, real model directories, real hardware specs go in a machine-local file the
  consumer creates from the template (e.g. `~/.claude/context/hardware-profile.md`, or a
  private `~/.claude/context/tiers.local.json` that overrides the committed generic
  `tiers.json`). The local file takes precedence; the committed file stays generic.

For policy that *should* travel with the plugin, the pattern is a SessionStart hook that
injects an in-repo context file as `additionalContext`. `orchestration`'s
`inject_orchestration_context.py` reads its bundled `context/agent-orchestration.md`,
strips frontmatter, and emits it into the session — so the orchestration baseline ships
with the plugin instead of depending on a user-level context file. It fails open: a
missing or garbled file prints nothing and exits 0.

The discriminant: anything that identifies a specific machine, account, or private path
stays out of the repo; anything generic enough to publish ships as a `*.template.md` or
a placeholder config.

## Versioning and release

`plugins/<name>/.claude-plugin/plugin.json` is the **single source of truth** for a
plugin's version; the install cache keys off it. Its `marketplace.json` entry is a
derived duplicate:

- `python3 ci/check-versions.py --check` fails on any drift (run by `verify.sh` and
  pre-commit).
- `python3 ci/check-versions.py --fix` copies plugin.json versions into
  `marketplace.json`.
- `python3 ci/release.py` does the per-plugin bump end-to-end.

Never hand-edit a version in `marketplace.json` — bump plugin.json (or let `release.py`
do it) and run `--fix`.

`ci/release.py` is Conventional-Commit-driven and **per-plugin**: for each plugin it
finds commits since that plugin's last `<name>-v*` tag, keeps only those whose
Conventional-Commit scope matches the plugin name, computes the highest implied bump
(breaking → major, `feat` → minor, `fix`/`perf` → patch), writes the new version,
prepends a per-plugin `CHANGELOG.md` section, syncs `marketplace.json`, then makes one
release commit and a per-plugin tag. It defaults to `--dry-run`; `--apply` writes.

## CI is verify-only; releases are local

`.github/workflows/ci.yml` **verifies and never publishes**. There is no tag-on-merge,
no auto-release — releases stay local via `ci/release.py`, run deliberately by the
maintainer.

The portable gate set lives in one script, `scripts/verify.sh`, so CI and the
committed pre-commit hook run the **exact same checks**:

```bash
bash scripts/verify.sh   # exit 0 = clean; exit non-zero = failures on stdout
```

`verify.sh` runs, in order: `lint-no-bare-python`, `ruff`, `check-versions --check`,
`validate-plugins`, `verify_hook_runtime_controls`, `check-vendored-sync`,
`lint-frontmatter`, `gen-skill-index --check`, and `check-notice`. CI wraps that with
the parts that need OS-specific tooling a committer may not have locally: a tri-OS matrix
(Ubuntu + Windows required, macOS non-blocking) on Python 3.12 and 3.13, the per-plugin
pytest suites behind a **≥90% line-coverage gate**, and the OS-specific linters
(`shellcheck` on Linux, `PSScriptAnalyzer` on Windows).

To wire the pre-commit hook after cloning:

```bash
python3 -m pip install -r requirements-dev.txt
git config core.hooksPath .githooks
```

`docs/skill-index.md` is generated, not hand-maintained: `gen-skill-index.py --check`
fails the build on drift, so after adding or renaming a skill or agent, run
`python3 ci/gen-skill-index.py --write` and stage the index.

See [`CONTRIBUTING.md`](../CONTRIBUTING.md) for the full contributor and maintainer
workflow.
