param(
    [switch]$SkipInstall,
    [switch]$RestartBot,
    [int]$BotPort = 8080,
    [int]$BotPortTimeoutSeconds = 90,
    [int]$ExistingNapcatReconnectTimeoutSeconds = 10,
    [int]$NapcatLoginTimeoutSeconds = 300
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

. (Join-Path $PSScriptRoot "start_all_helpers.ps1")

Set-Location $Root

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logDir = Join-Path $Root (Join-Path "logs\start_all" $timestamp)
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

$botStdout = Join-Path $logDir "qqbot_stdout.log"
$botStderr = Join-Path $logDir "qqbot_stderr.log"
$launcherLog = Join-Path $logDir "launcher.log"
$botPidFile = Join-Path $Root "run\qqbot.pid"
$envFile = Join-Path $Root ".env"

function Write-LauncherLog {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $Message
    Add-Content -Path $launcherLog -Value $line
}

function Get-NapcatProcesses {
    Get-Process -Name "NapCatWinBootMain" -ErrorAction SilentlyContinue |
        Where-Object { -not $_.HasExited } |
        Sort-Object Id
}

function Get-NapcatProcess {
    Get-NapcatProcesses | Select-Object -First 1
}

function Stop-NapcatProcesses {
    param(
        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Process[]]$Processes
    )

    foreach ($process in $Processes) {
        Stop-ProcessTree -ProcessId $process.Id
    }
}

function Get-WindowsTerminalAncestor {
    param(
        [Parameter(Mandatory = $true)]
        [CimInstance]$Process
    )

    $current = $Process
    for ($i = 0; $i -lt 12 -and $current; $i++) {
        if ($current.Name -eq "WindowsTerminal.exe") {
            return Get-Process -Id ([int]$current.ProcessId) -ErrorAction SilentlyContinue
        }

        if (-not $current.ParentProcessId) {
            break
        }

        $parentId = [int]$current.ParentProcessId
        $current = Get-CimInstance Win32_Process -Filter "ProcessId=$parentId" -ErrorAction SilentlyContinue
    }

    return $null
}

function Get-NapcatTerminalProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$StartNapcatScript,
        [Parameter(Mandatory = $true)]
        [string]$WindowTitle
    )

    $titleProcess = Get-Process -Name "WindowsTerminal" -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like "*$WindowTitle*" } |
        Select-Object -First 1
    if ($titleProcess) {
        return $titleProcess
    }

    $escapedStartScript = [regex]::Escape($StartNapcatScript)
    $launcherProcesses = @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -and $_.CommandLine -match $escapedStartScript }
    )

    foreach ($launcherProcess in $launcherProcesses) {
        $terminalProcess = Get-WindowsTerminalAncestor -Process $launcherProcess
        if ($terminalProcess -and $terminalProcess.MainWindowHandle -ne 0) {
            return $terminalProcess
        }
    }

    return $null
}

$startBotScript = Join-Path $PSScriptRoot "start_bot.ps1"
$startNapcatScript = Join-Path $PSScriptRoot "start_napcat_onekey.ps1"
$napcatRoot = Join-Path $Root "tools\napcat\onekey\NapCat.44498.Shell"
$napcatExe = Join-Path $napcatRoot "NapCatWinBootMain.exe"

if (-not (Test-Path $startBotScript)) {
    throw "qqbot startup script not found: $startBotScript"
}

if (-not (Test-Path $napcatExe)) {
    throw "NapCat executable not found: $napcatExe"
}

if (-not (Test-Path $startNapcatScript)) {
    throw "NapCat startup script not found: $startNapcatScript"
}

Write-LauncherLog "Logs: $logDir"
$botProcess = $null
$botWasAlreadyRunning = Test-TcpPortOpen -HostName "127.0.0.1" -Port $BotPort

