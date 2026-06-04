param(
    [string[]]$Accounts = @("1443944862", "2629227874"),
    [switch]$NoQuickLogin
)

$ErrorActionPreference = "Stop"
try {
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
}
catch {
}
$chcp = Join-Path $env:WINDIR "System32\chcp.com"
if (Test-Path $chcp) {
    & $chcp 65001 | Out-Null
}

$WorkspaceRoot = Split-Path -Parent $PSScriptRoot
$NapCatRoot = Join-Path $WorkspaceRoot "napcat\onekey\NapCat.44498.Shell"
$AccountScript = Join-Path $PSScriptRoot "start-napcat-account.ps1"

if (-not (Test-Path $AccountScript)) {
    throw "NapCat account startup script not found: $AccountScript"
}

function Start-NapCatProcess {
    param(
        [string]$Account,
        [switch]$NoQuickLogin
    )

    $label = if ($NoQuickLogin -or -not $Account) { "default" } else { $Account }
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $AccountScript
    )
    if ($NoQuickLogin) {
        $arguments += "-NoQuickLogin"
    }
    elseif ($Account) {
        $arguments += "-Account"
        $arguments += $Account
    }

    Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList $arguments `
        -WorkingDirectory $NapCatRoot `
        | Out-Null
}

if ($NoQuickLogin -or -not $Accounts -or $Accounts.Count -eq 0) {
    Start-NapCatProcess -Account "" -NoQuickLogin
    exit 0
}

foreach ($account in $Accounts) {
    if (-not ($account -match '^\d+$')) {
        throw "Invalid NapCat account: $account"
    }

    Write-Host "Starting NapCat quick login account: $account"
    Start-NapCatProcess -Account $account
    Start-Sleep -Seconds 2
}
