# Plugin Schema Gotchas

Distilled from [`affaan-m/everything-claude-code`](https://github.com/affaan-m/everything-claude-code) at commit [`4774946d`](https://github.com/affaan-m/everything-claude-code/blob/4774946db57a072f9b878f233a80f2ec6f5ac342/.claude-plugin/PLUGIN_SCHEMA_NOTES.md) (MIT licensed). Cross-verify against your current Claude Code release before relying — these constraints have shifted across versions historically (see the [flip-flop history](#flip-flop-history-for-the-hooks-field) below).

This document captures undocumented but enforced constraints of the Claude Code plugin manifest validator. The validator is strict and opinionated; the most common failure mode is a vague `Invalid input` error on a manifest that looks reasonable.

## TL;DR cheat sheet

1. `version` is **mandatory** — even if some example manifests omit it.
2. Do **not** declare `agents` — `agents/*.md` files are auto-discovered. Adding the field causes `agents: Invalid input`.
3. Do **not** declare `hooks` for the standard `hooks/hooks.json` — auto-loaded in Claude Code v2.1+. Declaring it errors with `Duplicate hooks file detected`.
4. Include `"mcpServers": {}` if your plugin ships a root `.mcp.json` you don't want auto-bundled into Claude plugin installs.
5. `commands` and `skills` are **arrays**, never strings — even for a single entry.

## The `agents` field: don't add

The validator rejects any form of `agents` in `plugin.json` — string path, array of paths, array of directories. Error:

```
agents: Invalid input
```

Agent `.md` files under `agents/` are discovered automatically by convention. They do not need to be declared.

If you see `Invalid input` and your manifest has `agents` in it, that's the cause.

## The `hooks` field: don't add (for the standard file)

Claude Code v2.1+ automatically loads `hooks/hooks.json` from any installed plugin by convention. Declaring it explicitly in `plugin.json` produces:

```
Duplicate hooks file detected: ./hooks/hooks.json resolves to already-loaded file.
The standard hooks/hooks.json is loaded automatically, so manifest.hooks should
only reference additional hook files.
```

**Additional hook files (not the standard `hooks/hooks.json`)** *can* be declared. Only the standard path must be omitted.

### Flip-flop history (for the `hooks` field)

These commit SHAs are from **`affaan-m/everything-claude-code`**, not this repo. They document how Claude Code's behavior changed across versions:

| Commit (in ecc) | Action | Trigger |
|---|---|---|
| `22ad036` | ADD hooks | "hooks not loading" |
| `a7bc5f2` | REMOVE hooks | "duplicate hooks error" (ecc #52) |
| `779085e` | ADD hooks | "agents not loading" (ecc #88) |
| `e3a1306` | REMOVE hooks | "duplicate hooks error" (ecc #103) |

Root cause: pre-v2.1 Claude Code required explicit `hooks` declaration; v2.1+ auto-loads. If you upgrade Claude Code and your hooks stop loading, this table is the first place to look.

## The `"mcpServers": {}` opt-out

Claude Code auto-discovers a plugin-root `.mcp.json` and bundles those MCP servers into the plugin install. If you don't want that — typically because the resulting MCP tool names exceed 64 characters and get rejected by strict OpenAI-compatible gateways — explicitly opt out by including:

```json
{
  "mcpServers": {}
}
```

The overlong tool names look like `mcp__plugin_<marketplace>_<plugin>_<server>__<tool>`. With a long marketplace + plugin + server identifier, even a normal tool name can blow the 64-char limit.

**Current state of `garrettmanley/claude-marketplace`:** No plugin currently ships a root `.mcp.json`, so this gotcha doesn't bite today. But if any plugin starts shipping MCP definitions, add the opt-out unless you want them auto-bundled.

## Field shape rules

`commands`, `skills`, and any `hooks` reference are **always arrays**, even for a single entry:

```json
{
  "commands": ["./commands/"],
  "skills": ["./skills/"]
}
```

Strings are not accepted. The validator errors generically.

## Validator behavior notes

- `claude plugin validate` is stricter than some marketplace previews. Validation may pass locally but fail during install.
- Errors are often generic (`Invalid input`) and do not indicate root cause.
- Cross-platform installs (especially Windows) are less forgiving of path assumptions. Use POSIX-style paths in manifests (`./hooks/x.json`, not `.\\hooks\\x.json`).
- Treat the validator as hostile and literal. Choose verbosity over convenience.

## Minimal known-good `plugin.json`

```json
{
  "name": "your-plugin",
  "version": "0.1.0",
  "description": "What this plugin does in one sentence.",
  "author": { "name": "Garrett Manley", "email": "garrettmanley@gmail.com" },
  "license": "MIT"
}
```

That's it. No `agents`, no `hooks`, no `commands`/`skills` unless you have non-conventional paths. Convention-based auto-discovery handles the rest.

## Anti-patterns

These look correct but get rejected:

- String values where arrays are required
- `"agents"` declared in any form
- `"hooks"` declared for the standard `hooks/hooks.json`
- Missing `version`
- Relying on inferred paths instead of explicit ones
- Assuming marketplace install behavior matches local `claude plugin validate` output
- Removing `"mcpServers": {}` when the plugin also ships a root `.mcp.json` (re-enables auto-bundling)

## Applicability notes

### Current compliance snapshot (2026-05-15)

All 11 plugin manifests in `plugins/*/.claude-plugin/plugin.json` were audited and comply with the rules above:

| Plugin | `version` | No `agents` | No `hooks` | Notes |
|---|---|---|---|---|
| `discipline` | `0.2.0` | ✓ | ✓ | Has `hooks/hooks.json`; relies on auto-discovery (correct) |
| `aether` | `0.1.0` | ✓ | ✓ |  |
| `agentic` | `0.1.0` | ✓ | ✓ |  |
| `evidence` | `0.1.0` | ✓ | ✓ |  |
| `orchestration` | `0.1.0` | ✓ | ✓ |  |
| `stewardship` | `0.1.0` | ✓ | ✓ |  |
| `windows` | `0.1.0` | ✓ | ✓ |  |
| `docs` | `1.1.0` | ✓ | ✓ | Verified 2026-06-25 (`--strict` pass) |
| `review` | `1.1.0` | ✓ | ✓ | Verified 2026-06-25 (`--strict` pass); 16 agents auto-discovered from `agents/` |
| `retrospective` | `1.1.0` | ✓ | ✓ | Verified 2026-06-25 (`--strict` pass); `hooks/hooks.json` auto-discovered |
| `git` | `1.1.0` | ✓ | ✓ | Verified 2026-06-25 (`--strict` pass) |
| `learning` | `1.2.0` | ✓ | ✓ | Verified 2026-06-25 (`--strict` pass); `hooks/hooks.json` auto-discovered |

None ship a root `.mcp.json`, so the `mcpServers` opt-out is not currently relevant.

> **2026-06-25 audit:** the four Phase-5 plugins (`docs`, `review`, `retrospective`,
> `git`) and the later-added `learning` plugin were validated with
> `claude plugin validate ./plugins/<name> --strict` and confirmed to carry no
> `agents`/`hooks`/`mcpServers` keys (relying on directory auto-discovery). The
> per-plugin version columns above for the original seven predate the 1.x releases
> and are left as the historical snapshot.

### When to revisit this doc

- Any new plugin added to the marketplace
- Any Claude Code minor-version upgrade (the v2.1+ auto-load behavior could shift again)
- Any time you see `Invalid input` or `Duplicate hooks file` errors on install

### Incidents log

(None to date. Append entries when a real-world failure exposes a new gotcha.)

## Caveats (verify before relying)

- **`PostToolUseFailure` event:** ecc declares it in `hooks/hooks.json:248` against the official schema URL, but it does not appear in stock Claude Code's documented event list. Verify against [`json.schemastore.org/claude-code-settings.json`](https://json.schemastore.org/claude-code-settings.json) before lifting any `PostToolUseFailure` hooks.
- **The "v2.1+" auto-load claim:** Assertion is from ecc's doc, not from a Claude Code release note we've personally seen. The current marketplace uses Claude Code v2.x and behavior matches the doc, but if you upgrade Claude Code and hooks stop loading, check release notes.

## Further reading

The full ecc source doc, with sections we omitted for brevity (contributor recommendations, philosophical framing): [PLUGIN_SCHEMA_NOTES.md @ 4774946d](https://github.com/affaan-m/everything-claude-code/blob/4774946db57a072f9b878f233a80f2ec6f5ac342/.claude-plugin/PLUGIN_SCHEMA_NOTES.md).
