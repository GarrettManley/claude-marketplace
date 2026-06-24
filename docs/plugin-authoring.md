---
status: active
author: Garrett Manley
created: 2026-06-23
diataxis: how-to
---

# Plugin Authoring

How to add a new plugin to this marketplace. Read [`plugin-schema-gotchas.md`](plugin-schema-gotchas.md)
alongside this — it documents the undocumented-but-enforced constraints of the Claude Code
manifest validator that the steps below assume you already know.

The golden rule of this repo: **convention-based auto-discovery over declaration.** You declare
the bare minimum in `plugin.json` and let Claude Code find the rest by directory layout. Most
manifest failures come from over-declaring.

## Directory layout

A plugin is a directory under `plugins/<name>/`. The name is the install slug
(`<name>@garrettmanley`) and must match across the directory name, the `plugin.json` `name`, and
the marketplace entry.

```
plugins/<name>/
├── .claude-plugin/
│   └── plugin.json          # manifest (required)
├── agents/                  # *.agent.md — auto-discovered
├── commands/                # *.md slash commands — auto-discovered
├── skills/
│   └── <skill-name>/
│       └── SKILL.md         # one dir per skill — auto-discovered
├── hooks/
│   └── hooks.json           # auto-loaded by convention (do NOT declare it)
├── scripts/
│   ├── init.sh              # optional project initializer (Unix)
│   └── init.ps1             # optional project initializer (PowerShell 7+)
├── tests/                   # pytest, if the plugin ships Python
└── README.md
```

Every directory is optional except `.claude-plugin/plugin.json`. Ship only what the plugin needs.

## `plugin.json` required fields

`name` and `version` are the only mandatory fields. `version` is mandatory even though some
upstream examples omit it — `ci/validate-plugins.py` and the install cache both reject a manifest
without it.

A known-good minimal manifest:

```json
{
  "name": "your-plugin",
  "version": "0.1.0",
  "description": "What this plugin does in one sentence.",
  "author": { "name": "Garrett Manley", "email": "garrettmanley@gmail.com", "url": "https://garrettmanley.com" },
  "repository": "https://github.com/garrettmanley/claude-marketplace",
  "license": "MIT",
  "keywords": ["one", "two", "three"]
}
```

What you must **not** put in `plugin.json`:

- **No `agents` field.** Agent files under `agents/` are auto-discovered. Declaring `agents` in
  any form (string, array of paths, array of dirs) makes the validator reject the manifest with
  `agents: Invalid input`.
- **No `hooks` field for the standard `hooks/hooks.json`.** Claude Code auto-loads that file by
  convention; declaring it errors with `Duplicate hooks file detected`. (Only *additional*,
  non-standard hook files may be declared — most plugins never need that.)

What must be an array when present (never a bare string):

- `commands`, `skills`, `keywords` — `ci/validate-plugins.py` enforces the array type. In
  practice you usually omit `commands` and `skills` entirely and rely on directory
  auto-discovery; only declare them if your files live in non-conventional paths.

See `plugin-schema-gotchas.md` for the full validator constraint set, the `"mcpServers": {}`
opt-out, and the flip-flop history behind the `hooks`-field rule.

## Agents (`*.agent.md`)

Drop agent files in `agents/` using the `*.agent.md` naming convention. They are discovered
automatically — no manifest entry. Each needs YAML frontmatter:

```markdown
---
name: spec-code-drift-checker
description: Use this agent when ... (when-to-invoke triggers the dispatcher keys on).
tools: Bash, Grep, Read
---

You are a specialist reviewer. Your job is narrow and precise: ...
```

`name` and `description` are required (see the frontmatter gate below); `tools` is optional and
scopes the agent's tool access.

## Skills (`SKILL.md` frontmatter)

Each skill is a directory under `skills/<skill-name>/` containing a `SKILL.md`. The frontmatter
must carry a non-empty `name` and `description`:

```markdown
---
name: your-skill
description: Use when ... — a trigger-shaped description so the model knows when to reach for it.
version: 0.1.0
dependencies: []
---

# Your Skill

(skill body)
```

`ci/lint-frontmatter.py` enforces only **presence and parseability** of `name` and `description`
across every `plugins/*/skills/*/SKILL.md` and `plugins/*/agents/*.md`. It checks the frontmatter
block opens and terminates with `---`, both keys exist, and neither is empty (description is also
sanity-bounded at 4096 chars). Description *quality* is deliberately out of scope. Run it directly:

```bash
python3 ci/lint-frontmatter.py
```

## Component authoring conventions

The linter enforces structure, not quality. These conventions keep the marketplace signal-dense
rather than "AI-slop" noise — follow them for every new skill, agent, and command:

- **Trigger-shaped descriptions.** Write each `description` in the third person as *what it does +
  when to use it*, leading with a concrete trigger: `Use when …` / `Use PROACTIVELY when …`. Name
  the specific artifacts, file types, or situations that should fire it. Vague descriptions
  ("helps with documentation") don't get invoked at the right time.
