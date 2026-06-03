param(
    [string]$Account = "",
    [switch]$NoQuickLogin
)

$ErrorActionPreference = "Stop"
try {
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
}
catch {
}
$chcp = Join-Path $env:WINDIR "System32\chcp.com"
if (Test-Path $chcp) {
    & $chcp 65001 | Out-Null
}

$WorkspaceRoot = Split-Path -Parent $PSScriptRoot
$NapCatRoot = Join-Path $WorkspaceRoot "napcat\onekey\NapCat.44498.Shell"
$NapCatExe = Join-Path $NapCatRoot "NapCatWinBootMain.exe"

if (-not (Test-Path $NapCatExe)) {
    throw "NapCat executable not found: $NapCatExe"
}

Set-Location $NapCatRoot

if ($NoQuickLogin -or -not $Account) {
    & $NapCatExe
    exit $LASTEXITCODE
}

if (-not ($Account -match '^\d+$')) {
    throw "Invalid NapCat account: $Account"
}

& $NapCatExe $Account
exit $LASTEXITCODE
