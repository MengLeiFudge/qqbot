param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$WorkspaceRoot = Split-Path -Parent $PSScriptRoot
$AppRoot = Join-Path $WorkspaceRoot "nonebot2"
$DataRoot = Join-Path $WorkspaceRoot "data\nonebot2"
$ConfigDir = Join-Path $DataRoot "config"
$RunRoot = Join-Path $DataRoot "run"
$VenvRoot = Join-Path $DataRoot ".venv"

New-Item -ItemType Directory -Path $ConfigDir -Force | Out-Null
New-Item -ItemType Directory -Path $RunRoot -Force | Out-Null

$env:QQBOT_CONFIG_FILE = Join-Path $ConfigDir "qqbot.toml"
$env:QQBOT_DATA_ROOT = $RunRoot
$env:QQBOT_VENV_PATH = $VenvRoot

$envFile = Join-Path $ConfigDir ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+?)\s*=\s*(.*)\s*$') {
            [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
        }
    }
}

Set-Location $AppRoot
$startScript = Join-Path $AppRoot "scripts\start_bot.ps1"
if ($SkipInstall) {
    & $startScript -SkipInstall
}
else {
    & $startScript
}
