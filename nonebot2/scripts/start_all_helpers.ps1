function Test-TcpPortOpen {
    param(
        [string]$HostName = "127.0.0.1",
        [int]$Port = 8080,
        [int]$TimeoutMilliseconds = 500
    )

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $asyncResult = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $asyncResult.AsyncWaitHandle.WaitOne($TimeoutMilliseconds, $false)) {
            return $false
        }

        $client.EndConnect($asyncResult)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Get-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string[]]$Keys
    )

    if (-not (Test-Path $Path)) {
        return ""
    }

    $values = @{}
    foreach ($line in Get-Content -Path $Path -ErrorAction SilentlyContinue) {
        if ($line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
            continue
        }

        $key = $Matches[1]
        $value = $Matches[2].Trim()
        if (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        $values[$key] = $value
    }

    foreach ($key in $Keys) {
        if ($values.ContainsKey($key)) {
            return $values[$key]
        }
    }

    return ""
}

function ConvertTo-NormalizedProcessText {
    param(
        [string]$Value
    )

    if (-not $Value) {
        return ""
    }

    return $Value.ToLowerInvariant().Replace("/", "\")
}

function Test-ProjectBotProcessCommandLine {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [string]$ExecutablePath,
        [string]$CommandLine
    )

    $normalizedCommandLine = ConvertTo-NormalizedProcessText -Value $CommandLine
    if (-not $normalizedCommandLine) {
        return $false
    }

    $normalizedRoot = ConvertTo-NormalizedProcessText -Value $Root
    $normalizedPythonPath = ConvertTo-NormalizedProcessText -Value (Join-Path $Root ".venv\Scripts\python.exe")
    $normalizedBotPath = ConvertTo-NormalizedProcessText -Value (Join-Path $Root "bot.py")
    $normalizedExecutablePath = ConvertTo-NormalizedProcessText -Value $ExecutablePath

    $hasBotEntrypoint =
        $normalizedCommandLine.Contains($normalizedBotPath) -or
        $normalizedCommandLine -match '(^|[\\/"\s])bot\.py($|["\s])'

    if (-not $hasBotEntrypoint) {
        return $false
    }

    return (
        $normalizedCommandLine.Contains($normalizedRoot) -or
        $normalizedCommandLine.Contains($normalizedPythonPath) -or
        $normalizedExecutablePath -eq $normalizedPythonPath
    )
}

