<#
NapCat 启动与更新共用的本地运行包读取入口。
QQ 仅从项目选版清单解析，不使用系统注册表或桌面 QQ 的热更新选择。
#>

function Get-NapCatBundleVersion {
    <# 读取发布包实际版本；解析失败时不把安装标记当作版本证据。 #>
    param([string]$Root)

    $bundle = Join-Path $Root "napcat.mjs"
    if (-not (Test-Path -LiteralPath $bundle -PathType Leaf)) { return "" }
    $source = Get-Content -LiteralPath $bundle -Raw -Encoding UTF8
    $match = [regex]::Match($source, '["''](?<version>\d+\.\d+\.\d+)["'']\s*\|\|\s*["'']1\.0\.0-dev["'']')
    if (-not $match.Success) { throw "Cannot read NapCat version from $bundle." }
    return $match.Groups["version"].Value
}

function Get-QQRuntimeInfo {
    <# 从解包后的 QQ 自身配置读取完整构建；不启动 QQ 或修改其文件。 #>
    param([string]$Root)

    $exe = Join-Path $Root "QQ.exe"
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "QQ executable is missing: $exe" }
    $selectionPath = Join-Path $Root "versions\config.json"
    if (-not (Test-Path -LiteralPath $selectionPath -PathType Leaf)) {
        throw "QQ version selection is missing: $selectionPath"
    }
    $selection = Get-Content -LiteralPath $selectionPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $version = [string]$selection.curVersion
    if ($version -notmatch '^\d+\.\d+\.\d+-\d+$') { throw "Invalid QQ curVersion in $selectionPath." }
    $versionRoot = Join-Path $Root "versions\$version"
    $packagePath = Join-Path $versionRoot "resources\app\package.json"
    $package = Get-Content -LiteralPath $packagePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $arch = [string]$package.eleArch
    if ([string]$package.version -ne $version -or $arch -notin @("x64", "arm64", "ia32")) {
        throw "QQ package metadata does not match its selected build: $packagePath"
    }
    $nativeDll = Join-Path $versionRoot "QQNT.dll"
    if (-not (Test-Path -LiteralPath $nativeDll -PathType Leaf)) { throw "QQ native runtime is missing: $nativeDll" }
    return [pscustomobject]@{
        Root = $Root; Exe = $exe; Version = $version; Architecture = $arch
        Key = "$version-$arch"; SelectionPath = $selectionPath; NativeDll = $nativeDll
    }
}

function Get-ManagedQQRuntime {
    <# 仅接受本地选版清单；首次未部署或版本漂移时停止启动。 #>
    param([string]$OneKeyRoot)

    $manifestPath = Join-Path $OneKeyRoot "qq-runtime.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "Independent QQ is not prepared. Run napcat/scripts/update.ps1 -AssumeYes before starting bots."
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $key = [string]$manifest.qq_version
    if ($manifest.schema_version -ne 1 -or $key -notmatch '^\d+\.\d+\.\d+-\d+-x64$') {
        throw "Invalid independent QQ selection: $manifestPath"
    }
    $runtime = Get-QQRuntimeInfo -Root (Join-Path $OneKeyRoot "qq\$key")
    if ($runtime.Key -ne $key) {
        throw "Independent QQ changed from $key to $($runtime.Key). Run the paired updater; system QQ will not be used."
    }
    return $runtime
}

function Save-QQRuntimeSelection {
    <# 只在所属进程停止后调用；原子替换清单，避免启动器读到半份 JSON。 #>
    param([string]$OneKeyRoot, [System.Collections.IDictionary]$Selection)

    $path = Join-Path $OneKeyRoot "qq-runtime.json"
    $temporary = Join-Path $OneKeyRoot ("qq-runtime-{0}.tmp" -f [guid]::NewGuid().ToString("N"))
    [System.IO.File]::WriteAllText($temporary, ($Selection | ConvertTo-Json -Depth 5), [System.Text.UTF8Encoding]::new($false))
    if (Test-Path -LiteralPath $path) {
        [System.IO.File]::Replace($temporary, $path, [System.Management.Automation.Language.NullString]::Value)
    }
    else {
        [System.IO.File]::Move($temporary, $path)
    }
}
