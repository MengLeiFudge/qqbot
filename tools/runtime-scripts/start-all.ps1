param(
    [ValidateSet("astrbot")]
    [string]$Target = "astrbot",
    [switch]$SkipInstall,
    [switch]$Child,
    [ValidateSet("", "astrbot", "napcat-astrbot", "napcat-astrbot-demon", "napcat-astrbot-angel")]
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

if ($Target -eq "astrbot") {
    if (-not $PSBoundParameters.ContainsKey("FeatureMode")) {
        $FeatureMode = "full"
    }
    if (-not $PSBoundParameters.ContainsKey("AstrBotProfile")) {
        $AstrBotProfile = "both"
    }
}

$ErrorActionPreference = "Stop"
$ScriptRoot = $PSScriptRoot
$WorkspaceRoot = Split-Path -Parent (Split-Path -Parent $ScriptRoot)

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

    return Join-Path $WorkspaceRoot "data\astrbot\logs\start_all\$RunId\$Component"
}

function Get-NapCatLoginMarkerRoot {
    return Join-Path $WorkspaceRoot "data\launcher\napcat-quick-login"
}

function Get-NapCatLoginMarkerPath {
    param([string]$Account)

    return Join-Path (Get-NapCatLoginMarkerRoot) "$Account.ready"
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

function Test-AsciiText {
    param([string]$Text)

    if (-not $Text) {
        return $true
    }
    foreach ($char in $Text.ToCharArray()) {
        $codePoint = [int]$char
        if (-not ($codePoint -eq 9 -or $codePoint -eq 10 -or $codePoint -eq 13 -or ($codePoint -ge 32 -and $codePoint -le 126))) {
            return $false
        }
    }
    return $true
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
        $lines = Get-Content -Path $Path -Tail $Count -Encoding UTF8 -ErrorAction Stop
        return ($lines -join "`n").Trim()
    }
    catch {
        return ""
    }
}

function Get-SafeConsoleLogTailText {
    param(
        [string]$Path,
        [int]$Count = 12
    )

    $tail = Get-LogTailText -Path $Path -Count $Count
    if (-not $tail) {
        return ""
    }

    $safeLines = @()
    foreach ($line in @($tail -split "\r?\n")) {
        $cleanLine = Remove-LogDecoration -Text $line
        if (-not $cleanLine) {
            continue
        }
        if (Test-AsciiText -Text $cleanLine) {
            $safeLines += $cleanLine
        }
    }
    if ($safeLines.Count -gt 0) {
        return ($safeLines -join "`n").Trim()
    }
    return "Recent log only contains non-ASCII text; open the log file directly."
}

function Limit-LogText {
    param(
        [string]$Text,
        [int]$MaxLength = 240
    )

    if (-not $Text) {
        return ""
    }
    $singleLine = ($Text -replace "\s+", " ").Trim()
    if ($singleLine.Length -le $MaxLength) {
        return $singleLine
    }
    return ($singleLine.Substring(0, $MaxLength) + "...")
}

function Remove-LogDecoration {
    param([string]$Text)

    if (-not $Text) {
        return ""
    }
    return (($Text -replace "\x1B\[[0-9;]*[A-Za-z]", "") -replace "[\x00-\x08\x0B\x0C\x0E-\x1F]", "").Trim()
}

function Join-TextFromCodePoints {
    param([int[]]$CodePoints)

    return -join ($CodePoints | ForEach-Object { [string][char]$_ })
}

function Test-DecorativeQrLine {
    param([string]$Text)

    if (-not $Text) {
        return $false
    }
    foreach ($char in $Text.ToCharArray()) {
        $codePoint = [int]$char
        if (-not ([char]::IsWhiteSpace($char) -or $codePoint -eq 0x2580 -or $codePoint -eq 0x2584 -or $codePoint -eq 0x2588)) {
            return $false
        }
    }
    return $true
}

