$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Definition
$py = 'D:\workbuddy\binaries\python\versions\3.13.12\python.exe'
$script = Join-Path $here 'gateway_401_selfheal.py'
$arg = '"{0}" --loop' -f $script
$action = New-ScheduledTaskAction -Execute $py -Argument $arg -WorkingDirectory $here
$tLogon = New-ScheduledTaskTrigger -AtLogOn
$tNow = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(-1)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RunOnlyIfNetworkAvailable:$false -RestartCount 20 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 3650) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'HermesGateway401SelfHeal' -Action $action -Trigger @($tLogon, $tNow) -Settings $settings -Description 'Hermes gateway 401 storm self-heal watchdog (loops forever; auto-restarts on failure)' -Force
Start-ScheduledTask -TaskName 'HermesGateway401SelfHeal'
Start-Sleep -Seconds 10
$info = Get-ScheduledTaskInfo -TaskName 'HermesGateway401SelfHeal'
$out = ('OK|name=HermesGateway401SelfHeal|state=' + (Get-ScheduledTask -TaskName 'HermesGateway401SelfHeal').State + '|lastResult=' + $info.LastTaskResult + '|lastRun=' + $info.LastRunTime)
$out | Out-File -FilePath (Join-Path $here '_reg_selfheal_result.txt') -Encoding ascii
