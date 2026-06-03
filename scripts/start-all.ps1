param(
    [switch]$SkipInstall,
    [string[]]$NapCatAccounts = @("1443944862", "2629227874"),
    [switch]$SkipNapCat
)

$ErrorActionPreference = "Stop"
$ScriptRoot = $PSScriptRoot

function New-PowerShellWtCommand {
    param(
        [string]$Script,
        [string[]]$ExtraArgs = @()
    )

    $command = @(
        "powershell.exe",
        "-NoExit",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $Script
    ) + $ExtraArgs
    return $command
}

function Add-WtTab {
    param(
        [System.Collections.Generic.List[string]]$Arguments,
        [string]$Title,
        [string[]]$Command
    )

    if ($Arguments.Count -gt 0) {
        $Arguments.Add(";")
        $Arguments.Add("new-tab")
    }
    $Arguments.Add("--title")
    $Arguments.Add($Title)
    foreach ($item in $Command) {
        $Arguments.Add($item)
    }
}

$nonebotArgs = @(
)
if ($SkipInstall) {
    $nonebotArgs += "-SkipInstall"
}

$wtArgs = [System.Collections.Generic.List[string]]::new()
$wtArgs.Add("-w")
$wtArgs.Add("-1")
Add-WtTab `
    -Arguments $wtArgs `
    -Title "NoneBot2-1443944862" `
    -Command (New-PowerShellWtCommand -Script (Join-Path $ScriptRoot "start-nonebot2.ps1") -ExtraArgs $nonebotArgs)

Add-WtTab `
    -Arguments $wtArgs `
    -Title "AstrBot-2629227874" `
    -Command (New-PowerShellWtCommand -Script (Join-Path $ScriptRoot "start-astrbot.ps1"))

if (-not $SkipNapCat) {
    foreach ($account in $NapCatAccounts) {
        Add-WtTab `
            -Arguments $wtArgs `
            -Title "NapCat-$account" `
            -Command (New-PowerShellWtCommand `
                -Script (Join-Path $ScriptRoot "start-napcat-account.ps1") `
                -ExtraArgs @("-Account", $account))
    }
}

Start-Process -FilePath "wt.exe" -ArgumentList $wtArgs | Out-Null
