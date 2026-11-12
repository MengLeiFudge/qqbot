# 独立 QQ 的目标选择、官方安装包校验与准备；仅由 update.ps1 点源加载。

function Get-SupportedQQVersions {
    <# Windows x64 支持构建按完整版本降序排列，顺序用于可用候选选择。 #>
    param([object]$Matrix)

    $versions = @($Matrix.PSObject.Properties | Where-Object {
        $_.Name -match '^9\.\d+\.\d+-\d+-x64$' -and $_.Value.send -and $_.Value.recv
    } | Sort-Object { [version]($_.Name -replace '-x64$', '' -replace '-', '.') } -Descending)
    if ($versions.Count -eq 0) { throw "The target NapCat release has no Windows x64 QQ builds in its support table." }
    return @($versions | ForEach-Object { [string]$_.Name })
}

function Get-VerifiedReleaseArchive {
    param([object]$Release, [string]$AssetName)

    $asset = @($Release.assets | Where-Object { $_.name -eq $AssetName })
    if ($asset.Count -ne 1 -or [string]$asset[0].digest -notmatch '^sha256:(?<hash>[a-fA-F0-9]{64})$') {
        throw "Release $($Release.tag_name) has no unique $AssetName asset with a SHA-256 digest."
    }
    $expectedHash = $Matches.hash.ToLowerInvariant()
    $asset = $asset[0]
    $path = Join-Path $DownloadRoot ("NapCat-{0}-{1}" -f $Release.tag_name, $AssetName)
    New-Item -ItemType Directory -Path $DownloadRoot -Force | Out-Null
    if (Test-Path -LiteralPath $path) {
        if ((Get-Item -LiteralPath $path).Length -ne [long]$asset.size -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) {
            Move-NapCatUpdateArtifact -Path $path
        }
    }
    if (-not (Test-Path -LiteralPath $path)) {
        Write-Step "Downloading verified release asset: $AssetName"
        Invoke-NapCatWebRequest -Uri $asset.browser_download_url -OutFile $path -TimeoutSeconds 300
    }
    if ((Get-Item -LiteralPath $path).Length -ne [long]$asset.size -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) {
        Move-NapCatUpdateArtifact -Path $path
        throw "Release asset failed size or SHA-256 verification: $AssetName"
    }
    return $path
}

function Assert-TencentSignature {
    param([string]$Path)

    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($signature.Status -ne 'Valid' -or $null -eq $signature.SignerCertificate -or $signature.SignerCertificate.Subject -notmatch 'O="?Tencent (Technology|Technology \(Shenzhen\))') {
        throw "QQ file does not have a valid Tencent signature: $Path"
    }
}

function Get-QQInstallerVersion {
    param([string]$Path)

    Assert-TencentSignature -Path $Path
    $version = (Get-Item -LiteralPath $Path).VersionInfo.ProductVersion
    if ($version -notmatch '^(?<major>9\.\d+\.\d+)[.-](?<build>\d+)(?:-|$)') {
        throw "Cannot read a complete QQ installer version: $Path"
    }
    return "$($Matches.major)-$($Matches.build)-x64"
}

function Get-QQExtractor {
    param([object]$Release)

    # 解包器来自同一官方 Release；每次从已核验的归档取出，不执行 QQ 安装器。
    $archive = Get-VerifiedReleaseArchive -Release $Release -AssetName 'NapCat.Shell.Windows.OneKey.zip'
    $root = Join-Path $DownloadRoot ("qq-extractor-$timestamp")
    Expand-Archive -LiteralPath $archive -DestinationPath $root -Force
    $executables = @(Get-ChildItem -LiteralPath $root -Recurse -File -Filter '7z.exe')
    if ($executables.Count -ne 1 -or -not (Test-Path -LiteralPath (Join-Path $executables[0].DirectoryName '7z.dll'))) {
        throw "The official OneKey archive has no unique complete 7-Zip extractor: $root"
    }
    return $executables[0].FullName
}

