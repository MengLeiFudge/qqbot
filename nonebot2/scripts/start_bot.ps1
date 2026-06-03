param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

. (Join-Path $PSScriptRoot "start_bot_helpers.ps1")

Set-Location $Root

$VenvPath = if ($env:QQBOT_VENV_PATH) { $env:QQBOT_VENV_PATH } else { ".venv" }
$PythonPath = Join-Path $VenvPath "Scripts\python.exe"
$env:PYTHONPATH = Join-Path $Root "src"

if (-not (Test-VenvHealthy -VenvPath $VenvPath)) {
    $version = Get-PreferredPythonVersion
    Write-Host "Rebuilding $VenvPath with Python $version ..."
    New-ProjectVenv -VenvPath $VenvPath -Version $version
}

if (-not $SkipInstall) {
    & $PythonPath -m pip install -U pip
    & $PythonPath -m pip install -e .[dev]
}

if (-not $env:QQBOT_CONFIG_FILE -and -not (Test-Path ".env") -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Copied .env.example to .env. Update access token if needed."
}

& $PythonPath bot.py
