$ErrorActionPreference = 'Stop'
$bat = 'E:\workbuddy\国外模型\hermes\start_agnes_pool_hidden.vbs'
$act = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument ('"' + $bat + '"')
$trg = New-ScheduledTaskTrigger -AtLogOn
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName 'AgnesKeyPoolWatchdog' -Action $act -Trigger $trg -Settings $set -Force | Select-Object TaskName,State
Start-ScheduledTask -TaskName 'AgnesKeyPoolWatchdog'
Start-Sleep -Seconds 2
Get-ScheduledTask -TaskName 'AgnesKeyPoolWatchdog' | Select-Object TaskName,State | Format-List
