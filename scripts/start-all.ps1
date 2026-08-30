param(
    [Parameter(Position = 0)]
    [ValidateSet("all", "yunqi", "yelin")]
    [string]$Target = "all",
    [switch]$ForceRestart,
    [switch]$SkipInstall,
    [int]$TimeoutSeconds = 240
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkspaceRoot = Split-Path -Parent $ScriptRoot
$AccountsPath = Join-Path $WorkspaceRoot "napcat\accounts.json"
$NapCatEnsureScript = Join-Path $WorkspaceRoot "napcat\scripts\ensure-account.ps1"

if (-not (Test-Path $AccountsPath)) {
    throw "Account manifest not found: $AccountsPath"
}
if (-not (Test-Path $NapCatEnsureScript)) {
    throw "NapCat account launcher not found: $NapCatEnsureScript"
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
    $invokeArguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $Path) + $Arguments
    & powershell.exe @invokeArguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
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

$readyAccounts = @()
Write-Host "[qqbot] Starting target '$Target'."
foreach ($account in $accounts) {
    Write-Host "[qqbot] Starting $($account.label) ($($account.qq)) via $($account.framework.name)."
    if ($account.connectionMode -eq "reverse-client") {
        Invoke-FrameworkStart -Account $account
        Invoke-NapCatStart -Account $account
    }
    elseif ($account.connectionMode -eq "forward-server") {
        Invoke-NapCatStart -Account $account
        Invoke-FrameworkStart -Account $account
        Wait-OneBotPeer -Account $account -Timeout $TimeoutSeconds
    }
    else {
        throw "Unsupported connection mode '$($account.connectionMode)' for target '$($account.target)'."
    }
    $readyAccounts += ("{0}({1}) framework={2} onebot={3}" -f $account.label, $account.qq, $account.framework.name, $account.oneBotPort)
}
Write-Host "[qqbot] Target '$Target' is ready."
foreach ($summary in $readyAccounts) {
    Write-Host "[qqbot] READY $summary"
}
