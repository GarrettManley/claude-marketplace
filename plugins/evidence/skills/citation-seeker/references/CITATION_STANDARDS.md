# Citation Standards

Defines the "Threshold of Truth" for engineering documentation.

## Tier 1: Canonical (Automatic Authority)

- **RFCs**: Official Internet protocols (e.g. RFC 9110 HTTP semantics).
- **Official Documentation**: Vendor docs from the maintainer (`learn.microsoft.com`, `docs.aws.amazon.com`, `firebase.google.com`, `modelcontextprotocol.io`, `docs.anthropic.com`).
- **Peer-Reviewed Papers**: Found via Semantic Scholar, ACM Digital Library, IEEE Xplore, or arXiv.
- **Standards Organizations**: W3C, ISO, IEEE, IETF specifications.

## Tier 2: Expert (Requires Corroboration)

- **Primary Research Blogs**: Netflix Tech Blog, Uber Engineering, AWS Architecture, Anthropic engineering posts, Cloudflare blog technical posts.
- **Conference Talks**: From major conferences (Strange Loop, USENIX, RustConf) when the speaker is a recognized expert in the domain.
- **Reputable Books**: Recent (within 3 years for fast-moving fields), from publishers like O'Reilly, Manning, Pragmatic Bookshelf.

Tier 2 sources should be paired with a Tier 1 corroborator when used to anchor a load-bearing claim.

## Tier 3: Prohibited for Documentation

- Personal blogs (unless the author is a core maintainer of the technology being discussed).
- Reddit / Stack Overflow / Hacker News (use as **leads** to chase down primary sources, never as citations).
- Medium / Dev.to / dev-aggregator sites (same — leads only).
- LLM-generated summaries (including this one — verify before citing).

## Documenting Evidence

Every load-bearing fact in a spec must follow this format:

```
> "Fact statement here." [1]
>
> **Proof**: `cmd output snippet`  (for empirical claims)
> **Citation**: [1] URL to authoritative source.  (for external claims)
```

A single fact can have both — empirical proof from your own environment AND an external citation showing the documented behavior matches.
