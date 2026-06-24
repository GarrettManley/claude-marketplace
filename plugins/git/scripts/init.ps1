#Requires -Version 7
[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$Quiet
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# init.ps1 — git@garrettmanley plugin initialiser (PowerShell 7+)
# Scaffolds an optional project-local commit-message rules file
# (.claude/commit-message-rules.yaml) from the bundled example when run inside
# a git repo. No global/user-level machine config is required by this plugin.

$PluginName    = 'git'
$RulesFilename = '.claude/commit-message-rules.yaml'

function Write-Status {
    param([string]$State, [string]$Detail)
    if (-not $Quiet) {
        Write-Output "[init:${PluginName}] ${State} — ${Detail}"
    }
}

# ── locate the example rules bundled with this skill ─────────────────────────
$ExampleRules = Join-Path $PSScriptRoot '..' 'skills' 'commit-message' 'rules.example.yaml'
$ExampleRules = [System.IO.Path]::GetFullPath($ExampleRules)

if (-not (Test-Path -LiteralPath $ExampleRules -PathType Leaf)) {
    Write-Status 'FAILED' "bundled example rules not found at: ${ExampleRules}"
    exit 1
}

# ── detect git repo ───────────────────────────────────────────────────────────
$GitRoot = git rev-parse --show-toplevel 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($GitRoot)) {
    Write-Status 'skipped' 'not inside a git repository; run from a project root to scaffold commit-message-rules.yaml'
    exit 0
}

$GitRoot = $GitRoot.Trim()
$Target  = Join-Path $GitRoot $RulesFilename

# ── idempotency check ─────────────────────────────────────────────────────────
if ((Test-Path -LiteralPath $Target -PathType Leaf) -and (-not $Force)) {
    Write-Status 'already configured' "${RulesFilename} already exists in this repo (use --force to overwrite)"
    exit 0
}

# ── scaffold ──────────────────────────────────────────────────────────────────
$TargetDir = Split-Path -Parent $Target
if (-not (Test-Path -LiteralPath $TargetDir -PathType Container)) {
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
}
Copy-Item -LiteralPath $ExampleRules -Destination $Target -Force

Write-Status 'CONFIGURED' "scaffolded ${RulesFilename} from bundled example; edit to match your project's CI guard"
exit 0
