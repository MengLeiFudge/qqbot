param(
    [ValidateSet("all", "nonebot2", "astrbot")]
    [string]$Target = "all",
    [switch]$SkipInstall,
    [switch]$RestartBot,
    [switch]$Child,
    [ValidateSet("", "nonebot2", "astrbot", "napcat-nonebot2", "napcat-astrbot")]
    [string]$Component = "",
    [string]$RunId = "",
    [string]$WindowTitle = ""
)

$ErrorActionPreference = "Stop"
$ScriptRoot = $PSScriptRoot
$WorkspaceRoot = Split-Path -Parent $ScriptRoot

function New-RunId {
    return Get-Date -Format "yyyyMMdd-HHmmss"
}

function Get-ControlRoot {
    param([string]$RunId)
    return Join-Path $WorkspaceRoot "data\launcher\$RunId"
}

function Get-ComponentLogRoot {
    param(
        [string]$Component,
        [string]$RunId
    )

    if ($Component -eq "astrbot" -or $Component -eq "napcat-astrbot") {
        return Join-Path $WorkspaceRoot "data\astrbot\logs\start_all\$RunId\$Component"
    }
    return Join-Path $WorkspaceRoot "data\nonebot2\logs\start_all\$RunId\$Component"
}

function Write-LauncherLog {
    param(
        [string]$LogFile,
        [string]$Message,
        [switch]$NoConsole
    )

    $parent = Split-Path -Parent $LogFile
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    if (-not $NoConsole) {
        Write-Host $line
    }
}

function Get-LogTailText {
    param(
        [string]$Path,
        [int]$Count = 12
    )

    if (-not (Test-Path $Path)) {
        return ""
    }
    try {
        $lines = Get-Content -Path $Path -Tail $Count -ErrorAction Stop
        return ($lines -join "`n").Trim()
    }
    catch {
        return ""
    }
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
        [string]$LogFile,
        [System.Diagnostics.Process]$Process = $null
    )

    Write-LauncherLog -LogFile $LogFile -Message "Waiting for port ${HostName}:$Port for up to $TimeoutSeconds seconds."
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (Test-TcpPort -HostName $HostName -Port $Port) {
            Write-LauncherLog -LogFile $LogFile -Message "Port ${HostName}:$Port is ready."
            return $true
        }
        if ($Process -and $Process.HasExited) {
            Write-LauncherLog -LogFile $LogFile -Message "Background process pid=$($Process.Id) exited before port ${HostName}:$Port was ready. exit_code=$($Process.ExitCode)"
            return $false
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    Write-LauncherLog -LogFile $LogFile -Message "Timed out waiting for port ${HostName}:$Port."
    return $false
}

function Get-AdminStatus {
    param([string]$Url)

    try {
        return Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 3
    }
    catch {
        return $null
    }
}

