#Requires -Version 7
[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$Quiet
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# setup.ps1 — one-command marketplace setup (PowerShell 7+, Windows/macOS/Linux)
#
# Detects the OS, then runs each plugin's scripts/init.ps1 (if present),
# passing through -Force/-Quiet, collects each init's status line, and prints a
# final config-status summary table.
#
# Contract:
#   -Force    Re-scaffold each plugin even if already configured.
#   -Quiet    Suppress per-plugin status lines (the summary table still prints).
#   Exit 0:   every init succeeded OR was already configured.
#   Exit 1:   at least one init hard-failed (or could not be executed).
#
# One plugin's failure does not abort the rest — every init runs, and the table
# reports each outcome.

$Plugins = @('evidence', 'orchestration', 'stewardship', 'discipline', 'git')

# Resolve the repo root from this script's own location (scripts/ -> repo root).
$RepoRoot   = Split-Path -Parent $PSScriptRoot
$PluginsDir = Join-Path $RepoRoot 'plugins'

# Detect the host OS (informational; init.ps1 handles platform specifics itself).
$OsName =
    if ($IsWindows) { 'Windows' }
    elseif ($IsMacOS) { 'macOS' }
    elseif ($IsLinux) { 'Linux' }
    else { 'unknown' }

function Write-Chatty {
    param([string]$Message)
    if (-not $Quiet) {
        Write-Output $Message
    }
}

Write-Chatty "[setup] OS: $OsName"
Write-Chatty "[setup] repo root: $RepoRoot"
Write-Chatty "[setup] initializing plugins: $($Plugins -join ', ')"
Write-Chatty ""

# Only -Force is passed through to each child init. -Quiet is NOT forwarded:
# we always want the child's status line so the summary table is meaningful;
# our own -Quiet suppresses echoing that captured output and the [setup] lines.

# Parse a child status line "[init:<plugin>] <STATE> — <detail>" into parts.
function Split-StatusLine {
    param([string]$Line)
    $body = $Line -replace '^\[init:[^\]]*\]\s*', ''
    $sep = ' — '
    $idx = $body.IndexOf($sep)
    if ($idx -ge 0) {
        $state  = $body.Substring(0, $idx).Trim()
        $detail = $body.Substring($idx + $sep.Length).Trim()
    }
    else {
        $state  = $body.Trim()
        $detail = ''
    }
    [pscustomobject]@{ State = $state; Detail = $detail }
}

$Results = [System.Collections.Generic.List[pscustomobject]]::new()
$HardFail = $false

foreach ($plugin in $Plugins) {
    $initPs1 = Join-Path $PluginsDir $plugin 'scripts' 'init.ps1'

    if (-not (Test-Path -LiteralPath $initPs1 -PathType Leaf)) {
        $Results.Add([pscustomobject]@{
                Plugin = $plugin; State = 'missing'; Detail = 'no scripts/init.ps1 in this plugin'
            })
        Write-Chatty "[setup] ${plugin}: no init.ps1 — skipping"
        continue
    }

    # Run the child init in a fresh pwsh process so a child 'exit 1' does not
    # terminate this orchestrator, and so child Set-StrictMode/preferences stay
    # isolated. Capture stdout+stderr and the real process exit code.
    $childArgs = @('-NoProfile', '-File', $initPs1)
    if ($Force) { $childArgs += '-Force' }

    $output = & pwsh @childArgs 2>&1
    $rc = $LASTEXITCODE

    $outLines = @($output | ForEach-Object { $_.ToString() })

    if (-not $Quiet -and $outLines.Count -gt 0) {
        $outLines | ForEach-Object { Write-Output $_ }
    }

    # The contract guarantees one "[init:<plugin>] <STATE> — ..." status line;
    # a plugin may also emit extra REMINDER lines. Take the first status line.
    $statusLine = $outLines | Where-Object { $_ -like '`[init:*' } | Select-Object -First 1
    if (-not $statusLine) {
        $statusLine = if ($outLines.Count -gt 0) { $outLines[0] } else { '' }
    }

    $parts = Split-StatusLine -Line $statusLine
    $Results.Add([pscustomobject]@{
            Plugin = $plugin; State = $parts.State; Detail = $parts.Detail
        })

    if ($rc -ne 0) {
        $HardFail = $true
    }
}

# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------
Write-Chatty ""
Write-Output "================ marketplace setup summary ================"
Write-Output ('{0,-14}  {1,-18}  {2}' -f 'PLUGIN', 'STATE', 'DETAIL')
Write-Output ('{0,-14}  {1,-18}  {2}' -f '------', '-----', '------')
foreach ($r in $Results) {
    $detailOneLine = ($r.Detail -replace '\r?\n', ' ')
    Write-Output ('{0,-14}  {1,-18}  {2}' -f $r.Plugin, $r.State, $detailOneLine)
}
Write-Output "=========================================================="

if ($HardFail) {
    Write-Output "[setup] FAILED — one or more plugin inits hard-failed (see table above)"
    exit 1
}

Write-Output "[setup] OK — all plugin inits succeeded or were already configured"
exit 0