function Get-LastSafeLogLine {
    param([string]$Text)

    if (-not $Text) {
        return ""
    }

    $lines = @($Text -split "\r?\n")
    [array]::Reverse($lines)
    foreach ($line in $lines) {
        $cleanLine = (Remove-LogDecoration -Text $line).Trim()
        if (-not $cleanLine) {
            continue
        }
        if (Test-DecorativeQrLine -Text $cleanLine) {
            continue
        }
        $qrDecodeUrlText = Join-TextFromCodePoints @(0x4E8C, 0x7EF4, 0x7801, 0x89E3, 0x7801)
        if ($cleanLine -match "(?i)token=|WebUi Token|$qrDecodeUrlText URL|txz\.qq\.com|authorization|cookie|password|secret") {
            continue
        }
        if (-not (Test-AsciiText -Text $cleanLine)) {
            continue
        }
        return (Limit-LogText -Text $cleanLine)
    }

    return ""
}

function Get-StartupLogSignalSummary {
    param(
        [string]$Path,
        [int]$Count = 120
    )

    if (-not $Path -or -not (Test-Path $Path)) {
        return ""
    }

    $tail = Get-LogTailText -Path $Path -Count $Count
    if (-not $tail) {
        return ""
    }

    $cleanTail = Remove-LogDecoration -Text $tail
    $signals = [System.Collections.Generic.List[string]]::new()
    $quickLoginFailedText = Join-TextFromCodePoints @(0x81EA, 0x52A8, 0x5FEB, 0x901F, 0x767B, 0x5F55, 0x5931, 0x8D25)
    $scanQrText = Join-TextFromCodePoints @(0x8BF7, 0x626B, 0x63CF, 0x4E0B, 0x9762, 0x7684, 0x4E8C, 0x7EF4, 0x7801)
    $qrSavedText = Join-TextFromCodePoints @(0x4E8C, 0x7EF4, 0x7801, 0x5DF2, 0x4FDD, 0x5B58, 0x5230)
    $adapterConnectedText = Join-TextFromCodePoints @(0x9002, 0x914D, 0x5668, 0x5DF2, 0x8FDE, 0x63A5)
    $connectionSucceededText = Join-TextFromCodePoints @(0x8FDE, 0x63A5, 0x6210, 0x529F)

    if ($cleanTail -match [regex]::Escape($quickLoginFailedText)) {
        [void]$signals.Add("NapCat quick login failed; waiting for QR login")
    }
    if ($cleanTail -match [regex]::Escape($scanQrText)) {
        [void]$signals.Add("NapCat is waiting for QR scan authorization")
    }
    if ($cleanTail -match "$([regex]::Escape($qrSavedText))\s+([^\r\n]+)") {
        [void]$signals.Add("QR image saved: $(Limit-LogText -Text $Matches[1] -MaxLength 160)")
    }
    elseif ($cleanTail -match "(?i)([A-Za-z]:\\[^\r\n]*?qrcode\.png)") {
        [void]$signals.Add("NapCat is waiting for QR login; shared QR image path detected")
        [void]$signals.Add("QR image saved: $(Limit-LogText -Text $Matches[1] -MaxLength 160)")
    }
    elseif ($cleanTail -match "(?i)qrcode\.png") {
        [void]$signals.Add("NapCat is waiting for QR login; shared QR image path detected")
    }
    if ($cleanTail -match "\[Core\]\s+\[Login\]\s+Login Error[^\r\n]*") {
        [void]$signals.Add("NapCat login error: $(Limit-LogText -Text $Matches[0])")
    }
    if ($cleanTail -match "EADDRINUSE[^\r\n]*") {
        [void]$signals.Add("Port conflict in child log: $(Limit-LogText -Text $Matches[0])")
    }
    if ($cleanTail -match "AstrBot started\.") {
        [void]$signals.Add("AstrBot started")
    }
    if ($cleanTail -match "WebUI is ready") {
        [void]$signals.Add("AstrBot WebUI is ready")
    }
    if ($cleanTail -match "Loading IM platform adapter[^\r\n]*") {
        [void]$signals.Add("AstrBot is loading IM platform adapters")
    }
    if ($cleanTail -match "LocalArtifactApi.*listening on http://127\.0\.0\.1:8080") {
        [void]$signals.Add("Local artifact API is listening")
    }
    if ($cleanTail -match "$([regex]::Escape($adapterConnectedText))|adapter.*connected|WebSocket.*connected|$([regex]::Escape($connectionSucceededText))") {
        [void]$signals.Add("OneBot/WebSocket connection appears in log")
    }

    $lastLine = Get-LastSafeLogLine -Text $cleanTail
    if ($lastLine) {
        [void]$signals.Add("latest ascii log: $lastLine")
    }

    $unique = [System.Collections.Generic.List[string]]::new()
    $seen = [System.Collections.Generic.HashSet[string]]::new()
    foreach ($signal in $signals) {
        if ($seen.Add($signal)) {
            [void]$unique.Add($signal)
        }
    }

    return ($unique -join "; ")
}