function Get-ProjectBotProcesses {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            Test-ProjectBotProcessCommandLine `
                -Root $Root `
                -ExecutablePath $_.ExecutablePath `
                -CommandLine $_.CommandLine
        }
}

function Get-ProjectBotProcessesFromPidFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PidFile
    )

    if (-not (Test-Path $PidFile)) {
        return @()
    }

    $rawPid = (Get-Content -Path $PidFile -TotalCount 1 -ErrorAction SilentlyContinue).Trim()
    if ($rawPid -notmatch '^\d+$') {
        return @()
    }

    $process = Get-Process -Id ([int]$rawPid) -ErrorAction SilentlyContinue
    if (-not $process -or $process.HasExited) {
        return @()
    }

    return [pscustomobject]@{
        ProcessId = $process.Id
    }
}

function Get-ProjectSourceLastWriteTime {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    $paths = @(
        (Join-Path $Root "bot.py"),
        (Join-Path $Root "pyproject.toml"),
        (Join-Path $Root "src")
    )

    $latest = Get-Date "1970-01-01T00:00:00Z"
    foreach ($path in $paths) {
        if (-not (Test-Path $path)) {
            continue
        }

        $items = Get-Item $path
        if ($items.PSIsContainer) {
            $items = Get-ChildItem -Path $path -Recurse -File -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -notmatch '(__pycache__|\.pyc$)' }
        }

        foreach ($item in $items) {
            if ($item.LastWriteTime -gt $latest) {
                $latest = $item.LastWriteTime
            }
        }
    }

    return $latest
}

function Test-ProjectBotProcessStale {
    param(
        [Parameter(Mandatory = $true)]
        [CimInstance]$Process,
        [Parameter(Mandatory = $true)]
        [DateTime]$SourceLastWriteTime
    )

    if (-not $Process.CreationDate) {
        return $false
    }

    return $SourceLastWriteTime -gt $Process.CreationDate
}

function Stop-ProcessTree {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ProcessId,
        [hashtable]$Seen = @{}
    )

    if ($Seen.ContainsKey($ProcessId)) {
        return
    }
    $Seen[$ProcessId] = $true

    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -ErrorAction SilentlyContinue
    foreach ($child in $children) {
        Stop-ProcessTree -ProcessId ([int]$child.ProcessId) -Seen $Seen
    }

    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function New-ChildProcessIndex {
    $childrenByParentId = @{}
    $allProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)

    foreach ($process in $allProcesses) {
        if ($null -eq $process.ParentProcessId) {
            continue
        }

        $parentKey = [string]([int]$process.ParentProcessId)
        if (-not $childrenByParentId.ContainsKey($parentKey)) {
            $childrenByParentId[$parentKey] = New-Object "System.Collections.Generic.List[int]"
        }

        $childrenByParentId[$parentKey].Add([int]$process.ProcessId)
    }

    return ,$childrenByParentId
}

function Stop-ProcessTreeFromIndex {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ProcessId,
        [Parameter(Mandatory = $true)]
        [hashtable]$ChildrenByParentId,
        [hashtable]$Seen = @{}
    )

    if ($Seen.ContainsKey($ProcessId)) {
        return
    }
    $Seen[$ProcessId] = $true

    $processKey = [string]$ProcessId
    if ($ChildrenByParentId.ContainsKey($processKey)) {
        foreach ($childId in $ChildrenByParentId[$processKey]) {
            Stop-ProcessTreeFromIndex `
                -ProcessId ([int]$childId) `
                -ChildrenByParentId $ChildrenByParentId `
                -Seen $Seen
        }
    }

    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Stop-ProjectBotProcesses {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Processes
    )

    # 旧实现会对每个节点单独查询 CIM 子进程；Windows 上很慢。
    # 这里先一次性建立父子索引，再按树后序停止，避免重启时卡二十秒左右。
    $childrenByParentId = New-ChildProcessIndex
    if ($null -eq $childrenByParentId) {
        $childrenByParentId = @{}
    }
    $seen = @{}

    foreach ($process in $Processes) {
        Stop-ProcessTreeFromIndex `
            -ProcessId ([int]$process.ProcessId) `
            -ChildrenByParentId $childrenByParentId `
            -Seen $seen
    }
}

function Wait-TcpPortOpen {
    param(
        [string]$HostName = "127.0.0.1",
        [int]$Port = 8080,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-TcpPortOpen -HostName $HostName -Port $Port) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }

    return $false
}

function Wait-TcpPortClosed {
    param(
        [string]$HostName = "127.0.0.1",
        [int]$Port = 8080,
        [int]$TimeoutSeconds = 5
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (-not (Test-TcpPortOpen -HostName $HostName -Port $Port -TimeoutMilliseconds 250)) {
            return $true
        }
        Start-Sleep -Milliseconds 250
    }

    return $false
}

function Test-TcpPortEstablished {
    param(
        [string]$HostName = "127.0.0.1",
        [int]$Port = 8080
    )

    try {
        $connections = Get-NetTCPConnection `
            -LocalAddress $HostName `
            -LocalPort $Port `
            -State Established `
            -ErrorAction SilentlyContinue

        return $null -ne ($connections | Select-Object -First 1)
    }
    catch {
        return $false
    }
}

function Test-OneBotConnected {
    param(
        [string]$HostName = "127.0.0.1",
        [int]$Port = 8080,
        [string]$LogPath = ""
    )

    if (Test-TcpPortEstablished -HostName $HostName -Port $Port) {
        return $true
    }

    if ($LogPath -and (Test-BotConnectedLog -LogPath $LogPath)) {
        return $true
    }

    return $false
}

function Test-BotConnectedLog {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LogPath
    )

    if (-not (Test-Path $LogPath)) {
        return $false
    }

    $content = Get-Content -Path $LogPath -Raw -ErrorAction SilentlyContinue
    return $content -match "OneBot V11 \| Bot .+ connected"
}

function Wait-BotConnectedLog {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LogPath,
        [int]$TimeoutSeconds = 300
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-BotConnectedLog -LogPath $LogPath) {
            return $true
        }
        Start-Sleep -Seconds 1
    }

    return $false
}

function Wait-OneBotConnected {
    param(
        [string]$HostName = "127.0.0.1",
        [int]$Port = 8080,
        [string]$LogPath = "",
        [int]$TimeoutSeconds = 300
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-OneBotConnected -HostName $HostName -Port $Port -LogPath $LogPath) {
            return $true
        }

        Start-Sleep -Seconds 1
    }

    return $false
}

function Initialize-WindowNativeMethods {
    if (-not ("QqbotStartAll.NativeMethods" -as [type])) {
        Add-Type -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

namespace QqbotStartAll {
    public static class NativeMethods {
        public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

        [DllImport("user32.dll")]
        public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

        [DllImport("user32.dll")]
        public static extern bool IsWindowVisible(IntPtr hWnd);

        [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
        public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

        [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
        public static extern int GetWindowTextLength(IntPtr hWnd);

        [DllImport("user32.dll")]
        public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

        public static IntPtr[] FindVisibleWindowsByTitleFragment(string titleFragment) {
            var handles = new List<IntPtr>();
            EnumWindows((hWnd, lParam) => {
                if (!IsWindowVisible(hWnd)) {
                    return true;
                }

                int length = GetWindowTextLength(hWnd);
                if (length <= 0) {
                    return true;
                }

                var builder = new StringBuilder(length + 1);
                GetWindowText(hWnd, builder, builder.Capacity);
                string title = builder.ToString();
                if (title.IndexOf(titleFragment, StringComparison.OrdinalIgnoreCase) >= 0) {
                    handles.Add(hWnd);
                }

                return true;
            }, IntPtr.Zero);

            return handles.ToArray();
        }
    }
}
"@
    }
}

function Set-ProcessMainWindowVisible {
    param(
        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Process]$Process,
        [Parameter(Mandatory = $true)]
        [bool]$Visible
    )

    Initialize-WindowNativeMethods

    $Process.Refresh()
    if ($Process.HasExited -or $Process.MainWindowHandle -eq 0) {
        return $false
    }

    $showCommand = 0
    if ($Visible) {
        $showCommand = 9
    }

    return [QqbotStartAll.NativeMethods]::ShowWindow($Process.MainWindowHandle, $showCommand)
}

function Hide-WindowByTitleFragment {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TitleFragment
    )

    Initialize-WindowNativeMethods
    $handles = [QqbotStartAll.NativeMethods]::FindVisibleWindowsByTitleFragment($TitleFragment)
    foreach ($handle in $handles) {
        if ([QqbotStartAll.NativeMethods]::ShowWindow($handle, 0)) {
            return $true
        }
    }

    return $false
}

function Hide-ProcessMainWindow {
    param(
        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Process]$Process
    )

    return Set-ProcessMainWindowVisible -Process $Process -Visible $false
}

function Show-ProcessMainWindow {
    param(
        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Process]$Process
    )

    return Set-ProcessMainWindowVisible -Process $Process -Visible $true
}
