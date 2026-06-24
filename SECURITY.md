# Security

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.x     | Yes       |
| < 1.0   | No        |

Only the latest 1.x release receives security fixes. Pre-1.0 versions are unsupported.

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Use [GitHub private security advisories](https://github.com/GarrettManley/claude-marketplace/security/advisories/new)
(the **Security** tab → **Report a vulnerability**). This keeps the disclosure private until a fix is ready.

Include:

- Affected plugin(s) and version
- Steps to reproduce or a proof-of-concept
- Impact assessment (what an attacker could do)
- Any suggested fix, if you have one

You'll receive an acknowledgement within 5 business days. If the vulnerability is confirmed, a fix and advisory will be published together once the patch is ready. Coordinated disclosure is preferred — please allow a reasonable window before publishing independently.

## What this repo ships

The `evidence` plugin includes a `secret-scan` PreToolUse hook that detects credential patterns in writes before they hit disk, and a scope-binding gate that restricts agent writes to declared paths. These are defense-in-depth controls for Claude Code sessions, not a substitute for repository-level secret scanning (which should be configured separately on any repo that uses these plugins).

The `discipline` plugin's `gateguard` hook gates destructive operations (`rm -rf`, force-pushes, DDL drops) until the agent presents investigation facts. It is not a security boundary — it is an agent-discipline gate.

## Responsible disclosure

We follow coordinated disclosure:

1. Reporter notifies us privately via the Security tab.
2. We confirm receipt within 5 business days and triage the report.
3. We develop and test a fix, targeting a timeline proportional to severity.
4. We publish a patch release and a GitHub Security Advisory simultaneously.
5. Reporter is credited in the advisory unless they prefer otherwise.