function Test-NapCatQuickLoginReady {
    param([string]$Account)

    return Test-Path (Get-NapCatLoginMarkerPath -Account $Account)
}

function Set-NapCatQuickLoginReady {
    param(
        [string]$Account,
        [bool]$Ready,
        [string]$Reason,
        [string]$LogFile = ""
    )

    $markerPath = Get-NapCatLoginMarkerPath -Account $Account
    $markerRoot = Split-Path -Parent $markerPath
    New-Item -ItemType Directory -Path $markerRoot -Force | Out-Null

    if ($Ready) {
        $content = @(
            "account=$Account",
            "ready=true",
            "updated_at=$((Get-Date).ToString('s'))",
            "reason=$Reason"
        )
        Set-Content -Path $markerPath -Value $content -Encoding UTF8
        if ($LogFile) {
            Write-LauncherLog -LogFile $LogFile -Message "NapCat quick-login marker set: account=$Account file=$markerPath reason=$Reason"
        }
    }
    else {
        if (Test-Path $markerPath) {
            Remove-Item -Path $markerPath -Force
        }
        if ($LogFile) {
            Write-LauncherLog -LogFile $LogFile -Message "NapCat quick-login marker cleared: account=$Account file=$markerPath reason=$Reason"
        }
    }
}

function Get-NapCatAccountForComponent {
    param([string]$ComponentName)

    switch ($ComponentName) {
        "napcat-astrbot-demon" { return "2629227874" }
        "napcat-astrbot-angel" { return "1443944862" }
        "napcat-astrbot" { return (Get-AstrBotAccount) }
        default { throw "Unknown NapCat component: $ComponentName" }
    }
}

function Get-NapCatComponentsMissingQuickLogin {
    param([string[]]$Components)

    $missing = @()
    foreach ($componentName in $Components) {
        $account = Get-NapCatAccountForComponent -ComponentName $componentName
        if (-not (Test-NapCatQuickLoginReady -Account $account)) {
            $missing += "$componentName/account=$account"
        }
    }
    return $missing
}

function Test-AllNapCatQuickLoginReady {
    param([string[]]$Components)

    return ((Get-NapCatComponentsMissingQuickLogin -Components $Components).Count -eq 0)
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

function Get-BackgroundProcessDiagnostic {
    param([System.Diagnostics.Process]$Process = $null)

    if (-not $Process) {
        return ""
    }

    try {
        if ($Process.HasExited) {
            return "background pid=$($Process.Id) exited exit_code=$($Process.ExitCode)"
        }
        return "background pid=$($Process.Id) running"
    }
    catch {
        return "background process status unavailable: $($_.Exception.Message)"
    }
}

function Get-TcpPortDiagnostic {
    param([int]$Port)

    try {
        $connections = @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue)
        if ($connections.Count -eq 0) {
            return "tcp local port $Port has no rows"
        }

        $items = @()
        foreach ($connection in @($connections | Sort-Object State, RemoteAddress, RemotePort | Select-Object -First 6)) {
            $owner = $connection.OwningProcess
            $processName = ""
            if ($owner) {
                try {
                    $ownerProcess = Get-Process -Id $owner -ErrorAction SilentlyContinue
                    if ($ownerProcess) {
                        $processName = "/$($ownerProcess.ProcessName)"
                    }
                }
                catch {
                }
            }
            $remote = "$($connection.RemoteAddress):$($connection.RemotePort)"
            $items += "$($connection.State) owner=$owner$processName remote=$remote"
        }
        if ($connections.Count -gt 6) {
            $items += "... total=$($connections.Count)"
        }
        return "tcp local port ${Port}: $($items -join '; ')"
    }
    catch {
        if (Test-TcpPort -HostName "127.0.0.1" -Port $Port) {
            return "tcp local port $Port accepts connections; Get-NetTCPConnection failed: $($_.Exception.Message)"
        }
        return "tcp local port $Port has no visible state; Get-NetTCPConnection failed: $($_.Exception.Message)"
    }
}