function Get-QQInstaller {
    <# 只下载已知腾讯地址；返回签名通过的实际构建，兼容性由候选选择负责。 #>
    param([uri]$Uri)

    if ($Uri.Scheme -ne 'https' -or $Uri.DnsSafeHost -ne 'qqdl.gtimg.cn' -or $Uri.Query -or $Uri.AbsolutePath -notmatch '^/qqfile/QQNT(?:V2)?/[0-9.]+/release/[a-f0-9]+/QQ_[a-zA-Z0-9_.-]+_x64_[0-9]+\.exe$') {
        throw 'The QQ download source is not a recognized Tencent Windows x64 installer URL.'
    }
    New-Item -ItemType Directory -Path $DownloadRoot -Force | Out-Null
    $path = Join-Path $DownloadRoot ([System.IO.Path]::GetFileName($Uri.AbsolutePath))
    if (Test-Path -LiteralPath $path) {
        try { return [pscustomobject]@{ Key = (Get-QQInstallerVersion -Path $path); Path = $path } }
        catch {
            Write-Step "Cached QQ installer is invalid: $($_.Exception.Message)"
            Move-NapCatUpdateArtifact -Path $path
        }
    }
    $downloadUri = $Uri
    if ($Uri.AbsolutePath -like '/qqfile/QQNTV2/*') {
        # 官网公开的无登录签名接口；短期签名 URL 只留在内存。
        $signed = Invoke-NapCatWebRequest -Uri 'https://im.qq.com/http2rpc/gotrpc/noauth/trpc.qqntv2.urlsign.UrlSign/GetSign' -JsonBody @{ url = $Uri.AbsoluteUri } -RequestHeaders @{ 'x-oidb' = '{"uint32_command":"0x9b8e","uint32_service_type":1}' }
        $downloadUri = [uri][string]$signed.data.url
        if ($signed.retcode -ne 0 -or $downloadUri.Scheme -ne 'https' -or $downloadUri.DnsSafeHost -ne $Uri.DnsSafeHost -or $downloadUri.AbsolutePath -ne $Uri.AbsolutePath) {
            throw 'The official QQ download signing request did not return the expected Tencent download URL.'
        }
    }
    Write-Step "Downloading official QQ installer: $([System.IO.Path]::GetFileName($path))"
    $partial = $path + '.partial'
    try {
        Invoke-NapCatWebRequest -Uri $downloadUri -OutFile $partial -TimeoutSeconds 300
        $key = Get-QQInstallerVersion -Path $partial
        Move-Item -LiteralPath $partial -Destination $path
        return [pscustomobject]@{ Key = $key; Path = $path }
    }
    finally { Move-NapCatUpdateArtifact -Path $partial }
}

