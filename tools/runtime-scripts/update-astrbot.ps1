param(
    [string]$PythonVersion = "3.14",
    [switch]$DryRun,
    [switch]$NoStopProcesses,
    [switch]$AssumeYes
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
$WorkspaceRoot = Split-Path -Parent (Split-Path -Parent $ScriptRoot)
$ExtraRequirements = Join-Path $ScriptRoot "astrbot-extra-requirements.txt"
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

function Resolve-CommandItems {
    param([string[]]$Command)

    $items = @()
    foreach ($item in @($Command)) {
        if ($null -ne $item -and -not [string]::IsNullOrWhiteSpace([string]$item)) {
            $items += [string]$item
        }
    }
    if ($items.Count -eq 0) {
        throw "Command is empty."
    }
    return $items
}

function Invoke-LoggedCommand {
    param([string[]]$Command)

    $commandItems = @(Resolve-CommandItems -Command $Command)
    Write-Step ("> " + ($commandItems -join " "))
    $exe = $commandItems[0]
    $arguments = @()
    if ($commandItems.Count -gt 1) {
        $arguments = @($commandItems[1..($commandItems.Count - 1)])
    }

    $stdoutFile = Join-Path $env:TEMP ("qqbot-update-stdout-{0}.log" -f ([guid]::NewGuid().ToString("N")))
    $stderrFile = Join-Path $env:TEMP ("qqbot-update-stderr-{0}.log" -f ([guid]::NewGuid().ToString("N")))
    $startArgs = @{
        FilePath = $exe
        NoNewWindow = $true
        Wait = $true
        PassThru = $true
        RedirectStandardOutput = $stdoutFile
        RedirectStandardError = $stderrFile
    }
    if ($arguments.Count -gt 0) {
        $startArgs.ArgumentList = $arguments
    }
    $process = Start-Process @startArgs

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
        throw "Command failed with exit code $($process.ExitCode): $($commandItems -join ' ')"
    }
}

function Invoke-CapturedCommand {
    param([string[]]$Command)

    $commandItems = @(Resolve-CommandItems -Command $Command)
    $exe = $commandItems[0]
    $arguments = @()
    if ($commandItems.Count -gt 1) {
        $arguments = @($commandItems[1..($commandItems.Count - 1)])
    }

    $stdoutFile = Join-Path $env:TEMP ("qqbot-update-stdout-{0}.log" -f ([guid]::NewGuid().ToString("N")))
    $stderrFile = Join-Path $env:TEMP ("qqbot-update-stderr-{0}.log" -f ([guid]::NewGuid().ToString("N")))
    $startArgs = @{
        FilePath = $exe
        NoNewWindow = $true
        Wait = $true
        PassThru = $true
        RedirectStandardOutput = $stdoutFile
        RedirectStandardError = $stderrFile
    }
    if ($arguments.Count -gt 0) {
        $startArgs.ArgumentList = $arguments
    }
    $process = Start-Process @startArgs

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

function Test-PyUvAvailable {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        return $false
    }

    $moduleCheck = Invoke-CapturedCommand @("py", "-$PythonVersion", "-m", "uv", "--version")
    return ($moduleCheck.ExitCode -eq 0)
}

function Get-UvToolInstalledState {
    param([string[]]$UvCommand)

    if (-not $UvCommand -or $UvCommand.Count -eq 0) {
        return [pscustomobject]@{
            IsInstalled = $false
            ToolList = ""
        }
    }

    $toolListCommand = @($UvCommand) + @("tool", "list", "--show-paths")
    $toolListResult = Invoke-CapturedCommand $toolListCommand
    $toolList = (($toolListResult.Stdout, $toolListResult.Stderr) -join "`n").Trim()
    if ($toolListResult.ExitCode -ne 0 -and $toolList -notmatch "No tools installed") {
        Add-Content -Path $logFile -Value $toolList -Encoding UTF8
        throw "Command failed with exit code $($toolListResult.ExitCode): $($toolListCommand -join ' ')"
    }
    Add-Content -Path $logFile -Value $toolList -Encoding UTF8

    $toolMatch = [regex]::Match(
        $toolList,
        '(?m)^astrbot\s+[^\r\n]*\((?<path>[^)\r\n]+)\)\s*$'
    )
    return [pscustomobject]@{
        IsInstalled = $toolMatch.Success
        ToolList = $toolList
        ToolPath = if ($toolMatch.Success) { $toolMatch.Groups["path"].Value } else { "" }
    }
}

