param(
    [Parameter(Position = 0)]
    [ValidateSet("all", "yunqi", "yelin", "xingyao", "yuecheng", "lanling")]
    [string]$Target = "all",
    [switch]$ForceRestart,
    [switch]$SkipInstall,
    [int]$TimeoutSeconds = 240,
    [switch]$AccountWorker,
    [switch]$NoPauseOnFailure,
    [string]$WindowTitle = ""
)

$ErrorActionPreference = "Stop"
$timer = [System.Diagnostics.Stopwatch]::StartNew()
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkspaceRoot = Split-Path -Parent $ScriptRoot
$AccountsPath = Join-Path $WorkspaceRoot "napcat\accounts.json"
$NapCatEnsureScript = Join-Path $WorkspaceRoot "napcat\scripts\ensure-account.ps1"
$NapCatHideScript = Join-Path $WorkspaceRoot "napcat\scripts\hide-account-windows.ps1"



function Invoke-PowerShellScript {
    param(
        [string]$Path,
        [string[]]$Arguments,
        [string]$Label,
        [switch]$WaitForLogin
    )

    if (-not (Test-Path $Path)) {
        throw "$Label script not found: $Path"
    }
    $invokeArguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", ('"{0}"' -f $Path)
    ) + $Arguments
    $process = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList $invokeArguments `
        -NoNewWindow `
        -PassThru
    # Windows PowerShell 5.1 loses ExitCode for fast children unless their handle is opened before exit.
    [void]$process.Handle
    if ($WaitForLogin) {
        # NapCat owns the startup timeout and suspends it while QQ requires a QR scan.
        $process.WaitForExit()
    }
    elseif (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        throw "$Label startup command timed out after $TimeoutSeconds seconds; PID: $($process.Id). The runtime was not stopped."
    }
    $exitCode = $process.ExitCode
    $process.Dispose()
    if ($exitCode -ne 0) {
        throw "$Label failed with exit code $exitCode."
    }
}

function Invoke-FrameworkStart {
    param([object]$Account)

    if ($null -eq $Account.framework) {
        throw "Target '$($Account.target)' has no framework start contract."
    }
    $startPath = Join-Path $WorkspaceRoot ([string]$Account.framework.startScript)
    $arguments = @()
    if ($ForceRestart) {
        $arguments += "-ForceRestart"
    }
    if ($SkipInstall) {
        $arguments += "-SkipInstall"
    }
    Invoke-PowerShellScript -Path $startPath -Arguments $arguments -Label ([string]$Account.framework.name)
}

function Invoke-NapCatStart {
    param([object]$Account)

    $arguments = @(
        "-Target", [string]$Account.target,
        "-TimeoutSeconds", [string]$TimeoutSeconds
    )
    Invoke-PowerShellScript -Path $NapCatEnsureScript -Arguments $arguments -Label ("NapCat/{0}" -f $Account.target) -WaitForLogin
}

function Invoke-NapCatWindowHide {
    param([object]$Account)

    Invoke-PowerShellScript `
        -Path $NapCatHideScript `
        -Arguments @("-Target", [string]$Account.target) `
        -Label ("NapCat window hide/{0}" -f $Account.target)
}

function Wait-OneBotPeer {
    param(
        [object]$Account,
        [int]$Timeout
    )

    $port = [int]$Account.oneBotPort
    $deadline = [DateTime]::UtcNow.AddSeconds($Timeout)
    $network = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties()
    while ([DateTime]::UtcNow -lt $deadline) {
        $connections = @($network.GetActiveTcpConnections() | Where-Object {
            $_.State -eq [System.Net.NetworkInformation.TcpState]::Established -and
            ($_.LocalEndPoint.Port -eq $port -or $_.RemoteEndPoint.Port -eq $port)
        })
        if ($connections.Count -gt 0) {
            Write-Host "[qqbot] $($Account.label) OneBot peer is connected on port $port."
            return
        }
        Start-Sleep -Milliseconds 250
    }
    throw "$($Account.label) did not establish its OneBot connection on port $port within $Timeout seconds."
}

function Invoke-AccountStart {
    param([object]$Account)

    Write-Host "[qqbot] Starting $($Account.label) ($($Account.qq)) via $($Account.framework.name)."
    if ($Account.connectionMode -eq "reverse-client") {
        Invoke-FrameworkStart -Account $Account
        Invoke-NapCatStart -Account $Account
    }
    elseif ($Account.connectionMode -eq "forward-server") {
        Invoke-NapCatStart -Account $Account
        Invoke-FrameworkStart -Account $Account
    }
    else {
        throw "Unsupported connection mode '$($Account.connectionMode)' for target '$($Account.target)'."
    }

    Wait-OneBotPeer -Account $Account -Timeout $TimeoutSeconds
    Invoke-NapCatWindowHide -Account $Account
    return ("{0}({1}) framework={2} onebot={3}" -f $Account.label, $Account.qq, $Account.framework.name, $Account.oneBotPort)
}

function Start-AccountWorker {
    param([object]$Account)

    $title = "QQBot-$($Account.label)-$($Account.qq)"
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", ('"{0}"' -f $PSCommandPath),
        "-Target", [string]$Account.target,
        "-TimeoutSeconds", [string]$TimeoutSeconds,
        "-AccountWorker",
        "-WindowTitle", $title
    )
    if ($ForceRestart) {
        $arguments += "-ForceRestart"
    }
    if ($SkipInstall) {
        $arguments += "-SkipInstall"
    }
    if ($NoPauseOnFailure) {
        $arguments += "-NoPauseOnFailure"
    }

    $process = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList $arguments `
        -WorkingDirectory $WorkspaceRoot `
        -WindowStyle Normal `
        -PassThru
    # Keep ExitCode available when an already-ready account worker closes immediately.
    [void]$process.Handle
    Write-Host "[qqbot] Opened $($Account.label) startup window. PID: $($process.Id)."
    return [pscustomobject]@{
        Account = $Account
        Process = $process
    }
}

