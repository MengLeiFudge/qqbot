param(
    [string]$Account = "",
    [switch]$NoQuickLogin
)

$ErrorActionPreference = "Stop"
try {
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
}
catch {
}
$chcp = Join-Path $env:WINDIR "System32\chcp.com"
if (Test-Path $chcp) {
    & $chcp 65001 | Out-Null
}

$WorkspaceRoot = Split-Path -Parent $PSScriptRoot
$OneKeyRoot = Join-Path $WorkspaceRoot "napcat\onekey"

function Resolve-NapCatRoot {
    $versionedRoots = @(Get-ChildItem -Path $OneKeyRoot -Directory -Filter "NapCat.*.Shell" -ErrorAction SilentlyContinue | Where-Object {
        Test-Path (Join-Path $_.FullName "NapCatWinBootMain.exe")
    } | Sort-Object LastWriteTime -Descending)
    if ($versionedRoots.Count -gt 0) {
        return $versionedRoots[0].FullName
    }

    $bootmain = Join-Path $OneKeyRoot "bootmain"
    if (Test-Path (Join-Path $bootmain "NapCatWinBootMain.exe")) {
        return $bootmain
    }

    if (Test-Path (Join-Path $OneKeyRoot "NapCatWinBootMain.exe")) {
        return $OneKeyRoot
    }

    throw "NapCat executable not found under: $OneKeyRoot"
}

$NapCatRoot = Resolve-NapCatRoot
$NapCatExe = Join-Path $NapCatRoot "NapCatWinBootMain.exe"

if (-not (Test-Path $NapCatExe)) {
    throw "NapCat executable not found: $NapCatExe"
}

Set-Location $NapCatRoot

if ($NoQuickLogin -or -not $Account) {
    & $NapCatExe
    exit $LASTEXITCODE
}

if (-not ($Account -match '^\d+$')) {
    throw "Invalid NapCat account: $Account"
}

& $NapCatExe $Account
exit $LASTEXITCODE
