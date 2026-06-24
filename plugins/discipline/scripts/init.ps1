#Requires -Version 7
[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$Quiet
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# discipline/scripts/init.ps1
# Scaffold an optional project-local config at .\.claude\discipline.local.md
# from the plugin's examples\discipline.local.md if absent.
#
# Usage: init.ps1 [-Force] [-Quiet]

# Resolve paths relative to this script's own location.
$pluginDir  = Split-Path -Parent $PSScriptRoot
$exampleFile = Join-Path $pluginDir 'examples' 'discipline.local.md'
$targetDir   = Join-Path (Get-Location).Path '.claude'
$targetFile  = Join-Path $targetDir 'discipline.local.md'

# Verify the example template exists — hard failure if missing.
if (-not (Test-Path $exampleFile -PathType Leaf)) {
    Write-Output "[init:discipline] FAILED — example template not found: $exampleFile"
    exit 1
}

# Already configured?
if ((Test-Path $targetFile -PathType Leaf) -and (-not $Force)) {
    if (-not $Quiet) {
        Write-Output "[init:discipline] already configured — $targetFile exists (use -Force to overwrite)"
    }
    exit 0
}

# Create .claude\ dir if absent.
if (-not (Test-Path $targetDir -PathType Container)) {
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
}

# Copy the example template.
Copy-Item -Path $exampleFile -Destination $targetFile -Force

if (-not $Quiet) {
    Write-Output "[init:discipline] CONFIGURED — wrote $targetFile"
}
exit 0
