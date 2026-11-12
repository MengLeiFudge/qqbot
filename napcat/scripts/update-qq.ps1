# 独立 QQ 的目标选择、官方安装包校验与准备；仅由 update.ps1 点源加载。

function Get-LatestSupportedQQ {
    param([object]$Matrix)

    $versions = @($Matrix.PSObject.Properties | Where-Object {
        $_.Name -match '^9\.\d+\.\d+-\d+-x64$' -and $_.Value.send -and $_.Value.recv
    } | Sort-Object { [version]($_.Name -replace '-x64$', '' -replace '-', '.') } -Descending)
    if ($versions.Count -eq 0) { throw "The target NapCat release has no Windows x64 QQ builds in its support table." }
    return [string]$versions[0].Name
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
    param([string]$TargetKey)

    # 完整版本由安装包签名和 ProductVersion 确认，不能把 9.9.x 系列号当作完整构建。
    New-Item -ItemType Directory -Path $DownloadRoot -Force | Out-Null
    foreach ($file in @(Get-ChildItem -LiteralPath $DownloadRoot -File -Filter 'QQ*.exe')) {
        $productVersion = $file.VersionInfo.ProductVersion
        if ($productVersion -match '^(?<major>9\.\d+\.\d+)[.-](?<build>\d+)(?:-|$)' -and "$($Matches.major)-$($Matches.build)-x64" -eq $TargetKey) {
            if ((Get-QQInstallerVersion -Path $file.FullName) -eq $TargetKey) { return $file.FullName }
        }
    }

    $metadata = Invoke-NapCatWebRequest -Uri 'https://qq-web.cdn-go.cn/im.qq.com_new/latest/rainbow/pcConfig.json'
    $uri = [uri][string]$metadata.Windows.ntDownloadX64Url
    if ($uri.Scheme -ne 'https' -or $uri.DnsSafeHost -ne 'qqdl.gtimg.cn' -or $uri.Query -or $uri.AbsolutePath -notmatch '^/qqfile/QQNT(?:V2)?/[0-9.]+/release/[a-f0-9]+/QQ_[a-zA-Z0-9_.-]+_x64_[0-9]+\.exe$') {
        throw 'The official QQ website did not provide a recognized Windows x64 installer URL.'
    }
    $path = Join-Path $DownloadRoot ([System.IO.Path]::GetFileName($uri.AbsolutePath))
    if (-not (Test-Path -LiteralPath $path)) {
        # 官网公开的无登录签名接口；短期签名 URL 只留在内存，不写入日志或选版清单。
        $signed = Invoke-NapCatWebRequest -Uri 'https://im.qq.com/http2rpc/gotrpc/noauth/trpc.qqntv2.urlsign.UrlSign/GetSign' -JsonBody @{ url = $uri.AbsoluteUri } -RequestHeaders @{ 'x-oidb' = '{"uint32_command":"0x9b8e","uint32_service_type":1}' }
        $downloadUri = [uri][string]$signed.data.url
        if ($signed.retcode -ne 0 -or $downloadUri.Scheme -ne 'https' -or $downloadUri.DnsSafeHost -ne $uri.DnsSafeHost -or $downloadUri.AbsolutePath -ne $uri.AbsolutePath) {
            throw 'The official QQ download signing request did not return the expected Tencent download URL.'
        }
        Write-Step "Downloading official QQ installer: $([System.IO.Path]::GetFileName($path))"
        $partial = $path + '.partial'
        try {
            Invoke-NapCatWebRequest -Uri $downloadUri -OutFile $partial -TimeoutSeconds 300
            Assert-TencentSignature -Path $partial
            Move-Item -LiteralPath $partial -Destination $path
        }
        finally { Move-NapCatUpdateArtifact -Path $partial }
    }
    $actualKey = Get-QQInstallerVersion -Path $path
    if ($actualKey -ne $TargetKey) {
        throw "NapCat requires latest supported QQ $TargetKey, but the official installer is $actualKey. Keep the current pair; place the unmodified Tencent-signed $TargetKey full installer in $DownloadRoot and retry. No system QQ or older build was selected."
    }
    return $path
}

function Prepare-ManagedQQ {
    param([string]$TargetKey, [object]$Release)

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
    $installer = Get-QQInstaller -TargetKey $TargetKey
    $extractor = Get-QQExtractor -Release $Release
    $root = Join-Path $DownloadRoot "qq-extract-$timestamp"
    New-Item -ItemType Directory -Path $root -Force | Out-Null
    $stdout = $logFile + '.qq-extract.out.log'
    $stderr = $logFile + '.qq-extract.err.log'
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
    if ($runtime.Key -ne $TargetKey) { throw "Extracted QQ $($runtime.Key) does not match latest supported build $TargetKey." }
    Assert-TencentSignature -Path $runtime.Exe
    Assert-TencentSignature -Path $runtime.NativeDll
    $hash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Step "QQ $TargetKey prepared; Tencent signatures and package version verified; SHA-256=$hash."
    return [pscustomobject]@{ StagingPath = $runtime.Root; InstallerHash = $hash }
}