function Prepare-ManagedQQ {
    <# 复用已验证运行包，或将指定官方安装包解到本次独立暂存目录；不停止机器人。 #>
    param([string]$TargetKey, [object]$Release, [string]$InstallerPath)

    $destination = Join-Path $OneKeyRoot "qq\$TargetKey"
    if (Test-Path -LiteralPath $destination) {
        try {
            $existing = Get-QQRuntimeInfo -Root $destination
            if ($existing.Key -eq $TargetKey) {
                Assert-TencentSignature -Path $existing.Exe
                Assert-TencentSignature -Path $existing.NativeDll
                return [pscustomobject]@{ StagingPath = ''; InstallerHash = '' }
            }
        }
        catch { Write-Step "Existing independent QQ needs replacement: $($_.Exception.Message)" }
    }
    if (-not $InstallerPath) { throw "No installer is available to prepare QQ $TargetKey." }
    if ((Get-QQInstallerVersion -Path $InstallerPath) -ne $TargetKey) { throw "QQ installer does not match selected build $TargetKey." }
    $installer = $InstallerPath
    $extractor = Get-QQExtractor -Release $Release
    $root = Join-Path $DownloadRoot ("qq-extract-{0}-{1}-{2}" -f $timestamp, $TargetKey, [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $root -Force | Out-Null
    $stdout = $logFile + '.' + (Split-Path -Leaf $root) + '.out.log'
    $stderr = $logFile + '.' + (Split-Path -Leaf $root) + '.err.log'
    $arguments = @('x', '-y', ('-o"{0}"' -f $root), ('"{0}"' -f $installer), 'Files\*')
    $process = Start-Process -FilePath $extractor -ArgumentList $arguments -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    [void]$process.Handle
    try {
        if (-not $process.WaitForExit(180000)) {
            $process.Kill()
            [void]$process.WaitForExit(5000)
            throw "QQ extraction exceeded 180 seconds. Inspect $stdout and $stderr."
        }
        if ($process.ExitCode -ne 0) { throw "QQ extraction failed with exit code $($process.ExitCode). Inspect $stdout and $stderr." }
    }
    finally { $process.Dispose() }
    $runtime = Get-QQRuntimeInfo -Root (Join-Path $root 'Files')
    if ($runtime.Key -ne $TargetKey) { throw "Extracted QQ $($runtime.Key) does not match selected build $TargetKey." }
    Assert-TencentSignature -Path $runtime.Exe
    Assert-TencentSignature -Path $runtime.NativeDll
    $hash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Step "QQ $TargetKey prepared; Tencent signatures and package version verified; SHA-256=$hash."
    return [pscustomobject]@{ StagingPath = $runtime.Root; InstallerHash = $hash }
}

function Prepare-LatestAvailableQQ {
    <# 从明确来源收集候选，按受支持的完整版本降序准备；候选不可用时继续下一项。 #>
    param([object]$Matrix, [object]$Release)

    $supported = @(Get-SupportedQQVersions -Matrix $Matrix)
    $candidates = [System.Collections.Generic.List[object]]::new()
    $qqRoot = Join-Path $OneKeyRoot 'qq'
    if (Test-Path -LiteralPath $qqRoot) {
        foreach ($directory in @(Get-ChildItem -LiteralPath $qqRoot -Directory)) {
            if ($directory.Name -notin $supported) { continue }
            try {
                $runtime = Get-QQRuntimeInfo -Root $directory.FullName
                if ($runtime.Key -eq $directory.Name) {
                    $candidates.Add([pscustomobject]@{ Key = $runtime.Key; InstallerPath = '' })
                }
            }
            catch { Write-Step "Independent QQ candidate is unavailable: $($_.Exception.Message)" }
        }
    }
    if (Test-Path -LiteralPath $DownloadRoot) {
        foreach ($file in @(Get-ChildItem -LiteralPath $DownloadRoot -File -Filter 'QQ*.exe')) {
            $version = $file.VersionInfo.ProductVersion
            if ($version -match '^(?<major>9\.\d+\.\d+)[.-](?<build>\d+)(?:-|$)') {
                $key = "$($Matches.major)-$($Matches.build)-x64"
                if ($key -in $supported) {
                    $candidates.Add([pscustomobject]@{ Key = $key; InstallerPath = $file.FullName })
                }
            }
        }
    }

    # 官网和 OneKey 是有限的明确来源；不从支持表构建号猜测历史下载地址。
    $uris = [System.Collections.Generic.HashSet[string]]::new()
    try {
        $metadata = Invoke-NapCatWebRequest -Uri 'https://qq-web.cdn-go.cn/im.qq.com_new/latest/rainbow/pcConfig.json'
        if (-not $metadata.Windows.ntDownloadX64Url) { throw 'The QQ website returned no Windows x64 download URL.' }
        [void]$uris.Add([string]$metadata.Windows.ntDownloadX64Url)
    }
    catch { Write-Step "QQ website source is unavailable; continuing with other candidates: $($_.Exception.Message)" }
    try {
        $extractor = Get-QQExtractor -Release $Release
        $installer = Join-Path (Split-Path -Parent $extractor) 'NapCatInstaller.exe'
        $bytes = [System.IO.File]::ReadAllBytes($installer)
        $text = [System.Text.Encoding]::ASCII.GetString($bytes) + [System.Text.Encoding]::Unicode.GetString($bytes)
        $links = [regex]::Matches($text, 'https://qqdl\.gtimg\.cn/qqfile/QQNT(?:V2)?/[0-9.]+/release/[a-f0-9]+/QQ_[a-zA-Z0-9_.-]+_x64_[0-9]+\.exe')
        if ($links.Count -eq 0) { throw 'The official OneKey installer provided no recognized Tencent QQ URL.' }
        foreach ($link in $links) { [void]$uris.Add($link.Value) }
    }
    catch { Write-Step "OneKey QQ source is unavailable; continuing with other candidates: $($_.Exception.Message)" }
    foreach ($address in $uris) {
        try {
            $uri = [uri]$address
            $series = [regex]::Match($uri.AbsolutePath, '^/qqfile/QQNT(?:V2)?/(?<version>9\.\d+\.\d+)/')
            if ($series.Success -and @($supported | Where-Object { $_.StartsWith($series.Groups['version'].Value + '-') }).Count -eq 0) {
                Write-Step "Skipping QQ source outside supported version series: $($series.Groups['version'].Value)."
                continue
            }
            $file = Get-QQInstaller -Uri $uri
            if ($file.Key -notin $supported) {
                Write-Step "Skipping unsupported QQ $($file.Key); checking other available candidates."
                continue
            }
            $candidates.Add([pscustomobject]@{ Key = $file.Key; InstallerPath = $file.Path })
        }
        catch { Write-Step "QQ download candidate is unavailable; continuing: $($_.Exception.Message)" }
    }

    foreach ($key in $supported) {
        $paths = @($candidates | Where-Object { $_.Key -eq $key } | Select-Object -ExpandProperty InstallerPath | Sort-Object -Unique)
        foreach ($path in $paths) {
            try {
                $prepared = Prepare-ManagedQQ -TargetKey $key -Release $Release -InstallerPath $path
                Write-Step "Selected newest available supported QQ: $key."
                return [pscustomobject]@{ Key = $key; StagingPath = $prepared.StagingPath; InstallerHash = $prepared.InstallerHash }
            }
            catch { Write-Step "QQ $key candidate could not be prepared; trying the next candidate: $($_.Exception.Message)" }
        }
    }
    throw 'No supported Windows x64 QQ candidate could be prepared. Inspect the source errors above; current processes were left unchanged.'
}
