---
name: agentic-app-setup
description: Use when starting a new AI app project (Claude API integration, MCP server, custom agent) or when reviewing the foundations of an existing one. Routes to the right official plugin (claude-api / agent-sdk-dev / mcp-server-dev) for the specific task while applying the marketplace's standard defaults — latest models, prompt-caching, eval discipline, repo structure.
version: 0.1.0
dependencies: []
---

# Agentic App Setup

Opinionated wiring of the official Anthropic plugins into a coherent starting point.

## When to use

- Starting a brand-new AI app project (Python, TypeScript, or Rust client of the Anthropic API).
- Adding an Anthropic SDK integration to an existing app.
- Building an MCP server (local stdio, HTTP, or apps-SDK with widgets).
- Building a custom Claude Code subagent or skill that orchestrates multiple LLM calls.

## What this skill does (vs delegates)

This skill **routes**. It does not duplicate the deep knowledge already in the official plugins. The actual implementation guidance lives in:

| Need | Use |
|------|-----|
| Anthropic SDK, prompt caching, model migration | `claude-api` skill (already enabled) |
| New Claude Agent SDK app | `agent-sdk-dev:new-sdk-app` command |
| Build / package an MCP server | `mcp-server-dev:build-mcp-server` (entry point), then `build-mcpb` or `build-mcp-app` per deployment model |
| Custom Claude Code plugin | `plugin-dev:create-plugin` |

## House defaults (apply these)

Before writing the first SDK call, set these conventions:

### 1. Model IDs

Default to the latest stable models. **The `claude-api` skill is the source of truth for current model IDs — always check it before committing one to code.** Model IDs cycle quarterly, so treat the values below as a starting point, not a pin:

- **Reasoning + complex tasks**: latest Opus (at time of writing, `claude-opus-4-8`; 1M context variant `claude-opus-4-8[1m]`)
- **Daily driver**: latest Sonnet (`claude-sonnet-4-6`)
- **Latency-sensitive / cost-sensitive**: latest Haiku (`claude-haiku-4-5`)

### 2. Prompt caching

**On by default** for any system prompt or tool definition that repeats across turns. Cache TTL is 5 minutes — design the conversation flow to keep cache warm if you're paying for cache misses.

```python
# Python SDK example
client.messages.create(
    model="claude-sonnet-4-6",
    system=[{
        "type": "text",
        "text": "You are a helpful assistant.",
        "cache_control": {"type": "ephemeral"}
    }],
    messages=[...],
)
```

See `references/PROMPT_CACHING.md` for the full pattern catalog.

### 3. Eval discipline

Every agent gets evals. No production AI app should ship without:

- A **golden test set** of input/output pairs (≥ 20 cases for v1, growing over time).
- An **eval runner** that compares outputs to expected (rule-based for structured outputs, semantic for prose).
- A **regression gate** in CI that blocks merges when eval scores drop.

Reference frameworks: `inspect-ai`, `lighteval`, custom Python harness. See `references/EVAL_DISCIPLINE.md` for templates.

### 4. Repo structure

For new agentic projects, prefer:

```
my-agent/
├── src/
│   ├── prompts/         # System prompts, tool definitions, eval cases — all .md or .json, never inline strings
│   ├── tools/           # Tool function implementations
│   ├── agent.py         # Or agent.ts — the main loop
│   └── evals/           # Eval cases + runner
├── tests/               # Unit tests for tools, NOT for prompt outputs
├── pyproject.toml       # Or package.json — pin SDK version
├── .env.example         # Document required vars (ANTHROPIC_API_KEY, etc.)
├── README.md
└── docs/
    ├── prompts.md       # Prompt design rationale
    └── evals.md         # Eval results, regression history
```

Prompts as files (not inline strings) makes them diff-able, cache-able, and reviewable. Tools in their own dir keeps the agent loop readable.

### 5. Observability

For anything that ships to a user:

- Log every model call with: model, input tokens, output tokens, cache_read tokens, cache_creation tokens, total cost.
- Tag spans with task ID for traceability.
- Store user feedback (thumbs up/down at minimum) for eval set growth.

## Anti-patterns (block-on-sight)

- Hardcoded API keys in source.
- Inline prompts that repeat across files (cacheable + reviewable wins lost).
- "AI" code paths with no eval coverage.
- Logging that captures user PII or full conversation transcripts without consent.
- Using a deprecated model ID without a migration path.

## When NOT to use this skill

- Generic Python/TS work that happens to call OpenAI / Gemini / other providers — use the relevant provider's docs.
- Pure prompt engineering (writing the prompt, not the app around it) — that's `claude-api` directly.
- Cloudflare Workers AI — that's `cloudflare:agents-sdk`.
