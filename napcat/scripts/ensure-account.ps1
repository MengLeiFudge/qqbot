param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("yunqi", "yelin", "xingyao", "yuecheng", "lanling")]
    [string]$Target,
    [switch]$ForceRestart,
    [switch]$UseChildWindow,
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
$timer = [System.Diagnostics.Stopwatch]::StartNew()
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$AccountsPath = Join-Path $ProjectRoot "accounts.json"
$DataRoot = Join-Path $ProjectRoot "data"
$LogRoot = Join-Path $DataRoot ("logs\accounts\{0}" -f $Target)
$MarkerRoot = Join-Path $DataRoot "quick-login"
$ConfigureScript = Join-Path $ScriptRoot "configure-account.ps1"
$BuiltinScript = Join-Path $ScriptRoot "ensure-builtin-plugin.ps1"
$StartScript = Join-Path $ScriptRoot "start-account.ps1"

$manifest = Get-Content -Path $AccountsPath -Raw -Encoding UTF8 | ConvertFrom-Json
$items = @($manifest.accounts | Where-Object { $_.target -eq $Target })
if ($items.Count -ne 1) {
    throw "NapCat target '$Target' is missing or duplicated in $AccountsPath."
}
$item = $items[0]
$account = [string]$item.qq
$port = [int]$item.oneBotPort
$markerPath = Join-Path $MarkerRoot ("{0}.ready" -f $account)

New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
New-Item -ItemType Directory -Path $MarkerRoot -Force | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logName = if ($UseChildWindow) { "napcat-{0}.window.out.log" } else { "napcat-{0}.out.log" }
$stdoutLog = Join-Path $LogRoot ($logName -f $timestamp)
$stderrLog = Join-Path $LogRoot ("napcat-{0}.err.log" -f $timestamp)

function Test-TcpPort {
    param([int]$Port)

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync("127.0.0.1", $Port)
        if (-not $task.Wait(500)) {
            return $false
        }
        return $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
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

function Get-AccountProcessIds {
    param([switch]$RootsOnly)

    $processes = @(Get-CimInstance Win32_Process -OperationTimeoutSec 5)
    $accountPattern = "-Account\s+['`"]?$([regex]::Escape($account))['`"]?"
    $roots = @($processes | Where-Object {
        $_.CommandLine -and
        $_.CommandLine -match 'start-(napcat-)?account\.ps1' -and
        $_.CommandLine -match $accountPattern
    })
    if ($RootsOnly) {
        return @($roots | ForEach-Object { [int]$_.ProcessId })
    }
    $ids = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($root in $roots) {
        foreach ($processId in (Get-ProcessTreeIds -RootProcessId ([int]$root.ProcessId) -Processes $processes)) {
            [void]$ids.Add([int]$processId)
        }
    }
    return @($ids)
}

function Test-AccountConnectionReady {
    $processIds = @(Get-AccountProcessIds)
    if ($processIds.Count -eq 0) {
        return $false
    }
    $owned = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($processId in $processIds) {
        [void]$owned.Add([int]$processId)
    }

    if ($item.connectionMode -eq "forward-server") {
        foreach ($listener in @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)) {
            if ($owned.Contains([int]$listener.OwningProcess)) {
                return $true
            }
        }
        return $false
    }

    foreach ($connection in @(Get-NetTCPConnection -State Established -RemotePort $port -ErrorAction SilentlyContinue)) {
        if (
            $owned.Contains([int]$connection.OwningProcess) -and
            ($connection.LocalPort -eq $port -or $connection.RemotePort -eq $port)
        ) {
            return $true
        }
    }
    return $false
}

function Stop-AccountProcesses {
    $processIds = @(Get-AccountProcessIds | Sort-Object -Descending -Unique)
    foreach ($processId in $processIds) {
        if ($processId -ne $PID) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }
    foreach ($processId in $processIds) {
        if ($processId -ne $PID) {
            try {
                Wait-Process -Id $processId -Timeout 20 -ErrorAction SilentlyContinue
            }
            catch {
            }
        }
    }
}

function Get-AccountLogPath {
    <#
    .SYNOPSIS
    查找当前账号启动后生成的日志，排除上一次运行留下的登录提示。
    .PARAMETER Processes
    当前账号启动器进程，用其启动时间筛选日志。
    .OUTPUTS
    最新匹配日志的完整路径；没有匹配日志时返回空字符串。
    #>
    param([System.Diagnostics.Process[]]$Processes)

    if ($Processes.Count -eq 0) {
        return ""
    }
    $started = ($Processes | Sort-Object StartTime | Select-Object -First 1).StartTime
    $log = Get-ChildItem -LiteralPath $LogRoot -Filter "napcat-*.out.log" -File | Where-Object {
        $_.CreationTime -ge $started.AddSeconds(-2) -and $_.LastWriteTime -ge $started
    } | Sort-Object CreationTime -Descending | Select-Object -First 1
    if ($log) {
        return $log.FullName
    }
    return ""
}

