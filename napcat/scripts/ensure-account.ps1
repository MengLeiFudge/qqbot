param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("yunqi", "yelin", "xingyao", "yuecheng")]
    [string]$Target,
    [switch]$ForceRestart,
    [switch]$UseChildWindow,
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
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
$stdoutLog = Join-Path $LogRoot ("napcat-{0}.out.log" -f $timestamp)
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
    $processes = @(Get-CimInstance Win32_Process)
    $accountPattern = "-Account\s+['`"]?$([regex]::Escape($account))['`"]?"
    $roots = @($processes | Where-Object {
        $_.CommandLine -and
        $_.CommandLine -match 'start-(napcat-)?account\.ps1' -and
        $_.CommandLine -match $accountPattern
    })
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

    foreach ($connection in @(Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue)) {
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

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ConfigureScript -Target $Target
if ($LASTEXITCODE -ne 0) {
    throw "NapCat config policy failed for target '$Target'."
}
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $BuiltinScript
if ($LASTEXITCODE -ne 0) {
    throw "NapCat builtin plugin check failed."
}

if (-not $ForceRestart -and (Test-AccountConnectionReady)) {
    Set-Content -Path $markerPath -Value (Get-Date).ToString("o") -Encoding ASCII
    $readyProcessIds = @(Get-AccountProcessIds | Sort-Object -Unique)
    Write-Host "[NapCat] $($item.label) is already ready on OneBot port $port. PIDs: $($readyProcessIds -join ','). Logs: $LogRoot"
    exit 0
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
}
else {
    $start.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $start.RedirectStandardOutput = $stdoutLog
    $start.RedirectStandardError = $stderrLog
}
$process = Start-Process @start
Write-Host "[NapCat] Starting $($item.label) account $account. pid=$($process.Id)"

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    if (Test-AccountConnectionReady) {
        Set-Content -Path $markerPath -Value (Get-Date).ToString("o") -Encoding ASCII
        $logSummary = if ($UseChildWindow) { "child window" } else { "$stdoutLog ; $stderrLog" }
        Write-Host "[NapCat] $($item.label) is ready on OneBot port $port. PID: $($process.Id). Logs: $logSummary"
        exit 0
    }
    if ($process.HasExited) {
        break
    }
    Start-Sleep -Seconds 1
}

if (Test-Path $markerPath) {
    Remove-Item -Path $markerPath -Force
}
throw "NapCat account $account did not become ready within $TimeoutSeconds seconds. Logs: $stdoutLog ; $stderrLog"
