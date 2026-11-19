$ErrorActionPreference = 'Stop'
$py     = 'C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe'
$script = 'E:/workbuddy/国外模型/hermes/scripts/jince_watchdog.py'
$a = New-ScheduledTaskAction -Execute $py -Argument "`"$script`""
# 重复触发需要一个起始边界: 用 -Once -AtLogOn 打底, 再每 5 分钟重复; 另加开机/登录
$tRep  = New-ScheduledTaskTrigger -Once -AtLogOn -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration ([TimeSpan]::MaxValue)
$tBoot = New-ScheduledTaskTrigger -AtStartup
$tLog  = New-ScheduledTaskTrigger -AtLogOn
$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName 'JinCeWatchdog' -Action $a -Trigger $tRep,$tBoot,$tLog -Settings $s -Force | Select-Object TaskName,State | Format-List
Get-ScheduledTaskInfo -TaskName 'JinCeWatchdog' | Select-Object NextRunTime | Format-List
