$ErrorActionPreference = 'Stop'
$pyw = 'E:\workbuddy\国外模型\hermes\hermes-agent\venv\Scripts\pythonw.exe'
$wd  = 'E:\workbuddy\国外模型\hermes\agnes_pool_watchdog.py'
$act = New-ScheduledTaskAction -Execute $pyw -Argument ('"' + $wd + '"')
$trg = New-ScheduledTaskTrigger -AtLogOn
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName 'AgnesKeyPoolWatchdog' -Action $act -Trigger $trg -Settings $set -Force | Select-Object TaskName,State
Start-ScheduledTask -TaskName 'AgnesKeyPoolWatchdog'
