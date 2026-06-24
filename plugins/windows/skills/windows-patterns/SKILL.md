---
name: windows-patterns
description: Use whenever working in a Windows + PowerShell environment and you need to make a tooling decision (which shell, what allowlist pattern, how to handle a Windows-ism like CRLF/BOM/path separator). Covers PS5.1 vs PS7 routing, copy-pasteable settings.local.json allowlist patterns, and the standard list of "things that bite you on Windows."
version: 0.1.0
dependencies: []
---

# Windows Patterns

Field guide for Windows + PowerShell-flavored development with Claude Code.

## When to use

- Configuring `.claude/settings.local.json` permissions on a Windows project — see `references/ALLOWLIST_PATTERNS.md`.
- Deciding whether a script needs PowerShell 7+ (`pwsh`) or Windows PowerShell 5.1 (`powershell.exe`) — see `references/PS_VERSION_ROUTING.md`.
- Hitting a CRLF, BOM, path-separator, or `$env:` issue and wanting the standard fix — see `references/WINDOWS_ISMS.md`.
- Authoring a new shell script that should work on this machine — apply the conventions from all three references.

## Quick rules

- **Default to `pwsh` (PowerShell 7+)** for new work. Only fall back to `powershell.exe` (PS 5.1) when you need WMI process events, WinRT types, or a legacy COM interop.
- **PS 5.1 scripts with em-dashes / box-drawing chars MUST be saved as UTF-8 with BOM**, otherwise they'll mojibake. PS 7 doesn't care.
- **Multi-line `Edit` fails silently on Windows CRLF files** — source files often have `\r\n` but `old_string` arrives `\n`-only. Use single-line edits or `Write` for full rewrites.
- **Never `cd` then run a multi-root build** — use `--manifest-path` (cargo), `--prefix` (npm), or `-C` (git) instead.

See each reference doc for the full treatment of its area.
