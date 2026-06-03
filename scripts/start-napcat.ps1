param()

$ErrorActionPreference = "Stop"
$WorkspaceRoot = Split-Path -Parent $PSScriptRoot
$NapCatRoot = Join-Path $WorkspaceRoot "napcat\onekey\NapCat.44498.Shell"
$NapCatExe = Join-Path $NapCatRoot "NapCatWinBootMain.exe"

if (-not (Test-Path $NapCatExe)) {
    throw "NapCat executable not found: $NapCatExe"
}

Set-Location $NapCatRoot
& $NapCatExe
