param(
    [switch]$SkipInstall
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
