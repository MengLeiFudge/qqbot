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
}

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkspaceRoot = Split-Path -Parent $ScriptRoot
$AppRoot = Join-Path $WorkspaceRoot "nonebot2"
$DataRoot = Join-Path $WorkspaceRoot "data\nonebot2"
$VenvRoot = Join-Path $DataRoot ".venv"
$PythonPath = Join-Path $VenvRoot "Scripts\python.exe"
$LogRoot = Join-Path $DataRoot "logs\updates"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logFile = Join-Path $LogRoot "update-nonebot2-$timestamp.log"

New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null

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

Write-Step "NoneBot2 and OneBot adapter update started."
Write-Step "Workspace: $WorkspaceRoot"
Write-Step "Log: $logFile"
if ($DryRun) {
    Write-Step "DryRun enabled; no venv creation, pip install, or tests will be executed."
}

if (-not (Test-Path $PythonPath)) {
    if ($DryRun) {
        Write-Step "Would run: py -$PythonVersion -m venv $VenvRoot"
    }
    else {
        Invoke-LoggedCommand @("py", "-$PythonVersion", "-m", "venv", $VenvRoot)
    }
}

$editableTarget = "$AppRoot[dev]"
if ($DryRun) {
    Write-Step "Would run: $PythonPath -m pip install -U pip setuptools wheel"
    Write-Step "Would run: $PythonPath -m pip install -U --upgrade-strategy eager -e $editableTarget"
    Write-Step "Would run: $PythonPath -m pytest $AppRoot\tests\test_config.py -q"
    Write-Step "NoneBot2 update dry run finished."
    exit 0
}

if (-not (Test-Path $PythonPath)) {
    throw "Python executable not found after venv creation: $PythonPath"
}

Invoke-LoggedCommand @($PythonPath, "-m", "pip", "install", "-U", "pip", "setuptools", "wheel")
Invoke-LoggedCommand @($PythonPath, "-m", "pip", "install", "-U", "--upgrade-strategy", "eager", "-e", $editableTarget)
Invoke-LoggedCommand @($PythonPath, "-m", "pytest", (Join-Path $AppRoot "tests\test_config.py"), "-q")

Write-Step "NoneBot2 and OneBot adapter update finished. Start bot1 with scripts\start-nonebot2.bat."
