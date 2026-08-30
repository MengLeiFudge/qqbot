param(
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
$logFile = Join-Path $LogRoot "update-napcat-$timestamp.log"

New-Item -ItemType Directory -Path $NapCatRoot -Force | Out-Null
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null

function Write-Step {
    param([string]$Message)

    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

function Get-NormalizedReleaseTag {
    param([string]$Tag)

    if ([string]::IsNullOrWhiteSpace($Tag)) {
        return ""
    }
    return ($Tag.Trim() -replace '^[vV]', '')
}

function Get-InstalledNapCatRelease {
    if (-not (Test-Path $NapCatReleaseMarker)) {
        $updateLogs = @(Get-ChildItem -Path $LogRoot -File -Filter "update-napcat-*.log" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending)
        foreach ($updateLog in $updateLogs) {
            try {
                $content = Get-Content -Path $updateLog.FullName -Raw -Encoding UTF8
                $tagMatch = [regex]::Match($content, '(?m)Latest release:\s*(\S+)')
                if ($tagMatch.Success -and $content -match 'NapCat update finished') {
                    return [pscustomobject]@{
                        Tag = [string]$tagMatch.Groups[1].Value
                        Source = $updateLog.FullName
                    }
                }
            }
            catch {
            }
        }

        return [pscustomobject]@{
            Tag = ""
            Source = "missing-marker"
        }
    }

    try {
        $marker = Get-Content -Path $NapCatReleaseMarker -Raw -Encoding UTF8 | ConvertFrom-Json
        return [pscustomobject]@{
            Tag = [string]$marker.tag_name
            Source = $NapCatReleaseMarker
        }
    }
    catch {
        Write-Step "Failed to read NapCat release marker: $($_.Exception.Message)"
        return [pscustomobject]@{
            Tag = ""
            Source = "invalid-marker"
        }
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
        updated_at = (Get-Date).ToString("o")
    }
    $marker | ConvertTo-Json -Depth 4 | Set-Content -Path $NapCatReleaseMarker -Encoding UTF8
    Write-Step "Wrote NapCat release marker: $NapCatReleaseMarker"
}

function Remove-PathIfExists {
    param(
        [string]$Path,
        [string]$Description
    )

    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) {
        return
    }

    Write-Step "Cleaning $Description`: $Path"
    Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
}

function Remove-EmptyDirectoryIfExists {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) {
        return
    }

    $children = @(Get-ChildItem -LiteralPath $Path -Force -ErrorAction SilentlyContinue)
    if ($children.Count -eq 0) {
        Write-Step "Removing empty cache directory: $Path"
        Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    }
}

