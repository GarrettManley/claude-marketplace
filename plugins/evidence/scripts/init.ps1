#Requires -Version 7
[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$Quiet
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# evidence/scripts/init.ps1
# Generate the HMAC override key at ~/.claude/evidence-override-key if absent.
# The key is 64 hex chars (32 bytes) from a CSPRNG.  Permissions are restricted
# via icacls: inheritance removed, current user granted Read+Write only.
#
# Usage: init.ps1 [-Force] [-Quiet]
#
# -Force   Regenerate the key even if it already exists.
#          WARNING: this invalidates all outstanding HMAC tokens.
# -Quiet   Suppress the status line (still exits 0 on success).

$keyPath = Join-Path $env:USERPROFILE '.claude' 'evidence-override-key'
$keyDir  = Join-Path $env:USERPROFILE '.claude'

# Already configured?
if ((Test-Path $keyPath -PathType Leaf) -and (-not $Force)) {
    if (-not $Quiet) {
        Write-Output "[init:evidence] already configured — $keyPath exists (use -Force to regenerate; this invalidates outstanding tokens)"
    }
    exit 0
}

# Ensure ~/.claude/ directory exists (never truncates files).
if (-not (Test-Path $keyDir -PathType Container)) {
    New-Item -ItemType Directory -Path $keyDir | Out-Null
}

# Generate 64 hex chars (32 bytes) from Python's CSPRNG.
# Python 3 is required; fail with a clear error if absent.
$pythonExe = $null
foreach ($candidate in @('python3', 'python', 'py')) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $pythonExe = $candidate
        break
    }
}

if ($null -eq $pythonExe) {
    Write-Output "[init:evidence] FAILED — python3 not found; install Python 3 and retry"
    exit 1
}

$hexKey = & $pythonExe -c "import secrets; print(secrets.token_hex(32), end='')"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrEmpty($hexKey)) {
    Write-Output "[init:evidence] FAILED — python failed to generate key"
    exit 1
}

# Write without BOM, no trailing newline, ASCII encoding.
[System.IO.File]::WriteAllText($keyPath, $hexKey, [System.Text.Encoding]::ASCII)

# Restrict permissions: remove inheritance, grant current user Read+Write only.
# Matches the exact icacls form documented in the README.
$null = & icacls $keyPath /inheritance:r /grant:r "${env:USERNAME}:(R,W)" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Output "[init:evidence] FAILED — icacls could not set permissions on $keyPath"
    exit 1
}

if (-not $Quiet) {
    Write-Output "[init:evidence] CONFIGURED — wrote $keyPath (icacls inheritance:r, grant $env:USERNAME R,W)"
}
exit 0