function Wait-NoneBotConnection {
    param(
        [int]$TimeoutSeconds,
        [string]$LogFile,
        [System.Diagnostics.Process]$Process = $null
    )

    Write-LauncherLog -LogFile $LogFile -Message "Waiting for NoneBot OneBot connection for up to $TimeoutSeconds seconds."
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $status = Get-AdminStatus -Url "http://127.0.0.1:8080/admin/api/status"
        if ($status -and ($status.onebot_connected -or ([int]$status.connected_bot_count -ge 1))) {
            Write-LauncherLog -LogFile $LogFile -Message "NoneBot OneBot connection confirmed. connected_bot_count=$($status.connected_bot_count)"
            return $true
        }
        try {
            $connection = Get-NetTCPConnection -LocalPort 8080 -State Established -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($connection) {
                Write-LauncherLog -LogFile $LogFile -Message "NoneBot TCP connection confirmed on local port 8080."
                return $true
            }
        }
        catch {
        }
        if ($Process -and $Process.HasExited) {
            Write-LauncherLog -LogFile $LogFile -Message "Background process pid=$($Process.Id) exited before NoneBot OneBot connection was ready. exit_code=$($Process.ExitCode)"
            return $false
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    Write-LauncherLog -LogFile $LogFile -Message "Timed out waiting for NoneBot OneBot connection."
    return $false
}

function Wait-EstablishedConnection {
    param(
        [int]$Port,
        [int]$TimeoutSeconds,
        [string]$LogFile,
        [System.Diagnostics.Process]$Process = $null
    )

    Write-LauncherLog -LogFile $LogFile -Message "Waiting for established TCP connection on local port $Port for up to $TimeoutSeconds seconds."
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $connection = Get-NetTCPConnection -LocalPort $Port -State Established -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($connection) {
                Write-LauncherLog -LogFile $LogFile -Message "Established TCP connection confirmed on local port $Port."
                return $true
            }
        }
        catch {
            if (Test-TcpPort -HostName "127.0.0.1" -Port $Port) {
                Write-LauncherLog -LogFile $LogFile -Message "Port $Port is listening; established connection check is unavailable."
                return $true
            }
        }
        if ($Process -and $Process.HasExited) {
            Write-LauncherLog -LogFile $LogFile -Message "Background process pid=$($Process.Id) exited before TCP connection on local port $Port was ready. exit_code=$($Process.ExitCode)"
            return $false
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    Write-LauncherLog -LogFile $LogFile -Message "Timed out waiting for established TCP connection on local port $Port."
    return $false
}

function Stop-ProcessByPidFile {
    param(
        [string]$PidFile,
        [string]$Name,
        [string]$LogFile
    )

    if (-not (Test-Path $PidFile)) {
        Write-LauncherLog -LogFile $LogFile -Message "No existing $Name pid file found."
        return
    }

    $pidText = Get-Content -Path $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $pidText) {
        Write-LauncherLog -LogFile $LogFile -Message "$Name pid file is empty."
        return
    }
    $pidText = $pidText.Trim()
    if (-not ($pidText -match '^\d+$')) {
        Write-LauncherLog -LogFile $LogFile -Message "Invalid $Name pid file content: $pidText"
        return
    }

    $targetPid = [int]$pidText
    if ($targetPid -eq $PID) {
        Write-LauncherLog -LogFile $LogFile -Message "Skip stopping current launcher pid=$targetPid."
        return
    }

    $process = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
    if (-not $process) {
        Write-LauncherLog -LogFile $LogFile -Message "Existing $Name pid=$targetPid is not running."
        return
    }

    Write-LauncherLog -LogFile $LogFile -Message "Stopping existing $Name pid=$targetPid."
    Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
    try {
        Wait-Process -Id $targetPid -Timeout 30 -ErrorAction SilentlyContinue
    }
    catch {
    }
}

function Stop-ProcessByPort {
    param(
        [int]$Port,
        [string]$Name,
        [string]$LogFile
    )

    try {
        $owners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($owner in $owners) {
            if ($owner -and $owner -ne $PID) {
                Write-LauncherLog -LogFile $LogFile -Message "Stopping existing $Name pid=$owner by port $Port."
                Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
            }
        }
    }
    catch {
        $message = "Port owner lookup failed for {0} on {1}: {2}" -f $Name, $Port, $_.Exception.Message
        Write-LauncherLog -LogFile $LogFile -Message $message
    }
}

function Get-NapCatAccountProcesses {
    param([string]$Account)

    try {
        return Get-CimInstance Win32_Process |
            Where-Object {
                $_.CommandLine -and
                $_.CommandLine.Contains($Account) -and
                ($_.CommandLine -match 'NapCatWinBootMain|QQ\.exe') -and
                ($_.CommandLine -notmatch 'start-all\.ps1|start-napcat-account\.ps1')
            }
    }
    catch {
        return @()
    }
}

function Test-NapCatAccountRunning {
    param([string]$Account)
    $processes = @(Get-NapCatAccountProcesses -Account $Account)
    return $processes.Count -gt 0
}

