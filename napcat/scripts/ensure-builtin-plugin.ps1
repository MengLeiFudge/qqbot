param(
    [string]$NapCatRoot = "",
    [string]$LogFile = "",
    [string]$ConsolePrefix = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot

if (-not $NapCatRoot) {
    $NapCatRoot = Join-Path $ProjectRoot "onekey\napcat"
}

$PluginId = "napcat-plugin-builtin"
$PluginZipUrl = "https://github.com/NapNeko/napcat-plugin-index/releases/download/v1.0.0/napcat-plugin-builtin.zip"
$PluginRoot = Join-Path $NapCatRoot "plugins"
$PluginDir = Join-Path $PluginRoot $PluginId
$PluginIndex = Join-Path $PluginDir "index.mjs"
$PluginPackage = Join-Path $PluginDir "package.json"
$PluginStatusConfig = Join-Path $NapCatRoot "config\plugins.json"
$DownloadRoot = Join-Path $ProjectRoot "data\downloads"

function Write-EnsureLog {
    param([string]$Message)

    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    if ($LogFile) {
        try {
            $parent = Split-Path -Parent $LogFile
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
            Add-Content -Path $LogFile -Value $line -Encoding UTF8
        }
        catch {
        }
    }
    try {
        if ($ConsolePrefix) {
            Write-Host "$ConsolePrefix $line"
        }
        else {
            Write-Host $line
        }
    }
    catch {
    }
}

function Test-NapCatBuiltinPluginReady {
    if (-not (Test-Path -LiteralPath $PluginIndex)) {
        return $false
    }
    if (-not (Test-Path -LiteralPath $PluginPackage)) {
        return $false
    }
    try {
        $package = Get-Content -Path $PluginPackage -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([string]$package.name -ne $PluginId) {
            return $false
        }
        $indexText = Get-Content -Path $PluginIndex -Raw -Encoding UTF8
        return ($indexText -match 'prefix:\s*"#napcat"' -and $indexText -match 'plugin_onmessage')
    }
    catch {
        return $false
    }
}

function Test-FileHasUtf8Bom {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }
    $stream = $null
    try {
        $stream = [System.IO.File]::OpenRead($Path)
        if ($stream.Length -lt 3) {
            return $false
        }
        $buffer = New-Object byte[] 3
        [void]$stream.Read($buffer, 0, 3)
        return ($buffer[0] -eq 0xEF -and $buffer[1] -eq 0xBB -and $buffer[2] -eq 0xBF)
    }
    finally {
        if ($null -ne $stream) {
            $stream.Dispose()
        }
    }
}

function Write-Utf8NoBomText {
    param(
        [string]$Path,
        [string]$Text
    )

    $encoding = New-Object System.Text.UTF8Encoding -ArgumentList $false
    [System.IO.File]::WriteAllText($Path, $Text, $encoding)
}

function Ensure-NapCatBuiltinPluginEnabled {
    if ($DryRun) {
        Write-EnsureLog "DryRun enabled; would enable NapCat builtin plugin in: $PluginStatusConfig"
        return
    }

    $status = [pscustomobject]@{}
    if (Test-Path -LiteralPath $PluginStatusConfig) {
        try {
            $rawStatus = Get-Content -Path $PluginStatusConfig -Raw -Encoding UTF8
            if ($rawStatus.Trim()) {
                $loadedStatus = $rawStatus | ConvertFrom-Json
                if ($null -ne $loadedStatus -and -not ($loadedStatus -is [array])) {
                    $status = $loadedStatus
                }
                else {
                    Write-EnsureLog "Invalid NapCat plugin status config shape; recreating: $PluginStatusConfig"
                }
            }
        }
        catch {
            Write-EnsureLog "Invalid NapCat plugin status config; recreating: $PluginStatusConfig"
            $status = [pscustomobject]@{}
        }
    }

    $changed = $false
    $hasUtf8Bom = Test-FileHasUtf8Bom -Path $PluginStatusConfig
    $property = $status.PSObject.Properties[$PluginId]
    if ($null -eq $property) {
        Add-Member -InputObject $status -NotePropertyName $PluginId -NotePropertyValue $true
        $changed = $true
    }
    elseif ($property.Value -ne $true) {
        $property.Value = $true
        $changed = $true
    }

    if ($changed -or $hasUtf8Bom) {
        $parent = Split-Path -Parent $PluginStatusConfig
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        $json = $status | ConvertTo-Json -Depth 20
        Write-Utf8NoBomText -Path $PluginStatusConfig -Text $json
        if ($hasUtf8Bom) {
            Write-EnsureLog "NapCat plugin status config rewritten without UTF-8 BOM: $PluginStatusConfig"
        }
        else {
            Write-EnsureLog "NapCat builtin plugin enabled in: $PluginStatusConfig"
        }
    }
    else {
        Write-EnsureLog "NapCat builtin plugin already enabled in: $PluginStatusConfig"
    }
}

if (-not (Test-Path -LiteralPath $NapCatRoot)) {
    throw "NapCat root not found: $NapCatRoot"
}

if (Test-NapCatBuiltinPluginReady) {
    Ensure-NapCatBuiltinPluginEnabled
    Write-EnsureLog "NapCat builtin plugin already ready: $PluginDir"
    exit 0
}

if ($DryRun) {
    Write-EnsureLog "DryRun enabled; would install NapCat builtin plugin from $PluginZipUrl to $PluginDir"
    Ensure-NapCatBuiltinPluginEnabled
    exit 0
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$zipPath = Join-Path $DownloadRoot ("napcat-plugin-builtin-$timestamp.zip")
$extractRoot = Join-Path $DownloadRoot ("napcat-plugin-builtin-$timestamp")

try {
    New-Item -ItemType Directory -Path $DownloadRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $PluginRoot -Force | Out-Null

    Write-EnsureLog "Downloading NapCat builtin plugin: $PluginZipUrl"
    Invoke-WebRequest -Uri $PluginZipUrl -Headers @{ "User-Agent" = "qqbot-napcat-builtin-plugin" } -OutFile $zipPath -TimeoutSec 180

    Write-EnsureLog "Extracting NapCat builtin plugin to: $PluginDir"
    if (Test-Path -LiteralPath $extractRoot) {
        Remove-Item -LiteralPath $extractRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $extractRoot -Force | Out-Null
    Expand-Archive -Path $zipPath -DestinationPath $extractRoot -Force

    if (Test-Path -LiteralPath $PluginDir) {
        Remove-Item -LiteralPath $PluginDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $PluginDir -Force | Out-Null
    Move-Item -Path (Join-Path $extractRoot "*") -Destination $PluginDir -Force

    if (-not (Test-NapCatBuiltinPluginReady)) {
        throw "Installed NapCat builtin plugin did not pass readiness checks: $PluginDir"
    }

    Ensure-NapCatBuiltinPluginEnabled
    Write-EnsureLog "NapCat builtin plugin installed: $PluginDir"
}
finally {
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $extractRoot) {
        Remove-Item -LiteralPath $extractRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
