param(
    [Parameter(Position = 0)]
    [ValidateSet("all", "astrbot", "maibot", "napcat")]
    [string]$Target = "all"
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkspaceRoot = Split-Path -Parent $ScriptRoot

$components = [ordered]@{
    astrbot = Join-Path $WorkspaceRoot "astrbot\scripts\update.ps1"
    maibot = Join-Path $WorkspaceRoot "maibot-yelin\scripts\update.ps1"
    napcat = Join-Path $WorkspaceRoot "napcat\scripts\update.ps1"
}

$selected = if ($Target -eq "all") { @($components.Keys) } else { @($Target) }
foreach ($name in $selected) {
    $script = $components[$name]
    if (-not (Test-Path $script)) {
        throw "$name update script not found: $script"
    }
    Write-Host "[qqbot] Updating $name to its latest stable release."
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script
    if ($LASTEXITCODE -ne 0) {
        throw "$name update failed with exit code $LASTEXITCODE."
    }
}

Write-Host "[qqbot] Update target '$Target' finished. Review and commit each repository separately; nothing was pushed."