function Start-BackgroundPowerShell {
    param(
        [string]$CommandText,
        [string]$WorkingDirectory,
        [string]$StdoutLog,
        [string]$StderrLog,
        [string]$LauncherLog
    )

    $wrappedCommand = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; " +
        "`$env:PYTHONUTF8 = '1'; `$env:PYTHONIOENCODING = 'utf-8'; " +
        "& { $CommandText }"
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        $wrappedCommand
    )
    $process = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList $arguments `
        -WorkingDirectory $WorkingDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput $StdoutLog `
        -RedirectStandardError $StderrLog `
        -PassThru
    Write-LauncherLog -LogFile $LauncherLog -Message "Started background PowerShell pid=$($process.Id)."
    return $process
}

function Start-NoneBotComponent {
    param(
        [string]$RunId,
        [switch]$NoNapCatWait
    )

    $logRoot = Get-ComponentLogRoot -Component "nonebot2" -RunId $RunId
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $launcherLog = Join-Path $logRoot "launcher.log"
    $stdoutLog = Join-Path $logRoot "qqbot_stdout.log"
    $stderrLog = Join-Path $logRoot "qqbot_stderr.log"
    New-Item -ItemType File -Path $stdoutLog -Force | Out-Null
    New-Item -ItemType File -Path $stderrLog -Force | Out-Null

    Write-LauncherLog -LogFile $launcherLog -Message "Starting NoneBot2 component."
    Stop-ProcessByPidFile -PidFile (Join-Path $WorkspaceRoot "data\nonebot2\run\qqbot.pid") -Name "NoneBot2" -LogFile $launcherLog
    Stop-ProcessByPort -Port 8080 -Name "NoneBot2" -LogFile $launcherLog

    $script = Join-Path $ScriptRoot "start-nonebot2.ps1"
    $extra = if ($SkipInstall) { "-SkipInstall" } else { "" }
    $command = "& '$script' $extra"
    $process = Start-BackgroundPowerShell -CommandText $command -WorkingDirectory $WorkspaceRoot -StdoutLog $stdoutLog -StderrLog $stderrLog -LauncherLog $launcherLog
    Write-LauncherLog -LogFile $launcherLog -Message "NoneBot2 stdout log: $stdoutLog"

    if (-not (Wait-TcpPort -HostName "127.0.0.1" -Port 8080 -TimeoutSeconds 90 -LogFile $launcherLog -Process $process)) {
        $tail = Get-LogTailText -Path $stdoutLog
        if ($tail) {
            Write-Host "Recent NoneBot2 output:" -ForegroundColor Yellow
            Write-Host $tail
        }
        if ($process.HasExited) {
            throw "NoneBot2 exited before opening port 8080. exit_code=$($process.ExitCode). Log: $stdoutLog"
        }
        throw "NoneBot2 did not open port 8080. Log: $stdoutLog"
    }
    if (-not $NoNapCatWait) {
        Write-LauncherLog -LogFile $launcherLog -Message "NoneBot2 component is ready for NapCat."
    }
}

function Start-AstrBotComponent {
    param([string]$RunId)

    $logRoot = Get-ComponentLogRoot -Component "astrbot" -RunId $RunId
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $launcherLog = Join-Path $logRoot "launcher.log"
    $stdoutLog = Join-Path $logRoot "astrbot_stdout.log"
    $stderrLog = Join-Path $logRoot "astrbot_stderr.log"
    New-Item -ItemType File -Path $stdoutLog -Force | Out-Null
    New-Item -ItemType File -Path $stderrLog -Force | Out-Null

    Write-LauncherLog -LogFile $launcherLog -Message "Starting AstrBot component."
    Stop-ProcessByPort -Port 6185 -Name "AstrBot" -LogFile $launcherLog
    Stop-ProcessByPort -Port 6199 -Name "AstrBot" -LogFile $launcherLog

    $script = Join-Path $ScriptRoot "start-astrbot.ps1"
    $command = "& '$script'"
    $process = Start-BackgroundPowerShell -CommandText $command -WorkingDirectory $WorkspaceRoot -StdoutLog $stdoutLog -StderrLog $stderrLog -LauncherLog $launcherLog
    Write-LauncherLog -LogFile $launcherLog -Message "AstrBot stdout log: $stdoutLog"

    if (-not (Wait-TcpPort -HostName "127.0.0.1" -Port 6185 -TimeoutSeconds 360 -LogFile $launcherLog -Process $process)) {
        $tail = Get-LogTailText -Path $stdoutLog
        if ($tail) {
            Write-Host "Recent AstrBot output:" -ForegroundColor Yellow
            Write-Host $tail
        }
        if ($process.HasExited) {
            throw "AstrBot exited before opening port 6185. exit_code=$($process.ExitCode). Log: $stdoutLog"
        }
        throw "AstrBot did not open port 6185. Log: $stdoutLog"
    }
    if (-not (Wait-TcpPort -HostName "127.0.0.1" -Port 6199 -TimeoutSeconds 360 -LogFile $launcherLog)) {
        throw "AstrBot did not open port 6199."
    }
}

function Start-NapCatComponent {
    param(
        [string]$RunId,
        [string]$Account,
        [int]$BotPort,
        [string]$DoneCheck
    )

    $componentName = if ($Account -eq "1443944862") { "napcat-nonebot2" } else { "napcat-astrbot" }
    $logRoot = Get-ComponentLogRoot -Component $componentName -RunId $RunId
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $launcherLog = Join-Path $logRoot "launcher.log"
    $stdoutLog = Join-Path $logRoot "napcat_stdout.log"
    $stderrLog = Join-Path $logRoot "napcat_stderr.log"
    New-Item -ItemType File -Path $stdoutLog -Force | Out-Null
    New-Item -ItemType File -Path $stderrLog -Force | Out-Null

    Write-LauncherLog -LogFile $launcherLog -Message "Starting NapCat account $Account."
    if (-not (Wait-TcpPort -HostName "127.0.0.1" -Port $BotPort -TimeoutSeconds 120 -LogFile $launcherLog)) {
        throw "Target bot port $BotPort is not ready for NapCat account $Account."
    }

    if (Test-NapCatAccountRunning -Account $Account) {
        Write-LauncherLog -LogFile $launcherLog -Message "NapCat account $Account is already running; waiting for connection."
        $process = $null
    }
    else {
        $script = Join-Path $ScriptRoot "start-napcat-account.ps1"
        $command = "& '$script' -Account '$Account'"
        $process = Start-BackgroundPowerShell -CommandText $command -WorkingDirectory $WorkspaceRoot -StdoutLog $stdoutLog -StderrLog $stderrLog -LauncherLog $launcherLog
        Write-LauncherLog -LogFile $launcherLog -Message "NapCat stdout log: $stdoutLog"
    }

    if ($DoneCheck -eq "nonebot2") {
        if (-not (Wait-NoneBotConnection -TimeoutSeconds 120 -LogFile $launcherLog -Process $process)) {
            $tail = Get-LogTailText -Path $stderrLog
            if ($tail) {
                Write-Host "Recent NapCat error output:" -ForegroundColor Yellow
                Write-Host $tail
            }
            throw "NapCat account $Account did not connect to NoneBot2."
        }
    }
    else {
        if (-not (Wait-EstablishedConnection -Port $BotPort -TimeoutSeconds 120 -LogFile $launcherLog -Process $process)) {
            $tail = Get-LogTailText -Path $stderrLog
            if ($tail) {
                Write-Host "Recent NapCat error output:" -ForegroundColor Yellow
                Write-Host $tail
            }
            throw "NapCat account $Account did not connect to AstrBot."
        }
    }
}

function Complete-Child {
    param(
        [string]$RunId,
        [string]$Component
    )

    $controlRoot = Get-ControlRoot -RunId $RunId
    New-Item -ItemType Directory -Path $controlRoot -Force | Out-Null
    Set-Content -Path (Join-Path $controlRoot "$Component.done") -Value "done" -Encoding UTF8
}

function Fail-Child {
    param(
        [string]$RunId,
        [string]$Component,
        [string]$Message
    )

    $controlRoot = Get-ControlRoot -RunId $RunId
    New-Item -ItemType Directory -Path $controlRoot -Force | Out-Null
    Set-Content -Path (Join-Path $controlRoot "$Component.failed") -Value $Message -Encoding UTF8
}

function Invoke-Child {
    if (-not $RunId) {
        throw "Child mode requires -RunId."
    }
    if (-not $Component) {
        throw "Child mode requires -Component."
    }
    if ($WindowTitle) {
        try {
            $Host.UI.RawUI.WindowTitle = $WindowTitle
        }
        catch {
        }
    }

    try {
        switch ($Component) {
            "nonebot2" { Start-NoneBotComponent -RunId $RunId -NoNapCatWait }
            "astrbot" { Start-AstrBotComponent -RunId $RunId }
            "napcat-nonebot2" { Start-NapCatComponent -RunId $RunId -Account "1443944862" -BotPort 8080 -DoneCheck "nonebot2" }
            "napcat-astrbot" { Start-NapCatComponent -RunId $RunId -Account "2629227874" -BotPort 6199 -DoneCheck "astrbot" }
            default { throw "Unknown component: $Component" }
        }
        Complete-Child -RunId $RunId -Component $Component
        Write-Host "$Component ready. Closing this window."
        exit 0
    }
    catch {
        $message = $_.Exception.Message
        Write-Host "Startup failed: $message" -ForegroundColor Red
        Fail-Child -RunId $RunId -Component $Component -Message $message
        Read-Host "Press Enter to close this window"
        exit 1
    }
}

function Start-ChildWindow {
    param(
        [string]$RunId,
        [string]$Component,
        [string]$Title
    )

    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $PSCommandPath,
        "-Child",
        "-RunId",
        $RunId,
        "-Component",
        $Component,
        "-WindowTitle",
        $Title
    )
    if ($SkipInstall) {
        $arguments += "-SkipInstall"
    }
    Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -WorkingDirectory $WorkspaceRoot | Out-Null
}

function Start-ComponentWindow {
    param(
        [string]$RunId,
        [string]$Component
    )

    switch ($Component) {
        "nonebot2" { Start-ChildWindow -RunId $RunId -Component $Component -Title "NoneBot2-1443944862" }
        "astrbot" { Start-ChildWindow -RunId $RunId -Component $Component -Title "AstrBot-2629227874" }
        "napcat-nonebot2" { Start-ChildWindow -RunId $RunId -Component $Component -Title "NapCat-1443944862" }
        "napcat-astrbot" { Start-ChildWindow -RunId $RunId -Component $Component -Title "NapCat-2629227874" }
        default { throw "Unknown component: $Component" }
    }
}

function Wait-Children {
    param(
        [string]$RunId,
        [string[]]$Components
    )

    $controlRoot = Get-ControlRoot -RunId $RunId
    New-Item -ItemType Directory -Path $controlRoot -Force | Out-Null
    $pending = [System.Collections.Generic.HashSet[string]]::new([string[]]$Components)
    while ($pending.Count -gt 0) {
        $readyThisRound = $false
        foreach ($componentName in @($pending)) {
            $donePath = Join-Path $controlRoot "$componentName.done"
            $failedPath = Join-Path $controlRoot "$componentName.failed"
            if (Test-Path $failedPath) {
                $message = Get-Content -Raw -Path $failedPath
                throw "$componentName failed: $message"
            }
            if (Test-Path $donePath) {
                [void]$pending.Remove($componentName)
                Write-Host "$componentName ready."
                $readyThisRound = $true
            }
        }
        if ($pending.Count -gt 0) {
            if ($readyThisRound) {
                Write-Host "Waiting for: $($pending -join ', ')"
            }
            Start-Sleep -Seconds 1
        }
    }
}

function Invoke-Parent {
    $runId = New-RunId
    $controlRoot = Get-ControlRoot -RunId $runId
    New-Item -ItemType Directory -Path $controlRoot -Force | Out-Null

    $botComponents = @()
    $napcatComponents = @()
    if ($Target -eq "nonebot2" -or $Target -eq "all") {
        $botComponents += "nonebot2"
        $napcatComponents += "napcat-nonebot2"
    }
    if ($Target -eq "astrbot" -or $Target -eq "all") {
        $botComponents += "astrbot"
        $napcatComponents += "napcat-astrbot"
    }

    Write-Host "Starting target: $Target"
    Write-Host "Starting bot services: $($botComponents -join ', ')"
    foreach ($componentName in $botComponents) {
        Start-ComponentWindow -RunId $runId -Component $componentName
    }
    Wait-Children -RunId $runId -Components $botComponents

    Write-Host "Starting NapCat accounts: $($napcatComponents -join ', ')"
    foreach ($componentName in $napcatComponents) {
        Start-ComponentWindow -RunId $runId -Component $componentName
    }
    Wait-Children -RunId $runId -Components $napcatComponents
    Write-Host "All targets are ready."
}

if ($Child) {
    Invoke-Child
    exit $LASTEXITCODE
}

if ($RestartBot) {
    $runId = New-RunId
    Start-NoneBotComponent -RunId $runId
    $restartLogRoot = Get-ComponentLogRoot -Component "nonebot2" -RunId $runId
    $restartLogFile = Join-Path $restartLogRoot "launcher.log"
    if (-not (Wait-NoneBotConnection -TimeoutSeconds 120 -LogFile $restartLogFile)) {
        exit 2
    }
    exit 0
}

try {
    Invoke-Parent
    exit 0
}
catch {
    $message = $_.Exception.Message
    Write-Host "Startup failed: $message" -ForegroundColor Red
    exit 1
}
