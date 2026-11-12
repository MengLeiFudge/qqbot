param(
    [string]$Account = "",
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

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$OneKeyRoot = Join-Path $ProjectRoot "onekey"

. (Join-Path $PSScriptRoot "qq-runtime.ps1")
$NapCatRoot = Join-Path $OneKeyRoot "napcat"
$NapCatExe = Join-Path $NapCatRoot "NapCatWinBootMain.exe"
$injectPath = Join-Path $NapCatRoot "NapCatWinBootHook.dll"
foreach ($path in @($NapCatExe, $injectPath, (Join-Path $NapCatRoot "qqnt.json"), (Join-Path $NapCatRoot "loadNapCat.js"))) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "NapCat runtime file is missing: $path" }
}
if ($Account -and $Account -notmatch '^\d+$') { throw "Invalid NapCat account: $Account" }

$qqRuntime = Get-ManagedQQRuntime -OneKeyRoot $OneKeyRoot
$selection = Get-Content -LiteralPath (Join-Path $OneKeyRoot "qq-runtime.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$napcatVersion = Get-NapCatBundleVersion -Root $NapCatRoot
if ([string]$selection.napcat_version -ne $napcatVersion) {
    throw "Independent QQ was selected for NapCat $($selection.napcat_version), but the runtime is $napcatVersion. Run the paired updater first."
}

# 各账号可同时读取；持有到启动器退出，阻止 QQ 内置热更新原子替换选版文件。
$versionLease = [System.IO.File]::Open($qqRuntime.SelectionPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
try {
    $lockedRuntime = Get-QQRuntimeInfo -Root $qqRuntime.Root
    if ($lockedRuntime.Key -ne $qqRuntime.Key) { throw "QQ version changed before its startup lease was acquired." }
    $env:NAPCAT_PATCH_PACKAGE = Join-Path $NapCatRoot "qqnt.json"
    $env:NAPCAT_LOAD_PATH = Join-Path $NapCatRoot "loadNapCat.js"
    $env:NAPCAT_INJECT_PATH = $injectPath
    $env:NAPCAT_LAUNCHER_PATH = $NapCatExe
    $env:NAPCAT_MAIN_PATH = Join-Path $NapCatRoot "napcat.mjs"
    $bootArguments = @($qqRuntime.Exe, $injectPath)
    if ($NoQuickLogin -or -not $Account) {
        $env:NAPCAT_QUICK_ACCOUNT = $null
    }
    else {
        $env:NAPCAT_QUICK_ACCOUNT = $Account
        $bootArguments += $Account
    }
    Write-Host "[NapCat] Using independent QQ $($qqRuntime.Key): $($qqRuntime.Exe)"
    Push-Location $NapCatRoot
    try {
        # 使用官方引导程序的公开路径参数，不执行会 pause 的桌面 QQ 启动批处理。
        & $NapCatExe @bootArguments
        $exitCode = $LASTEXITCODE
    }
    finally { Pop-Location }
}
finally { $versionLease.Dispose() }
exit $exitCode
