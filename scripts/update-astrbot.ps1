param(
    [string]$PythonVersion = "3.14",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
try {
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
}
catch {
    # Output may be redirected; environment variables below still keep Python logs UTF-8.
}

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkspaceRoot = Split-Path -Parent $ScriptRoot
$AstrRoot = Join-Path $WorkspaceRoot "data\astrbot"
$LogRoot = Join-Path $AstrRoot "logs\updates"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logFile = Join-Path $LogRoot "update-astrbot-$timestamp.log"

New-Item -ItemType Directory -Path $AstrRoot -Force | Out-Null
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null

$env:ASTRBOT_ROOT = $AstrRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

function Write-Step {
    param([string]$Message)

    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

function Invoke-LoggedCommand {
    param([string[]]$Command)

    Write-Step ("> " + ($Command -join " "))
    $exe = $Command[0]
    $arguments = @()
    if ($Command.Count -gt 1) {
        $arguments = $Command[1..($Command.Count - 1)]
    }

    $stdoutFile = Join-Path $env:TEMP ("qqbot-update-stdout-{0}.log" -f ([guid]::NewGuid().ToString("N")))
    $stderrFile = Join-Path $env:TEMP ("qqbot-update-stderr-{0}.log" -f ([guid]::NewGuid().ToString("N")))
    $process = Start-Process `
        -FilePath $exe `
        -ArgumentList $arguments `
        -NoNewWindow `
        -Wait `
        -PassThru `
        -RedirectStandardOutput $stdoutFile `
        -RedirectStandardError $stderrFile

    foreach ($path in @($stdoutFile, $stderrFile)) {
        if (Test-Path $path) {
            Get-Content -Path $path -Encoding UTF8 | ForEach-Object {
                Write-Host $_
                Add-Content -Path $logFile -Value $_ -Encoding UTF8
            }
            Remove-Item -Path $path -Force -ErrorAction SilentlyContinue
        }
    }

    if ($process.ExitCode -ne 0) {
        throw "Command failed with exit code $($process.ExitCode): $($Command -join ' ')"
    }
}

function Invoke-CapturedCommand {
    param([string[]]$Command)

    $exe = $Command[0]
    $arguments = @()
    if ($Command.Count -gt 1) {
        $arguments = $Command[1..($Command.Count - 1)]
    }

    $stdoutFile = Join-Path $env:TEMP ("qqbot-update-stdout-{0}.log" -f ([guid]::NewGuid().ToString("N")))
    $stderrFile = Join-Path $env:TEMP ("qqbot-update-stderr-{0}.log" -f ([guid]::NewGuid().ToString("N")))
    $process = Start-Process `
        -FilePath $exe `
        -ArgumentList $arguments `
        -NoNewWindow `
        -Wait `
        -PassThru `
        -RedirectStandardOutput $stdoutFile `
        -RedirectStandardError $stderrFile

    $stdout = ""
    $stderr = ""
    if (Test-Path $stdoutFile) {
        $stdout = Get-Content -Path $stdoutFile -Raw -Encoding UTF8
        Remove-Item -Path $stdoutFile -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path $stderrFile) {
        $stderr = Get-Content -Path $stderrFile -Raw -Encoding UTF8
        Remove-Item -Path $stderrFile -Force -ErrorAction SilentlyContinue
    }

    [pscustomobject]@{
        ExitCode = $process.ExitCode
        Stdout = $stdout
        Stderr = $stderr
    }
}

function Get-UvCommand {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        return @("uv")
    }

    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw "uv not found and Windows py launcher is not available. Install uv first: https://docs.astral.sh/uv/"
    }

    $moduleCheck = Invoke-CapturedCommand @("py", "-$PythonVersion", "-m", "uv", "--version")
    if ($moduleCheck.ExitCode -eq 0) {
        return @("py", "-$PythonVersion", "-m", "uv")
    }

    if ($DryRun) {
        Write-Step "uv not found. Would run: py -$PythonVersion -m pip install --user -U uv"
        return @()
    }

    Write-Step "uv not found; installing uv for current Windows user."
    Invoke-LoggedCommand @("py", "-$PythonVersion", "-m", "pip", "install", "--user", "-U", "uv")
    return @("py", "-$PythonVersion", "-m", "uv")
}

Write-Step "AstrBot update started."
Write-Step "Workspace: $WorkspaceRoot"
Write-Step "ASTRBOT_ROOT: $AstrRoot"
Write-Step "Log: $logFile"
if ($DryRun) {
    Write-Step "DryRun enabled; no install or upgrade command will be executed."
}

$uvCommand = Get-UvCommand
$canUseUv = $uvCommand.Count -gt 0

if ($canUseUv) {
    $toolListCommand = @($uvCommand + @("tool", "list", "--show-paths"))
    $toolListResult = Invoke-CapturedCommand $toolListCommand
    $toolList = (($toolListResult.Stdout, $toolListResult.Stderr) -join "`n").Trim()
    if ($toolListResult.ExitCode -ne 0 -and $toolList -notmatch "No tools installed") {
        Add-Content -Path $logFile -Value $toolList -Encoding UTF8
        throw "Command failed with exit code $($toolListResult.ExitCode): $($toolListCommand -join ' ')"
    }
    Add-Content -Path $logFile -Value $toolList -Encoding UTF8
    $isInstalled = $toolList -match "(?m)^astrbot\s"
}
else {
    $isInstalled = $false
}

if ($isInstalled) {
    Write-Step "Existing uv tool package found: astrbot"
    if ($DryRun) {
        Write-Step "Would run: uv tool upgrade astrbot --python $PythonVersion"
    }
    else {
        Invoke-LoggedCommand @($uvCommand + @("tool", "upgrade", "astrbot", "--python", $PythonVersion))
    }
}
else {
    Write-Step "uv tool package not found; installing astrbot."
    if ($DryRun) {
        Write-Step "Would run: uv tool install astrbot --python $PythonVersion"
    }
    else {
        Invoke-LoggedCommand @($uvCommand + @("tool", "install", "astrbot", "--python", $PythonVersion))
    }
}

Write-Step "AstrBot version after update:"
if ($DryRun) {
    Write-Step "DryRun skipped version check."
}
else {
    if (Get-Command astrbot -ErrorAction SilentlyContinue) {
        Invoke-LoggedCommand @("astrbot", "--version")
    }
    else {
        $versionCommand = @($uvCommand + @("tool", "run", "--from", "astrbot", "--python", $PythonVersion, "astrbot", "--version"))
        Invoke-LoggedCommand $versionCommand
    }
}

Write-Step "Update finished. Start bot2 with scripts\start-astrbot.bat."
