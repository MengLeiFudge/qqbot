param(
    [int]$Port = 6185,
    [int]$AiocqhttpPort = 6200,
    [string]$PythonVersion = "3.14",
    [ValidateSet("", "dual", "full")]
    [string]$FeatureMode = "",
    [ValidateSet("demon", "angel")]
    [string]$BotProfile = "demon"
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

function Join-CodePoints {
    param([int[]]$CodePoints)
    return -join ($CodePoints | ForEach-Object { [string][char]$_ })
}

$ProfileDisplayNames = @{
    demon = ((Join-CodePoints @(0xD83D, 0xDC7F)) + (Join-CodePoints @(0x68C9, 0x82B1, 0x7CD6)) + (Join-CodePoints @(0xD83D, 0xDC7F)))
    angel = ((Join-CodePoints @(0xD83D, 0xDE07)) + (Join-CodePoints @(0x68C9, 0x82B1, 0x7CD6)) + (Join-CodePoints @(0xD83D, 0xDE07)))
}
$ProfilePersonaNames = @{
    demon = (Join-CodePoints @(0x6076, 0x9B54, 0x68C9, 0x82B1, 0x7CD6))
    angel = (Join-CodePoints @(0x5929, 0x4F7F, 0x68C9, 0x82B1, 0x7CD6))
}
$ProfileAccounts = @{
    demon = "2629227874"
    angel = "1443944862"
}

function Test-NoneBot2AdminStatus {
    try {
        $status = Invoke-RestMethod -Uri "http://127.0.0.1:8080/admin/api/status" -Method Get -TimeoutSec 3
    }
    catch {
        return $false
    }
    return $null -ne $status -and
        $null -ne $status.PSObject.Properties["connected_bot_count"] -and
        $null -ne $status.PSObject.Properties["onebot_connected"]
}

if ($FeatureMode -eq "full" -and (Test-NoneBot2AdminStatus)) {
    throw "QQBot AstrBot feature mode full requires NoneBot2 to be offline. Stop bot1 first or use FeatureMode dual."
}

New-Item -ItemType Directory -Path $AstrRoot -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $AstrRoot ".astrbot") -Force | Out-Null
New-Item -ItemType Directory -Path $RuntimePluginRoot -Force | Out-Null

function Sync-AstrBotProfileConfig {
    param(
        [string]$ConfigPath,
        [string]$Profile,
        [int]$OneBotPort
    )

    if (-not (Test-Path $ConfigPath)) {
        return
    }

    $displayName = $ProfileDisplayNames[$Profile]
    $personaName = $ProfilePersonaNames[$Profile]
    if (-not $displayName -or -not $personaName) {
        throw "Unknown AstrBot profile: $Profile"
    }

    $rawConfig = Get-Content -Raw -Path $ConfigPath -Encoding UTF8
    if (-not $rawConfig.Trim()) {
        return
    }

    $config = $rawConfig | ConvertFrom-Json
    $changed = $false

    if ($config.provider_settings) {
        if (Set-JsonObjectProperty -Target $config.provider_settings -Name "default_personality" -Value $personaName) {
            $changed = $true
        }
    }

    if ($config.subagent_orchestrator -and $config.subagent_orchestrator.agents) {
        foreach ($agent in @($config.subagent_orchestrator.agents)) {
            if (Set-JsonObjectProperty -Target $agent -Name "persona_id" -Value $personaName) {
                $changed = $true
            }
        }
    }

    if ($config.platform) {
        foreach ($platform in @($config.platform)) {
            if ($platform.type -eq "aiocqhttp" -and (Set-JsonObjectProperty -Target $platform -Name "id" -Value $displayName)) {
                $changed = $true
            }
            if ($platform.type -eq "aiocqhttp" -and (Set-JsonObjectProperty -Target $platform -Name "ws_reverse_port" -Value $OneBotPort)) {
                $changed = $true
            }
        }
    }

    if ($changed) {
        $json = $config | ConvertTo-Json -Depth 100
        Set-Content -Path $ConfigPath -Value $json -Encoding UTF8
    }
}

function Set-JsonObjectProperty {
    param(
        [object]$Target,
        [string]$Name,
        [object]$Value
    )

    $property = $Target.PSObject.Properties[$Name]
    if ($property) {
        if ($property.Value -ne $Value) {
            $property.Value = $Value
            return $true
        }
        return $false
    }

    $Target | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    return $true
}

Sync-AstrBotProfileConfig -ConfigPath (Join-Path $AstrRoot "data\cmd_config.json") -Profile $BotProfile -OneBotPort $AiocqhttpPort

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
$env:QQBOT_ASTRBOT_PROFILE = $BotProfile
$env:QQBOT_ASTRBOT_ACCOUNT = $ProfileAccounts[$BotProfile]

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
