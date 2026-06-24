---
name: citation-seeker
description: Use before generating public documentation, specs, blog posts, or any architectural claim that should hold up under scrutiny. Enforces high-fidelity engineering documentation by requiring authoritative, peer-reviewed, or canonical citations for technical claims.
version: 0.1.0
dependencies: []
---

# Citation-Seeker

Ensures documentation is substantiated by evidence and authoritative research.

## When to use

Invoke before drafting a spec, ADR, threat model, blog post, or any document another engineer (or you in six months) will rely on. Gather citations upfront — citations gathered before drafting are dramatically better than citations bolted on later.

## Core Directives

### 1. The Substantiation Rule

You are **forbidden** from making an architectural claim without:

- **Evidence**: A link to a `verification_cmd` pass in the workspace, or
- **Citation**: A link to a Tier 1 or Tier 2 authoritative source.

A claim with neither is unprovable and must be rewritten as a hypothesis or removed.

### 2. Research Protocol

When searching for citations, prioritize in this order:

1. **RFCs & Standards**: IETF, W3C, ISO, IEEE.
2. **Official Engineering Docs**: Vendor docs from the maintainer (Microsoft Learn, Anthropic docs, AWS docs, etc.).
3. **Peer-Reviewed Research**: ACM Digital Library, IEEE Xplore, Semantic Scholar, arXiv.

See `references/CITATION_STANDARDS.md` for the full tiered taxonomy and the canonical "Documenting Evidence" format.

## Verification Logic

Every citation must pass two checks:

- **Authority**: From the prioritized list above.
- **Temporal Relevance**: Reflects the current state of the field (check publish/update date — be skeptical of >3-year-old claims for fast-moving domains like AI/agentic systems).
