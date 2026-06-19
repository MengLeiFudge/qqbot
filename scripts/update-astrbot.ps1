param(
    [string]$PythonVersion = "3.14",
    [switch]$DryRun,
    [switch]$NoStopProcesses
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

function Format-ProcessSummary {
    param([array]$Processes)

    if (-not $Processes -or $Processes.Count -eq 0) {
        return "(none)"
    }
    return (($Processes | ForEach-Object { "$($_.ProcessId): $($_.Name)" }) -join "; ")
}

function Test-PathUnderRoot {
    param(
        [string]$Path,
        [string]$Root
    )

    if ([string]::IsNullOrWhiteSpace($Path) -or [string]::IsNullOrWhiteSpace($Root)) {
        return $false
    }

    try {
        $fullPath = [System.IO.Path]::GetFullPath($Path.Trim('"'))
        $fullRoot = [System.IO.Path]::GetFullPath($Root.Trim('"'))
        $rootPrefix = $fullRoot
        if (-not $rootPrefix.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
            $rootPrefix += [System.IO.Path]::DirectorySeparatorChar
        }

        return (
            $fullPath.Equals($fullRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
            $fullPath.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)
        )
    }
    catch {
        return $false
    }
}

function Test-AstrBotProcessRoot {
    param([object]$ProcessInfo)

    if (-not $ProcessInfo -or [int]$ProcessInfo.ProcessId -eq $PID) {
        return $false
    }

    $commandLine = [string]$ProcessInfo.CommandLine
    $executablePath = [string]$ProcessInfo.ExecutablePath
    $escapedWorkspace = [regex]::Escape($WorkspaceRoot)
    $escapedAstrBotExe = [regex]::Escape("\Scripts\astrbot.exe")

    $isWorkspaceLauncher = (
        $commandLine -and
        $commandLine -match $escapedWorkspace -and
        $commandLine -match '(?i)start-astrbot\.ps1'
    )
    $isAstrBotRunCommand = (
        $commandLine -and
        $commandLine -match $escapedAstrBotExe -and
        $commandLine -match '(?i)\srun\s+-p\s+6185(\s|$)'
    )
    $isUvToolAstrBotExe = (
        (Test-PathUnderRoot -Path $executablePath -Root (Join-Path $env:APPDATA "uv\tools\astrbot")) -and
        $commandLine -and
        $commandLine -match '(?i)\srun\s+-p\s+6185(\s|$)'
    )

    return ($isWorkspaceLauncher -or $isAstrBotRunCommand -or $isUvToolAstrBotExe)
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

function Get-ProcessDepth {
    param(
        [object]$ProcessInfo,
        [hashtable]$ProcessById
    )

    $depth = 0
    $seen = [System.Collections.Generic.HashSet[int]]::new()
    $parentId = [int]$ProcessInfo.ParentProcessId
    while ($parentId -and $ProcessById.ContainsKey($parentId) -and $seen.Add($parentId)) {
        $depth += 1
        $parent = $ProcessById[$parentId]
        $parentId = [int]$parent.ParentProcessId
    }
    return $depth
}

function Get-AstrBotProcesses {
    $allProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $targetIds = [System.Collections.Generic.HashSet[int]]::new()
    $roots = @($allProcesses | Where-Object { Test-AstrBotProcessRoot -ProcessInfo $_ })

    foreach ($root in $roots) {
        foreach ($processId in (Get-ProcessTreeIds -RootProcessId ([int]$root.ProcessId) -Processes $allProcesses)) {
            if ($processId -ne $PID) {
                [void]$targetIds.Add([int]$processId)
            }
        }
    }

    @($allProcesses | Where-Object { $targetIds.Contains([int]$_.ProcessId) })
}

function Stop-AstrBotProcesses {
    param([array]$Processes)

    $processById = @{}
    foreach ($processInfo in $Processes) {
        $processById[[int]$processInfo.ProcessId] = $processInfo
    }
    $orderedProcesses = @($Processes | Sort-Object @{ Expression = { Get-ProcessDepth -ProcessInfo $_ -ProcessById $processById }; Descending = $true })

    foreach ($processInfo in $orderedProcesses) {
        Write-Step "Stopping AstrBot process $($processInfo.ProcessId): $($processInfo.Name)"
        Stop-Process -Id $processInfo.ProcessId -Force -ErrorAction SilentlyContinue
    }

    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Seconds 1
        $remaining = @(Get-AstrBotProcesses)
        if ($remaining.Count -eq 0) {
            return
        }
    } while ((Get-Date) -lt $deadline)

    throw "Some AstrBot processes are still running: $(Format-ProcessSummary $remaining)"
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

$running = @(Get-AstrBotProcesses)
if ($running.Count -gt 0) {
    if ($DryRun) {
        if ($NoStopProcesses) {
            Write-Step "Would require these AstrBot processes to be closed manually before upgrade: $(Format-ProcessSummary $running)"
        }
        else {
            Write-Step "Would stop running AstrBot processes before upgrade: $(Format-ProcessSummary $running)"
        }
    }
    elseif ($NoStopProcesses) {
        throw "AstrBot is running. Close these processes first or rerun without -NoStopProcesses: $(Format-ProcessSummary $running)"
    }
    else {
        Write-Step "Running AstrBot processes detected before upgrade: $(Format-ProcessSummary $running)"
        Stop-AstrBotProcesses $running
    }
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
