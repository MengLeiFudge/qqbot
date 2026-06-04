param(
    [switch]$DryRun,
    [switch]$NoStopProcesses
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
$NapCatRoot = Join-Path $WorkspaceRoot "napcat"
$OneKeyRoot = Join-Path $NapCatRoot "onekey"
$DataRoot = Join-Path $WorkspaceRoot "data\napcat"
$DownloadRoot = Join-Path $DataRoot "downloads"
$ArchiveRoot = Join-Path $DataRoot "archives"
$LogRoot = Join-Path $DataRoot "logs\updates"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logFile = Join-Path $LogRoot "update-napcat-$timestamp.log"

New-Item -ItemType Directory -Path $NapCatRoot -Force | Out-Null
New-Item -ItemType Directory -Path $DownloadRoot -Force | Out-Null
New-Item -ItemType Directory -Path $ArchiveRoot -Force | Out-Null
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null

function Write-Step {
    param([string]$Message)

    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

function Get-NapCatProcesses {
    $escapedRoot = [regex]::Escape($WorkspaceRoot)
    @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -and
        ($_.CommandLine -match 'NapCatWinBootMain|NapCat\.Shell|QQ\.exe') -and
        ($_.CommandLine -match $escapedRoot)
    })
}

function Format-ProcessSummary {
    param([array]$Processes)

    if (-not $Processes -or $Processes.Count -eq 0) {
        return "(none)"
    }
    return (($Processes | ForEach-Object { "$($_.ProcessId): $($_.Name)" }) -join "; ")
}

function Stop-NapCatProcesses {
    param([array]$Processes)

    foreach ($processInfo in $Processes) {
        Write-Step "Stopping process $($processInfo.ProcessId): $($processInfo.Name)"
        Stop-Process -Id $processInfo.ProcessId -Force -ErrorAction SilentlyContinue
    }

    Start-Sleep -Seconds 2
    $remaining = @(Get-NapCatProcesses)
    if ($remaining.Count -gt 0) {
        throw "Some NapCat/QQ processes are still running: $(Format-ProcessSummary $remaining)"
    }
}

Write-Step "NapCat update started."
Write-Step "Workspace: $WorkspaceRoot"
Write-Step "Log: $logFile"
if ($DryRun) {
    Write-Step "DryRun enabled; no download or package replacement will be executed."
}

$api = "https://api.github.com/repos/NapNeko/NapCatQQ/releases/latest"
if ($DryRun) {
    $running = @(Get-NapCatProcesses)
    if ($running.Count -gt 0) {
        if ($NoStopProcesses) {
            Write-Step "Would require these processes to be closed manually: $(Format-ProcessSummary $running)"
        }
        else {
            Write-Step "Would stop running NapCat/QQ processes: $(Format-ProcessSummary $running)"
        }
    }
    Write-Step "Would query latest release: $api"
    Write-Step "Would download asset matching NapCat Shell Windows OneKey zip."
    Write-Step "Would archive current napcat\onekey to data\napcat\archives\onekey-$timestamp."
    Write-Step "Would extract the new package into napcat\onekey."
    Write-Step "NapCat update dry run finished."
    exit 0
}

$running = @(Get-NapCatProcesses)
if ($running.Count -gt 0) {
    if ($NoStopProcesses) {
        throw "NapCat/QQ is running. Close these processes first or rerun without -NoStopProcesses: $(Format-ProcessSummary $running)"
    }
    Write-Step "Running NapCat/QQ processes detected: $(Format-ProcessSummary $running)"
    Stop-NapCatProcesses $running
}

$headers = @{ "User-Agent" = "qqbot-update-script" }
$release = Invoke-RestMethod -Uri $api -Headers $headers
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

Write-Step "Latest release: $version"
Write-Step "Downloading: $($asset.name)"
Invoke-WebRequest -Uri $asset.browser_download_url -Headers $headers -OutFile $zipPath

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

if (Test-Path $OneKeyRoot) {
    Write-Step "Archiving current onekey: $archivePath"
    Move-Item -Path $OneKeyRoot -Destination $archivePath
}

Write-Step "Activating new onekey package."
Move-Item -Path $newOneKeyRoot -Destination $OneKeyRoot
Remove-Item -Path $extractRoot -Recurse -Force -ErrorAction SilentlyContinue

Write-Step "NapCat update finished. Start bots with scripts\start-all.bat."