function Write-WaitDiagnostic {
    param(
        [string]$LogFile,
        [string]$Phase,
        [int]$Port,
        [System.Diagnostics.Process]$Process = $null,
        [string]$StatusLogFile = ""
    )

    $parts = @($Phase)
    $processStatus = Get-BackgroundProcessDiagnostic -Process $Process
    if ($processStatus) {
        $parts += $processStatus
    }
    $parts += (Get-TcpPortDiagnostic -Port $Port)

    $logSummary = Get-StartupLogSignalSummary -Path $StatusLogFile
    if ($logSummary) {
        $parts += "log=$logSummary"
    }

    Write-LauncherLog -LogFile $LogFile -Message ($parts -join " | ")
}

function Wait-TcpPort {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutSeconds,
        [string]$LogFile,
        [System.Diagnostics.Process]$Process = $null,
        [string]$AbortLogFile = "",
        [string[]]$AbortPatterns = @(),
        [string]$StatusLogFile = "",
        [int]$DiagnosticIntervalSeconds = 15
    )

    Write-LauncherLog -LogFile $LogFile -Message "Waiting for port ${HostName}:$Port for up to $TimeoutSeconds seconds."
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $nextDiagnosticAt = (Get-Date).AddSeconds($DiagnosticIntervalSeconds)
    do {
        if (Test-TcpPort -HostName $HostName -Port $Port) {
            Write-LauncherLog -LogFile $LogFile -Message "Port ${HostName}:$Port is ready."
            return $true
        }
        if ($Process -and $Process.HasExited) {
            Write-LauncherLog -LogFile $LogFile -Message "Background process pid=$($Process.Id) exited before port ${HostName}:$Port was ready. exit_code=$($Process.ExitCode)"
            return $false
        }
        if ($AbortLogFile -and $AbortPatterns.Count -gt 0 -and (Test-Path $AbortLogFile)) {
            $tail = Get-LogTailText -Path $AbortLogFile -Count 80
            foreach ($pattern in $AbortPatterns) {
                if ($tail -match $pattern) {
                    Write-LauncherLog -LogFile $LogFile -Message "Aborting wait for port ${HostName}:$Port because log matched: $pattern"
                    return $false
                }
            }
        }
        if ((Get-Date) -ge $nextDiagnosticAt) {
            Write-WaitDiagnostic -LogFile $LogFile -Phase "Still waiting for port ${HostName}:$Port." -Port $Port -Process $Process -StatusLogFile $StatusLogFile
            $nextDiagnosticAt = (Get-Date).AddSeconds($DiagnosticIntervalSeconds)
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    Write-WaitDiagnostic -LogFile $LogFile -Phase "Final status before timeout waiting for port ${HostName}:$Port." -Port $Port -Process $Process -StatusLogFile $StatusLogFile
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

function Wait-EstablishedConnection {
    param(
        [int]$Port,
        [int]$TimeoutSeconds,
        [string]$LogFile,
        [System.Diagnostics.Process]$Process = $null,
        [string]$StatusLogFile = "",
        [int]$DiagnosticIntervalSeconds = 15
    )

    Write-LauncherLog -LogFile $LogFile -Message "Waiting for established TCP connection on local port $Port for up to $TimeoutSeconds seconds."
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $nextDiagnosticAt = (Get-Date).AddSeconds($DiagnosticIntervalSeconds)
    do {
        try {
            $connection = Get-NetTCPConnection -LocalPort $Port -State Established -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($connection) {
                Write-LauncherLog -LogFile $LogFile -Message "Established TCP connection confirmed on local port $Port. $(Get-TcpPortDiagnostic -Port $Port)"
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
        if ((Get-Date) -ge $nextDiagnosticAt) {
            Write-WaitDiagnostic -LogFile $LogFile -Phase "Still waiting for established TCP connection on local port $Port." -Port $Port -Process $Process -StatusLogFile $StatusLogFile
            $nextDiagnosticAt = (Get-Date).AddSeconds($DiagnosticIntervalSeconds)
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    Write-WaitDiagnostic -LogFile $LogFile -Phase "Final status before timeout waiting for established TCP connection on local port $Port." -Port $Port -Process $Process -StatusLogFile $StatusLogFile
    Write-LauncherLog -LogFile $LogFile -Message "Timed out waiting for established TCP connection on local port $Port."
    return $false
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
        foreach ($owner in $owners) {
            if ($owner -and $owner -ne $PID) {
                try {
                    Wait-Process -Id $owner -Timeout 20 -ErrorAction SilentlyContinue
                }
                catch {
                }
            }
        }
        if ($owners.Count -gt 0) {
            $deadline = (Get-Date).AddSeconds(20)
            while ((Get-Date) -lt $deadline) {
                if (-not (Test-TcpPort -HostName "127.0.0.1" -Port $Port)) {
                    Write-LauncherLog -LogFile $LogFile -Message "Port $Port is released."
                    return
                }
                Start-Sleep -Seconds 1
            }
            Write-LauncherLog -LogFile $LogFile -Message "Port $Port still accepts TCP after stopping $Name owners; continuing with startup."
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
        [string]$PathSuffix,
        [string]$LogFile
    )

    $configPath = Join-Path $WorkspaceRoot "napcat\onekey\napcat\config\onebot11_$Account.json"
    if (-not (Test-Path $configPath)) {
        if ($LogFile) {
            Write-LauncherLog -LogFile $LogFile -Message "NapCat OneBot config not found for account ${Account}: $configPath"
        }
        return
    }

    $rawConfig = Get-Content -Raw -Path $configPath -Encoding UTF8
    if (-not $rawConfig.Trim()) {
        if ($LogFile) {
            Write-LauncherLog -LogFile $LogFile -Message "NapCat OneBot config is empty for account ${Account}: $configPath"
        }
        return
    }
    $config = $rawConfig | ConvertFrom-Json
    if (-not $config.network) {
        if ($LogFile) {
            Write-LauncherLog -LogFile $LogFile -Message "NapCat OneBot config has no network section for account ${Account}: $configPath"
        }
        return
    }

    $targetUrl = "ws://127.0.0.1:$BotPort$PathSuffix"
    $clients = @($config.network.websocketClients)
    $client = $clients | Where-Object { $_.name -eq $ClientName } | Select-Object -First 1
    if (-not $client) {
        if ($clients.Count -gt 0) {
            $client = $clients[0]
            if ($LogFile) {
                Write-LauncherLog -LogFile $LogFile -Message "NapCat OneBot client '$ClientName' not found for account $Account; using first websocket client '$($client.name)'."
            }
        }
        else {
            if ($LogFile) {
                Write-LauncherLog -LogFile $LogFile -Message "NapCat OneBot config has no websocket clients for account ${Account}: $configPath"
            }
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
        if ($LogFile) {
            Write-LauncherLog -LogFile $LogFile -Message "Updated NapCat OneBot client config: account=$Account client=$($client.name) url=$targetUrl enable=True file=$configPath"
        }
    }
    elseif ($LogFile) {
        Write-LauncherLog -LogFile $LogFile -Message "NapCat OneBot client config already matches target: account=$Account client=$($client.name) url=$targetUrl enable=True file=$configPath"
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
    if ($FeatureMode -eq "full") {
        Stop-ProcessByPort -Port 8080 -Name "AstrBot artifact API" -LogFile $launcherLog
    }
    Complete-ChildStage -RunId $RunId -Component "astrbot" -Stage "ports-cleared"

    $script = Join-Path $ScriptRoot "start-astrbot.ps1"
    $featureModeArg = if ($FeatureMode) { " -FeatureMode '$FeatureMode'" } else { "" }
    $command = "& '$script'$featureModeArg -BotProfile '$AstrBotProfile' -AiocqhttpPort $AstrBotOneBotPort -AngelAiocqhttpPort $AstrBotAngelOneBotPort"
    $process = Start-BackgroundPowerShell -CommandText $command -WorkingDirectory $WorkspaceRoot -StdoutLog $stdoutLog -StderrLog $stderrLog -LauncherLog $launcherLog
    Write-LauncherLog -LogFile $launcherLog -Message "AstrBot stdout log: $stdoutLog"

    if (-not (Wait-TcpPort -HostName "127.0.0.1" -Port 6185 -TimeoutSeconds 360 -LogFile $launcherLog -Process $process -StatusLogFile $stdoutLog)) {
        $tail = Get-SafeConsoleLogTailText -Path $stdoutLog
        if ($tail) {
            Write-Host "Recent AstrBot output:" -ForegroundColor Yellow
            Write-Host $tail
        }
        if ($process.HasExited) {
            throw "AstrBot exited before opening port 6185. exit_code=$($process.ExitCode). Log: $stdoutLog"
        }
        throw "AstrBot did not open port 6185. Log: $stdoutLog"
    }
    $platformAiocqhttpErrorText = Join-TextFromCodePoints @(0x53D1, 0x751F, 0x9519, 0x8BEF)
    $platformAbortPatterns = @("platform_aiocqhttp_.*$([regex]::Escape($platformAiocqhttpErrorText))", "WinError 10013", "PermissionError")
    if (-not (Wait-TcpPort -HostName "127.0.0.1" -Port $AstrBotOneBotPort -TimeoutSeconds 120 -LogFile $launcherLog -Process $process -AbortLogFile $stdoutLog -AbortPatterns $platformAbortPatterns -StatusLogFile $stdoutLog)) {
        $tail = Get-SafeConsoleLogTailText -Path $stdoutLog
        if ($tail) {
            Write-Host "Recent AstrBot output:" -ForegroundColor Yellow
            Write-Host $tail
        }
        throw "AstrBot did not open port $AstrBotOneBotPort. Log: $stdoutLog"
    }
    if ($AstrBotProfile -eq "both" -and -not (Wait-TcpPort -HostName "127.0.0.1" -Port $AstrBotAngelOneBotPort -TimeoutSeconds 120 -LogFile $launcherLog -Process $process -AbortLogFile $stdoutLog -AbortPatterns $platformAbortPatterns -StatusLogFile $stdoutLog)) {
        $tail = Get-SafeConsoleLogTailText -Path $stdoutLog
        if ($tail) {
            Write-Host "Recent AstrBot output:" -ForegroundColor Yellow
            Write-Host $tail
        }
        throw "AstrBot did not open port $AstrBotAngelOneBotPort. Log: $stdoutLog"
    }
    if ($FeatureMode -eq "full") {
        $artifactAbortPatterns = @("LocalArtifactApi.*failed to listen", "WinError 10013", "PermissionError")
        if (-not (Wait-TcpPort -HostName "127.0.0.1" -Port 8080 -TimeoutSeconds 120 -LogFile $launcherLog -Process $process -AbortLogFile $stdoutLog -AbortPatterns $artifactAbortPatterns -StatusLogFile $stdoutLog)) {
            $tail = Get-SafeConsoleLogTailText -Path $stdoutLog
            if ($tail) {
                Write-Host "Recent AstrBot output:" -ForegroundColor Yellow
                Write-Host $tail
            }
            throw "AstrBot full mode did not open local artifact API port 8080. Log: $stdoutLog"
        }
    }
}

function Start-NapCatComponent {
    param(
        [string]$RunId,
        [string]$Account,
        [int]$BotPort,
        [string]$ComponentName = ""
    )

    $componentName = if ($ComponentName) { $ComponentName } else { "napcat-astrbot" }
    $logRoot = Get-ComponentLogRoot -Component $componentName -RunId $RunId
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $launcherLog = Join-Path $logRoot "launcher.log"
    $stdoutLog = Join-Path $logRoot "napcat_stdout.log"
    $stderrLog = Join-Path $logRoot "napcat_stderr.log"
    New-Item -ItemType File -Path $stdoutLog -Force | Out-Null
    New-Item -ItemType File -Path $stderrLog -Force | Out-Null

    Write-LauncherLog -LogFile $launcherLog -Message "Starting NapCat account $Account."

    Sync-NapCatOneBotClientConfig -Account $Account -BotPort $BotPort -ClientName "astrbot-reverse-ws" -PathSuffix "/ws" -LogFile $launcherLog

    Stop-NapCatAccountProcesses -Account $Account -LogFile $launcherLog
    $botStdoutLog = Join-Path (Get-ComponentLogRoot -Component "astrbot" -RunId $RunId) "astrbot_stdout.log"
    if (-not (Wait-TcpPort -HostName "127.0.0.1" -Port $BotPort -TimeoutSeconds 300 -LogFile $launcherLog -StatusLogFile $botStdoutLog)) {
        throw "Target bot port $BotPort is not ready for NapCat account $Account."
    }
    $botSummary = Get-StartupLogSignalSummary -Path $botStdoutLog
    if ($botSummary) {
        Write-LauncherLog -LogFile $launcherLog -Message "Target bot status before starting NapCat account ${Account}: $botSummary"
    }
    $script = Join-Path $ScriptRoot "start-napcat-account.ps1"
    $command = "& '$script' -Account '$Account'"
    $process = Start-BackgroundPowerShell -CommandText $command -WorkingDirectory $WorkspaceRoot -StdoutLog $stdoutLog -StderrLog $stderrLog -LauncherLog $launcherLog
    Write-LauncherLog -LogFile $launcherLog -Message "NapCat stdout log: $stdoutLog"

    if (-not (Wait-EstablishedConnection -Port $BotPort -TimeoutSeconds 120 -LogFile $launcherLog -Process $process -StatusLogFile $stdoutLog)) {
        $statusSummary = Get-StartupLogSignalSummary -Path $stdoutLog
        Set-NapCatQuickLoginReady -Account $Account -Ready $false -Reason "connection-timeout" -LogFile $launcherLog
        if ($statusSummary) {
            Write-Host "NapCat startup status: $statusSummary" -ForegroundColor Yellow
            Write-LauncherLog -LogFile $launcherLog -Message "NapCat startup status before failure: $statusSummary"
        }
        $tail = Get-SafeConsoleLogTailText -Path $stderrLog
        if ($tail) {
            Write-Host "Recent NapCat error output:" -ForegroundColor Yellow
            Write-Host $tail
        }
        if ($statusSummary) {
            throw "NapCat account $Account did not connect to AstrBot. Status: $statusSummary"
        }
        throw "NapCat account $Account did not connect to AstrBot."
    }

    Set-NapCatQuickLoginReady -Account $Account -Ready $true -Reason "established-connection" -LogFile $launcherLog
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

function Complete-ChildStage {
    param(
        [string]$RunId,
        [string]$Component,
        [string]$Stage
    )

    $controlRoot = Get-ControlRoot -RunId $RunId
    New-Item -ItemType Directory -Path $controlRoot -Force | Out-Null
    Set-Content -Path (Join-Path $controlRoot "$Component.$Stage") -Value "done" -Encoding UTF8
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

function Wait-ChildStages {
    param(
        [string]$RunId,
        [string[]]$Components,
        [string]$Stage,
        [int]$TimeoutSeconds
    )

    $controlRoot = Get-ControlRoot -RunId $RunId
    New-Item -ItemType Directory -Path $controlRoot -Force | Out-Null
    $pending = [System.Collections.Generic.HashSet[string]]::new([string[]]$Components)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ($pending.Count -gt 0) {
        foreach ($componentName in @($pending)) {
            $failedPath = Join-Path $controlRoot "$componentName.failed"
            if (Test-Path $failedPath) {
                $message = Get-Content -Raw -Path $failedPath
                throw "$componentName failed: $message"
            }
            $stagePath = Join-Path $controlRoot "$componentName.$Stage"
            if (Test-Path $stagePath) {
                [void]$pending.Remove($componentName)
            }
        }
        if ($pending.Count -eq 0) {
            return
        }
        if ((Get-Date) -ge $deadline) {
            throw "Timed out waiting for stage '$Stage': $($pending -join ', ')"
        }
        Start-Sleep -Seconds 1
    }
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
            "astrbot" { Start-AstrBotComponent -RunId $RunId }
            "napcat-astrbot" { Start-NapCatComponent -RunId $RunId -Account (Get-AstrBotAccount) -BotPort $AstrBotOneBotPort -ComponentName "napcat-astrbot" }
            "napcat-astrbot-demon" { Start-NapCatComponent -RunId $RunId -Account "2629227874" -BotPort $AstrBotOneBotPort -ComponentName "napcat-astrbot-demon" }
            "napcat-astrbot-angel" { Start-NapCatComponent -RunId $RunId -Account "1443944862" -BotPort $AstrBotAngelOneBotPort -ComponentName "napcat-astrbot-angel" }
            default { throw "Unknown component: $Component" }
        }
        Complete-Child -RunId $RunId -Component $Component
        Write-Host "$Component ready. Closing this window."
        exit 0
    }
    catch {
        $message = $_.Exception.Message
        if ($Component -like "napcat-*") {
            try {
                $account = Get-NapCatAccountForComponent -ComponentName $Component
                $logRoot = Get-ComponentLogRoot -Component $Component -RunId $RunId
                $launcherLog = Join-Path $logRoot "launcher.log"
                Set-NapCatQuickLoginReady -Account $account -Ready $false -Reason "child-failed" -LogFile $launcherLog
            }
            catch {
            }
        }
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
        "astrbot" { Start-ChildWindow -RunId $RunId -Component $Component -Title (Get-AstrBotTitle) }
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
    if ($AstrBotProfile -eq "both" -and $FeatureMode -ne "full") {
        throw "AstrBotProfile both requires -FeatureMode full so AstrBot-only event ownership is explicit."
    }
    if ($AstrBotProfile -eq "angel" -and $FeatureMode -ne "full") {
        throw "AstrBotProfile angel requires -FeatureMode full so AstrBot-only event ownership is explicit."
    }

    $runId = New-RunId
    $controlRoot = Get-ControlRoot -RunId $runId
    New-Item -ItemType Directory -Path $controlRoot -Force | Out-Null

    $botComponents = @("astrbot")
    $napcatComponents = @()
    if ($AstrBotProfile -eq "both") {
        $napcatComponents += "napcat-astrbot-demon"
        $napcatComponents += "napcat-astrbot-angel"
    }
    else {
        $napcatComponents += "napcat-astrbot"
    }

    Write-Host "Starting target: $Target"
    Write-Host "Starting bot services: $($botComponents -join ', ')"
    foreach ($componentName in $botComponents) {
        Start-ComponentWindow -RunId $runId -Component $componentName
    }
    $startedNapCatInParallel = $false
    if ($napcatComponents.Count -gt 0) {
        Wait-ChildStages -RunId $runId -Components $botComponents -Stage "ports-cleared" -TimeoutSeconds 90
        Write-Host "Starting NapCat accounts: $($napcatComponents -join ', ')"
        if ($AstrBotProfile -eq "both" -and (Test-AllNapCatQuickLoginReady -Components $napcatComponents)) {
            Write-Host "NapCat quick-login markers are complete; starting accounts in parallel."
            foreach ($componentName in $napcatComponents) {
                Start-ComponentWindow -RunId $runId -Component $componentName
            }
            $startedNapCatInParallel = $true
        }
        elseif ($AstrBotProfile -eq "both") {
            $missingMarkers = Get-NapCatComponentsMissingQuickLogin -Components $napcatComponents
            Write-Host "NapCat quick-login marker missing for $($missingMarkers -join ', '); starting accounts serially to protect shared QR image."
            foreach ($componentName in $napcatComponents) {
                Start-ComponentWindow -RunId $runId -Component $componentName
                Write-Host "Waiting for NapCat account startup before launching the next account: $componentName"
                Wait-Children -RunId $runId -Components @($componentName)
            }
        }
        else {
            foreach ($componentName in $napcatComponents) {
                Start-ComponentWindow -RunId $runId -Component $componentName
            }
            $startedNapCatInParallel = $true
        }
    }
    $remainingComponents = @($botComponents)
    if ($startedNapCatInParallel) {
        $remainingComponents += $napcatComponents
    }
    if ($remainingComponents.Count -gt 0) {
        Wait-Children -RunId $runId -Components $remainingComponents
    }
    Write-Host "All targets are ready."
}

if ($Child) {
    Invoke-Child
    exit $LASTEXITCODE
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
