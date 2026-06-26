---
name: horizon-scanning
description: Use periodically (monthly cadence) to identify SOTA local models 7B-14B and new MCP servers worth adopting. Prevents model lock-in by re-evaluating tier assignments in `configs/tiers.json` against current benchmarks. Triggered manually, or surfaced as a DUE reminder by the stewardship plugin's nightly steward on a monthly cadence (it reminds; the scan itself stays interactive).
version: 0.1.0
dependencies: []
---

# Horizon Scanning

Keeps the orchestration plugin's tier assignments "best-in-class" by periodically re-evaluating against published benchmarks.

## Scanning Protocol

When triggered, you MUST:

- Search for "State of the Art (SOTA) 7B-14B local models" for tool-calling and chain-of-thought.
- Check the [MCP Server Gallery](https://github.com/modelcontextprotocol/servers) for new integrations worth adding.
- Compare current tier model benchmarks (`configs/tiers.json`) against new entries.
- After completing the sweep (whether or not a tier is swapped), reset the stewardship steward's cadence clock so its nightly DUE reminder clears: `python "$(claude plugin root stewardship@garrettmanley)/scripts/horizon_scan_schedule.py" --mark-done`. The steward only *reminds* on a monthly cadence — it cannot run this scan headless (see `docs/adr/0010-horizon-scan-cadence-reminder.md`).

## Re-evaluation Logic

If a candidate model consistently outperforms the current Reasoning or Tooling tier on Tier 1 benchmarks AND fits the VRAM ceiling defined in `configs/tiers.json`:

1. **Plan**: Propose a load-test implementation plan (one representative task per tier capability listed in `tiers.json`).
2. **Vet**: Run the load test on real workloads. Pay attention to: t/s under VRAM contention, JSON output validity, tool-calling precision.
3. **Swap**: Update `configs/tiers.json` with the new model. Bump the orchestration plugin version. Document the swap in a marketplace commit message ("orchestration: swap Reasoning tier from X to Y per benchmark Z").

## Authoritative Sources

Tier 1 (treat as authoritative):

- **[Hugging Face Open LLM Leaderboard](https://huggingface.co/spaces/open-llm-leaderboard/open_llm_leaderboard)** — comprehensive but watch the eval freshness date.
- **[Ollama Library](https://ollama.com/library)** — new model availability + popularity metrics.
- **Anthropic / OpenAI / Google developer blogs** — for general-purpose breakthroughs that often cascade to local models within 2-3 months.

Tier 2 (corroborate before acting):

- Independent benchmark blogs (artificialanalysis.ai, The Pragmatic Engineer, etc.).
- Reddit r/LocalLLaMA — fast pulse on community benchmarks but heavily anecdotal.

## When to Run

- **Monthly cadence**: routine sweep, low-effort. Mark items worth investigating.
- **On benchmark drop**: when a major leaderboard update lands, prioritize the sweep.
- **On new tier need**: if a project's needs don't fit the existing tiers (e.g., need a vision model, or a multilingual specialist), use this skill to scout.

## Anti-patterns

- **Don't swap tiers based on a single benchmark.** Cross-reference at least two.
- **Don't ignore the VRAM ceiling.** A 13B model that's 1% better but partial-offloads is a regression against your VRAM target (see `configs/tiers.json`).
- **Don't fork tiers.** If projects need different models, they can override via project-level config — keep the marketplace tier definitions canonical.
