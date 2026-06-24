# Agent & Workflow Orchestration Defaults

Standing policy for the Claude Code Agent tool (subagents) and dynamic Workflow tool.
This is the **efficient baseline** — `ultracode` and `+Nk` budget directives still escalate
to maximum effort on top of it. This policy ships with the `orchestration@garrettmanley`
plugin and is injected at session start by its `SessionStart` hook; it is the canonical
baseline.

## Standing Workflow authorization (category-based)

Workflows are **pre-authorized — no per-task ask** — for these task shapes:

- **Code review / audit** — multi-dimension find → adversarial verify.
- **Deep research / multi-source investigation** — fan-out search → deep-read → cited synthesis.
- **Structured codebase map** — the request is for a ranked/layered/indexed view across
  modules or services. Casual orientation questions ("how does X work?") stay single-agent.
- **Migrations & repo-wide sweeps** — discover sites → transform → verify; use worktree
  isolation when agents mutate files in parallel.
- **Multi-perspective design** — judge panel of independent approaches, scored synthesis.

Scale fan-out to the request wording: "check / look at" → 2–3 agents, single-vote verify;
"thoroughly / audit / comprehensive" → larger pool + 3-vote adversarial verify. Outside these
categories, use single agents or propose the workflow with rough scope first. Trivial or
conversational turns never get a workflow.

## Agent tool: delegate + parallelize by default (with floor)

- Codebase searches and exploration go to **Explore subagents** when the scope is more than
  ~3 files or file locations are unknown. Single-file, known-path lookups stay inline —
  delegation overhead exceeds the win. Main context is reserved for synthesis, decisions,
  and edits.
- Independent work items fan out as **parallel Agent calls in a single message** — never
  serially when there's no dependency.
- Once a search is delegated, don't duplicate it inline.

## Model routing for delegated agents

Match model tier to agent role via the Agent tool's `model` param / Workflow `agent()`
`opts.model`:

| Tier | Route here |
|------|------------|
| `haiku` | Mechanical sweeps: file inventories, grep-and-summarize, frontmatter/convention checks, bulk verification votes, log triage |
| `sonnet` | Standard exploration, well-scoped implementation inside known patterns, test-writing in defined areas |
| omit (inherit session model) | Synthesis, judging/scoring, architecture, security-sensitive review, final verification, anything ambiguous |

Rule of thumb: **route down only when the task is mechanical and the output is cheaply
verifiable**; a down-routed agent doing judgment work fails silently. When unsure, inherit.

## Model-independence

These defaults apply regardless of which Claude model drives the session — capability tier
changes fan-out *size* and routing, not whether delegation happens.

## Precedence vs `orchestration:local-orchestrator`

Explore/Agent subagents are the **default for interactive codebase searches and code-quality
work**, superseding the local-orchestrator skill's ">10 files → local model" trigger.
The local tier runs on llama-server (llama.cpp) rather than Ollama
(binary + GGUFs at your configured paths per `configs/tiers.json`, one-model-per-process; see this plugin's
`configs/tiers.json`). Reserve the local tier for high-volume log/history compaction and
offline batch loops where cloud tokens would be wasted.

## Guardrails

- When delegated work touches a directory that contains your employer's private repos, **restate the corporate-repo exclusion**
  (`your-employer-repo*`, `your-private-repo/`) in the agent/workflow prompt — don't assume subagents
  inherit it.
- If a workflow bounds coverage (top-N, sampling, no-retry), log what was dropped —
  silent truncation reads as full coverage.
