# Changelog

All notable changes to the **windows** plugin are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres
to [Semantic Versioning](https://semver.org/).

## 1.1.0 — 2026-06-24

- Relocated the reference docs (`WINDOWS_ISMS.md`, `PS_VERSION_ROUTING.md`, `ALLOWLIST_PATTERNS.md`) into the skill directory at `skills/windows-patterns/references/` so the skill loads them on demand; README paths updated to match.
- Manifest enriched with `$schema`, `homepage`, `repository`, `license`, `keywords`, and category metadata.

## 1.0.0 — initial public release

First public release. Windows + PowerShell helpers: copy-pasteable allowlist patterns for .claude/settings.local.json, PS5.1 vs PS7 routing decision tree, common Windows-isms (CRLF, BOM, $env:, path separators).
