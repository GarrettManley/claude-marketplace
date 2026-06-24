# PowerShell + Windows Allowlist Patterns

Copy-pasteable entries for `.claude/settings.local.json` `permissions.allow` array.
Reduces permission prompt noise without granting blanket shell access.

## Read-only system inspection

```json
"Bash(Get-CimInstance Win32_Processor)",
"Bash(Get-CimInstance Win32_ComputerSystem)",
"Bash(Get-CimInstance Win32_VideoController)",
"Bash(systeminfo)",
"Bash(wmic *)",
"PowerShell(Get-CimInstance *)",
"PowerShell(Get-WmiObject *)",
"PowerShell(Get-Process *)",
"PowerShell(Get-Service *)",
"PowerShell($env:*)"
```

## Process management (read)

```json
"Bash(tasklist)",
"Bash(tasklist /FI *)",
"Bash(Get-Process)",
"Bash(Get-Process *)"
```

## Process termination — REQUIRES JUDGMENT, do not blanket-allow

```json
// Allow specific processes only:
"Bash(taskkill /IM ollama.exe /F)",
"Bash(Stop-Process -Name ollama -Force)"
// NOT: "Bash(taskkill *)"
```

## Network / DNS

```json
"Bash(nslookup *)",
"Bash(Test-NetConnection *)",
"Bash(Resolve-DnsName *)",
"Bash(Get-NetTCPConnection)",
"Bash(Get-NetTCPConnection *)"
```

## Package managers

```json
// winget (read)
"Bash(winget list)",
"Bash(winget list *)",
"Bash(winget search *)",
"Bash(winget show *)",

// winget (mutate) - case-by-case
"Bash(winget install *)",
"Bash(winget upgrade *)",

// Chocolatey (if used)
"Bash(choco list *)",
"Bash(choco search *)",
```

## Git operations (Windows-specific patterns)

```json
"Bash(git config --get core.autocrlf)",
"Bash(git ls-files --eol)",
"Bash(git status --short)"
```

## Environment variable inspection

```json
"PowerShell($env:PATH)",
"PowerShell($env:USERPROFILE)",
"PowerShell($env:LOCALAPPDATA)",
"PowerShell($env:APPDATA)",
"PowerShell($env:PROGRAMFILES)"
```

## Ollama (local LLM)

```json
"Bash(ollama list)",
"Bash(ollama ps)",
"Bash(ollama show *)",
"Bash(curl -s http://localhost:11434/api/tags)",
"Bash(curl -s http://localhost:11434/api/ps)",
"PowerShell(Invoke-RestMethod -Uri http://localhost:11434/api/tags)",
"PowerShell(Invoke-RestMethod -Uri http://localhost:11434/api/ps)"
```

## What NOT to allowlist

- `Bash(*)` — kills the entire permission system.
- `Bash(rm *)`, `Bash(Remove-Item *)`, `Bash(del *)` — too broad; allow specific targets only.
- `Bash(reg *)`, `Bash(regedit *)` — registry mutation should always prompt.
- `Bash(*--force*)`, `Bash(*--no-verify*)` — bypass-safety patterns should always prompt.

## Project-specific allowlist hygiene

When adding a new pattern:

1. Make it as narrow as possible (`Bash(npm test)` not `Bash(npm *)`).
2. Group by category (system inspection, build, deploy, etc.) with comments.
3. Re-review periodically — a pattern allowed for a one-off task often outlives its purpose.

The `fewer-permission-prompts` skill (built-in to Claude Code) can scan your transcripts and suggest patterns based on what you've actually approved repeatedly.
