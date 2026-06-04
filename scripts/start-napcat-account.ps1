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
    $currentRoot = Join-Path $OneKeyRoot "napcat"
    if (Test-Path (Join-Path $currentRoot "NapCatWinBootMain.exe")) {
        return @{
            Root = $currentRoot
            Mode = "launcher"
            Launcher = Join-Path $currentRoot "launcher-user.bat"
            Exe = Join-Path $currentRoot "NapCatWinBootMain.exe"
        }
    }

    $versionedRoots = @(Get-ChildItem -Path $OneKeyRoot -Directory -Filter "NapCat.*.Shell" -ErrorAction SilentlyContinue | Where-Object {
        Test-Path (Join-Path $_.FullName "NapCatWinBootMain.exe")
    } | Sort-Object LastWriteTime -Descending)
    if ($versionedRoots.Count -gt 0) {
        return @{
            Root = $versionedRoots[0].FullName
            Mode = "direct"
            Launcher = ""
            Exe = Join-Path $versionedRoots[0].FullName "NapCatWinBootMain.exe"
        }
    }

    $bootmain = Join-Path $OneKeyRoot "bootmain"
    if (Test-Path (Join-Path $bootmain "NapCatWinBootMain.exe")) {
        return @{
            Root = $bootmain
            Mode = "direct"
            Launcher = ""
            Exe = Join-Path $bootmain "NapCatWinBootMain.exe"
        }
    }

    if (Test-Path (Join-Path $OneKeyRoot "NapCatWinBootMain.exe")) {
        return @{
            Root = $OneKeyRoot
            Mode = "direct"
            Launcher = ""
            Exe = Join-Path $OneKeyRoot "NapCatWinBootMain.exe"
        }
    }

    throw "NapCat executable not found under: $OneKeyRoot"
}

$resolved = Resolve-NapCatRoot
$NapCatRoot = $resolved.Root
$NapCatExe = $resolved.Exe

if (-not (Test-Path $NapCatExe)) {
    throw "NapCat executable not found: $NapCatExe"
}
if ($resolved.Mode -eq "launcher" -and -not (Test-Path $resolved.Launcher)) {
    throw "NapCat launcher not found: $($resolved.Launcher)"
}

Set-Location $NapCatRoot

if ($NoQuickLogin -or -not $Account) {
    if ($resolved.Mode -eq "launcher") {
        & $resolved.Launcher
    }
    else {
        & $NapCatExe
    }
    exit $LASTEXITCODE
}

if (-not ($Account -match '^\d+$')) {
    throw "Invalid NapCat account: $Account"
}

if ($resolved.Mode -eq "launcher") {
    $env:NAPCAT_QUICK_ACCOUNT = $Account
    & $resolved.Launcher
}
else {
    & $NapCatExe $Account
}
exit $LASTEXITCODE
