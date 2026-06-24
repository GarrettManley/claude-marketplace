# PowerShell Version Routing

Decision tree for picking `pwsh` (PS 7+) vs `powershell.exe` (PS 5.1).

## Default: PowerShell 7+ (`pwsh`)

Use for **all new work** unless one of the PS 5.1 cases below applies.

Why default to PS 7:
- Pipeline chain operators `&&` / `||` work like bash.
- Ternary `$cond ? $a : $b`, null-coalescing `??`, null-conditional `?.` operators.
- Cross-platform (works on Linux/macOS too if you ever port).
- Faster startup in recent versions.
- Active development — bug fixes land here, not in 5.1.
- Default file encoding is UTF-8 without BOM (modern, no surprises).

## Use Windows PowerShell 5.1 (`powershell.exe`) when

### 1. WMI process-creation events

`Register-WmiEvent` for process-creation/deletion silently no-ops in PS 7.6.

```powershell
# PS 5.1 only — works
Register-WmiEvent -Query "SELECT * FROM Win32_ProcessStartTrace" -Action { ... }
```

### 2. WinRT types

Loading WinRT types like `Windows.UI.Notifications.ToastNotificationManager` requires the `[Windows.Foundation.Metadata.ApiInformation, Windows.Foundation, ContentType=WindowsRuntime]` syntax that's only available in 5.1.

```powershell
# PS 5.1 only — needed for native Windows toast notifications
[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]
```

### 3. Legacy COM interop

Older COM objects (Outlook automation, Internet Explorer COM, certain ActiveX components) sometimes work better in 5.1 due to the .NET Framework binding model.

### 4. Group Policy / DSC

Windows-specific configuration tooling (DSC v1, certain GPO cmdlets) targets the .NET Framework runtime that 5.1 uses.

### 5. Scripts with multi-byte chars saved without BOM

PS 5.1 reads files as ANSI by default. Em-dashes (`—`), box-drawing chars (`╔╗╚╝`), and other non-ASCII content will mojibake unless the file is saved as **UTF-8 with BOM**.

In VS Code: bottom-right encoding indicator → "Save with Encoding" → "UTF-8 with BOM".

## How to invoke

Both shells coexist on Windows 11. Disambiguate with the executable name:

```bash
# Use PS 7 explicitly
pwsh -NoProfile -Command "Get-Process | Select-Object -First 5"

# Use PS 5.1 explicitly
powershell -NoProfile -Command "Register-WmiEvent ..."
```

In Claude Code, the `Bash` tool lets you choose by invoking either binary. The `PowerShell` tool defaults to whatever the system has registered as the default — usually `pwsh` on Windows 11 with both installed.

## Detecting which shell ran a script

Inside a script, you can check:

```powershell
if ($PSVersionTable.PSVersion.Major -ge 7) {
    # PS 7+ specific code
} else {
    # PS 5.1 fallback
}

# Cross-version platform check
if ($PSVersionTable.Platform -eq 'Win32NT') {
    # Windows-only branch
}
```

## When in doubt

Run on PS 7. If something silently fails (no error, no output where expected), fall back to PS 5.1 and that's usually the fix. The cases above cover ~95% of the version-divergence pain points encountered in Windows tooling.
