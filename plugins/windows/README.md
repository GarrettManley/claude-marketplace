# windows@garrettmanley

Windows + PowerShell reference pack for Claude Code sessions. Surfaces the recurring
friction points — CRLF, BOM encoding, `/tmp` absence, `$env:` syntax, path separators,
PS version divergence, file locks — as on-demand reference docs pulled by a single skill,
so baseline session context stays small and the knowledge is shared across all your
Windows projects.

## Install

Enable from the `garrettmanley` marketplace:

```
/plugin marketplace add garrettmanley/claude-marketplace
/plugin enable windows@garrettmanley
```

## Components

### Skills

| Skill | Description |
|-------|-------------|
| `windows-patterns` | Field guide for Windows + PowerShell development decisions: which shell to use, what allowlist pattern to add, and how to handle the common Windows-isms. Routes to the appropriate reference doc. |

### Reference docs

The skill loads these on demand; they are not injected at every session start.

| Document | Contents |
|----------|----------|
| `skills/windows-patterns/references/WINDOWS_ISMS.md` | Catalog of Windows-specific traps (CRLF in multi-line edits, BOM/encoding table by tool, path separators, `$env:` vs `%NAME%`, `/tmp` absence, `find` disambiguation, file locks) with mitigations. |
| `skills/windows-patterns/references/PS_VERSION_ROUTING.md` | Decision tree for `pwsh` (PS 7+) vs `powershell.exe` (PS 5.1): default to PS 7, drop to 5.1 for WMI process events, WinRT types, legacy COM, DSC v1, or scripts with multi-byte chars saved without BOM. |
| `skills/windows-patterns/references/ALLOWLIST_PATTERNS.md` | Copy-pasteable `.claude/settings.local.json` `permissions.allow` entries organized by category: system inspection, process management, network/DNS, package managers, git, environment variable reads. |

### Hooks

None. Reference docs are pulled on demand by the skill.

## Usage

The `windows-patterns` skill triggers automatically when Claude detects a Windows or
PowerShell tooling decision. You can also invoke it explicitly:

```
Use the windows-patterns skill to figure out whether this script needs pwsh or powershell.exe.
```

```
Check windows-patterns — I'm getting a silent failure on a multi-line Edit.
```

```
I need the allowlist entry for Get-Process. See windows-patterns.
```

Typical scenarios:

- **Choosing a shell**: "Should this automation script use `pwsh` or `powershell.exe`?" →
  skill routes to `PS_VERSION_ROUTING.md`.
- **CRLF edit failure**: Edit reports success but the file didn't change → `WINDOWS_ISMS.md`
  covers single-line-edit workaround and `.gitattributes` `eol=lf` pattern.
- **Permission prompt reduction**: Adding a new PowerShell command to an existing project →
  `ALLOWLIST_PATTERNS.md` has narrow-scoped entries ready to paste.
- **BOM confusion**: PS 5.1 script with non-ASCII output is mojibaking → `WINDOWS_ISMS.md`
  encoding table and `WINDOWS_ISMS.md` + `PS_VERSION_ROUTING.md` explain when BOM is required.

## Configuration

This plugin has no environment variable overrides and no `.local.md` config file. It ships
reference docs only; there is no hook behavior to tune.

To reduce permission prompts in a Windows project, copy the relevant entries from
`skills/windows-patterns/references/ALLOWLIST_PATTERNS.md` into your project's `.claude/settings.local.json`:

```json
{
  "permissions": {
    "allow": [
      "PowerShell(Get-Process *)",
      "PowerShell($env:PATH)",
      "Bash(winget list)"
    ]
  }
}
```

The built-in `fewer-permission-prompts` skill can scan your past transcripts and suggest
patterns based on commands you have already approved repeatedly.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Edit` tool reports success but the file is unchanged | CRLF mismatch: `old_string` uses `\n` but the file has `\r\n`. Switch to single-line edits, or use `Write` to rewrite the whole file. See `skills/windows-patterns/references/WINDOWS_ISMS.md`. |
| PS 5.1 script outputs `â€"` instead of `—` (mojibake) | The file was saved as UTF-8 without BOM. In VS Code, bottom-right encoding → "Save with Encoding" → "UTF-8 with BOM". PS 7 doesn't have this requirement. |
| `Register-WmiEvent` fires in test but silently no-ops in production | PS 7.6 drops WMI process-creation events. Run the WMI subscription with `powershell.exe` (PS 5.1). See `skills/windows-patterns/references/PS_VERSION_ROUTING.md`. |
| Python code opens `/tmp/foo` and gets `FileNotFoundError` on Windows | `/tmp` does not exist on Windows outside of Git Bash. Use `tempfile.gettempdir()` or `os.environ['LOCALAPPDATA'] + r'\Temp'`. See `skills/windows-patterns/references/WINDOWS_ISMS.md`. |

## Cross-platform notes

This plugin is Windows-only by design. The skill's trigger description scopes it to
"Windows + PowerShell environment" decisions, so it will not fire on macOS or Linux
sessions. There are no `init.sh` / `init.ps1` scripts — install is purely via
`/plugin enable`.

The reference docs assume Windows 11 and PS 7+ as the baseline, with explicit callouts
for the cases where PS 5.1 is required. Forward slashes work in most Windows path contexts
and are preferred in JSON / Python strings to avoid double-backslash escaping.
