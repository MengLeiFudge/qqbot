param(
    [int]$Port = 6185
)

$ErrorActionPreference = "Stop"
try {
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
}
catch {
    # Output may be redirected; environment variables below still keep Python logs UTF-8.
}

$WorkspaceRoot = Split-Path -Parent $PSScriptRoot
$AppRoot = Join-Path $WorkspaceRoot "astrbot"
$AstrRoot = Join-Path $WorkspaceRoot "data\astrbot"
$VenvRoot = Join-Path $AstrRoot ".venv"

New-Item -ItemType Directory -Path $AstrRoot -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $AstrRoot ".astrbot") -Force | Out-Null
$env:ASTRBOT_ROOT = $AstrRoot
$env:PYTHONPATH = $AppRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Set-Location $AstrRoot
$python = Join-Path $VenvRoot "Scripts\python.exe"
if (Test-Path $python) {
    & $python -m astrbot.cli run -p $Port
    exit $LASTEXITCODE
}

if (Get-Command uv -ErrorAction SilentlyContinue) {
    & uv run astrbot run -p $Port
    exit $LASTEXITCODE
}

throw "AstrBot Windows venv not found: $python. Create it with: py -3.14 -m venv $VenvRoot"
