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

$WorkspaceRoot = Split-Path -Parent $PSScriptRoot
$NapCatRoot = Join-Path $WorkspaceRoot "napcat\onekey\NapCat.44498.Shell"
$NapCatExe = Join-Path $NapCatRoot "NapCatWinBootMain.exe"

if (-not (Test-Path $NapCatExe)) {
    throw "NapCat executable not found: $NapCatExe"
}

Set-Location $NapCatRoot

if ($NoQuickLogin -or -not $Accounts -or $Accounts.Count -eq 0) {
    & $NapCatExe
    exit $LASTEXITCODE
}

foreach ($account in $Accounts) {
    if (-not ($account -match '^\d+$')) {
        throw "Invalid NapCat account: $account"
    }

    Write-Host "Starting NapCat quick login account: $account"
    Start-Process -FilePath $NapCatExe -ArgumentList @($account) -WorkingDirectory $NapCatRoot | Out-Null
    Start-Sleep -Seconds 2
}
