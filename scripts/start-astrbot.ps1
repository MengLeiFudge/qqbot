param(
    [int]$Port = 6185,
    [int]$AiocqhttpPort = 6200,
    [int]$AngelAiocqhttpPort = 6201,
    [string]$PythonVersion = "3.14",
    [ValidateSet("", "dual", "full")]
    [string]$FeatureMode = "",
    [ValidateSet("demon", "angel", "both")]
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

    if ($Profile -eq "both") {
        Sync-AstrBotBothProfileConfig -ConfigPath $ConfigPath -DemonOneBotPort $OneBotPort -AngelOneBotPort $AngelAiocqhttpPort
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

function Sync-AstrBotBothProfileConfig {
    param(
        [string]$ConfigPath,
        [int]$DemonOneBotPort,
        [int]$AngelOneBotPort
    )

    if (-not (Test-Path $ConfigPath)) {
        return
    }

    $rawConfig = Get-Content -Raw -Path $ConfigPath -Encoding UTF8
    if (-not $rawConfig.Trim()) {
        return
    }

    $config = $rawConfig | ConvertFrom-Json
    $changed = $false

    if ($config.provider_settings) {
        if (Set-JsonObjectProperty -Target $config.provider_settings -Name "default_personality" -Value "default") {
            $changed = $true
        }
    }

    if ($config.subagent_orchestrator -and $config.subagent_orchestrator.agents) {
        foreach ($agent in @($config.subagent_orchestrator.agents)) {
            if (Set-JsonObjectProperty -Target $agent -Name "persona_id" -Value "default") {
                $changed = $true
            }
        }
    }

    $keptPlatforms = @()
    if ($config.platform) {
        foreach ($platform in @($config.platform)) {
            if ($platform.type -ne "aiocqhttp") {
                $keptPlatforms += $platform
            }
        }
    }

    $angelPlatform = New-AiocqhttpPlatformConfig -Profile "angel" -OneBotPort $AngelOneBotPort
    $demonPlatform = New-AiocqhttpPlatformConfig -Profile "demon" -OneBotPort $DemonOneBotPort
    $nextPlatforms = @($keptPlatforms + $angelPlatform + $demonPlatform)
    if (Set-JsonObjectProperty -Target $config -Name "platform" -Value $nextPlatforms) {
        $changed = $true
    }

    if ($changed) {
        $json = $config | ConvertTo-Json -Depth 100
        Set-Content -Path $ConfigPath -Value $json -Encoding UTF8
    }
}

function New-AiocqhttpPlatformConfig {
    param(
        [ValidateSet("demon", "angel")]
        [string]$Profile,
        [int]$OneBotPort
    )

    return [PSCustomObject]@{
        id = $ProfileDisplayNames[$Profile]
        type = "aiocqhttp"
        enable = $true
        ws_reverse_host = "0.0.0.0"
        ws_reverse_port = $OneBotPort
        ws_reverse_token = ""
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

function Invoke-LocalPythonScript {
    param(
        [string]$ScriptPath,
        [string[]]$Arguments
    )

    $venvPython = Join-Path $AstrRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        & $venvPython $ScriptPath @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Python script failed: $ScriptPath"
        }
        return
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python $ScriptPath @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Python script failed: $ScriptPath"
        }
        return
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py "-$PythonVersion" $ScriptPath @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Python script failed: $ScriptPath"
        }
        return
    }

    throw "No Python runtime is available for $ScriptPath"
}

Sync-AstrBotProfileConfig -ConfigPath (Join-Path $AstrRoot "data\cmd_config.json") -Profile $BotProfile -OneBotPort $AiocqhttpPort

if (Test-Path $LocalPluginRoot) {
    Get-ChildItem -Path $LocalPluginRoot -Directory | ForEach-Object {
        $target = Join-Path $RuntimePluginRoot $_.Name
        if (Test-Path $target) {
            Remove-Item -Path $target -Recurse -Force
        }
        Copy-Item -Path $_.FullName -Destination $RuntimePluginRoot -Recurse -Force
    }
}

$env:ASTRBOT_ROOT = $AstrRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
if ($FeatureMode) {
    $env:QQBOT_ASTRBOT_FEATURE_MODE = $FeatureMode
}
$env:QQBOT_ASTRBOT_PROFILE = $BotProfile
if ($BotProfile -eq "both") {
    $env:QQBOT_ASTRBOT_ACCOUNT = $ProfileAccounts["angel"]
}
else {
    $env:QQBOT_ASTRBOT_ACCOUNT = $ProfileAccounts[$BotProfile]
}

Set-Location $AstrRoot

$directAstrBot = Join-Path $env:APPDATA "uv\tools\astrbot\Scripts\astrbot.exe"
if (Test-Path $directAstrBot) {
    & $directAstrBot run -p $Port
    exit $LASTEXITCODE
}

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
