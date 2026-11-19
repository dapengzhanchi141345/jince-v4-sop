# rebuild_jince_guard_tasks.ps1 — 重建金策 4 守护计划任务（JinCeEventGuard 等整族从系统任务表消失时跑）
# 背景: 该 4 任务约 11-12 起被疑安全软件/系统清理反复清掉; 看门狗对不存在任务的「轻踢」无效, 见 Nmin 无新拍逐拍涨即跑本脚本。
# 用法(管理员用户直接可注册; git-bash 里 schtasks 会 Permission denied, 必须走 PowerShell):
#   powershell -NoProfile -ExecutionPolicy Bypass -File rebuild_jince_guard_tasks.ps1
# 验收: 输出 4 行 CREATED OK + 全 Ready/Running; 再 Start-ScheduledTask -TaskName JinCeEventGuard, 读 E:\GoldstrategyEngine\data\event_guard.log 尾出 [事件快通道完成] 新拍才算活。
# ⚠️ 手动单跑 event_guard.py 会真实改账户态(撤活挂单/置 halt_new_entries=True), 跑完实读账户 diff 再报, 不当纯监控。
$ErrorActionPreference = 'Continue'
$exe = 'C:\Users\ASUS\.workbuddy\binaries\python\envs\ate\Scripts\pythonw.exe'
$tasks = @(
  @{Name='JinCeEventGuard';     Script='E:\GoldstrategyEngine\event_guard.py';          Min=5},
  @{Name='JinCeAntiStall';      Script='E:\GoldstrategyEngine\tools\anti_stall.py';     Min=20},
  @{Name='JinceShadowGuardian'; Script='E:\GoldstrategyEngine\tools\guardian_tick.py'; Min=15},
  @{Name='JinCeBootGuardian';   Script='E:\GoldstrategyEngine\boot_guardian.py';       Min=10; Boot=$true}
)
foreach ($t in $tasks) {
  $action = New-ScheduledTaskAction -Execute $exe -Argument $t.Script -WorkingDirectory 'E:\GoldstrategyEngine'
  $trig = @()
  if ($t.Boot) { $trig += New-ScheduledTaskTrigger -AtLogOn; $trig += New-ScheduledTaskTrigger -AtStartup }
  $trig += New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes $t.Min)
  $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 0)
  $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
  try {
    Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trig -Settings $settings -Principal $principal -Force | Out-Null
    Write-Host ("CREATED OK: " + $t.Name)
  } catch { Write-Host ("ERROR " + $t.Name + ": " + $_.Exception.Message) }
}
Write-Host '=== verify ==='
Get-ScheduledTask -TaskName 'JinCeEventGuard','JinCeAntiStall','JinceShadowGuardian','JinCeBootGuardian' -ErrorAction SilentlyContinue | Select-Object TaskName, State