function Clear-NapCatUpdateCaches {
    param(
        [string]$Reason,
        [string[]]$SpecificPaths = @(),
        [switch]$All
    )

    if ($DryRun) {
        Write-Step "DryRun enabled; would clean NapCat update caches. reason=$Reason"
        return
    }

    $targets = [System.Collections.Generic.List[string]]::new()
    foreach ($path in @($SpecificPaths)) {
        if (-not [string]::IsNullOrWhiteSpace($path)) {
            [void]$targets.Add($path)
        }
    }

    if ($All) {
        foreach ($root in @($DownloadRoot)) {
            if (Test-Path -LiteralPath $root) {
                foreach ($child in @(Get-ChildItem -LiteralPath $root -Force -ErrorAction SilentlyContinue)) {
                    [void]$targets.Add($child.FullName)
                }
            }
        }
        if (Test-Path -LiteralPath $OneKeyRoot) {
            if (Test-Path -LiteralPath $ArchiveRoot) {
                foreach ($child in @(Get-ChildItem -LiteralPath $ArchiveRoot -Force -ErrorAction SilentlyContinue)) {
                    [void]$targets.Add($child.FullName)
                }
            }
        }
        else {
            Write-Step "Keeping NapCat archives because current onekey is missing; archives may be needed for manual recovery."
        }
    }

    if ($targets.Count -eq 0) {
        Remove-EmptyDirectoryIfExists -Path $DownloadRoot
        Remove-EmptyDirectoryIfExists -Path $ArchiveRoot
        return
    }

    $seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($target in @($targets)) {
        if (-not $seen.Add([System.IO.Path]::GetFullPath($target))) {
            continue
        }
        Remove-PathIfExists -Path $target -Description "NapCat update cache ($Reason)"
    }

    Remove-EmptyDirectoryIfExists -Path $DownloadRoot
    Remove-EmptyDirectoryIfExists -Path $ArchiveRoot
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

    if ($AssumeYes) {
        Write-Step "AssumeYes enabled; auto-confirming NapCat update."
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
    $allProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $targetIds = [System.Collections.Generic.HashSet[int]]::new()
    $roots = @($allProcesses | Where-Object {
        (Test-NapCatProcessRoot -ProcessInfo $_) -or
        (Test-NapCatQQRoot -ProcessInfo $_)
    })

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

function Test-NapCatQQRoot {
    param([object]$ProcessInfo)

    $name = [string]$ProcessInfo.Name
    $commandLine = [string]$ProcessInfo.CommandLine
    return (
        $name -match '(?i)^QQ\.exe$' -and
        $commandLine -match '(?i)\s--enable-logging(\s|$)' -and
        $commandLine -notmatch '(?i)\s--type='
    )
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

function Get-OneKeyConfigRoot {
    param([string]$Root)

    $currentConfig = Join-Path $Root "napcat\config"
    if (Test-Path $currentConfig) {
        return $currentConfig
    }

    $legacyConfig = Get-ChildItem -Path $Root -Directory -Filter "NapCat.*.Shell" -ErrorAction SilentlyContinue |
        ForEach-Object {
            Get-ChildItem -Path (Join-Path $_.FullName "versions") -Directory -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending |
                Select-Object -First 1
        } |
        ForEach-Object {
            $candidate = Join-Path $_.FullName "resources\app\napcat\config"
            if (Test-Path $candidate) {
                $candidate
            }
        } |
        Select-Object -First 1

    if ($legacyConfig) {
        return $legacyConfig
    }

    $bootmainConfig = Join-Path $Root "bootmain\config"
    if (Test-Path $bootmainConfig) {
        return $bootmainConfig
    }

    return ""
}

function Test-OneKeyHasAccountConfigs {
    param([string]$Root)

    $configRoot = Get-OneKeyConfigRoot -Root $Root
    if (-not $configRoot) {
        return $false
    }

    foreach ($pattern in @("napcat_*.json", "napcat_protocol_*.json", "onebot11_*.json")) {
        $files = @(Get-ChildItem -Path $configRoot -File -Filter $pattern -ErrorAction SilentlyContinue)
        if ($files.Count -gt 0) {
            return $true
        }
    }

    return $false
}

function Get-NapCatConfigMigrationRoot {
    param([string[]]$PreferredRoots)

    foreach ($root in @($PreferredRoots)) {
        if ($root -and (Test-Path $root) -and (Test-OneKeyHasAccountConfigs -Root $root)) {
            return $root
        }
    }

    $archives = @(Get-ChildItem -Path $ArchiveRoot -Directory -Filter "onekey-*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending)
    foreach ($archive in $archives) {
        if (Test-OneKeyHasAccountConfigs -Root $archive.FullName) {
            return $archive.FullName
        }
    }

    return ""
}

function Copy-NapCatAccountConfigs {
    param(
        [string]$FromRoot,
        [string]$ToRoot
    )

    $sourceConfig = Get-OneKeyConfigRoot -Root $FromRoot
    $targetConfig = Get-OneKeyConfigRoot -Root $ToRoot
    if (-not $sourceConfig) {
        Write-Step "No previous NapCat account config directory found; skipping config migration."
        return
    }
    if (-not $targetConfig) {
        $targetConfig = Join-Path $ToRoot "napcat\config"
        New-Item -ItemType Directory -Path $targetConfig -Force | Out-Null
    }

    $patterns = @("napcat_*.json", "napcat_protocol_*.json", "onebot11_*.json")
    $copied = 0
    foreach ($pattern in $patterns) {
        $files = @(Get-ChildItem -Path $sourceConfig -File -Filter $pattern -ErrorAction SilentlyContinue)
        foreach ($file in $files) {
            Copy-Item -Path $file.FullName -Destination (Join-Path $targetConfig $file.Name) -Force
            $copied += 1
        }
    }
    Write-Step "Migrated NapCat account config files: $copied"
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
        "-NapCatRoot", (Join-Path $TargetRoot "napcat"),
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

Write-Step "NapCat update started."
Write-Step "Project: $ProjectRoot"
Write-Step "Log: $logFile"
if ($DryRun) {
    Write-Step "DryRun enabled; no download or package replacement will be executed."
}

$api = "https://api.github.com/repos/NapNeko/NapCatQQ/releases/latest"
if ($DryRun) {
    Write-Step "Would query latest release: $api"
}

$headers = @{ "User-Agent" = "qqbot-update-script" }
$release = Invoke-RestMethod -Uri $api -Headers $headers -TimeoutSec 30
$asset = @($release.assets | Where-Object {
    $_.name -match '(?i)NapCat.*Shell.*Windows.*OneKey.*\.zip$' -or
    $_.name -match '(?i)NapCat.*Windows.*OneKey.*\.zip$' -or
    $_.name -match '(?i)NapCat.*Shell.*\.zip$'
} | Select-Object -First 1)

if (-not $asset) {
    $assetNames = ($release.assets | ForEach-Object { $_.name }) -join ", "
    throw "No matching NapCat Windows Shell zip asset found in latest release. Assets: $assetNames"
}

$version = if ($release.tag_name) { $release.tag_name } else { "latest" }
$zipPath = Join-Path $DownloadRoot ("NapCat-{0}-{1}.zip" -f $version, $timestamp)
$extractRoot = Join-Path $DownloadRoot ("extract-$timestamp")
$newOneKeyRoot = Join-Path $NapCatRoot ("onekey.new-$timestamp")
$archivePath = Join-Path $ArchiveRoot ("onekey-$timestamp")
$installedRelease = Get-InstalledNapCatRelease
$installedVersion = if ($installedRelease.Tag) { $installedRelease.Tag } else { "(unknown)" }

Write-Step "Latest release: $version"
Write-Step "Installed release: $installedVersion (source: $($installedRelease.Source))"
if (
    $installedRelease.Tag -and
    (Get-NormalizedReleaseTag -Tag $installedRelease.Tag) -eq (Get-NormalizedReleaseTag -Tag $version)
) {
    Write-Step "NapCat is already at latest release $version; skipping download and package replacement."
    Ensure-NapCatBuiltinPlugin -TargetRoot $OneKeyRoot
    Sync-NapCatAccountPolicies
    Clear-NapCatUpdateCaches -Reason "already latest" -All
    exit 0
}

if (-not (Confirm-NapCatUpdate `
    -InstalledVersion $installedVersion `
    -TargetVersion $version `
    -Asset $asset `
    -ZipPath $zipPath `
    -ExtractRoot $extractRoot `
    -NewOneKeyRoot $newOneKeyRoot `
    -ArchivePath $archivePath)) {
    Clear-NapCatUpdateCaches -Reason "skipped before download" -All
    exit 0
}

if ($DryRun) {
    $running = @(Get-NapCatProcesses)
    Write-Step "Would download asset: $($asset.name)"
    Write-Step "Would extract the new package into: $newOneKeyRoot"
    if ($running.Count -gt 0) {
        if ($NoStopProcesses) {
            Write-Step "Would require these processes to be closed manually before activation: $(Format-ProcessSummary $running)"
        }
        else {
            Write-Step "Would stop running NapCat/QQ processes before activation: $(Format-ProcessSummary $running)"
        }
    }
    Write-Step "Would archive current napcat\onekey to: $archivePath"
    Write-Step "Would activate the prepared package as napcat\onekey."
    Write-Step "Would ensure NapCat builtin plugin after activation."
    Write-Step "Would write NapCat release marker: $NapCatReleaseMarker"
    Write-Step "NapCat update dry run finished."
    exit 0
}

$updateSucceeded = $false
try {
    Write-Step "Downloading: $($asset.name)"
    New-Item -ItemType Directory -Path $DownloadRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $ArchiveRoot -Force | Out-Null
    Invoke-WebRequest -Uri $asset.browser_download_url -Headers $headers -OutFile $zipPath -TimeoutSec 300

    Write-Step "Extracting: $zipPath"
    New-Item -ItemType Directory -Path $extractRoot -Force | Out-Null
    Expand-Archive -Path $zipPath -DestinationPath $extractRoot -Force

    $sourceRoot = $extractRoot
    $children = @(Get-ChildItem -Path $extractRoot -Force)
    if ($children.Count -eq 1 -and $children[0].PSIsContainer) {
        $sourceRoot = $children[0].FullName
    }

    New-Item -ItemType Directory -Path $newOneKeyRoot -Force | Out-Null
    Move-Item -Path (Join-Path $sourceRoot "*") -Destination $newOneKeyRoot -Force

    $running = @(Get-NapCatProcesses)
    if ($running.Count -gt 0) {
        if ($NoStopProcesses) {
            throw "NapCat/QQ is running. The new package is ready at $newOneKeyRoot. Close these processes first or rerun without -NoStopProcesses: $(Format-ProcessSummary $running)"
        }
        Write-Step "Prepared new package; stopping running NapCat/QQ processes before activation: $(Format-ProcessSummary $running)"
        Stop-NapCatProcesses $running
    }

    $hadExistingOneKey = Test-Path $OneKeyRoot
    if ($hadExistingOneKey) {
        Write-Step "Archiving current onekey: $archivePath"
        Wait-DirectoryCanMove -Path $OneKeyRoot -TimeoutSeconds 30
        try {
            Move-Item -Path $OneKeyRoot -Destination $archivePath
        }
        catch {
            $remaining = @(Get-NapCatProcesses)
            throw "Failed to archive current onekey. Remaining related processes: $(Format-ProcessSummary $remaining). Error: $($_.Exception.Message)"
        }
    }

    Write-Step "Activating new onekey package."
    Move-Item -Path $newOneKeyRoot -Destination $OneKeyRoot
    $configSourceRoot = ""
    if ($hadExistingOneKey) {
        $configSourceRoot = Get-NapCatConfigMigrationRoot -PreferredRoots @($archivePath)
    }
    if ($configSourceRoot) {
        if ($configSourceRoot -ne $archivePath) {
            Write-Step "Using fallback NapCat config source: $configSourceRoot"
        }
        Copy-NapCatAccountConfigs -FromRoot $configSourceRoot -ToRoot $OneKeyRoot
    }
    else {
        Write-Step "No previous NapCat account config directory found; skipping config migration."
    }
    Ensure-NapCatBuiltinPlugin -TargetRoot $OneKeyRoot
    Sync-NapCatAccountPolicies
    Write-NapCatReleaseMarker -Tag $version -Asset $asset
    $updateSucceeded = $true
}
finally {
    if ($updateSucceeded) {
        Clear-NapCatUpdateCaches -Reason "successful update" -SpecificPaths @($zipPath, $extractRoot, $archivePath)
    }
    else {
        Clear-NapCatUpdateCaches -Reason "failed or interrupted update" -SpecificPaths @($zipPath, $extractRoot, $newOneKeyRoot)
    }
}

Write-Step "NapCat update finished. Start bots with the qqbot root scripts\start-all.bat."
