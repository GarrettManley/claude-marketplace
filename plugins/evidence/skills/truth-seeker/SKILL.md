---
name: truth-seeker
description: Use before updating any context files, documentation, or making a claim that future work will rely on. Enforces high-fidelity engineering by requiring mandatory verification traces — every fact must have an internal proof (command output) or external citation (Tier 1/2 source) attached.
version: 0.1.0
dependencies: []
---

# Truth-Seeker

Enforces verification-first updates: no context file change without proof.

## When to use

Invoke before editing a context file (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.claude/`), updating documentation, or making any load-bearing claim future work will rely on. Every fact needs a verification trace — internal proof or external citation — before it lands.

## Core Directives

### 1. Mandatory Research Before Mutation

Before proposing a context-file change or making a load-bearing claim, you MUST:

- Consult any project context (`CLAUDE.md`, `GEMINI.md`, `.claude/`, `docs/`).
- Consult user-level context (`~/.claude/context/`).
- Run `Grep` / `Glob` / actual code reads to verify the documentation matches the current codebase. Memory and prior conversation context may be stale.

If the claim is about external behavior (an API, a library, a standard), use `WebFetch` or the `microsoft-docs` / `Context7` skills to fetch primary documentation.

### 2. Proof of Truth Protocol

Facts are only valid if they include a **Verification Trace**:

- **Internal**: A successful terminal command output (`grep` result, `cargo build` pass, `npm test` green, `python -c "..." → expected output`).
- **External**: A Tier 1 (Official) or Tier 2 (Expert) URL plus the relevant excerpt — not just the URL.

A claim with neither is a hypothesis. Mark it as such ("Hypothesis: ...") rather than as fact.

### 3. The "Stale Memory" Rule

When recalling something from prior conversation context or saved memory:

- **State the source** ("per the project memory", "per CLAUDE.md", "per my earlier search").
- **Verify if load-bearing** — recalled facts about file paths, function names, or schema shapes must be re-verified before being acted on. Refactors happen.
- **Update the memory** if the recalled state turns out to be wrong.

See `references/VERIFICATION_GUIDE.md` for the full tiered taxonomy and command patterns.
