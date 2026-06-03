param(
    [switch]$SkipInstall,
    [string[]]$NapCatAccounts = @("1443944862", "2629227874"),
    [switch]$SkipNapCat,
    [switch]$RestartBot
)

$ErrorActionPreference = "Stop"
$ScriptRoot = $PSScriptRoot
$WorkspaceRoot = Split-Path -Parent $ScriptRoot

function Write-LauncherLog {
    param(
        [string]$LogFile,
        [string]$Message
    )

    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port
    )

    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        try {
            $result = $client.BeginConnect($HostName, $Port, $null, $null)
            if (-not $result.AsyncWaitHandle.WaitOne(1000)) {
                return $false
            }
            $client.EndConnect($result)
            return $true
        }
        finally {
            $client.Close()
        }
    }
    catch {
        return $false
    }
}

function Wait-TcpPort {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutSeconds,
        [string]$LogFile
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (Test-TcpPort -HostName $HostName -Port $Port) {
            Write-LauncherLog -LogFile $LogFile -Message "Port ${HostName}:$Port is ready."
            return $true
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    Write-LauncherLog -LogFile $LogFile -Message "Timed out waiting for port ${HostName}:$Port."
    return $false
}

function Get-AdminStatus {
    param(
        [string]$Url
    )

    try {
        return Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 3
    }
    catch {
        return $null
    }
}

function Wait-OneBotConnection {
    param(
        [string]$StatusUrl,
        [int]$TimeoutSeconds,
        [string]$LogFile
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $status = Get-AdminStatus -Url $StatusUrl
        if ($status -and ($status.onebot_connected -or ([int]$status.connected_bot_count -ge 1))) {
            Write-LauncherLog -LogFile $LogFile -Message "OneBot connection confirmed. connected_bot_count=$($status.connected_bot_count)"
            return $true
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    Write-LauncherLog -LogFile $LogFile -Message "Timed out waiting for OneBot connection."
    return $false
}

function Stop-ExistingNoneBot {
    param(
        [string]$LogFile
    )

    $pidFile = Join-Path $WorkspaceRoot "data\nonebot2\run\qqbot.pid"
    if (-not (Test-Path $pidFile)) {
        Write-LauncherLog -LogFile $LogFile -Message "No existing NoneBot2 pid file found."
        return
    }

    $pidText = Get-Content -Path $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $pidText) {
        Write-LauncherLog -LogFile $LogFile -Message "NoneBot2 pid file is empty."
        return
    }
    $pidText = $pidText.Trim()
    if (-not ($pidText -match '^\d+$')) {
        Write-LauncherLog -LogFile $LogFile -Message "Invalid NoneBot2 pid file content: $pidText"
        return
    }

    $botPid = [int]$pidText
    if ($botPid -eq $PID) {
        Write-LauncherLog -LogFile $LogFile -Message "Skip stopping current launcher pid=$botPid."
        return
    }

    $process = Get-Process -Id $botPid -ErrorAction SilentlyContinue
    if (-not $process) {
        Write-LauncherLog -LogFile $LogFile -Message "Existing NoneBot2 pid=$botPid is not running."
        return
    }

    Write-LauncherLog -LogFile $LogFile -Message "Stopping existing NoneBot2 pid=$botPid."
    Stop-Process -Id $botPid -Force -ErrorAction SilentlyContinue
    try {
        Wait-Process -Id $botPid -Timeout 30 -ErrorAction SilentlyContinue
    }
    catch {
    }
    Write-LauncherLog -LogFile $LogFile -Message "Existing NoneBot2 stop requested."
}

function Start-RestartBot {
    $runId = Get-Date -Format "yyyyMMdd-HHmmss"
    $logRoot = Join-Path $WorkspaceRoot "data\nonebot2\logs\start_all\$runId"
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $launcherLog = Join-Path $logRoot "launcher.log"
    $stdoutLog = Join-Path $logRoot "qqbot_stdout.log"
    $stderrLog = Join-Path $logRoot "qqbot_stderr.log"
    New-Item -ItemType File -Path $stdoutLog -Force | Out-Null
    New-Item -ItemType File -Path $stderrLog -Force | Out-Null
    Write-LauncherLog -LogFile $launcherLog -Message "RestartBot mode started."
    Start-Sleep -Seconds 2
    Stop-ExistingNoneBot -LogFile $launcherLog

    $nonebotScript = Join-Path $ScriptRoot "start-nonebot2.ps1"
    $nonebotExtraArgs = if ($SkipInstall) { "-SkipInstall" } else { "" }
    $nonebotCommand = "& '$nonebotScript' $nonebotExtraArgs > '$stdoutLog' 2> '$stderrLog'"
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        $nonebotCommand
    )

    Write-LauncherLog -LogFile $launcherLog -Message "Starting NoneBot2 in a hidden background PowerShell."
    $process = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList $arguments `
        -WorkingDirectory $WorkspaceRoot `
        -WindowStyle Hidden `
        -PassThru

    Write-LauncherLog -LogFile $launcherLog -Message "NoneBot2 process started. pid=$($process.Id)"
    if (-not (Wait-TcpPort -HostName "127.0.0.1" -Port 8080 -TimeoutSeconds 90 -LogFile $launcherLog)) {
        exit 1
    }

    if (-not (Wait-OneBotConnection -StatusUrl "http://127.0.0.1:8080/admin/api/status" -TimeoutSeconds 120 -LogFile $launcherLog)) {
        Write-LauncherLog -LogFile $launcherLog -Message "QQBot is running, but no OneBot connection was confirmed. Existing NapCat may still be starting."
        exit 2
    }

    Write-LauncherLog -LogFile $launcherLog -Message "RestartBot mode completed."
}

if ($RestartBot) {
    Start-RestartBot
    exit 0
}

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