function Wait-AccountWorkers {
    <#
    .SYNOPSIS
    等待每个已打开的账号窗口退出，收集失败后统一交给主窗口处理。
    #>
    param([object[]]$Workers)

    $failures = [System.Collections.Generic.List[string]]::new()
    $pending = [System.Collections.Generic.List[object]]::new()
    foreach ($worker in $Workers) {
        $pending.Add($worker)
    }
    # 扫码由账号窗口等待；主窗口的生命周期覆盖所有已打开的账号窗口。
    while ($pending.Count -gt 0) {
        for ($i = $pending.Count - 1; $i -ge 0; $i--) {
            $worker = $pending[$i]
            if (-not $worker.Process.WaitForExit(0)) {
                continue
            }
            $exitCode = $worker.Process.ExitCode
            Write-Host "[qqbot] $($worker.Account.label) startup window exited with code $exitCode."
            if ($exitCode -ne 0) {
                [void]$failures.Add("$($worker.Account.label)=$exitCode")
            }
            $worker.Process.Dispose()
            $pending.RemoveAt($i)
        }
        if ($pending.Count -gt 0) {
            Start-Sleep -Milliseconds 100
        }
    }
    if ($failures.Count -gt 0) {
        throw "Account startup worker failed: $($failures -join ', ')."
    }
}

$startupLog = ""
$transcriptStarted = $false
try {
    $logRoot = Join-Path $WorkspaceRoot "logs\startup"
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $role = if ($AccountWorker) { $Target } else { "main-$Target" }
    $startupLog = Join-Path $logRoot ("start-{0}-{1}-{2}.log" -f $role, (Get-Date -Format "yyyyMMdd-HHmmss"), $PID)
    Start-Transcript -LiteralPath $startupLog | Out-Null
    $transcriptStarted = $true
    Write-Host "[qqbot] 启动日志：$startupLog"

    if (-not (Test-Path $AccountsPath)) {
        throw "Account manifest not found: $AccountsPath"
    }
    if (-not (Test-Path $NapCatEnsureScript)) {
        throw "NapCat account launcher not found: $NapCatEnsureScript"
    }
    if (-not (Test-Path $NapCatHideScript)) {
        throw "NapCat window controller not found: $NapCatHideScript"
    }
    $manifest = Get-Content -Path $AccountsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Target -eq "all") {
        $accounts = @($manifest.accounts | Where-Object { $_.autoStart -eq $true })
    }
    else {
        $accounts = @($manifest.accounts | Where-Object { $_.target -eq $Target })
    }
    if ($accounts.Count -eq 0) {
        throw "No account is configured for target '$Target'."
    }

    if ($AccountWorker) {
        if ($Target -eq "all" -or $accounts.Count -ne 1) {
            throw "Account worker mode requires exactly one account target."
        }
        if ($WindowTitle) {
            try {
                $Host.UI.RawUI.WindowTitle = $WindowTitle
            }
            catch {
            }
        }

        $summary = Invoke-AccountStart -Account $accounts[0]
        Write-Host "[qqbot] READY $summary"
        Write-Host ("[qqbot] $Target ready in {0:F2}s. Closing this window." -f $timer.Elapsed.TotalSeconds)
    }
    else {
        Write-Host "[qqbot] Starting target '$Target'."
        Write-Host "[qqbot] 正在打开账号窗口；主窗口会等待所有账号窗口结束。"
        $workers = [System.Collections.Generic.List[object]]::new()
        $launchFailures = [System.Collections.Generic.List[string]]::new()
        foreach ($account in $accounts) {
            try {
                $worker = Start-AccountWorker -Account $account
                $workers.Add($worker)
            }
            catch {
                [void]$launchFailures.Add("$($account.label): $($_.Exception.Message)")
                Write-Host "[qqbot] 无法打开 $($account.label) 的启动窗口：$($_.Exception.Message)" -ForegroundColor Red
            }
        }
        # 部分窗口打开失败时，也要先等待已经打开的窗口结束，再汇总错误。
        Wait-AccountWorkers -Workers $workers.ToArray()
        if ($launchFailures.Count -gt 0) {
            throw "Account startup window failed to open: $($launchFailures -join '; ')."
        }

        Write-Host ("[qqbot] Target '$Target' is ready in {0:F2}s." -f $timer.Elapsed.TotalSeconds)
        foreach ($account in $accounts) {
            $summary = "{0}({1}) framework={2} onebot={3}" -f $account.label, $account.qq, $account.framework.name, $account.oneBotPort
            Write-Host "[qqbot] READY $summary"
        }
    }
    exit 0
}
catch {
    Write-Host "[qqbot] Startup failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host $_.InvocationInfo.PositionMessage
    Write-Host "[qqbot] 启动日志：$startupLog"
    if (-not $NoPauseOnFailure) {
        [void](Read-Host "按 Enter 关闭此窗口")
    }
    exit 1
}
finally {
    if ($transcriptStarted) {
        Stop-Transcript | Out-Null
    }
}
