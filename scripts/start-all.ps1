param(
    [switch]$SkipInstall,
    [string[]]$NapCatAccounts = @("1443944862", "2629227874"),
    [switch]$SkipNapCat
)

$ErrorActionPreference = "Stop"
$ScriptRoot = $PSScriptRoot

$nonebotArgs = @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    (Join-Path $ScriptRoot "start-nonebot2.ps1")
)
if ($SkipInstall) {
    $nonebotArgs += "-SkipInstall"
}

Start-Process powershell.exe -ArgumentList $nonebotArgs

Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    (Join-Path $ScriptRoot "start-astrbot.ps1")
)

if (-not $SkipNapCat) {
    $napcatArgs = @(
        "-NoExit",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        (Join-Path $ScriptRoot "start-napcat.ps1")
    )
    if ($NapCatAccounts.Count -gt 0) {
        $napcatArgs += "-Accounts"
        foreach ($account in $NapCatAccounts) {
            $napcatArgs += $account
        }
    }

    Start-Process powershell.exe -ArgumentList $napcatArgs
}
