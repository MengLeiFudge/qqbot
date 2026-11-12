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
. (Join-Path $ScriptRoot "update-qq.ps1")

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

Write-Step "NapCat / independent QQ update started. Automatic=$Automatic"
Write-Step "Project: $ProjectRoot"
Write-Step "Log: $logFile"
New-Item -ItemType Directory -Path $DataRoot -Force | Out-Null
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
$rollbackComplete = $true
$runtimeArchived = $false
$runtimeActivated = $false
$selectionChanged = $false
$qqActivated = $false
$qqBackup = ''
$qqDestination = ''
$oldSelection = $null
$newRuntimeRoot = Join-Path $OneKeyRoot "napcat.new-$timestamp"
$extractRoot = Join-Path $DownloadRoot "extract-$timestamp"
$archivePath = Join-Path $ArchiveRoot "napcat-$timestamp"
$selectionPath = Join-Path $OneKeyRoot 'qq-runtime.json'
$version = ""
try {
    $previous = $null
    if (Test-Path -LiteralPath $StatePath) {
        $previous = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $state.blocked_release = [string]$previous.blocked_release
        $state.backup_path = [string]$previous.backup_path
        if ($previous.status -in @('activating', 'restarting')) { $state.blocked_release = [string]$previous.target_release }
    }
    $canSaveState = $true
    $installed = Get-InstalledNapCatRelease
    $state.installed_release = $installed.Tag
    $headers = @{ 'User-Agent' = 'qqbot-update-script' }
    $release = Invoke-NapCatWebRequest -Uri 'https://api.github.com/repos/NapNeko/NapCatQQ/releases/latest'
    $version = [string]$release.tag_name
    if ($release.draft -or $release.prerelease -or $version -notmatch '^v?\d+\.\d+\.\d+$') {
        throw "The latest NapCat release is not a stable version: $version. Current runtime was left unchanged."
    }
    $state.target_release = $version
    $normalizedVersion = Get-NormalizedReleaseTag $version
    if ($installed.Tag -and [version]$installed.Tag -gt [version]$normalizedVersion) {
        throw "Local NapCat $($installed.Tag) is newer than stable $version. Automatic downgrade is not allowed."
    }
    $napcatChanged = $installed.Tag -ne $normalizedVersion
    $matrix = Get-NapCatQQMatrix -Tag $version
    $targetQQ = Get-LatestSupportedQQ -Matrix $matrix
    $state.qq_version = $targetQQ
    Write-Step "Target pair: NapCat $version / QQ $targetQQ. Installed NapCat: $($installed.Tag)."
    if ($Automatic -and $null -ne $previous -and ($previous.blocked_release -eq $version -or ($previous.target_release -eq $version -and $previous.status -in @('activating', 'restarting')))) {
        $state.blocked_release = $version
        $state.backup_path = [string]$previous.backup_path
        throw "Automatic activation of $version is paused after an interrupted or failed activation. Inspect $StatePath before retrying manually."
    }
    $currentQQ = $null
    if (Test-Path -LiteralPath $selectionPath) {
        $oldSelection = Get-Content -LiteralPath $selectionPath -Raw -Encoding UTF8 | ConvertFrom-Json
        try { $currentQQ = Get-ManagedQQRuntime -OneKeyRoot $OneKeyRoot }
        catch { Write-Step "Independent QQ needs preparation: $($_.Exception.Message)" }
    }
    $qqChanged = $null -eq $currentQQ -or $currentQQ.Key -ne $targetQQ
    if (-not $napcatChanged -and -not $qqChanged -and [string]$oldSelection.napcat_version -eq $normalizedVersion) {
        Assert-TencentSignature -Path $currentQQ.Exe
        Assert-TencentSignature -Path $currentQQ.NativeDll
        $state.status = 'up_to_date'
        Save-NapCatUpdateState -State $state
        Write-Step "NapCat and independent QQ already match the latest supported pair; no processes were changed."
        exit 0
    }
    $asset = @($release.assets | Where-Object { $_.name -eq 'NapCat.Shell.zip' })
    if ($asset.Count -ne 1) { throw "Release $version has no unique NapCat.Shell.zip asset." }
    $asset = $asset[0]
    $zipPath = Join-Path $DownloadRoot ("NapCat-{0}-{1}" -f $version, $asset.name)
    Write-Step "Selected independent QQ target: $targetQQ. Desktop QQ will not be updated or stopped."
    if (-not (Confirm-NapCatUpdate -InstalledVersion $installed.Tag -TargetVersion $version -Asset $asset -ZipPath $zipPath -ExtractRoot $extractRoot -NewOneKeyRoot $newRuntimeRoot -ArchivePath $archivePath)) {
        $state.status = 'skipped'
        Save-NapCatUpdateState -State $state
        exit 0
    }
    if ($DryRun) {
        Write-Step "Would prepare and verify both packages, activate NapCat then independent QQ $targetQQ, and restart active bots once."
        exit 0
    }

    # 两个包都准备成功后才能停止机器人；QQ 最新官网包若领先支持表则明确失败。
    $preparedQQ = Prepare-ManagedQQ -TargetKey $targetQQ -Release $release
    if ($napcatChanged) {
        $zipPath = Get-VerifiedReleaseArchive -Release $release -AssetName 'NapCat.Shell.zip'
        Expand-Archive -LiteralPath $zipPath -DestinationPath $extractRoot -Force
        $sourceRoot = $extractRoot
        if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot 'napcat.mjs'))) {
            $children = @(Get-ChildItem -LiteralPath $extractRoot -Directory)
            if ($children.Count -eq 1) { $sourceRoot = $children[0].FullName }
        }
        foreach ($name in @('napcat.mjs', 'NapCatWinBootMain.exe', 'NapCatWinBootHook.dll', 'loadNapCat.js', 'qqnt.json')) {
            if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot $name) -PathType Leaf)) {
                throw "NapCat runtime archive is missing $name. Current processes were left unchanged."
            }
        }
        if ((Get-NapCatBundleVersion -Root $sourceRoot) -ne $normalizedVersion) {
            throw "Downloaded NapCat runtime does not match $version. Current processes were left unchanged."
        }
        Move-Item -LiteralPath $sourceRoot -Destination $newRuntimeRoot
    }
    $state.status = 'prepared'
    Save-NapCatUpdateState -State $state

    $loginMutex = [System.Threading.Mutex]::new($false, 'Local\QQBot-NapCat-Login')
    $ownsLoginMutex = $false
    try {
        try { $ownsLoginMutex = $loginMutex.WaitOne(30000) }
        catch [System.Threading.AbandonedMutexException] { $ownsLoginMutex = $true }
        if (-not $ownsLoginMutex) { throw 'A NapCat account is logging in. Activation was deferred without changing the current pair.' }
        $running = @(Get-NapCatProcesses)
        if ($Automatic) {
            $manifest = Get-Content -LiteralPath (Join-Path $ProjectRoot 'accounts.json') -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($account in @($manifest.accounts | Where-Object { $_.autoStart -ne $true })) {
                $accountPattern = '-Account\s+[''" ]?' + [regex]::Escape([string]$account.qq) + '(?:[''" ]|$)'
                if (@($running | Where-Object { $_.CommandLine -match $accountPattern }).Count -gt 0) {
                    throw "Manually managed account $($account.target) is running; automatic activation is deferred."
                }
            }
        }
        if ($running.Count -gt 0 -and $NoStopProcesses) {
            throw "NapCat is running. Close workspace processes first or omit -NoStopProcesses: $(Format-ProcessSummary $running)"
        }
        $state.status = 'activating'
        $state.blocked_release = $version
        $state.backup_path = $archivePath
        Save-NapCatUpdateState -State $state
        $rollbackComplete = $false
        if ($running.Count -gt 0) {
            $stopped = $true
            Write-Step "Prepared both packages; stopping workspace-owned processes: $(Format-ProcessSummary $running)"
            Stop-NapCatProcesses -Processes $running
        }
        New-Item -ItemType Directory -Path $ArchiveRoot -Force | Out-Null
        if ($napcatChanged) {
            if (Test-Path -LiteralPath $RuntimeRoot) {
                Wait-DirectoryCanMove -Path $RuntimeRoot -TimeoutSeconds 30
                Move-Item -LiteralPath $RuntimeRoot -Destination $archivePath
                $runtimeArchived = $true
                Copy-NapCatRuntimeState -FromRoot $archivePath -ToRoot $newRuntimeRoot
            }
            Ensure-NapCatBuiltinPlugin -TargetRoot $newRuntimeRoot
            Move-Item -LiteralPath $newRuntimeRoot -Destination $RuntimeRoot
            $runtimeActivated = $true
        }
        if ($preparedQQ.StagingPath) {
            $qqDestination = Join-Path $OneKeyRoot "qq\$targetQQ"
            New-Item -ItemType Directory -Path (Split-Path -Parent $qqDestination) -Force | Out-Null
            if (Test-Path -LiteralPath $qqDestination) {
                $backup = Join-Path $ArchiveRoot "qq-$targetQQ-$timestamp"
                Move-Item -LiteralPath $qqDestination -Destination $backup
                $qqBackup = $backup
            }
            Move-Item -LiteralPath $preparedQQ.StagingPath -Destination $qqDestination
            $qqActivated = $true
        }
        $qqRuntime = Get-QQRuntimeInfo -Root (Join-Path $OneKeyRoot "qq\$targetQQ")
        if ($qqRuntime.Key -ne $targetQQ) { throw 'Prepared QQ changed before activation.' }
        $installerHash = $preparedQQ.InstallerHash
        if (-not $installerHash -and $null -ne $oldSelection -and $oldSelection.qq_version -eq $targetQQ) { $installerHash = [string]$oldSelection.installer_sha256 }
        Save-QQRuntimeSelection -OneKeyRoot $OneKeyRoot -Selection ([ordered]@{ schema_version = 1; qq_version = $targetQQ; napcat_version = $normalizedVersion; installer_sha256 = $installerHash; selected_at = [DateTime]::UtcNow.ToString('o') })
        $selectionChanged = $true
        Sync-NapCatAccountPolicies
        Write-NapCatReleaseMarker -Tag $version -Asset $asset
        $state.installed_release = $normalizedVersion
        Write-Step "Activated NapCat $version, then independent QQ $targetQQ. Desktop QQ was left unchanged."
    }
    catch {
        if ($runtimeActivated) { Move-NapCatUpdateArtifact -Path $RuntimeRoot }
        if ($runtimeArchived) { Move-Item -LiteralPath $archivePath -Destination $RuntimeRoot }
        if ($qqActivated) { Move-NapCatUpdateArtifact -Path $qqDestination }
        if ($qqBackup) { Move-Item -LiteralPath $qqBackup -Destination $qqDestination }
        if ($selectionChanged) {
            if ($null -ne $oldSelection) {
                $restoredSelection = [ordered]@{}
                foreach ($property in $oldSelection.PSObject.Properties) { $restoredSelection[$property.Name] = $property.Value }
                Save-QQRuntimeSelection -OneKeyRoot $OneKeyRoot -Selection $restoredSelection
            }
            else { Move-NapCatUpdateArtifact -Path $selectionPath }
        }
        $state.installed_release = $installed.Tag
        $rollbackComplete = $true
        Write-Step 'Activation failed; restored the previous NapCat / QQ selection before recovery.'
        throw
    }
    finally {
        if ($ownsLoginMutex) { $loginMutex.ReleaseMutex() }
        $loginMutex.Dispose()
    }

    if ($stopped -or -not $Automatic) {
        $state.status = 'restarting'
        Save-NapCatUpdateState -State $state
        $restartAttempted = $true
        $restartStarted = [DateTime]::UtcNow
        Restart-NapCatBots -State $state
        Assert-NapCatHookReady -RestartStarted $restartStarted
    }
    $state.status = 'updated'
    $state.blocked_release = ''
    Save-NapCatUpdateState -State $state
    Write-Step "Paired update finished. State: $StatePath"
}
catch {
    $failure = $_
    Write-Step "Paired update failed: $($failure.Exception.Message)"
    if ($canSaveState) {
        $state.status = 'failed'
        $state.error = $failure.Exception.Message
        try { Save-NapCatUpdateState -State $state }
        catch { Write-Step "Could not save failure state: $($_.Exception.Message)" }
    }
    if ($stopped -and $rollbackComplete -and -not $restartAttempted) {
        $restartAttempted = $true
        try { Restart-NapCatBots -State $state }
        catch {
            Write-Step "Previous runtime recovery failed: $($_.Exception.Message)"
            $state.error += ' Recovery restart: ' + $_.Exception.Message
            Save-NapCatUpdateState -State $state
        }
    }
    throw $failure
}
finally {
    try {
        foreach ($path in @($extractRoot, $newRuntimeRoot, (Join-Path $DownloadRoot "qq-extract-$timestamp"), (Join-Path $DownloadRoot "qq-extractor-$timestamp"))) { Move-NapCatUpdateArtifact -Path $path }
    }
    finally { $lock.Dispose() }
}
