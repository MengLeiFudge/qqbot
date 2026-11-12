param(
    [ValidateRange(15, 1440)]
    [int]$IntervalMinutes = 60,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$taskName = "QQBot-NapCat-AutoUpdate"
$updateScript = Join-Path $PSScriptRoot "update.ps1"
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($null -ne $existing) {
    $ownedAction = @($existing.Actions | Where-Object { $_.Arguments -like ('*"{0}"*' -f $updateScript) })
    $ownerSid = [string]$existing.Principal.UserId
    if ($ownerSid -notmatch '^S-1-') {
        try { $ownerSid = ([System.Security.Principal.NTAccount]::new($ownerSid).Translate([System.Security.Principal.SecurityIdentifier])).Value }
        catch { throw "无法确认计划任务 $taskName 的运行用户，未改动任务：$($_.Exception.Message)" }
    }
    if ($ownedAction.Count -ne 1 -or $ownerSid -ne $identity.User.Value) {
        throw "计划任务 $taskName 属于其他部署或用户。请先核对任务，避免覆盖。"
    }
}

if ($Remove) {
    if ($null -ne $existing) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }
    Write-Host "已移除 NapCat 自动更新计划。正在运行的机器人和更新进程继续运行。"
    exit 0
}

# 使用当前用户的交互会话，让需要重新登录的 QQ 可以显示扫码窗口；不保存密码。
$principal = New-ScheduledTaskPrincipal -UserId $identity.User.Value -LogonType Interactive -RunLevel Limited
$arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -Automatic' -f $updateScript
$action = New-ScheduledTaskAction -Execute (Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe") -Argument $arguments -WorkingDirectory $workspaceRoot
$hourly = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes($IntervalMinutes) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$logon = New-ScheduledTaskTrigger -AtLogOn -User $identity.User.Value
$logon.Delay = "PT2M"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 45)
$task = New-ScheduledTask -Action $action -Trigger @($hourly, $logon) -Principal $principal -Settings $settings -Description "定期检查 NapCat 官方稳定版，先更新 NapCat，再选择能取得且受支持的尽可能新独立 QQ 构建；需要时恢复机器人连接，不更新桌面 QQ。"
Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Host "已启用 $taskName：每 $IntervalMinutes 分钟检查一次，并在用户登录两分钟后检查。首次检查已启动。"
Write-Host "更新状态：napcat\data\updates\napcat.json；更新日志：napcat\data\logs\updates。"
Get-ScheduledTaskInfo -TaskName $taskName | Select-Object LastRunTime,LastTaskResult,NextRunTime