- **Model tiering (agents).** Subagent frontmatter accepts an optional `model` field. **Omit it**
  for judgment work — reviewers, analysers, design/architecture agents — so they inherit the
  session's (strong) model; pinning a judgment agent to a weaker model silently degrades it. Only
  set `model: haiku` for genuinely mechanical agents (file inventories, grep-and-summarize, bulk
  frontmatter/convention checks) whose output is cheaply verifiable. When unsure, omit.
- **Progressive disclosure (skills).** Keep `SKILL.md` itself a navigable decision tree: when to
  use it, the steps/interface, and links. Push deep material (large tables, long examples, full
  reference text) into sibling files (`references/…`, `dimensions/…`) the skill points at, so the
  always-loaded body stays small and the detail loads on demand.

## Wiring into `marketplace.json`

`.claude-plugin/marketplace.json` lists every plugin. `plugin.json` is the single source of truth
for the **version**; the marketplace entry duplicates it and is kept honest automatically — never
hand-edit the version there.

Add an entry to the `plugins` array. `source` must be `./plugins/<dir>` and `name` must match the
plugin.json `name`:

```json
{
  "name": "your-plugin",
  "source": "./plugins/your-plugin",
  "description": "Same one-sentence description as plugin.json.",
  "version": "0.1.0",
  "author": { "name": "Garrett Manley" },
  "keywords": ["one", "two", "three"]
}
```

Then sync the version field from plugin.json instead of typing it by hand:

```bash
python3 ci/check-versions.py --fix
```

`--fix` copies each plugin.json version into its marketplace entry and prints what changed.
`check-versions.py --check` (run by `scripts/verify.sh` and the pre-commit hook) fails on any
drift, and `validate-plugins.py` independently fails if a plugin with a manifest is missing from
`marketplace.json` (orphan detection) or if names mismatch. Validate before committing:

```bash
python3 ci/validate-plugins.py
```

## Regenerating the skill index

`docs/skill-index.md` is a generated discovery table of every skill and agent — do not hand-edit
it. After adding or renaming any skill or agent, regenerate it:

```bash
python3 ci/gen-skill-index.py --write
```

Stage the result. `gen-skill-index.py --check` (also in `scripts/verify.sh`) fails when the file
drifts from the frontmatter it is generated from, so a stale index blocks the pre-merge gate.

## The `init.sh` / `init.ps1` contract

A plugin that needs project-local or user-level scaffolding ships a matched pair of initializers
in `scripts/`: `init.sh` (Unix / macOS / Git-Bash) and `init.ps1` (PowerShell 7+). They are
invoked by the user, not auto-run on install. The pair is held to a single behavioral contract so
their conventions match across every plugin:

- **Idempotent.** A second run with no flags is a no-op. Detect the already-configured state and
  exit 0 without rewriting anything.
- **`--force` / `-Force`.** Overwrite existing files with fresh templates.
- **`--quiet` / `-Quiet`.** Suppress all output (used in tests and CI).
- **Single status line.** Emit exactly one line in the form `[init:<plugin>] <STATE> — <detail>`,
  where `<STATE>` is one of `CONFIGURED`, `already configured`, `skipped`, or `FAILED`. Honor
  `--quiet` by printing nothing.
- **Skip cleanly out of scope.** If the plugin scaffolds repo-local config and the cwd is not a
  git repo, emit a `skipped` status and exit 0 — not an error.
- **Fail loud on real errors.** Missing bundled templates or unwritable targets emit `FAILED` and
  exit 1.

The two scripts must be behaviorally equivalent — same flags, same status grammar, same exit
codes. The bash side runs under `set -euo pipefail`; the PowerShell side under
`Set-StrictMode -Version Latest` and `$ErrorActionPreference = 'Stop'`. Behavioral idempotency is
covered by `plugins/<name>/tests/test_init.py`, which drives `init.sh` as a subprocess. CI lints
the scripts cross-OS (`shellcheck -S warning` on Linux, `PSScriptAnalyzer` on Windows), so keep
both clean.

> **Context routing.** Initializers that touch user-level config scaffold the real file from a
> committed **generic template** (placeholders like `<GPU model>` / `<N> GB VRAM`) into a
> user-level location (e.g. `~/.claude/context/*.local.*`). Never commit a real machine, account,
> identity, or secret value into the repo — publishable repo, private context. See
> `docs/adr/0005-context-routing.md` and the CONTRIBUTING "Shared patterns" section.

## Pre-commit checklist

Before committing a new plugin, run the full portable gate set — the same one the pre-commit hook
and CI run:

```bash
bash scripts/verify.sh
```

It runs, in order: `lint-no-bare-python`, `ruff`, `check-versions --check`, `validate-plugins`,
hook-runtime-controls, `check-vendored-sync`, `lint-frontmatter`, `gen-skill-index --check`, and
the `NOTICE` attribution gate. Exit 0 means clean. The pytest suites and cross-OS shell linters
run in CI (they need OS-specific tools a committer may not have locally); see `CONTRIBUTING.md`
for the dev-toolchain setup and the maintainer pre-merge gate.
