param(
    [switch]$DryRun,
    [switch]$NoStopProcesses,
    [switch]$AssumeYes,
    [switch]$Automatic
)

$ErrorActionPreference = "Stop"
try {
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
}
catch {
}

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$NapCatRoot = $ProjectRoot
$OneKeyRoot = Join-Path $NapCatRoot "onekey"
$DataRoot = Join-Path $NapCatRoot "data"
$DownloadRoot = Join-Path $DataRoot "downloads"
$ArchiveRoot = Join-Path $DataRoot "archives"
$LogRoot = Join-Path $DataRoot "logs\updates"
$NapCatReleaseMarker = Join-Path $OneKeyRoot ".qqbot-napcat-release.json"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$WorkspaceRoot = Split-Path -Parent $ProjectRoot
$RuntimeRoot = Join-Path $OneKeyRoot "napcat"
$StatePath = Join-Path $DataRoot "updates\napcat.json"
$TrashRoot = Join-Path $WorkspaceRoot ".codex\trash\$timestamp\napcat-update"
$logFile = Join-Path $LogRoot "update-napcat-$timestamp.log"

New-Item -ItemType Directory -Path $NapCatRoot -Force | Out-Null
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null

function Write-Step {
    param([string]$Message)

    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

. (Join-Path $ScriptRoot "update-runtime.ps1")

function Get-NormalizedReleaseTag {
    param([string]$Tag)

    if ([string]::IsNullOrWhiteSpace($Tag)) {
        return ""
    }
    return ($Tag.Trim() -replace '^[vV]', '')
}

function Get-InstalledNapCatRelease {
    $version = Get-NapCatBundleVersion -Root $RuntimeRoot
    return [pscustomobject]@{
        Tag = $version
        Source = Join-Path $RuntimeRoot "napcat.mjs"
    }
}

function Write-NapCatReleaseMarker {
    param(
        [string]$Tag,
        [object]$Asset
    )

    $marker = [ordered]@{
        tag_name = $Tag
        asset_name = [string]$Asset.name
        asset_url = [string]$Asset.browser_download_url
        bundle_sha256 = (Get-FileHash -LiteralPath (Join-Path $RuntimeRoot "napcat.mjs") -Algorithm SHA256).Hash.ToLowerInvariant()
        qq_version = $qqRuntime.Key
        updated_at = (Get-Date).ToString("o")
    }
    $marker | ConvertTo-Json -Depth 4 | Set-Content -Path $NapCatReleaseMarker -Encoding UTF8
    Write-Step "Wrote NapCat release marker: $NapCatReleaseMarker"
}

function Confirm-NapCatUpdate {
    param(
        [string]$InstalledVersion,
        [string]$TargetVersion,
        [object]$Asset,
        [string]$ZipPath,
        [string]$ExtractRoot,
        [string]$NewOneKeyRoot,
        [string]$ArchivePath
    )

    Write-Step "NapCat update confirmation:"
    Write-Step "  Installed release: $InstalledVersion"
    Write-Step "  Target release: $TargetVersion"
    Write-Step "  Download asset: $($Asset.name)"
    Write-Step "  Download URL: $($Asset.browser_download_url)"
    Write-Step "  Download path: $ZipPath"
    Write-Step "  Extract path: $ExtractRoot"
    Write-Step "  Prepared package path: $NewOneKeyRoot"
    Write-Step "  Archive current package to: $ArchivePath"
    if ($NoStopProcesses) {
        Write-Step "  Activation requires running NapCat/QQ processes to be closed manually."
    }
    else {
        Write-Step "  Activation will stop related NapCat/QQ processes in this workspace."
    }
    Write-Step "  Account OneBot configs will be migrated after activation."

    if ($AssumeYes -or $Automatic) {
        Write-Step "Automatic update confirmation accepted."
        return $true
    }
    if ($DryRun) {
        Write-Step "DryRun enabled; would ask for NapCat confirmation here."
        return $true
    }

    $answer = Read-Host "Proceed with NapCat download and update? Type Y to continue"
    if ($answer -match '(?i)^(y|yes)$') {
        Write-Step "User confirmed NapCat update."
        return $true
    }

    Write-Step "NapCat update skipped by user before download."
    return $false
}

function Get-NapCatProcesses {
    $allProcesses = @(Get-CimInstance Win32_Process -OperationTimeoutSec 10 -ErrorAction Stop)
    $targetIds = [System.Collections.Generic.HashSet[int]]::new()
    $roots = @($allProcesses | Where-Object { Test-NapCatProcessRoot -ProcessInfo $_ })

    foreach ($root in $roots) {
        foreach ($processId in (Get-ProcessTreeIds -RootProcessId ([int]$root.ProcessId) -Processes $allProcesses)) {
            if ($processId -ne $PID) {
                [void]$targetIds.Add([int]$processId)
            }
        }
    }

    @($allProcesses | Where-Object { $targetIds.Contains([int]$_.ProcessId) })
}

function Format-ProcessSummary {
    param([array]$Processes)

    if (-not $Processes -or $Processes.Count -eq 0) {
        return "(none)"
    }
    return (($Processes | ForEach-Object { "$($_.ProcessId): $($_.Name)" }) -join "; ")
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

function Get-ProcessStopRank {
    param([object]$ProcessInfo)

    $name = [string]$ProcessInfo.Name
    $commandLine = [string]$ProcessInfo.CommandLine

    if ($name -match '(?i)^QQ\.exe$') {
        return 10
    }
    if ($name -match '(?i)^NapCatWinBootMain\.exe$') {
        return 20
    }
    if ($name -match '(?i)^node\.exe$') {
        return 30
    }
    if ($commandLine -match '(?i)(start-(?:napcat-)?account\.ps1|launcher-user\.bat)') {
        return 80
    }
    if ($name -match '(?i)^(powershell|cmd|conhost)\.exe$') {
        return 90
    }
    return 50
}

function Stop-NapCatProcesses {
    param([array]$Processes)

    $processById = @{}
    foreach ($processInfo in $Processes) {
        $processById[[int]$processInfo.ProcessId] = $processInfo
    }
    $orderedProcesses = @($Processes | Sort-Object `
        @{ Expression = { Get-ProcessStopRank -ProcessInfo $_ }; Ascending = $true },
        @{ Expression = { Get-ProcessDepth -ProcessInfo $_ -ProcessById $processById }; Descending = $true })

    foreach ($processInfo in $orderedProcesses) {
        Write-Step "Stopping process $($processInfo.ProcessId): $($processInfo.Name)"
        Stop-Process -Id $processInfo.ProcessId -Force -ErrorAction SilentlyContinue
    }

    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Seconds 1
        $remaining = @(Get-NapCatProcesses)
        if ($remaining.Count -eq 0) {
            return
        }
    } while ((Get-Date) -lt $deadline)

    throw "Some NapCat/QQ processes are still running: $(Format-ProcessSummary $remaining)"
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

function Test-NapCatProcessRoot {
    param([object]$ProcessInfo)

    if (-not $ProcessInfo -or [int]$ProcessInfo.ProcessId -eq $PID) {
        return $false
    }

    $commandLine = [string]$ProcessInfo.CommandLine
    $executablePath = [string]$ProcessInfo.ExecutablePath
    $name = [string]$ProcessInfo.Name
    $projectRootPattern = [regex]::Escape($ProjectRoot)
    $escapedOneKey = [regex]::Escape($OneKeyRoot)

    $referencesWorkspace = (
        ($commandLine -and $commandLine -match $projectRootPattern) -or
        (Test-PathUnderRoot -Path $executablePath -Root $ProjectRoot)
    )
    $referencesOneKey = (
        ($commandLine -and $commandLine -match $escapedOneKey) -or
        (Test-PathUnderRoot -Path $executablePath -Root $OneKeyRoot)
    )
    $hasNapCatMarker = (
        ($commandLine -and $commandLine -match '(?i)(NapCatWinBootMain|NapCat\.Shell|launcher-user\.bat|start-(?:napcat-)?account\.ps1|napcat[\\/]+onekey|QQ\.exe|NapCatQQ)') -or
        ($name -match '(?i)^(NapCatWinBootMain|QQ|node)\.exe$')
    )

    return ($referencesOneKey -or ($referencesWorkspace -and $hasNapCatMarker))
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

function Wait-DirectoryCanMove {
    param(
        [string]$Path,
        [int]$TimeoutSeconds = 30
    )

    if (-not (Test-Path $Path)) {
        return
    }

    $parent = Split-Path -Parent $Path
    $leaf = Split-Path -Leaf $Path
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = ""

    do {
        $probeName = "{0}.move-probe-{1}" -f $leaf, ([guid]::NewGuid().ToString("N"))
        $probePath = Join-Path $parent $probeName
        try {
            Rename-Item -Path $Path -NewName $probeName -ErrorAction Stop
            Rename-Item -Path $probePath -NewName $leaf -ErrorAction Stop
            return
        }
        catch {
            $lastError = $_.Exception.Message
            if ((Test-Path $probePath) -and -not (Test-Path $Path)) {
                try {
                    Rename-Item -Path $probePath -NewName $leaf -ErrorAction Stop
                }
                catch {
                    throw "Directory move probe left package at $probePath and restore failed: $($_.Exception.Message)"
                }
            }
            Start-Sleep -Seconds 1
        }
    } while ((Get-Date) -lt $deadline)

    $remaining = @(Get-NapCatProcesses)
    throw "NapCat onekey directory is still locked: $Path. Remaining related processes: $(Format-ProcessSummary $remaining). Last error: $lastError"
}

function Ensure-NapCatBuiltinPlugin {
    param(
        [string]$TargetRoot
    )

    $script = Join-Path $ScriptRoot "ensure-builtin-plugin.ps1"
    if (-not (Test-Path $script)) {
        throw "NapCat builtin plugin ensure script not found: $script"
    }
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $script,
        "-NapCatRoot", $TargetRoot,
        "-LogFile", $logFile,
        "-ConsolePrefix", "[NapCatUpdate]"
    )
    if ($DryRun) {
        $arguments += "-DryRun"
    }

    & powershell.exe @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "NapCat builtin plugin ensure failed with exit code $LASTEXITCODE."
    }
}

function Sync-NapCatAccountPolicies {
    $script = Join-Path $ScriptRoot "configure-account.ps1"
    $accountsPath = Join-Path $ProjectRoot "accounts.json"
    if (-not (Test-Path $script) -or -not (Test-Path $accountsPath)) {
        throw "NapCat account policy files are incomplete."
    }
    $manifest = Get-Content -Path $accountsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($item in @($manifest.accounts)) {
        if ($DryRun) {
            Write-Step "Would enforce account policy: $($item.target) -> $($item.oneBotPort)"
            continue
        }
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script -Target ([string]$item.target)
        if ($LASTEXITCODE -ne 0) {
            throw "NapCat account policy failed for target '$($item.target)'."
        }
    }
}

Write-Step "NapCat update started. Automatic=$Automatic"
Write-Step "Project: $ProjectRoot"
Write-Step "Log: $logFile"
$lock = $null
try {
    $lock = [System.IO.File]::Open((Join-Path $DataRoot "napcat-update.lock"), [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
}
catch [System.IO.IOException] {
    Write-Step "Another NapCat update owns the workspace lock; this check was skipped."
    exit 0
}

$state = [ordered]@{ checked_at = [DateTime]::UtcNow.ToString("o"); status = "checking"; installed_release = ""; target_release = ""; qq_version = ""; blocked_release = ""; backup_path = ""; restart_pid = $null; restart_deadline = ""; error = ""; log = $logFile }
$canSaveState = $false
$stopped = $false
$restartAttempted = $false
$runtimeArchived = $false
$runtimeActivated = $false
$newRuntimeRoot = Join-Path $OneKeyRoot "napcat.new-$timestamp"
$extractRoot = Join-Path $DownloadRoot "extract-$timestamp"
$archivePath = Join-Path $ArchiveRoot "napcat-$timestamp"
$version = ""
try {
    $previous = $null
    if (Test-Path -LiteralPath $StatePath) {
        $previous = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    $canSaveState = $true
    $headers = @{ "User-Agent" = "qqbot-update-script" }
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/NapNeko/NapCatQQ/releases/latest" -Headers $headers -TimeoutSec 30
    $version = [string]$release.tag_name
    if ($release.draft -or $release.prerelease -or $version -notmatch "^v?\d+\.\d+\.\d+$") {
        throw "The latest NapCat release is not a stable version: $version. Current runtime was left unchanged."
    }
    $installed = Get-InstalledNapCatRelease
    if (-not $installed.Tag) {
        throw "Current NapCat runtime was not found at $RuntimeRoot. Complete the initial installation before enabling automatic updates."
    }
    $state.installed_release = $installed.Tag
    $state.target_release = $version
    Write-Step "Latest release: $version; installed release: $($installed.Tag) (source: $($installed.Source))."
    if ($Automatic -and $null -ne $previous -and (($previous.blocked_release -eq $version) -or ($previous.target_release -eq $version -and $previous.status -in @("activating", "restarting")))) {
        $state.status = "blocked"
        $state.blocked_release = $version
        $state.error = [string]$previous.error
        $state.backup_path = [string]$previous.backup_path
        Save-NapCatUpdateState -State $state
        throw "Automatic update for $version is paused after an interrupted or failed activation. Inspect $StatePath and its log before retrying manually."
    }
    if ([version](Get-NormalizedReleaseTag $installed.Tag) -ge [version](Get-NormalizedReleaseTag $version)) {
        $state.status = "up_to_date"
        Save-NapCatUpdateState -State $state
        Write-Step "No newer stable release; no package or running process was changed."
        exit 0
    }

    $qqRuntime = Get-InstalledQQRuntime
    $state.qq_version = $qqRuntime.Key
    Assert-NapCatQQCompatibility -Tag $version -Runtime $qqRuntime
    $asset = @($release.assets | Where-Object { $_.name -eq "NapCat.Shell.zip" } | Select-Object -First 1)
    if ($asset.Count -ne 1) {
        throw "Release $version has no NapCat.Shell.zip runtime package. Current processes were left unchanged."
    }
    $asset = $asset[0]
    if ([string]$asset.digest -notmatch "^sha256:(?<hash>[a-fA-F0-9]{64})$") {
        throw "Release asset has no usable SHA-256 digest: $($asset.name). Current processes were left unchanged."
    }
    $expectedHash = $Matches.hash.ToLowerInvariant()
    $zipPath = Join-Path $DownloadRoot ("NapCat-{0}-Shell.zip" -f $version)
    if (-not (Confirm-NapCatUpdate -InstalledVersion $installed.Tag -TargetVersion $version -Asset $asset -ZipPath $zipPath -ExtractRoot $extractRoot -NewOneKeyRoot $newRuntimeRoot -ArchivePath $archivePath)) {
        $state.status = "skipped"
        Save-NapCatUpdateState -State $state
        exit 0
    }
    if ($DryRun) {
        Write-Step "Would verify the complete runtime, preserve state, archive $RuntimeRoot to $archivePath, and activate $version."
        Write-Step "Automatic mode restarts active bots through scripts/start-all.ps1 after activation."
        exit 0
    }

    New-Item -ItemType Directory -Path $DownloadRoot -Force | Out-Null
    if (Test-Path -LiteralPath $zipPath) {
        $cached = Get-Item -LiteralPath $zipPath
        if ($cached.Length -ne [long]$asset.size -or (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) {
            Move-NapCatUpdateArtifact -Path $zipPath
        }
    }
    if (-not (Test-Path -LiteralPath $zipPath)) {
        Write-Step "Downloading: $($asset.name)"
        Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url -Headers $headers -OutFile $zipPath -TimeoutSec 300
    }
    if ((Get-Item -LiteralPath $zipPath).Length -ne [long]$asset.size -or (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) {
        Move-NapCatUpdateArtifact -Path $zipPath
        throw "NapCat runtime archive failed size or SHA-256 verification. Current processes were left unchanged."
    }
    Write-Step "Release archive size and SHA-256 verified."
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractRoot -Force
    $sourceRoot = $extractRoot
    if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot "napcat.mjs"))) {
        $children = @(Get-ChildItem -LiteralPath $extractRoot -Directory)
        if ($children.Count -eq 1) { $sourceRoot = $children[0].FullName }
    }
    foreach ($name in @("napcat.mjs", "NapCatWinBootMain.exe", "NapCatWinBootHook.dll", "launcher-user.bat", "qqnt.json")) {
        if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot $name))) {
            throw "NapCat runtime archive is missing $name. Current processes were left unchanged."
        }
    }
    $bundleVersion = Get-NapCatBundleVersion -Root $sourceRoot
    if ($bundleVersion -ne (Get-NormalizedReleaseTag $version)) {
        throw "Downloaded runtime version $bundleVersion does not match $version. Current processes were left unchanged."
    }
    Move-Item -LiteralPath $sourceRoot -Destination $newRuntimeRoot
    $state.status = "prepared"
    Save-NapCatUpdateState -State $state

    $loginMutex = [System.Threading.Mutex]::new($false, "Local\QQBot-NapCat-Login")
    $ownsLoginMutex = $false
    try {
        try { $ownsLoginMutex = $loginMutex.WaitOne(30000) }
        catch [System.Threading.AbandonedMutexException] { $ownsLoginMutex = $true }
        if (-not $ownsLoginMutex) {
            throw "A NapCat account is logging in. Current runtime was left unchanged; the next scheduled check can retry."
        }
        $currentQQ = Get-InstalledQQRuntime
        if ($currentQQ.Key -ne $qqRuntime.Key) {
            Assert-NapCatQQCompatibility -Tag $version -Runtime $currentQQ
            $qqRuntime = $currentQQ
            $state.qq_version = $qqRuntime.Key
        }
        $running = @(Get-NapCatProcesses)
        if ($Automatic) {
            $manifest = Get-Content -LiteralPath (Join-Path $ProjectRoot "accounts.json") -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($account in @($manifest.accounts | Where-Object { $_.autoStart -ne $true })) {
                $accountPattern = '-Account\s+[''" ]?' + [regex]::Escape([string]$account.qq) + '(?:[''" ]|$)'
                if (@($running | Where-Object { $_.CommandLine -match $accountPattern }).Count -gt 0) {
                    throw "Manually managed NapCat account $($account.target) is running. Automatic activation is deferred until it stops."
                }
            }
        }
        if ($running.Count -gt 0 -and $NoStopProcesses) {
            throw "NapCat is running. Close the workspace processes first or omit -NoStopProcesses: $(Format-ProcessSummary $running)"
        }
        # Persist the activation boundary before stopping anything, so interruption cannot trigger another automatic restart.
        $state.status = "activating"
        $state.blocked_release = $version
        $state.backup_path = $archivePath
        Save-NapCatUpdateState -State $state
        if ($running.Count -gt 0) {
            $stopped = $true
            Write-Step "Prepared complete runtime; stopping workspace-owned processes: $(Format-ProcessSummary $running)"
            Stop-NapCatProcesses -Processes $running
        }
        New-Item -ItemType Directory -Path $ArchiveRoot -Force | Out-Null
        Wait-DirectoryCanMove -Path $RuntimeRoot -TimeoutSeconds 30
        Move-Item -LiteralPath $RuntimeRoot -Destination $archivePath
        $runtimeArchived = $true
        Copy-NapCatRuntimeState -FromRoot $archivePath -ToRoot $newRuntimeRoot
        Ensure-NapCatBuiltinPlugin -TargetRoot $newRuntimeRoot
        Move-Item -LiteralPath $newRuntimeRoot -Destination $RuntimeRoot
        $runtimeActivated = $true
        Sync-NapCatAccountPolicies
        Write-NapCatReleaseMarker -Tag $version -Asset $asset
        $state.installed_release = $version
        Write-Step "NapCat $version activated. Previous runtime retained at $archivePath."
    }
    catch {
        if ($runtimeArchived) {
            if ($runtimeActivated) { Move-NapCatUpdateArtifact -Path $RuntimeRoot }
            Move-Item -LiteralPath $archivePath -Destination $RuntimeRoot
            $state.installed_release = $installed.Tag
            Write-Step "Activation failed; restored the previous runtime from $archivePath."
        }
        throw
    }
    finally {
        if ($ownsLoginMutex) { $loginMutex.ReleaseMutex() }
        $loginMutex.Dispose()
    }

    if ($Automatic -and $stopped) {
        $state.status = "restarting"
        Save-NapCatUpdateState -State $state
        $restartAttempted = $true
        $restartStarted = [DateTime]::UtcNow
        Restart-NapCatBots -State $state
        Assert-NapCatHookReady -RestartStarted $restartStarted
    }
    $state.status = "updated"
    $state.blocked_release = ""
    Save-NapCatUpdateState -State $state
    Write-Step "NapCat update finished. Runtime: $RuntimeRoot; state: $StatePath"
    if (-not $Automatic -and $stopped) {
        Write-Step "Start bots with the qqbot root scripts/start-all.bat to restore connections."
    }
}
catch {
    $failure = $_
    Write-Step "NapCat update failed: $($failure.Exception.Message)"
    if ($canSaveState) {
        $state.status = "failed"
        $state.error = $failure.Exception.Message
        if ($stopped) { $state.blocked_release = $version }
        try { Save-NapCatUpdateState -State $state }
        catch { Write-Step "Could not save failure state: $($_.Exception.Message)" }
    }
    if ($Automatic -and $stopped -and -not $restartAttempted) {
        $restartAttempted = $true
        try { Restart-NapCatBots -State $state }
        catch {
            Write-Step "Previous runtime restart failed: $($_.Exception.Message)"
            $state.error += " Recovery restart: " + $_.Exception.Message
            Save-NapCatUpdateState -State $state
        }
    }
    throw $failure
}
finally {
    try {
        foreach ($path in @($extractRoot, $newRuntimeRoot)) { Move-NapCatUpdateArtifact -Path $path }
    }
    finally { $lock.Dispose() }
}
