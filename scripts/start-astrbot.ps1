param(
    [int]$Port = 6185
)

$ErrorActionPreference = "Stop"
$WorkspaceRoot = Split-Path -Parent $PSScriptRoot
$AppRoot = Join-Path $WorkspaceRoot "astrbot"
$AstrRoot = Join-Path $WorkspaceRoot "data\astrbot"

New-Item -ItemType Directory -Path $AstrRoot -Force | Out-Null
$env:ASTRBOT_ROOT = $AstrRoot

Set-Location $AppRoot
$python = Join-Path $AppRoot ".venv\Scripts\python.exe"
if (Test-Path $python) {
    & $python -m astrbot.cli run -p $Port
    exit $LASTEXITCODE
}

if (Get-Command uv -ErrorAction SilentlyContinue) {
    & uv run astrbot run -p $Port
    exit $LASTEXITCODE
}

throw "AstrBot Windows venv not found: $python. Create it in $AppRoot or install uv."
