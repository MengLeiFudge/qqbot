param(
    [Parameter(Position = 0)]
    [ValidateSet("all", "astrbot", "maibot", "napcat")]
    [string]$Target = "all"
)

$ErrorActionPreference = "Stop"
$WorkspaceRoot = Split-Path -Parent $PSScriptRoot

if ($Target -ne 'napcat') {
    & py -3 (Join-Path $PSScriptRoot 'frameworks\install_release.py') $Target
    if ($LASTEXITCODE -ne 0) {
        throw "Framework installation failed with exit code $LASTEXITCODE."
    }
}

if ($Target -in @('all', 'napcat')) {
    $script = Join-Path $WorkspaceRoot 'napcat\scripts\update.ps1'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script
    if ($LASTEXITCODE -ne 0) {
        throw "NapCat update failed with exit code $LASTEXITCODE."
    }
}
