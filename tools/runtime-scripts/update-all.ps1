param(
    [switch]$DryRun,
    [switch]$SkipNapCat,
    [switch]$SkipAstrBot,
    [switch]$NoStopProcesses,
    [switch]$AssumeYes
)

$ErrorActionPreference = "Stop"
try {
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
}
catch {
}

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Invoke-UpdateScript {
    param(
        [string]$Name,
        [string]$ScriptName
    )

    $script = Join-Path $ScriptRoot $ScriptName
    if (-not (Test-Path $script)) {
        throw "Update script not found: $script"
    }

    Write-Host ""
    Write-Host "==== Updating $Name ===="
    $arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $script)
    if ($DryRun) {
        $arguments += "-DryRun"
    }
    if ($AssumeYes -and ($ScriptName -eq "update-napcat.ps1" -or $ScriptName -eq "update-astrbot.ps1")) {
        $arguments += "-AssumeYes"
    }
    if ($NoStopProcesses -and ($ScriptName -eq "update-napcat.ps1" -or $ScriptName -eq "update-astrbot.ps1")) {
        $arguments += "-NoStopProcesses"
    }

    & powershell.exe @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Name update failed with exit code $LASTEXITCODE"
    }
}

if ($DryRun) {
    Write-Host "DryRun enabled; no download, install, upgrade, or package replacement will be executed."
}
if ($AssumeYes) {
    Write-Host "AssumeYes enabled; NapCat and AstrBot prompts will be auto-confirmed."
}

if (-not $SkipNapCat) {
    Invoke-UpdateScript -Name "NapCat" -ScriptName "update-napcat.ps1"
}
if (-not $SkipAstrBot) {
    Invoke-UpdateScript -Name "AstrBot" -ScriptName "update-astrbot.ps1"
}

Write-Host ""
Write-Host "All selected update steps finished."
