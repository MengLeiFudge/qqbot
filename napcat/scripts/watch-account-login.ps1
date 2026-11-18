param(
    [Parameter(Mandatory = $true)]
    [string]$Account,
    [Parameter(Mandatory = $true)]
    [string]$LogPath,
    [int]$WindowMinutes = 10,
    [int]$MaxQrRefreshes = 3
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$PauseRoot = Join-Path $ProjectRoot "data\login-pause"
$pausePath = Join-Path $PauseRoot ("{0}.txt" -f $Account)

function Get-AccountProcessIds {
    $patterns = @(
        "-Account\s+['"" ]?{0}(?:['"" ]|$)" -f [regex]::Escape($Account),
        "-q\s+{0}(?:\s|$)" -f [regex]::Escape($Account)
    )
    $ids = [System.Collections.Generic.List[int]]::new()
    foreach ($process in @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='QQ.exe' OR Name='NapCatWinBootMain.exe'" -ErrorAction SilentlyContinue)) {
        $commandLine = [string]$process.CommandLine
        if (-not $commandLine -or [int]$process.ProcessId -eq $PID) {
            continue
        }
        if ($commandLine -match 'watch-account-login\.ps1') {
            continue
        }
        foreach ($pattern in $patterns) {
            if ($commandLine -match $pattern) {
                [void]$ids.Add([int]$process.ProcessId)
                break
            }
        }
    }
    return @($ids | Sort-Object -Unique)
}

function Stop-AccountLogin {
    param([string]$Reason)

    New-Item -ItemType Directory -Path $PauseRoot -Force | Out-Null
    Set-Content -Path $pausePath -Value (Get-Date).ToString("o") -Encoding ASCII
    foreach ($processId in @(Get-AccountProcessIds | Sort-Object -Descending -Unique)) {
        if ($processId -ne $PID) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }
    Add-Content -Path (Join-Path $PauseRoot ("{0}.log" -f $Account)) -Value ("{0:o} {1}" -f (Get-Date), $Reason) -Encoding UTF8
}

# 后台只看二维码请求频率：正常在线时不会有二维码，连续换码说明登录卡住，必须停进程。
while ($true) {
    Start-Sleep -Seconds 30
    if (@(Get-AccountProcessIds).Count -eq 0) {
        exit 0
    }
    if (-not (Test-Path -LiteralPath $LogPath -PathType Leaf)) {
        continue
    }
    $encoding = if ($LogPath.EndsWith(".window.out.log")) { "Unicode" } else { "UTF8" }
    $lines = @(Get-Content -LiteralPath $LogPath -Encoding $encoding -Tail 400 -ErrorAction SilentlyContinue)
    $now = Get-Date
    $recent = 0
    foreach ($line in $lines) {
        $clean = $line -replace '\x1b\[[0-?]*[ -/]*[@-~]', ''
        if ($clean -notmatch '^\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[warn\] \u4e8c\u7ef4\u7801\u5df2\u4fdd\u5b58\u5230') {
            continue
        }
        $issuedAt = [DateTime]::MinValue
        if ([DateTime]::TryParseExact($clean.Substring(0, 14), "MM-dd HH:mm:ss", [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::None, [ref]$issuedAt)) {
            if ($issuedAt -gt $now.AddDays(1)) {
                $issuedAt = $issuedAt.AddYears(-1)
            }
            if (($now - $issuedAt).TotalMinutes -le $WindowMinutes) {
                $recent++
            }
        }
    }
    if ($recent -ge $MaxQrRefreshes) {
        Stop-AccountLogin -Reason ("{0} 分钟内出现 {1} 次二维码请求，已停止该账号以避免 QQ 判定异常登录。" -f $WindowMinutes, $recent)
        exit 0
    }
}