function Get-NapCatLoginStatus {
    <#
    .SYNOPSIS
    只提取登录状态和二维码，避免转发日志中的私人消息。
    .PARAMETER LogPath
    当前账号的标准输出日志；可见子窗口使用 UTF-16 日志。
    .OUTPUTS
    登录状态、二维码图片路径、刷新标记、生成时间和二维码方块字符。
    #>
    param([string]$LogPath)

    $login = [pscustomobject]@{ State = "Unknown"; QrPath = ""; QrStamp = ""; QrCode = ""; QrIssuedAt = [DateTime]::MinValue }
    if (-not $LogPath -or -not (Test-Path -LiteralPath $LogPath -PathType Leaf)) {
        return $login
    }
    $encoding = if ($LogPath.EndsWith(".window.out.log")) { "Unicode" } else { "UTF8" }
    $lines = @(Get-Content -LiteralPath $LogPath -Encoding $encoding -Tail 160 -ErrorAction SilentlyContinue)
    $qrLines = [System.Collections.Generic.List[string]]::new()
    foreach ($line in $lines) {
        $line = $line -replace '\x1b\[[0-?]*[ -/]*[@-~]', ''
        # The official launcher pauses after QQ exits, so its live process alone is not a usable login.
        if ($line -match '^Process exited\.\s*$') {
            $login.State = "ProcessExited"
            $qrLines.Clear()
        }
        elseif ($line -match '^\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[info\].*\u8d26\u53f7\u72b6\u6001\u53d8\u66f4\u4e3a\u79bb\u7ebf\s*$') {
            $login.State = "Offline"
            $qrLines.Clear()
        }
        elseif ($line -match '^\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[info\].*\u8d26\u53f7\u72b6\u6001\u53d8\u66f4\u4e3a\u5728\u7ebf\s*$') {
            $login.State = "LoggedIn"
            $qrLines.Clear()
        }
        elseif (
            $line -match '^\[NapCat\] \[WebUi\] \u81ea\u52a8.*\u767b\u5f55\u6210\u529f:' -or
            $line -match '^\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[(debug|info)\] (\u672c\u8d26\u53f7\u6570\u636e/\u7f13\u5b58\u76ee\u5f55|\[Core\] \[Config\]|\[AdapterManager\])'
        ) {
            # QR login has no success message; these initialization stages run only after login.
            $login.State = "LoggedIn"
            $qrLines.Clear()
        }
        elseif ($line -match '^\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[warn\] \u8bf7\u626b\u63cf') {
            $login.State = "WaitingForQr"
            $login.QrStamp = $line
            $qrLines.Clear()
        }
        elseif ($line -match '^\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[warn\] \u4e8c\u7ef4\u7801\u5df2\u4fdd\u5b58\u5230\s+(?<path>.+?\.png)\s*$') {
            $login.State = "WaitingForQr"
            $login.QrPath = $Matches.path.Trim()
            $login.QrStamp = $line
        }
        elseif ($line -match '^\[NapCat\] \[WebUi\] .*\u767b\u5f55\u5931\u8d25:') {
            $login.State = "QuickLoginFailed"
        }
        elseif ($line -match '^\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[error\] \[Core\] \[Login\] Login Error') {
            # 过期后 NapCat 会自行取新码；其他错误不会触发这条刷新路径。
            $login.State = if ($line -match 'ErrType:\s*1\s+ErrCode:\s*3\s*$') { "RefreshingQr" } else { "LoginFailed" }
            $qrLines.Clear()
        }
        elseif ($login.State -eq "WaitingForQr" -and $line -match '^[\u2580-\u259f ]+$' -and $line.Trim()) {
            [void]$qrLines.Add($line.TrimEnd())
        }
    }
    $login.QrCode = $qrLines -join [Environment]::NewLine
    if ($login.QrStamp -match '^(?<time>\d{2}-\d{2} \d{2}:\d{2}:\d{2})') {
        $issuedAt = [DateTime]::MinValue
        if ([DateTime]::TryParseExact($Matches.time, "MM-dd HH:mm:ss", [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::None, [ref]$issuedAt)) {
            # 日志没有年份；跨年复用旧进程时，十二月的记录属于上一年。
            if ($issuedAt -gt (Get-Date).AddDays(1)) {
                $issuedAt = $issuedAt.AddYears(-1)
            }
            $login.QrIssuedAt = $issuedAt
        }
    }
    return $login
}

function Wait-AccountReady {
    <#
    .SYNOPSIS
    等待账号所属的 OneBot 连接就绪，扫码等待不计入启动超时。
    .PARAMETER Processes
    当前账号启动器进程；进程全部退出时停止等待并报错。
    .PARAMETER LogPath
    当前标准输出日志；省略时查找复用启动器对应的日志。
    .OUTPUTS
    就绪返回 true；离线、退出、登录失败或二维码停止刷新时返回 false，由调用方恢复旧实例一次。
    #>
    param(
        [System.Diagnostics.Process[]]$Processes,
        [string]$LogPath = ""
    )

    if ($Processes.Count -eq 0) {
        throw "NapCat account $account exited before startup could be observed. Logs: $LogRoot"
    }
    foreach ($run in $Processes) {
        [void]$run.Handle
    }
    if (-not $LogPath) {
        $LogPath = Get-AccountLogPath -Processes $Processes
    }

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $waitingForQr = $false
    $qrStamp = ""
    $lastState = "Unknown"
    while ($true) {
        if (@($Processes | Where-Object { -not $_.HasExited }).Count -eq 0) {
            throw "NapCat account $account exited before OneBot port $port became ready. Logs: $LogRoot"
        }
        $login = Get-NapCatLoginStatus -LogPath $LogPath
        # A live OneBot socket survives QQ logout; inspect account state before accepting the port.
        if ($login.State -eq "ProcessExited") {
            Write-Host "[NapCat] $($item.label) ($account) QQ process has exited; the remaining launcher cannot provide OneBot port $port."
            return $false
        }
        if ($login.State -eq "Offline") {
            Write-Host "[NapCat] $($item.label) ($account) is logged out; its OneBot port does not indicate a valid QQ login."
            return $false
        }
        if ($login.State -eq "LoginFailed") {
            Write-Host "[NapCat] $($item.label) QQ 登录失败，当前二维码已不可用。日志：$LogPath"
            return $false
        }
        # 正常过期约两分钟就会生成下一张码；额外留一分钟，识别停止刷新的登录。
        if ($login.State -in @("WaitingForQr", "RefreshingQr") -and $login.QrIssuedAt -ne [DateTime]::MinValue -and (Get-Date) -ge $login.QrIssuedAt.AddMinutes(3)) {
            Write-Host "[NapCat] $($item.label) 的二维码已超过三分钟没有刷新，需要重新建立登录。日志：$LogPath"
            return $false
        }
        if ($login.State -in @("Unknown", "LoggedIn") -and (Test-AccountConnectionReady)) {
            return $true
        }
        if ($login.State -eq "WaitingForQr") {
            if (-not $waitingForQr) {
                $waitingForQr = $true
                if (Test-Path -LiteralPath $markerPath) {
                    Remove-Item -LiteralPath $markerPath -Force
                }
                Write-Host "[NapCat] $($item.label) ($account) requires QQ login. Scan with this account's mobile QQ and approve login. Waiting without a time limit."
            }
            if ($login.QrStamp -ne $qrStamp) {
                $qrStamp = $login.QrStamp
                if ($login.QrCode) {
                    Write-Host $login.QrCode
                }
                if ($login.QrPath) {
                    Write-Host "[NapCat] 请扫描本窗口最新显示的二维码。图片路径由多个账号共用，已打开的旧图片可能过期：$($login.QrPath)"
                }
            }
        }
        elseif ($login.State -eq "RefreshingQr" -and $lastState -ne $login.State) {
            Write-Host "[NapCat] $($item.label) 的二维码已过期，正在等待新码；请以接下来显示的二维码为准。"
        }
        elseif ($login.State -eq "LoggedIn" -and $waitingForQr) {
            $waitingForQr = $false
            $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
            Write-Host "[NapCat] $($item.label) logged in; waiting for OneBot port $port."
        }
        elseif ($login.State -eq "QuickLoginFailed" -and $lastState -ne $login.State) {
            Write-Host "[NapCat] $($item.label) quick login failed; waiting for NapCat to issue a QR code."
        }
        $lastState = $login.State
        if (-not $waitingForQr -and [DateTime]::UtcNow -ge $deadline) {
            throw "NapCat account $account did not become ready within $TimeoutSeconds seconds, excluding QR login. Last login state: $lastState. The runtime was not stopped. Logs: $LogRoot"
        }
        Start-Sleep -Seconds 1
    }
}

if (-not $ForceRestart) {
    $readyProcessIds = @(Get-AccountProcessIds -RootsOnly | Sort-Object -Unique)
    if ($readyProcessIds.Count -gt 0) {
        $runs = @(Get-Process -Id $readyProcessIds -ErrorAction SilentlyContinue)
        $login = Get-NapCatLoginStatus -LogPath (Get-AccountLogPath -Processes $runs)
        # 只让已经就绪的账号在锁外复用；重新扫码也必须进入登录队列。
        if ($login.State -in @("Unknown", "LoggedIn") -and (Test-AccountConnectionReady)) {
            Set-Content -Path $markerPath -Value (Get-Date).ToString("o") -Encoding ASCII
            Write-Host ("[NapCat] {0} ready in {1:F2}s; existing PIDs: {2}. Logs: {3}" -f `
                $item.label, $timer.Elapsed.TotalSeconds, ($readyProcessIds -join ','), $LogRoot)
            exit 0
        }
        Write-Host "[NapCat] $($item.label) 的现有连接尚未就绪，将进入登录队列检查当前登录。"
    }
}

# 新启动和已有进程的扫码等待共用登录锁，已在线账号仍可并行复用。
$loginMutex = [System.Threading.Mutex]::new($false, "Local\QQBot-NapCat-Login")
$ownsLoginMutex = $false
try {
    Write-Host "[NapCat] $($item.label) is waiting for the shared login slot. Finish any other account's QR login first."
    while (-not $ownsLoginMutex) {
        try {
            $ownsLoginMutex = $loginMutex.WaitOne(1000)
        }
        catch [System.Threading.AbandonedMutexException] {
            $ownsLoginMutex = $true
        }
    }
    # Another startup request may have restored this account while this request waited.
    if (-not $ForceRestart) {
        $readyProcessIds = @(Get-AccountProcessIds -RootsOnly | Sort-Object -Unique)
        if ($readyProcessIds.Count -gt 0) {
            $runs = @(Get-Process -Id $readyProcessIds -ErrorAction SilentlyContinue)
            if (Wait-AccountReady -Processes $runs) {
                Set-Content -Path $markerPath -Value (Get-Date).ToString("o") -Encoding ASCII
                Write-Host "[NapCat] $($item.label) is ready; reused the login completed by another startup request."
                exit 0
            }
        }
    }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ConfigureScript -Target $Target
    if ($LASTEXITCODE -ne 0) {
        throw "NapCat config policy failed for target '$Target'."
    }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $BuiltinScript
    if ($LASTEXITCODE -ne 0) {
        throw "NapCat builtin plugin check failed."
    }

    if ($item.connectionMode -eq "forward-server" -and (Test-TcpPort -Port $port)) {
        $knownIds = @(Get-AccountProcessIds)
        if ($knownIds.Count -eq 0) {
            throw "OneBot port $port is already owned by an unrelated process. Use a deliberate process cleanup before retrying."
        }
    }

    Stop-AccountProcesses
    if (Test-Path $markerPath) {
        Remove-Item -Path $markerPath -Force
    }

    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $StartScript,
        "-Account", $account
    )
    $start = @{
        FilePath = "powershell.exe"
        ArgumentList = $arguments
        PassThru = $true
    }
    if ($UseChildWindow) {
        $start.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
        # Tee preserves the interactive console and supplies account-owned login diagnostics to the parent.
        $command = '"& ''{0}'' -Account ''{1}'' | Tee-Object -FilePath ''{2}''; exit $LASTEXITCODE"' -f `
            $StartScript.Replace("'", "''"), $account, $stdoutLog.Replace("'", "''")
        $start.ArgumentList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command)
    }
    else {
        $start.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
        $start.RedirectStandardOutput = $stdoutLog
        $start.RedirectStandardError = $stderrLog
    }
    $process = Start-Process @start
    Write-Host "[NapCat] Starting $($item.label) account $account. pid=$($process.Id)"

    if (-not (Wait-AccountReady -Processes @($process) -LogPath $stdoutLog)) {
        throw "NapCat account $account stopped or logged out during startup. The runtime was not restarted again. Check its login window and logs: $LogRoot"
    }
    Set-Content -Path $markerPath -Value (Get-Date).ToString("o") -Encoding ASCII
    $logSummary = if ($UseChildWindow) { "child window ; $stdoutLog" } else { "$stdoutLog ; $stderrLog" }
    Write-Host "[NapCat] $($item.label) is ready on OneBot port $port. PID: $($process.Id). Logs: $logSummary"
    exit 0
}
finally {
    if ($ownsLoginMutex) {
        $loginMutex.ReleaseMutex()
    }
    $loginMutex.Dispose()
}
