# init.ps1 — orchestration plugin initializer (PowerShell 7+)
# Sets up ~/.claude/context/tiers.local.json and ~/.claude/context/hardware-profile.md
# from the plugin's shipped templates when those files are absent.
#
# Usage:
#   .\init.ps1            # idempotent: no-op if already configured
#   .\init.ps1 -Force     # overwrite existing files with fresh templates
#   .\init.ps1 -Quiet     # suppress the status line
[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$Quiet
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$pluginDir = Split-Path -Parent $PSScriptRoot
$contextDir = Join-Path $env:USERPROFILE '.claude' 'context'

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
function Write-StatusLine {
    param([string]$Verb, [string]$Detail)
    if (-not $Quiet) {
        Write-Output "[init:orchestration] $Verb — $Detail"
    }
}

function Write-Note {
    # Quiet-gated supplementary output (post-init reminders), mirroring the bash init.
    param([string]$Message)
    if (-not $Quiet) {
        Write-Output $Message
    }
}

function Copy-IfAbsent {
    <#
    .SYNOPSIS
    Copies $Source to $Dest unless $Dest already exists (and -Force not set).
    Returns 'configured' or 'already configured'.
    #>
    param(
        [string]$Source,
        [string]$Dest
    )
    if ((Test-Path $Dest) -and (-not $Force)) {
        return 'already configured'
    }
    Copy-Item -Path $Source -Destination $Dest -Force
    return 'configured'
}

# ---------------------------------------------------------------------------
# Ensure context dir exists (mkdir -p equivalent; never truncates files)
# ---------------------------------------------------------------------------
if (-not (Test-Path $contextDir)) {
    New-Item -ItemType Directory -Force -Path $contextDir | Out-Null
}

# ---------------------------------------------------------------------------
# (1) tiers.local.json
# ---------------------------------------------------------------------------
$tiersSrc  = Join-Path $pluginDir 'configs' 'tiers.json'
$tiersDest = Join-Path $contextDir 'tiers.local.json'

if (-not (Test-Path $tiersSrc)) {
    Write-StatusLine 'FAILED' "source not found: $tiersSrc"
    exit 1
}

$tiersResult = Copy-IfAbsent -Source $tiersSrc -Dest $tiersDest

# ---------------------------------------------------------------------------
# (2) hardware-profile.md
# ---------------------------------------------------------------------------
$profileTemplate = Join-Path $pluginDir 'context' 'hardware-profile.template.md'
$profileDest     = Join-Path $contextDir 'hardware-profile.md'

if (-not (Test-Path $profileTemplate)) {
    Write-StatusLine 'FAILED' "template not found: $profileTemplate"
    exit 1
}

$profileResult = Copy-IfAbsent -Source $profileTemplate -Dest $profileDest

# ---------------------------------------------------------------------------
# Compose status line
# ---------------------------------------------------------------------------
$configuredList = [System.Collections.Generic.List[string]]::new()
$alreadyList    = [System.Collections.Generic.List[string]]::new()

$resultMap = @{
    'tiers.local.json'   = $tiersResult
    'hardware-profile.md' = $profileResult
}

foreach ($label in $resultMap.Keys) {
    if ($resultMap[$label] -eq 'configured') {
        $configuredList.Add($label)
    } else {
        $alreadyList.Add($label)
    }
}

if ($configuredList.Count -gt 0 -and $alreadyList.Count -eq 0) {
    Write-StatusLine 'CONFIGURED' "created: $($configuredList -join ', ')"
    Write-Note '[init:orchestration] REMINDER: edit ~/.claude/context/tiers.local.json — fill in <path-to>/llama-server.exe, <path-to-models>/, <GPU model>, and <N> GB VRAM ceiling.'
    Write-Note '[init:orchestration] REMINDER: edit ~/.claude/context/hardware-profile.md — replace all <placeholder> values with your real hardware details.'
} elseif ($configuredList.Count -eq 0 -and $alreadyList.Count -gt 0) {
    Write-StatusLine 'already configured' ($alreadyList -join ', ')
} else {
    # mixed
    $parts = [System.Collections.Generic.List[string]]::new()
    if ($configuredList.Count -gt 0) {
        $parts.Add("created: $($configuredList -join ', ')")
    }
    if ($alreadyList.Count -gt 0) {
        $parts.Add("already configured: $($alreadyList -join ', ')")
    }
    Write-StatusLine 'CONFIGURED' ($parts -join '; ')
    if ($configuredList -contains 'tiers.local.json') {
        Write-Note '[init:orchestration] REMINDER: edit ~/.claude/context/tiers.local.json — fill in <path-to>/llama-server.exe, <path-to-models>/, <GPU model>, and <N> GB VRAM ceiling.'
    }
    if ($configuredList -contains 'hardware-profile.md') {
        Write-Note '[init:orchestration] REMINDER: edit ~/.claude/context/hardware-profile.md — replace all <placeholder> values with your real hardware details.'
    }
}

exit 0
