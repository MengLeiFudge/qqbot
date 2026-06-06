param(
    [int]$Port = 6185,
    [string]$PythonVersion = "3.14",
    [ValidateSet("", "dual", "full")]
    [string]$FeatureMode = ""
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
$LocalPluginRoot = Join-Path $WorkspaceRoot "astrbot-local-plugins"
$RuntimePluginRoot = Join-Path $AstrRoot "data\plugins"

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port
    )

    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        try {
            $result = $client.BeginConnect($HostName, $Port, $null, $null)
            if (-not $result.AsyncWaitHandle.WaitOne(1000)) {
                return $false
            }
            $client.EndConnect($result)
            return $true
        }
        finally {
            $client.Close()
        }
    }
    catch {
        return $false
    }
}

if ($FeatureMode -eq "full" -and (Test-TcpPort -HostName "127.0.0.1" -Port 8080)) {
    throw "QQBot AstrBot feature mode full requires NoneBot2 to be offline. Stop bot1 first or use FeatureMode dual."
}

New-Item -ItemType Directory -Path $AstrRoot -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $AstrRoot ".astrbot") -Force | Out-Null
New-Item -ItemType Directory -Path $RuntimePluginRoot -Force | Out-Null

if (Test-Path $LocalPluginRoot) {
    Get-ChildItem -Path $LocalPluginRoot -Directory | ForEach-Object {
        $target = Join-Path $RuntimePluginRoot $_.Name
        New-Item -ItemType Directory -Path $target -Force | Out-Null
        Copy-Item -Path (Join-Path $_.FullName "*") -Destination $target -Recurse -Force
    }
}

$env:ASTRBOT_ROOT = $AstrRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
if ($FeatureMode) {
    $env:QQBOT_ASTRBOT_FEATURE_MODE = $FeatureMode
}

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
