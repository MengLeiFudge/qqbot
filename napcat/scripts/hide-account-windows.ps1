[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("yunqi", "yelin", "xingyao", "yuecheng")]
    [string]$Target
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$AccountsPath = Join-Path $ProjectRoot "accounts.json"

$manifest = Get-Content -Path $AccountsPath -Raw -Encoding UTF8 | ConvertFrom-Json
$items = @($manifest.accounts | Where-Object { $_.target -eq $Target })
if ($items.Count -ne 1) {
    throw "NapCat target '$Target' is missing or duplicated in $AccountsPath."
}
$account = [string]$items[0].qq

function Get-ProcessTreeIds {
    param(
        [int]$RootProcessId,
        [object[]]$Processes
    )

    $ids = [System.Collections.Generic.HashSet[int]]::new()
    $queue = [System.Collections.Generic.Queue[int]]::new()
    $queue.Enqueue($RootProcessId)
    while ($queue.Count -gt 0) {
        $currentId = $queue.Dequeue()
        if (-not $ids.Add($currentId)) {
            continue
        }
        foreach ($child in @($Processes | Where-Object { $_.ParentProcessId -eq $currentId })) {
            $queue.Enqueue([int]$child.ProcessId)
        }
    }
    return @($ids)
}

function Get-AccountProcessIds {
    $processes = @(Get-CimInstance Win32_Process)
    $accountPattern = "-Account\s+['`"]?$([regex]::Escape($account))['`"]?"
    $roots = @($processes | Where-Object {
        $_.CommandLine -and
        $_.CommandLine -match 'start-(napcat-)?account\.ps1' -and
        $_.CommandLine -match $accountPattern
    })
    $ids = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($root in $roots) {
        foreach ($processId in (Get-ProcessTreeIds -RootProcessId ([int]$root.ProcessId) -Processes $processes)) {
            [void]$ids.Add([int]$processId)
        }
    }
    return @($ids)
}

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class QqbotWindowApi
{
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool ShowWindowAsync(IntPtr windowHandle, int command);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool IsWindowVisible(IntPtr windowHandle);
}
'@

$processIds = @(Get-AccountProcessIds | Sort-Object -Unique)
if ($processIds.Count -eq 0) {
    throw "No owned NapCat process tree was found for account $account."
}

$handles = [System.Collections.Generic.List[System.IntPtr]]::new()
foreach ($processId in $processIds) {
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($null -eq $process -or $process.MainWindowHandle -eq [System.IntPtr]::Zero) {
        continue
    }
    [void]$handles.Add($process.MainWindowHandle)
    [void][QqbotWindowApi]::ShowWindowAsync($process.MainWindowHandle, 0)
}

if ($handles.Count -gt 0) {
    Start-Sleep -Milliseconds 200
    $visibleCount = @($handles | Where-Object { [QqbotWindowApi]::IsWindowVisible($_) }).Count
    if ($visibleCount -gt 0) {
        throw "Failed to hide $visibleCount owned NapCat window(s) for account $account."
    }
}

Write-Host "[NapCat] Hidden $($handles.Count) owned window(s) for account $account."
