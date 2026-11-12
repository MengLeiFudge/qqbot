# NapCat 更新器的 HTTP、归档、状态和重启支持；仅由 update.ps1 点源加载。
. (Join-Path $PSScriptRoot "qq-runtime.ps1")

function Invoke-NapCatWebRequest {
    <#
    在原有超时预算内请求官方发布与下载接口，仅对临时连接错误最多尝试三次。
    当前进程指定 TLS 1.2，沿用 Windows 系统代理和证书验证，结束时恢复协议设置。
    文件重试从头覆盖下载；完整性仍由更新器后续的大小和 SHA-256 校验确认。
    #>
    param(
        [uri]$Uri, [int]$TimeoutSeconds = 30, [string]$OutFile = "",
        [hashtable]$JsonBody, [hashtable]$RequestHeaders = @{}
    )

    $previousTls = [System.Net.ServicePointManager]::SecurityProtocol
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
        Write-Step "HTTP request: host=$($Uri.DnsSafeHost); TLS=1.2; timeout=${TimeoutSeconds}s."
        for ($attempt = 1; $attempt -le 3; $attempt++) {
            $remaining = [int][Math]::Floor($TimeoutSeconds - $timer.Elapsed.TotalSeconds)
            if ($remaining -lt 1) {
                throw "HTTP request exceeded ${TimeoutSeconds}s: $($Uri.DnsSafeHost)."
            }
            $httpHeaders = @{}
            foreach ($key in $headers.Keys) { $httpHeaders[$key] = $headers[$key] }
            foreach ($key in $RequestHeaders.Keys) { $httpHeaders[$key] = $RequestHeaders[$key] }
            $request = @{ Uri = $Uri.AbsoluteUri; Headers = $httpHeaders; TimeoutSec = $remaining; ErrorAction = "Stop" }
            if ($null -ne $JsonBody) {
                $request.Method = "Post"
                $request.ContentType = "application/json"
                $request.Body = $JsonBody | ConvertTo-Json -Depth 5 -Compress
            }
            try {
                if ($OutFile) {
                    Invoke-WebRequest @request -UseBasicParsing -OutFile $OutFile | Out-Null
                    return
                }
                return (Invoke-RestMethod @request)
            }
            catch [System.Net.WebException] {
                $failure = $_.Exception
                $transient = $failure.Status -in @(
                    [System.Net.WebExceptionStatus]::Timeout,
                    [System.Net.WebExceptionStatus]::ConnectFailure,
                    [System.Net.WebExceptionStatus]::ConnectionClosed,
                    [System.Net.WebExceptionStatus]::KeepAliveFailure,
                    [System.Net.WebExceptionStatus]::NameResolutionFailure,
                    [System.Net.WebExceptionStatus]::ProxyNameResolutionFailure,
                    [System.Net.WebExceptionStatus]::ReceiveFailure,
                    [System.Net.WebExceptionStatus]::SendFailure,
                    [System.Net.WebExceptionStatus]::SecureChannelFailure
                )
                $inner = $failure
                while ($null -ne $inner.InnerException) { $inner = $inner.InnerException }
                $reason = [regex]::Replace($inner.Message, 'https?://\S+', '<url>')
                Write-Step "HTTP request failed: host=$($Uri.DnsSafeHost); attempt=$attempt; status=$($failure.Status); reason=$reason"
                $delay = 2 * $attempt
                if (-not $transient -or $attempt -eq 3 -or ($TimeoutSeconds - $timer.Elapsed.TotalSeconds) -le ($delay + 1)) {
                    throw [System.IO.IOException]::new("HTTP request to $($Uri.DnsSafeHost) failed after $attempt attempt(s): $($failure.Status); $reason", $failure)
                }
                # 只有可重试的连接错误才退避；等待与后续请求共用同一截止时间。
                Write-Step "Retrying HTTP connection in ${delay}s; the original timeout budget is retained."
                Start-Sleep -Seconds $delay
            }
        }
    }
    finally {
        [System.Net.ServicePointManager]::SecurityProtocol = $previousTls
    }
}

function Get-NapCatQQMatrix {
    <# 只读取目标 Release 自己的支持表；未知构建不得由桌面 QQ 或模型名称推断。 #>
    param([string]$Tag)

    $ref = [uri]::EscapeDataString($Tag)
    $uri = "https://api.github.com/repos/NapNeko/NapCatQQ/contents/packages/napcat-core/external/napi2native.json?ref=$ref"
    $file = Invoke-NapCatWebRequest -Uri $uri
    $json = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($file.content))
    return ($json | ConvertFrom-Json)
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
