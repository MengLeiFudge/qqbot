param(
    [ValidateSet("all", "nonebot2", "astrbot")]
    [string]$Target = "all",
    [switch]$SkipInstall,
    [switch]$RestartBot,
    [switch]$Child,
    [ValidateSet("", "nonebot2", "astrbot", "napcat-nonebot2", "napcat-astrbot", "napcat-astrbot-demon", "napcat-astrbot-angel")]
    [string]$Component = "",
    [string]$RunId = "",
    [string]$WindowTitle = "",
    [ValidateSet("", "dual", "full")]
    [string]$FeatureMode = "",
    [ValidateSet("demon", "angel", "both")]
    [string]$AstrBotProfile = "demon",
    [int]$AstrBotOneBotPort = 6200,
    [int]$AstrBotAngelOneBotPort = 6201
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

    if ($Component -eq "astrbot" -or $Component.StartsWith("napcat-astrbot")) {
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

function Sync-NapCatOneBotClientConfig {
    param(
        [string]$Account,
        [int]$BotPort,
        [string]$ClientName,
        [string]$PathSuffix
    )

    $configPath = Join-Path $WorkspaceRoot "napcat\onekey\napcat\config\onebot11_$Account.json"
    if (-not (Test-Path $configPath)) {
        return
    }

    $rawConfig = Get-Content -Raw -Path $configPath -Encoding UTF8
    if (-not $rawConfig.Trim()) {
        return
    }
    $config = $rawConfig | ConvertFrom-Json
    if (-not $config.network) {
        return
    }

    $targetUrl = "ws://127.0.0.1:$BotPort$PathSuffix"
    $clients = @($config.network.websocketClients)
    $client = $clients | Where-Object { $_.name -eq $ClientName } | Select-Object -First 1
    if (-not $client) {
        if ($clients.Count -gt 0) {
            $client = $clients[0]
        }
        else {
            return
        }
    }

    $changed = $false
    if ($client.url -ne $targetUrl) {
        $client.url = $targetUrl
        $changed = $true
    }
    if ($client.enable -ne $true) {
        $client.enable = $true
        $changed = $true
    }

    if ($changed) {
        $json = $config | ConvertTo-Json -Depth 100
        Set-Content -Path $configPath -Value $json -Encoding UTF8
    }
}

function Get-ProcessTreeIds {
    param(
        [int]$RootProcessId,
        [object[]]$Processes
    )

    $ids = [System.Collections.Generic.HashSet[int]]::new()
    $queue = [System.Collections.Generic.Queue[int]]::new()
    $queue.Enqueue($RootProcessId)
    while ($queue.Count -gt 0) {
        $currentId = $queue.Dequeue()
        if (-not $ids.Add($currentId)) {
            continue
        }
        foreach ($child in @($Processes | Where-Object { $_.ParentProcessId -eq $currentId })) {
            $queue.Enqueue([int]$child.ProcessId)
        }
    }
    return @($ids)
}

function Stop-NapCatAccountProcesses {
    param(
        [string]$Account,
        [string]$LogFile
    )

    try {
        $allProcesses = @(Get-CimInstance Win32_Process)
        $accountPattern = "-Account\s+['""]?$([regex]::Escape($Account))['""]?"
        $roots = @($allProcesses | Where-Object {
            $_.CommandLine -and
            $_.CommandLine -match 'start-napcat-account\.ps1' -and
            $_.CommandLine -match $accountPattern
        })
        if ($roots.Count -eq 0) {
            Write-LauncherLog -LogFile $LogFile -Message "No existing NapCat launcher process found for account $Account."
            return
        }

        $targetIds = [System.Collections.Generic.HashSet[int]]::new()
        foreach ($root in $roots) {
            foreach ($processId in (Get-ProcessTreeIds -RootProcessId ([int]$root.ProcessId) -Processes $allProcesses)) {
                if ($processId -ne $PID) {
                    [void]$targetIds.Add([int]$processId)
                }
            }
        }
        if ($targetIds.Count -eq 0) {
            Write-LauncherLog -LogFile $LogFile -Message "Existing NapCat launcher process for account $Account only contains current process."
            return
        }

        Write-LauncherLog -LogFile $LogFile -Message "Stopping existing NapCat account $Account process tree: $($targetIds -join ', ')."
        foreach ($processId in @($targetIds)) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
        foreach ($processId in @($targetIds)) {
            try {
                Wait-Process -Id $processId -Timeout 20 -ErrorAction SilentlyContinue
            }
            catch {
            }
        }
    }
    catch {
        $message = "NapCat account process cleanup failed for {0}: {1}" -f $Account, $_.Exception.Message
        Write-LauncherLog -LogFile $LogFile -Message $message
    }
}

function Get-AstrBotAccount {
    if ($AstrBotProfile -eq "both") {
        return "2629227874"
    }
    if ($AstrBotProfile -eq "angel") {
        return "1443944862"
    }
    return "2629227874"
}

function Get-AstrBotTitle {
    if ($AstrBotProfile -eq "both") {
        return "AstrBot-both"
    }
    if ($AstrBotProfile -eq "angel") {
        return "AstrBot-1443944862"
    }
    return "AstrBot-2629227874"
}

function Get-AstrBotNapCatTitle {
    if ($AstrBotProfile -eq "both") {
        return "NapCat-AstrBot-both"
    }
    if ($AstrBotProfile -eq "angel") {
        return "NapCat-AstrBot-1443944862"
    }
    return "NapCat-2629227874"
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
    Stop-ProcessByPort -Port $AstrBotOneBotPort -Name "AstrBot" -LogFile $launcherLog
    if ($AstrBotProfile -eq "both") {
        Stop-ProcessByPort -Port $AstrBotAngelOneBotPort -Name "AstrBot" -LogFile $launcherLog
    }

    $script = Join-Path $ScriptRoot "start-astrbot.ps1"
    $featureModeArg = if ($FeatureMode) { " -FeatureMode '$FeatureMode'" } else { "" }
    $command = "& '$script'$featureModeArg -BotProfile '$AstrBotProfile' -AiocqhttpPort $AstrBotOneBotPort -AngelAiocqhttpPort $AstrBotAngelOneBotPort"
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
    if (-not (Wait-TcpPort -HostName "127.0.0.1" -Port $AstrBotOneBotPort -TimeoutSeconds 360 -LogFile $launcherLog)) {
        throw "AstrBot did not open port $AstrBotOneBotPort."
    }
    if ($AstrBotProfile -eq "both" -and -not (Wait-TcpPort -HostName "127.0.0.1" -Port $AstrBotAngelOneBotPort -TimeoutSeconds 360 -LogFile $launcherLog)) {
        throw "AstrBot did not open port $AstrBotAngelOneBotPort."
    }
}

function Start-NapCatComponent {
    param(
        [string]$RunId,
        [string]$Account,
        [int]$BotPort,
        [string]$DoneCheck,
        [string]$ComponentName = ""
    )

    $componentName = if ($ComponentName) { $ComponentName } elseif ($Account -eq "1443944862") { "napcat-nonebot2" } else { "napcat-astrbot" }
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

    if ($DoneCheck -eq "nonebot2") {
        Sync-NapCatOneBotClientConfig -Account $Account -BotPort $BotPort -ClientName "qqbot-reverse-ws" -PathSuffix "/onebot/v11/ws"
    }
    else {
        Sync-NapCatOneBotClientConfig -Account $Account -BotPort $BotPort -ClientName "astrbot-reverse-ws" -PathSuffix "/ws"
    }

    Stop-NapCatAccountProcesses -Account $Account -LogFile $launcherLog
    $script = Join-Path $ScriptRoot "start-napcat-account.ps1"
    $command = "& '$script' -Account '$Account'"
    $process = Start-BackgroundPowerShell -CommandText $command -WorkingDirectory $WorkspaceRoot -StdoutLog $stdoutLog -StderrLog $stderrLog -LauncherLog $launcherLog
    Write-LauncherLog -LogFile $launcherLog -Message "NapCat stdout log: $stdoutLog"

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
            "napcat-astrbot" { Start-NapCatComponent -RunId $RunId -Account (Get-AstrBotAccount) -BotPort $AstrBotOneBotPort -DoneCheck "astrbot" -ComponentName "napcat-astrbot" }
            "napcat-astrbot-demon" { Start-NapCatComponent -RunId $RunId -Account "2629227874" -BotPort $AstrBotOneBotPort -DoneCheck "astrbot" -ComponentName "napcat-astrbot-demon" }
            "napcat-astrbot-angel" { Start-NapCatComponent -RunId $RunId -Account "1443944862" -BotPort $AstrBotAngelOneBotPort -DoneCheck "astrbot" -ComponentName "napcat-astrbot-angel" }
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
    if ($FeatureMode) {
        $arguments += @("-FeatureMode", $FeatureMode)
    }
    if ($AstrBotProfile) {
        $arguments += @("-AstrBotProfile", $AstrBotProfile)
    }
    $arguments += @("-AstrBotOneBotPort", $AstrBotOneBotPort)
    $arguments += @("-AstrBotAngelOneBotPort", $AstrBotAngelOneBotPort)
    Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -WorkingDirectory $WorkspaceRoot | Out-Null
}

function Start-ComponentWindow {
    param(
        [string]$RunId,
        [string]$Component
    )

    switch ($Component) {
        "nonebot2" { Start-ChildWindow -RunId $RunId -Component $Component -Title "NoneBot2-1443944862" }
        "astrbot" { Start-ChildWindow -RunId $RunId -Component $Component -Title (Get-AstrBotTitle) }
        "napcat-nonebot2" { Start-ChildWindow -RunId $RunId -Component $Component -Title "NapCat-1443944862" }
        "napcat-astrbot" { Start-ChildWindow -RunId $RunId -Component $Component -Title (Get-AstrBotNapCatTitle) }
        "napcat-astrbot-demon" { Start-ChildWindow -RunId $RunId -Component $Component -Title "NapCat-AstrBot-2629227874" }
        "napcat-astrbot-angel" { Start-ChildWindow -RunId $RunId -Component $Component -Title "NapCat-AstrBot-1443944862" }
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
    if ($FeatureMode -eq "full" -and $Target -ne "astrbot") {
        throw "FeatureMode full is only allowed with -Target astrbot. Use dual when NoneBot2 is also running."
    }
    if ($AstrBotProfile -eq "both" -and $Target -ne "astrbot") {
        throw "AstrBotProfile both is only allowed with -Target astrbot because account 1443944862 belongs to bot1 outside AstrBot-only mode."
    }
    if ($AstrBotProfile -eq "both" -and $FeatureMode -ne "full") {
        throw "AstrBotProfile both requires -FeatureMode full so AstrBot-only event ownership is explicit."
    }
    if ($AstrBotProfile -eq "angel" -and $Target -ne "astrbot") {
        throw "AstrBotProfile angel is only allowed with -Target astrbot because account 1443944862 belongs to bot1 in dual mode."
    }
    if ($AstrBotProfile -eq "angel" -and $FeatureMode -ne "full") {
        throw "AstrBotProfile angel requires -FeatureMode full so AstrBot-only event ownership is explicit."
    }

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
        if ($AstrBotProfile -eq "both") {
            $napcatComponents += "napcat-astrbot-demon"
            $napcatComponents += "napcat-astrbot-angel"
        }
        else {
            $napcatComponents += "napcat-astrbot"
        }
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