function Confirm-AstrBotUpdate {
    param(
        [array]$RunningProcesses,
        [bool]$CanUsePathUv,
        [bool]$CanUsePyUv,
        [bool]$CanUsePyLauncher,
        [bool]$IsInstalled,
        [bool]$WillInstallUv,
        [string]$Action
    )

    $uvInvoker = if ($CanUsePathUv) {
        "uv"
    }
    elseif ($CanUsePyUv -or $WillInstallUv) {
        "py -$PythonVersion -m uv"
    }
    else {
        "(not available)"
    }
    $commandPreview = if ($Action -eq "upgrade") {
        "$uvInvoker tool upgrade astrbot --python $PythonVersion"
    }
    else {
        "$uvInvoker tool install astrbot --python $PythonVersion"
    }

    Write-Step "AstrBot update confirmation:"
    Write-Step "  Python version: $PythonVersion"
    Write-Step "  uv command: $uvInvoker"
    Write-Step "  Existing uv tool package: $(if ($IsInstalled) { 'astrbot installed' } else { 'astrbot not installed' })"
    Write-Step "  Planned action: $Action"
    Write-Step "  Planned command: $commandPreview"
    Write-Step "  Pinned plugin dependencies: $ExtraRequirements"
    if ($WillInstallUv) {
        Write-Step "  uv bootstrap command before update: py -$PythonVersion -m pip install --user -U uv"
    }
    elseif (-not $CanUsePathUv -and -not $CanUsePyUv -and -not $CanUsePyLauncher) {
        Write-Step "  uv bootstrap is unavailable because Windows py launcher was not found."
    }
    if ($RunningProcesses.Count -gt 0) {
        if ($NoStopProcesses) {
            Write-Step "  Running AstrBot processes must be closed manually: $(Format-ProcessSummary $RunningProcesses)"
        }
        else {
            Write-Step "  Related AstrBot processes in this workspace will be stopped: $(Format-ProcessSummary $RunningProcesses)"
        }
    }
    else {
        Write-Step "  Running AstrBot processes: (none)"
    }

    if ($AssumeYes) {
        Write-Step "AssumeYes enabled; auto-confirming AstrBot update."
        return $true
    }
    if ($DryRun) {
        Write-Step "DryRun enabled; would ask for AstrBot confirmation here."
        return $true
    }

    $answer = Read-Host "Proceed with AstrBot $Action? Type Y to continue"
    if ($answer -match '(?i)^(y|yes)$') {
        Write-Step "User confirmed AstrBot update."
        return $true
    }

    Write-Step "AstrBot update skipped by user before install or upgrade."
    return $false
}

function Get-UvCommand {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        return @("uv")
    }

    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw "uv not found and Windows py launcher is not available. Install uv first: https://docs.astral.sh/uv/"
    }

    if (Test-PyUvAvailable) {
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
$canUsePathUv = [bool](Get-Command uv -ErrorAction SilentlyContinue)
$canUsePyLauncher = [bool](Get-Command py -ErrorAction SilentlyContinue)
$canUsePyUv = $false
if (-not $canUsePathUv -and $canUsePyLauncher) {
    $canUsePyUv = Test-PyUvAvailable
}
$willInstallUv = (-not $canUsePathUv -and -not $canUsePyUv -and $canUsePyLauncher)

if ($canUsePathUv) {
    $precheckUvCommand = @("uv")
}
elseif ($canUsePyUv) {
    $precheckUvCommand = @("py", "-$PythonVersion", "-m", "uv")
}
else {
    $precheckUvCommand = @()
}

$toolState = Get-UvToolInstalledState -UvCommand $precheckUvCommand
$isInstalled = [bool]$toolState.IsInstalled
$action = if ($isInstalled) { "upgrade" } else { "install" }

if (-not (Confirm-AstrBotUpdate `
    -RunningProcesses $running `
    -CanUsePathUv $canUsePathUv `
    -CanUsePyUv $canUsePyUv `
    -CanUsePyLauncher $canUsePyLauncher `
    -IsInstalled $isInstalled `
    -WillInstallUv $willInstallUv `
    -Action $action)) {
    exit 0
}

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

$uvCommand = @(Get-UvCommand)

if ($isInstalled) {
    Write-Step "Existing uv tool package found: astrbot"
    if ($DryRun) {
        Write-Step "Would run: uv tool upgrade astrbot --python $PythonVersion"
    }
    else {
        Invoke-LoggedCommand (@($uvCommand) + @("tool", "upgrade", "astrbot", "--python", $PythonVersion))
    }
}
else {
    Write-Step "uv tool package not found; installing astrbot."
    if ($DryRun) {
        Write-Step "Would run: uv tool install astrbot --python $PythonVersion"
    }
    else {
        Invoke-LoggedCommand (@($uvCommand) + @("tool", "install", "astrbot", "--python", $PythonVersion))
    }
}

if ($DryRun) {
    $dryRunToolRoot = if (-not [string]::IsNullOrWhiteSpace($toolState.ToolPath)) {
        $toolState.ToolPath
    }
    elseif (-not [string]::IsNullOrWhiteSpace($env:UV_TOOL_DIR)) {
        Join-Path $env:UV_TOOL_DIR "astrbot"
    }
    else {
        Join-Path $env:APPDATA "uv\tools\astrbot"
    }
    $astrBotToolPython = Join-Path $dryRunToolRoot "Scripts\python.exe"
}
else {
    $postInstallToolState = Get-UvToolInstalledState -UvCommand $uvCommand
    if (-not $postInstallToolState.IsInstalled -or [string]::IsNullOrWhiteSpace($postInstallToolState.ToolPath)) {
        throw "AstrBot uv tool path is unavailable after install or upgrade."
    }
    $astrBotToolPython = Join-Path $postInstallToolState.ToolPath "Scripts\python.exe"
}
if ($DryRun) {
    Write-Step "Would install pinned AstrBot plugin dependencies from: $ExtraRequirements"
    Write-Step "Would run: uv pip install --python $astrBotToolPython --requirements $ExtraRequirements"
}
else {
    if (-not (Test-Path $ExtraRequirements -PathType Leaf)) {
        throw "AstrBot plugin dependency manifest is missing: $ExtraRequirements"
    }
    if (-not (Test-Path $astrBotToolPython -PathType Leaf)) {
        throw "AstrBot uv tool Python is missing after install or upgrade: $astrBotToolPython"
    }
    Write-Step "Installing pinned AstrBot plugin dependencies."
    Invoke-LoggedCommand (@($uvCommand) + @(
        "pip",
        "install",
        "--python",
        $astrBotToolPython,
        "--requirements",
        $ExtraRequirements
    ))
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
        $versionCommand = @($uvCommand) + @("tool", "run", "--from", "astrbot", "--python", $PythonVersion, "astrbot", "--version")
        Invoke-LoggedCommand $versionCommand
    }
}

Write-Step "Update finished. Start bots with scripts\start-all.bat."
