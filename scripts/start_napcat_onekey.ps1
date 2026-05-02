param(
    [string]$QuickLoginQQ = ""
)

$ErrorActionPreference = "Stop"
$NapcatRoot = "D:\project\python\qqbot\tools\napcat\onekey\NapCat.44498.Shell"

if (-not (Test-Path "$NapcatRoot\NapCatWinBootMain.exe")) {
    Write-Host "NapCat package not found: $NapcatRoot"
    exit 1
}

Set-Location $NapcatRoot

# Force UTF-8 console encoding before launching NapCat.
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
chcp 65001 > $null

if ($QuickLoginQQ -and $QuickLoginQQ -match '^\d+$') {
    Write-Host "Using NapCat quick login QQ: $QuickLoginQQ"
    & ".\NapCatWinBootMain.exe" $QuickLoginQQ
}
else {
    if ($QuickLoginQQ) {
        Write-Host "Ignoring invalid NapCat quick login QQ: $QuickLoginQQ"
    }
    & ".\napcat.bat"
}
