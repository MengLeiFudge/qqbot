param(
    [string]$NapCatRoot = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $NapCatRoot) {
    $NapCatRoot = Join-Path $ProjectRoot "onekey\napcat"
}

$pluginId = "napcat-plugin-qqbot-social"
$sourceRoot = Join-Path $ProjectRoot "plugins\$pluginId"
$pluginRoot = Join-Path $NapCatRoot "plugins\$pluginId"
$statusPath = Join-Path $NapCatRoot "config\plugins.json"
$manifestPath = Join-Path $ProjectRoot "accounts.json"
$encoding = New-Object System.Text.UTF8Encoding -ArgumentList $false

if (-not (Test-Path -LiteralPath $NapCatRoot -PathType Container)) {
    throw "NapCat root not found: $NapCatRoot"
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($null -eq $manifest.accounts -or $manifest.accounts -isnot [array]) {
    throw "NapCat account manifest must contain an accounts array: $manifestPath"
}
$accounts = @($manifest.accounts | Where-Object { $null -eq $_.framework } | ForEach-Object { [string]$_.qq })
foreach ($account in $accounts) {
    if ($account -notmatch '^\d+$') {
        throw "Invalid QQ in NapCat account manifest: $manifestPath"
    }
}

$status = [pscustomobject]@{}
if (Test-Path -LiteralPath $statusPath) {
    $status = Get-Content -LiteralPath $statusPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $status -or $status -isnot [pscustomobject]) {
        throw "NapCat plugin status must be a JSON object: $statusPath"
    }
}

New-Item -ItemType Directory -Path $pluginRoot -Force | Out-Null
foreach ($name in @("index.mjs", "package.json")) {
    $source = Join-Path $sourceRoot $name
    $destination = Join-Path $pluginRoot $name
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "QQBot social plugin source not found: $source"
    }
    Copy-Item -LiteralPath $source -Destination $destination -Force
}
# Keep policy local to the installed plugin; the account manifest remains its source of truth.
$accountJson = ConvertTo-Json -InputObject $accounts -Depth 5
[System.IO.File]::WriteAllText((Join-Path $pluginRoot "accounts.json"), $accountJson, $encoding)

$property = $status.PSObject.Properties[$pluginId]
if ($null -eq $property) {
    Add-Member -InputObject $status -NotePropertyName $pluginId -NotePropertyValue $true
}
else {
    $property.Value = $true
}
New-Item -ItemType Directory -Path (Split-Path -Parent $statusPath) -Force | Out-Null
[System.IO.File]::WriteAllText($statusPath, ($status | ConvertTo-Json -Depth 20), $encoding)
Write-Host "[NapCat] QQBot social plugin installed for $($accounts.Count) accounts without a framework: $pluginRoot"
