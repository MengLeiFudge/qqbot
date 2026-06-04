param(
    [int]$Port = 6185,
    [string]$PythonVersion = "3.14"
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
$AstrRoot = Join-Path $WorkspaceRoot "data\astrbot"

New-Item -ItemType Directory -Path $AstrRoot -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $AstrRoot ".astrbot") -Force | Out-Null
$env:ASTRBOT_ROOT = $AstrRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Set-Location $AstrRoot

if (Get-Command astrbot -ErrorAction SilentlyContinue) {
    & astrbot run -p $Port
    exit $LASTEXITCODE
}

if (Get-Command uv -ErrorAction SilentlyContinue) {
    & uv tool run --from astrbot --python $PythonVersion astrbot run -p $Port
    exit $LASTEXITCODE
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py "-$PythonVersion" -m uv tool run --from astrbot --python $PythonVersion astrbot run -p $Port
    exit $LASTEXITCODE
}

throw "AstrBot uv tool is not available. Run scripts\update-astrbot.bat first."
