$ErrorActionPreference = 'Stop'
# 先删掉路径乱码的旧任务
Unregister-ScheduledTask -TaskName 'JinCeWatchdog' -Confirm:$false -ErrorAction SilentlyContinue
$py     = 'C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe'
$script = 'E:/workbuddy/国外模型/hermes/scripts/jince_watchdog.py'
$a = New-ScheduledTaskAction -Execute $py -Argument "`"$script`""
$tRep  = New-ScheduledTaskTrigger -Once (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration ([TimeSpan]::MaxValue)
$tBoot = New-ScheduledTaskTrigger -AtStartup
$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName 'JinCeWatchdog' -Action $a -Trigger $tRep,$tBoot -Settings $s -Force | Select-Object TaskName,State | Format-List
# 验证路径没乱码
Write-Output "=== 复核任务动作路径(应含'国外模型'非问号) ==="
(Get-ScheduledTask -TaskName 'JinCeWatchdog').Actions | Select-Object Execute,Arguments | Format-List
Get-ScheduledTaskInfo -TaskName 'JinCeWatchdog' | Select-Object NextRunTime | Format-List
