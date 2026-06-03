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

function New-NapCatWtCommand {
    param(
        [string]$Account
    )

    $port = if ($Account -eq "1443944862") { "8080" } else { "6199" }
    $script = Join-Path $ScriptRoot "start-napcat-account.ps1"
    $commandText = @"
`$deadline = (Get-Date).AddSeconds(90)
do {
    `$ready = Test-NetConnection 127.0.0.1 -Port $port -InformationLevel Quiet
    if (`$ready) { break }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt `$deadline)
if (-not `$ready) { throw 'Target OneBot port $port is not ready for NapCat account $Account' }
& '$script' -Account '$Account'
"@

    return @(
        "powershell.exe",
        "-NoExit",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        $commandText
    )
}

function Add-WtTab {
    param(
        [System.Collections.Generic.List[string]]$Arguments,
        [ref]$TabCount,
        [string]$Title,
        [string[]]$Command
    )

    if ($TabCount.Value -gt 0) {
        $Arguments.Add(";")
    }
    $Arguments.Add("new-tab")
    $Arguments.Add("--title")
    $Arguments.Add($Title)
    foreach ($item in $Command) {
        $Arguments.Add($item)
    }
    $TabCount.Value += 1
}

$nonebotArgs = @(
)
if ($SkipInstall) {
    $nonebotArgs += "-SkipInstall"
}

$wtArgs = [System.Collections.Generic.List[string]]::new()
$wtArgs.Add("-w")
$wtArgs.Add("-1")
$tabCount = 0
Add-WtTab `
    -Arguments $wtArgs `
    -TabCount ([ref]$tabCount) `
    -Title "NoneBot2-1443944862" `
    -Command (New-PowerShellWtCommand -Script (Join-Path $ScriptRoot "start-nonebot2.ps1") -ExtraArgs $nonebotArgs)

Add-WtTab `
    -Arguments $wtArgs `
    -TabCount ([ref]$tabCount) `
    -Title "AstrBot-2629227874" `
    -Command (New-PowerShellWtCommand -Script (Join-Path $ScriptRoot "start-astrbot.ps1"))

if (-not $SkipNapCat) {
    foreach ($account in $NapCatAccounts) {
        Add-WtTab `
            -Arguments $wtArgs `
            -TabCount ([ref]$tabCount) `
            -Title "NapCat-$account" `
            -Command (New-NapCatWtCommand -Account $account)
    }
}

Start-Process -FilePath "wt.exe" -ArgumentList $wtArgs | Out-Null
