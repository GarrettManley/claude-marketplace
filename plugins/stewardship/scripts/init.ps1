# init.ps1 — stewardship plugin initializer (PowerShell 7+, Windows)
# Registers the nightly steward via Windows Task Scheduler by delegating to
# the existing register_nightly.ps1 helper.
#
# Contract:
#   -Force    Re-register even if the task already exists.
#   -Quiet    Suppress the status line.
#   Exit 0:   success OR already-configured.
#   Exit 1:   hard failure.
#
# Status line format:
#   [init:stewardship] <CONFIGURED|already configured|FAILED> — <detail>

[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$Quiet
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$PluginName = 'stewardship'
$TaskName   = 'stewardship-nightly-steward'

function Write-StatusLine {
    param([string]$Message)
    if (-not $Quiet) {
        Write-Output "[init:$PluginName] $Message"
    }
}

# Resolve paths relative to this script's location
$ScriptDir  = $PSScriptRoot
$RegisterPs1 = Join-Path $ScriptDir 'register_nightly.ps1'

if (-not (Test-Path $RegisterPs1)) {
    Write-StatusLine "FAILED — register_nightly.ps1 not found at: $RegisterPs1"
    exit 1
}

# ---------------------------------------------------------------------------
# Idempotency check: is the task already registered?
# ---------------------------------------------------------------------------
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($existingTask -and -not $Force) {
    Write-StatusLine "already configured — scheduled task '$TaskName' is registered (use -Force to re-register)"
    exit 0
}

# ---------------------------------------------------------------------------
# Delegate to register_nightly.ps1 with defaults (03:00, dry-run housekeep).
# Pass -Force so it uses Register-ScheduledTask -Force and overwrites on re-run.
# ---------------------------------------------------------------------------
try {
    & $RegisterPs1 -At '03:00' 2>&1 | Out-Null
}
catch {
    Write-StatusLine "FAILED — register_nightly.ps1 threw: $_"
    exit 1
}

# Verify the task was actually created
$verifyTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $verifyTask) {
    Write-StatusLine "FAILED — task '$TaskName' not found after registration attempt"
    exit 1
}

$logDir = Join-Path $env:LOCALAPPDATA 'stewardship-plugin\logs'
Write-StatusLine "CONFIGURED — scheduled task '$TaskName' registered at 03:00 daily
  Task name: $TaskName
  Log dir:   $logDir
  To run immediately: Start-ScheduledTask -TaskName '$TaskName'
  To unregister:      & '$RegisterPs1' -Unregister"
