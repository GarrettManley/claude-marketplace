# agentic@garrettmanley

Opinionated meta-overlay for AI app development. Routes to the right official plugin
(`claude-api`, `agent-sdk-dev`, `mcp-server-dev`, `plugin-dev`) and applies consistent
defaults that the individual plugins don't enforce: which model IDs to use, prompt caching
on by default, a minimum eval bar before shipping, and a canonical repo layout. For
engineers starting new Anthropic SDK integrations, MCP servers, or custom agents who want
a single entry point that wires everything together without duplicating the underlying
documentation.

## Install

```
/plugin marketplace add garrettmanley/claude-marketplace
/plugin enable agentic@garrettmanley
```

This plugin routes to the **official Anthropic plugins** `claude-api`, `agent-sdk-dev`,
`mcp-server-dev`, and `plugin-dev`. They are not shipped in this marketplace — add them
separately from their own source before the routing targets will resolve. Enable them
individually or as part of your standard plugin set.

## Components

| Component | Type | Description |
|-----------|------|-------------|
| `agentic-app-setup` | Skill | Entry point for new AI apps and foundation reviews; routes to the right official plugin while applying house defaults |

### Reference docs (bundled)

These are not skills — they are context documents the `agentic-app-setup` skill references
and that you can read directly.

| File | Contents |
|------|----------|
| `references/PROMPT_CACHING.md` | Standard 4-block cache pattern, hit-rate targets by app type, cache TTL math, conversation history caching |
| `references/EVAL_DISCIPLINE.md` | Golden test set structure, scoring strategies (exact / rule-based / LLM-judge), CI regression gate template, framework recommendations |

## Usage

Invoke the skill when:

- **Starting a new project.** The skill determines whether you need the Anthropic SDK,
  Agent SDK scaffolding, an MCP server, or a Claude Code plugin, then delegates to the
  appropriate entry point while applying the house defaults below.

- **Adding an Anthropic integration to an existing app.** The skill applies the model ID,
  caching, and eval conventions to what's already there.

- **Reviewing an existing AI app's foundations.** Model IDs out of date? Caching disabled?
  No evals? The skill audits against the checklist.

Example invocations (type in Claude Code):

```
Start a new AI app — Python client for the Anthropic API, multi-turn chat agent
```

```
Add Anthropic SDK to my existing TypeScript service
```

```
Review my agent's foundations — check model IDs, caching, eval coverage
```

```
Build a new MCP server with HTTP transport
```

The skill itself **routes**; it does not duplicate the deep SDK or MCP knowledge already in
the official plugins. If you know which official plugin you need, you can invoke that one
directly (`claude-api`, `agent-sdk-dev:new-sdk-app`, `mcp-server-dev:build-mcp-server`,
`plugin-dev:create-plugin`).

### House defaults applied

| Default | Value |
|---------|-------|
| Reasoning / complex tasks | latest Opus — at time of writing `claude-opus-4-8` (1M context: `claude-opus-4-8[1m]`) |
| Daily driver | latest Sonnet — `claude-sonnet-4-6` |
| Latency / cost-sensitive | latest Haiku — `claude-haiku-4-5` |
| Prompt caching | ON for any reused content ≥ 1024 tokens |
| Minimum golden test cases before v1 | 20 |
| CI eval gate | Hard block on > 5% score regression from main |
| LLM-judge usage | Supplementary only; never the sole regression gate |
| Prompts | Files, not inline strings (`src/prompts/`) |
| Observability | Log model, input tokens, output tokens, cache read/write tokens, cost per call |

Model IDs cycle quarterly. Always check the `claude-api` skill for the current latest before
committing a model ID to code.

### Canonical repo layout

For new agentic projects:

```
my-agent/
├── src/
│   ├── prompts/         # System prompts, tool definitions, few-shot examples — .md or .json
│   ├── tools/           # Tool function implementations
│   ├── agent.py         # (or agent.ts) the main loop
│   └── evals/
│       ├── golden/      # 001-happy-path.json, 002-empty-input.json, …
│       ├── runner.py
│       └── results/     # historical runs (gitignore or LFS)
├── tests/               # Unit tests for tools, NOT prompt outputs
├── pyproject.toml       # (or package.json) — pin SDK version
├── .env.example         # ANTHROPIC_API_KEY and any other required vars
├── README.md
└── docs/
    ├── prompts.md       # Prompt design rationale
    └── evals.md         # Eval results, regression history
```

## Configuration

This plugin has no hooks and no runtime env vars of its own. Configuration is entirely
through the official companion plugins it delegates to.

If you want to lock model IDs for a project so they are not overridden, add them to your
project's `CLAUDE.md` or `.ai/context/` files. The skill will respect those over its own
defaults.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Skill fires but the routing target ("use `agent-sdk-dev:new-sdk-app`") does nothing | The target plugin is not enabled. These are official Anthropic plugins, not part of this marketplace — add the plugin from its own source, then run `/plugin enable agent-sdk-dev` (or the relevant plugin) and retry. |
| Model IDs in the skill output look stale | Model IDs in `SKILL.md` reflect the knowledge cutoff. Run the `claude-api` skill directly to get the current latest before writing code. |
| Prompt caching code example fails at runtime | Check that the SDK version in `pyproject.toml` / `package.json` supports `cache_control`. The 4-block pattern requires SDK ≥ the version that shipped `cache_control` on message blocks — see `references/PROMPT_CACHING.md` for the exact API shape. |
| Eval runner template references `check_regression.py` but the file does not exist | The eval templates in `references/EVAL_DISCIPLINE.md` are starting-point scaffolds, not generated files. Copy the CI snippet and implement `check_regression.py` for your project's scoring shape. |

## Cross-platform

The plugin ships no init scripts and no hooks, so there are no platform-specific execution
differences. The Python SDK examples in `SKILL.md` and the reference docs use the Anthropic
Python client; the TypeScript equivalent follows the same API shape via
`@anthropic-ai/sdk`. Both work on Windows, macOS, and Linux without modification.