if ($botWasAlreadyRunning) {
    $projectBotProcesses = @()
    $loadedBotProcessFromPidFile = $false
    if ($RestartBot) {
        $projectBotProcesses = @(Get-ProjectBotProcessesFromPidFile -PidFile $botPidFile)
        $loadedBotProcessFromPidFile = $projectBotProcesses.Count -gt 0
    }
    if ($projectBotProcesses.Count -eq 0) {
        $projectBotProcesses = @(Get-ProjectBotProcesses -Root $Root)
    }

    if ($RestartBot -and $projectBotProcesses.Count -gt 0) {
        Write-LauncherLog "qqbot port 127.0.0.1:$BotPort is already open. RestartBot requested; stopping project bot process(es): $($projectBotProcesses.ProcessId -join ', ')."
        if ($loadedBotProcessFromPidFile) {
            foreach ($process in $projectBotProcesses) {
                Stop-Process -Id ([int]$process.ProcessId) -Force -ErrorAction SilentlyContinue
            }
        }
        else {
            Stop-ProjectBotProcesses -Processes $projectBotProcesses
        }
        Wait-TcpPortClosed -HostName "127.0.0.1" -Port $BotPort -TimeoutSeconds 5 | Out-Null
        $botWasAlreadyRunning = Test-TcpPortOpen -HostName "127.0.0.1" -Port $BotPort
    }
    else {
        $sourceLastWriteTime = Get-ProjectSourceLastWriteTime -Root $Root
        $staleBotProcesses = @(
            $projectBotProcesses |
                Where-Object { Test-ProjectBotProcessStale -Process $_ -SourceLastWriteTime $sourceLastWriteTime }
        )

        if ($staleBotProcesses.Count -gt 0) {
            Write-LauncherLog "qqbot port 127.0.0.1:$BotPort is already open, but project source is newer than bot process start time. Stopping stale process(es): $($staleBotProcesses.ProcessId -join ', ')."
            Stop-ProjectBotProcesses -Processes $staleBotProcesses
            Wait-TcpPortClosed -HostName "127.0.0.1" -Port $BotPort -TimeoutSeconds 5 | Out-Null
            $botWasAlreadyRunning = Test-TcpPortOpen -HostName "127.0.0.1" -Port $BotPort
        }
        elseif ($projectBotProcesses.Count -gt 0) {
            Write-LauncherLog "qqbot port 127.0.0.1:$BotPort is already open. Reusing current project bot process(es): $($projectBotProcesses.ProcessId -join ', ')."
        }
        else {
            Write-LauncherLog "qqbot port 127.0.0.1:$BotPort is already open, but it is not owned by this project's bot process. Reusing the existing service."
        }
    }
}

