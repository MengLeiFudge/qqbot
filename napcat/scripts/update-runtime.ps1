<#
NapCat 更新器的私有支持函数：解析实际 QQ、校验目标版本、保存恢复数据并调用根重启入口。
由 update.ps1 点源加载，复用其路径、日志和事务状态。
#>

function Get-NapCatBundleVersion {
    <# 从运行包的版本常量读取版本，避免把安装器元数据或历史日志当成实际版本。 #>
    param([string]$Root)

    $bundle = Join-Path $Root "napcat.mjs"
    if (-not (Test-Path -LiteralPath $bundle)) {
        return ""
    }
    $source = Get-Content -LiteralPath $bundle -Raw -Encoding UTF8
    $match = [regex]::Match($source, '["''](?<version>\d+\.\d+\.\d+)["'']\s*\|\|\s*["'']1\.0\.0-dev["'']')
    if (-not $match.Success) {
        throw "Cannot read NapCat version from $bundle. Update the version parser before replacing this package."
    }
    return $match.Groups["version"].Value
}

function Get-InstalledQQRuntime {
    <# 按官方 launcher-user.bat 使用的注册表入口解析 QQ，并读取热更新实际选择的构建。 #>
    $key = "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\QQ"
    $entry = Get-ItemProperty -LiteralPath $key -ErrorAction Stop
    $root = Split-Path -Parent ([string]$entry.UninstallString).Trim('"')
    $exe = Join-Path $root "QQ.exe"
    if (-not (Test-Path -LiteralPath $exe)) {
        throw "QQ executable was not found at $exe. Repair the QQ installation before updating NapCat."
    }

    $selection = Join-Path $root "versions\config.json"
    if (Test-Path -LiteralPath $selection) {
        $config = Get-Content -LiteralPath $selection -Raw -Encoding UTF8 | ConvertFrom-Json
        $version = [string]$config.curVersion
        if ($version -notmatch '^\d+\.\d+\.\d+-\d+$') {
            throw "Invalid QQ curVersion in $selection. NapCat was not stopped."
        }
        $packagePath = Join-Path $root "versions\$version\resources\app\package.json"
    }
    else {
        $packagePath = Join-Path $root "resources\app\package.json"
    }
    $package = Get-Content -LiteralPath $packagePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($selection -and (Test-Path -LiteralPath $selection) -and [string]$package.version -ne $version) {
        throw "QQ package version does not match $selection. NapCat was not stopped."
    }
    $version = [string]$package.version
    $arch = [string]$package.eleArch
    if ($version -notmatch '^\d+\.\d+\.\d+-\d+$' -or $arch -notin @("x64", "arm64", "ia32")) {
        throw "Cannot determine the QQ build and architecture from $packagePath. NapCat was not stopped."
    }
    return [pscustomobject]@{ Version = $version; Architecture = $arch; Key = "$version-$arch"; Exe = $exe }
}

function Assert-NapCatQQCompatibility {
    <# 使用目标 Release 自己的协议支持表校验完整构建；读取失败时保留当前运行。 #>
    param([string]$Tag, [object]$Runtime)

    $ref = [uri]::EscapeDataString($Tag)
    $uri = "https://api.github.com/repos/NapNeko/NapCatQQ/contents/packages/napcat-core/external/napi2native.json?ref=$ref"
    $file = Invoke-RestMethod -Uri $uri -Headers $headers -TimeoutSec 30
    $json = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($file.content))
    $matrix = $json | ConvertFrom-Json
    $entry = $matrix.PSObject.Properties[$Runtime.Key]
    if ($null -eq $entry -or -not $entry.Value.send -or -not $entry.Value.recv) {
        throw "NapCat $Tag does not support QQ $($Runtime.Key). Current processes and system QQ were left unchanged."
    }
    Write-Step "QQ compatibility confirmed: $($Runtime.Key) is supported by $Tag."
}

function Move-NapCatUpdateArtifact {
    <# 将本次事务的临时文件移到根可恢复目录，旧运行包由 ArchiveRoot 保留。 #>
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    New-Item -ItemType Directory -Path $TrashRoot -Force | Out-Null
    $destination = Join-Path $TrashRoot (Split-Path -Leaf $Path)
    if (Test-Path -LiteralPath $destination) {
        $destination += "-" + [guid]::NewGuid().ToString("N")
    }
    Move-Item -LiteralPath $Path -Destination $destination
}

