# Verification Guide

Defines the source tiers and command patterns that make a claim verifiable.

## Tiered Source Definitions (mirrors citation-seeker)

### Tier 1: Canonical (Auto-Approval)

- Official documentation from the technology's maintainer.
- Official GitHub repositories (READMEs, Wikis, releases).
- Published RFCs, ISO/W3C/IEEE/IETF standards.

### Tier 2: Expert (Cross-Reference Preferred)

- Established engineering blogs from companies known for technical rigor.
- MDN Web Docs, Wikipedia (conceptual / historical).
- Highly-voted Stack Overflow answers from recognized contributors.

### Tier 3: Community (Leads Only)

- Medium, Reddit, YouTube, Hacker News.
- **Rule**: Never commit as Truth without a Tier 1/2 corroborator. Use these to find the leads, then verify against authoritative sources.

## Verification Command Patterns

### File / pattern existence
- `Grep` for symbol or string presence.
- `Glob` for path patterns.
- `Read` to confirm file content.

### Build / type pass
- `npm run build`, `npm run typecheck`
- `cargo build`, `cargo check`
- `pytest`, `python -m mypy`
- `dotnet build`

### Behavior verification
- Single test run: `cargo test --manifest-path <path> <name>`
- Integration test: project-specific harness commands
- Live API check: `curl` + `jq` with the documented endpoint and a known input/output pair

### Documentation lookup
- Microsoft tech: `microsoft-docs` skill.
- Generic library docs: `Context7` skill (resolve-library-id then query-docs).
- Cloudflare docs: `cloudflare:cloudflare` skill.
- Generic web: `WebFetch` + summarize, then quote the relevant section.

## When Verification Is Not Required

- Trivial editorial changes (typo fixes, prose reflows that don't change meaning).
- Pure refactors where behavior is preserved by tests (verify the tests pass; that IS the proof).
- Hypotheticals explicitly framed as such ("if we did X, then Y might happen").