if (-not $botWasAlreadyRunning) {
    Write-LauncherLog "Starting qqbot in a hidden background PowerShell..."

    $botArgs = @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "`"$startBotScript`""
    )

    if ($SkipInstall) {
        $botArgs += "-SkipInstall"
    }

    $botProcess = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList $botArgs `
        -WindowStyle Hidden `
        -RedirectStandardOutput $botStdout `
        -RedirectStandardError $botStderr `
        -PassThru

    Write-LauncherLog "qqbot process id: $($botProcess.Id)"
}

Write-LauncherLog "Waiting for qqbot port 127.0.0.1:$BotPort ..."

if (-not (Wait-TcpPortOpen -HostName "127.0.0.1" -Port $BotPort -TimeoutSeconds $BotPortTimeoutSeconds)) {
    Write-LauncherLog "qqbot did not open port $BotPort within $BotPortTimeoutSeconds seconds."
    Write-LauncherLog "Keep this window open and check: $botStdout"
    Write-LauncherLog "Stderr: $botStderr"
    exit 1
}

Write-LauncherLog "qqbot port is open."

$napcatProcesses = @(Get-NapcatProcesses)
$napcatProcess = $null
$napcatWindowProcess = $null
$napcatStartedInThisRun = $false
$napcatWindowTitle = "QQBot-NapCat-$timestamp"
$napcatQuickLoginQQ = Get-DotEnvValue `
    -Path $envFile `
    -Keys @("QQBOT_NAPCAT_QQ", "QQBOT_BOT_QQ", "QQBOT_ACCOUNT_QQ")
$oneBotAlreadyConnected = Test-OneBotConnected -HostName "127.0.0.1" -Port $BotPort -LogPath $botStdout

if ($napcatProcesses.Count -gt 0) {
    if ($oneBotAlreadyConnected) {
        $napcatProcess = $napcatProcesses | Select-Object -First 1
        Write-LauncherLog "Reusing existing connected NapCat process id: $($napcatProcess.Id)"
    }
    else {
        Write-LauncherLog "Existing NapCat process is not connected yet; waiting up to $ExistingNapcatReconnectTimeoutSeconds seconds for reconnect. Process id(s): $($napcatProcesses.Id -join ', ')."
        $oneBotAlreadyConnected = Wait-OneBotConnected `
            -HostName "127.0.0.1" `
            -Port $BotPort `
            -LogPath $botStdout `
            -TimeoutSeconds $ExistingNapcatReconnectTimeoutSeconds

        if ($oneBotAlreadyConnected) {
            $napcatProcess = $napcatProcesses | Select-Object -First 1
            Write-LauncherLog "Reusing existing NapCat process after reconnect: $($napcatProcess.Id)"
        }
        else {
            Write-LauncherLog "Existing NapCat process did not reconnect; restarting it in a visible window for QR login. Process id(s): $($napcatProcesses.Id -join ', ')."
            Stop-NapcatProcesses -Processes $napcatProcesses
            Start-Sleep -Seconds 2
        }
    }
}

if (-not $oneBotAlreadyConnected -and -not $napcatProcess) {
    Write-LauncherLog "Starting NapCat. If QR login is required, scan it in the visible login window."
    if ($napcatQuickLoginQQ) {
        Write-LauncherLog "NapCat quick login account from .env: $napcatQuickLoginQQ"
    }

    $napcatStartArguments = @(
        "-w",
        "-1",
        "new-tab",
        "--title",
        $napcatWindowTitle,
        "-d",
        $napcatRoot,
        "powershell.exe",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $startNapcatScript
    )
    if ($napcatQuickLoginQQ) {
        $napcatStartArguments += "-QuickLoginQQ"
        $napcatStartArguments += $napcatQuickLoginQQ
    }

    $napcatWindowProcess = Start-Process `
        -FilePath "wt.exe" `
        -ArgumentList $napcatStartArguments `
        -WorkingDirectory $napcatRoot `
        -WindowStyle Normal `
        -PassThru
    $napcatStartedInThisRun = $true
    Start-Sleep -Seconds 2
}

if (-not $oneBotAlreadyConnected) {
    Write-LauncherLog "Waiting for OneBot connection. Timeout: $NapcatLoginTimeoutSeconds seconds."

    if (-not (Wait-OneBotConnected -HostName "127.0.0.1" -Port $BotPort -LogPath $botStdout -TimeoutSeconds $NapcatLoginTimeoutSeconds)) {
        Write-LauncherLog "NapCat did not connect to qqbot before timeout."
        Write-LauncherLog "NapCat window is left visible for QR scan or error inspection."
        Write-LauncherLog "qqbot stdout: $botStdout"
        Write-LauncherLog "qqbot stderr: $botStderr"
        exit 1
    }
}
else {
    Write-LauncherLog "OneBot connection already confirmed."
}

if (-not $napcatStartedInThisRun) {
    Write-LauncherLog "OneBot connected. Reused existing NapCat process; no new NapCat window to hide."
    exit 0
}

Write-LauncherLog "OneBot connected. Hiding NapCat window and closing launcher."

if (Hide-WindowByTitleFragment -TitleFragment $napcatWindowTitle) {
    Write-LauncherLog "NapCat terminal window hidden by title."
    exit 0
}

$terminalProcess = Get-NapcatTerminalProcess `
    -StartNapcatScript $startNapcatScript `
    -WindowTitle $napcatWindowTitle

if ($terminalProcess) {
    if (Hide-ProcessMainWindow -Process $terminalProcess) {
        Write-LauncherLog "NapCat terminal window hidden."
        exit 0
    }
}

$processToHide = $napcatWindowProcess
if (-not $processToHide -or $processToHide.HasExited) {
    $processToHide = Get-NapcatProcess
}

if ($processToHide) {
    if (Hide-ProcessMainWindow -Process $processToHide) {
        Write-LauncherLog "NapCat window hidden."
    }
    else {
        Write-LauncherLog "NapCat process has no hideable main window."
    }
}
else {
    Write-LauncherLog "NapCat launcher process already exited."
}

exit 0
