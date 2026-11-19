# wb_auto_finalize.ps1 - AUTO killer + finalize + restart (run via schtasks, independent of WorkBuddy)
$ErrorActionPreference = 'Continue'
$log = 'E:\workbuddy\.wb_auto_finalize.log'
function W($m){ ($m | Out-File -FilePath $log -Append -Encoding UTF8) }
W ('=== AUTO_FINALIZE START ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' ===')
Start-Sleep -Seconds 30
# 1) kill ALL WorkBuddy processes forcefully
Get-Process -Name 'WorkBuddy' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 5
& taskkill /IM WorkBuddy.exe /F 2>&1 | Out-Null
Start-Sleep -Seconds 3
$left = (Get-Process -Name 'WorkBuddy' -ErrorAction SilentlyContinue | Measure-Object).Count
W ('KILLED WorkBuddy, remaining=' + $left)
# 2) wait until dir is free (up to 30s)
$free = $false
for($i=0; $i -lt 6; $i++){
  try { Rename-Item -LiteralPath 'C:\Users\ASUS\.workbuddy' -NewName '.workbuddy_probe2' -ErrorAction Stop
        Rename-Item -LiteralPath 'C:\Users\ASUS\.workbuddy_probe2' -NewName '.workbuddy' -ErrorAction Stop
        $free = $true; W ('DIR_FREE_AFTER_' + $i + 's'); break } catch { Start-Sleep -Seconds 5 }
}
if(-not $free){ W 'WARN: dir still busy after 30s, proceeding anyway' }
# 3) run finalize (seed E copy -> rename -> junction -> sync -> delete old)
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File 'E:\workbuddy\.wb_finalize.ps1' *>> $log
W ('FINALIZE_DONE rc=' + $LASTEXITCODE)
# 4) restart WorkBuddy (from either path)
$exe1 = 'C:\Users\ASUS\AppData\Local\Programs\WorkBuddy\WorkBuddy.exe'
$exe2 = 'E:\workbuddy\workbuddy系统盘\Programs-WorkBuddy\WorkBuddy.exe'
if(Test-Path -LiteralPath $exe1){ Start-Process -FilePath $exe1; W ('RESTARTED from ' + $exe1) }
elseif(Test-Path -LiteralPath $exe2){ Start-Process -FilePath $exe2; W ('RESTARTED from ' + $exe2) }
else { W ('NO_EXE_FOUND') }
W ('=== AUTO_FINALIZE DONE ' + (Get-Date -Format 'HH:mm:ss') + ' ===')