function Copy-NapCatRuntimeState {
    <# 停止所属进程后复制完整配置、插件及运行数据，避免只迁移少数账号 JSON 而丢失状态。 #>
    param([string]$FromRoot, [string]$ToRoot)

    foreach ($name in @("config", "plugins", "data", "logs")) {
        $source = Join-Path $FromRoot $name
        if (Test-Path -LiteralPath $source) {
            Copy-Item -LiteralPath $source -Destination $ToRoot -Recurse -Force
        }
    }
    foreach ($file in @(Get-ChildItem -LiteralPath $FromRoot -File | Where-Object { $_.Name -match '(?i)\.(db|sqlite|sqlite3)(-.*)?$' })) {
        Copy-Item -LiteralPath $file.FullName -Destination $ToRoot -Force
    }
    Write-Step "Preserved NapCat config, plugins and runtime data from $FromRoot."
}

function Save-NapCatUpdateState {
    <# 原子保存更新状态；被中断的激活记录会阻止后台重复停止机器人。 #>
    param([System.Collections.IDictionary]$State)

    if ($DryRun) {
        return
    }
    $directory = Split-Path -Parent $StatePath
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $temporary = Join-Path $directory ([guid]::NewGuid().ToString("N") + ".json")
    [System.IO.File]::WriteAllText($temporary, ($State | ConvertTo-Json -Depth 5), [System.Text.UTF8Encoding]::new($false))
    if (Test-Path -LiteralPath $StatePath) {
        [System.IO.File]::Replace($temporary, $StatePath, [System.Management.Automation.Language.NullString]::Value)
    }
    else {
        [System.IO.File]::Move($temporary, $StatePath)
    }
}

function Restart-NapCatBots {
    <# 只调用既有根入口重启三台机器人；十分钟超时保留运行和日志，不再重启。 #>
    param([System.Collections.IDictionary]$State)

    $startScript = Join-Path $WorkspaceRoot "scripts\start-all.ps1"
    $stdout = $logFile + ".restart.out.log"
    $stderr = $logFile + ".restart.err.log"
    $arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ('"{0}"' -f $startScript), "-Target", "all", "-ForceRestart", "-SkipInstall", "-NoPauseOnFailure")
    $process = Start-Process powershell.exe -ArgumentList $arguments -WorkingDirectory $WorkspaceRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    [void]$process.Handle
    $State.restart_pid = $process.Id
    $State.restart_deadline = [DateTime]::UtcNow.AddMinutes(10).ToString("o")
    Save-NapCatUpdateState -State $State
    Write-Step "Restarting bots. PID: $($process.Id); deadline: $($State.restart_deadline); logs: $stdout ; $stderr"
    try {
        if (-not $process.WaitForExit(600000)) {
            throw "Bot restart exceeded 10 minutes. Runtime was left running; inspect PID $($process.Id) and $stdout before another restart."
        }
        if ($process.ExitCode -ne 0) {
            throw "Bot restart failed with exit code $($process.ExitCode). Inspect $stdout and $stderr; no second restart was attempted."
        }
    }
    finally {
        $process.Dispose()
    }
}

function Assert-NapCatHookReady {
    <# 检查本轮启动日志中的原生协议 Hook 成功记录，不通过发送消息验证。 #>
    param([datetime]$RestartStarted)

    $manifest = Get-Content -LiteralPath (Join-Path $ProjectRoot "accounts.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($account in @($manifest.accounts | Where-Object { $_.autoStart -eq $true })) {
        $directory = Join-Path $DataRoot ("logs\accounts\" + $account.target)
        $log = Get-ChildItem -LiteralPath $directory -File -Filter "napcat-*.out.log" | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
        if ($null -eq $log -or $log.LastWriteTimeUtc -lt $RestartStarted) {
            throw "No new NapCat startup log was found for $($account.target). Inspect $directory."
        }
        $text = Get-Content -LiteralPath $log.FullName -Raw -Encoding UTF8
        if ($text -notmatch 'NativePacketClient Hook 初始化成功' -or $text -match 'PacketBackend 不支持当前QQ版本架构|NativePacketClient Hook 初始化失败|测试Packet状态异常') {
            throw "NapCat protocol initialization was not confirmed for $($account.target). Inspect $($log.FullName)."
        }
        Write-Step "NapCat protocol Hook is ready for $($account.target). Log: $($log.FullName)"
    }
}
