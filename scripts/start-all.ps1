param(
    [Parameter(Position = 0)]
    [ValidateSet("all", "yunqi", "yelin")]
    [string]$Target = "all",
    [switch]$ForceRestart,
    [switch]$SkipInstall,
    [int]$TimeoutSeconds = 240,
    [switch]$AccountWorker,
    [switch]$NoPauseOnFailure,
    [string]$WindowTitle = ""
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkspaceRoot = Split-Path -Parent $ScriptRoot
$AccountsPath = Join-Path $WorkspaceRoot "napcat\accounts.json"
$NapCatEnsureScript = Join-Path $WorkspaceRoot "napcat\scripts\ensure-account.ps1"
$NapCatHideScript = Join-Path $WorkspaceRoot "napcat\scripts\hide-account-windows.ps1"
$QuickLoginRoot = Join-Path $WorkspaceRoot "napcat\data\quick-login"

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

function Invoke-PowerShellScript {
    param(
        [string]$Path,
        [string[]]$Arguments,
        [string]$Label
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
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        throw "$Label failed with exit code $($process.ExitCode)."
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
    if ($ForceRestart) {
        $arguments += "-ForceRestart"
    }
    Invoke-PowerShellScript -Path $NapCatEnsureScript -Arguments $arguments -Label ("NapCat/{0}" -f $Account.target)
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
    $deadline = (Get-Date).AddSeconds($Timeout)
    while ((Get-Date) -lt $deadline) {
        $connections = @(Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue | Where-Object {
            $_.LocalPort -eq $port -or $_.RemotePort -eq $port
        })
        if ($connections.Count -gt 0) {
            Write-Host "[qqbot] $($Account.label) OneBot peer is connected on port $port."
            return
        }
        Start-Sleep -Seconds 1
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
    param([object[]]$Workers)

    $failures = [System.Collections.Generic.List[string]]::new()
    foreach ($worker in $Workers) {
        $worker.Process.WaitForExit()
        if ($worker.Process.ExitCode -ne 0) {
            [void]$failures.Add("$($worker.Account.label)=$($worker.Process.ExitCode)")
        }
    }
    if ($failures.Count -gt 0) {
        throw "Account startup worker failed: $($failures -join ', ')."
    }
}

function Test-ParallelAccountStart {
    param([object[]]$SelectedAccounts)

    if ($SelectedAccounts.Count -lt 2) {
        return $false
    }
    foreach ($account in $SelectedAccounts) {
        $markerPath = Join-Path $QuickLoginRoot ("{0}.ready" -f $account.qq)
        if (-not (Test-Path $markerPath -PathType Leaf)) {
            return $false
        }
    }
    return $true
}

if ($AccountWorker) {
    try {
        if ($Target -eq "all" -or $accounts.Count -ne 1) {
            throw "Account worker mode requires exactly one yunqi or yelin target."
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
        Write-Host "[qqbot] Startup is complete. Closing this window."
        exit 0
    }
    catch {
        Write-Host "[qqbot] Startup failed: $($_.Exception.Message)" -ForegroundColor Red
        if (-not $NoPauseOnFailure) {
            [void](Read-Host "Press Enter to close this window")
        }
        exit 1
    }
}

Write-Host "[qqbot] Starting target '$Target'."
if (Test-ParallelAccountStart -SelectedAccounts $accounts) {
    Write-Host "[qqbot] Quick-login markers are present; opening account windows in parallel."
    $workers = @($accounts | ForEach-Object { Start-AccountWorker -Account $_ })
    Wait-AccountWorkers -Workers $workers
}
else {
    if ($accounts.Count -gt 1) {
        Write-Host "[qqbot] A quick-login marker is missing; opening account windows serially to protect the shared QR image."
    }
    foreach ($account in $accounts) {
        $worker = Start-AccountWorker -Account $account
        Wait-AccountWorkers -Workers @($worker)
    }
}

Write-Host "[qqbot] Target '$Target' is ready."
foreach ($account in $accounts) {
    $summary = "{0}({1}) framework={2} onebot={3}" -f $account.label, $account.qq, $account.framework.name, $account.oneBotPort
    Write-Host "[qqbot] READY $summary"
}
