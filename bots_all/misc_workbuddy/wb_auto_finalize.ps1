# wb_auto_finalize.ps1 - 全自动收尾：杀WB进程 -> 收尾迁移 -> 重启WB
# 由启动器以分离方式调用，脱离当前对话会话独立运行
$ErrorActionPreference = 'SilentlyContinue'
$resFile = 'E:\workbuddy\磁盘清理\.wb_result_final.txt'
$logFile = 'E:\workbuddy\磁盘清理\.wb_auto.log'
$lines = New-Object System.Collections.Generic.List[string]
function Log($m){ $lines.Add($m); Add-Content -LiteralPath $logFile -Value $m -Encoding UTF8 }

Add-Content -LiteralPath $logFile -Value '=== AUTO FINALIZE START ===' -Encoding UTF8

# 1) 请求关闭 WorkBuddy 全部进程
Log 'STEP1: killing WorkBuddy processes'
Get-Process -Name 'WorkBuddy','editor_sdk','sandbox-center','sandbox-cli','sandbox-cli-gc' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
# 再补一个兜底：等2秒确认退出
Start-Sleep -Seconds 3
$still = Get-Process -Name 'WorkBuddy' -ErrorAction SilentlyContinue
if($still){ Log ('WARN: WorkBuddy still running, count=' + $still.Count) } else { Log 'OK: WorkBuddy exited' }

# 2) 执行收尾脚本（迁移 + 删残留）
Log 'STEP2: running wb_finalize.ps1'
& powershell -NoProfile -ExecutionPolicy Bypass -File 'E:\workbuddy\.wb_finalize.ps1'
Start-Sleep -Seconds 2

# 3) 读取收尾结果并记录
Log 'STEP3: reading finalize result'
if(Test-Path -LiteralPath $resFile){
  Get-Content -LiteralPath $resFile -Encoding UTF8 | ForEach-Object { Log ('RESULT|' + $_) }
} else { Log 'WARN: result file not found' }

# 4) 验证 Junction
Log 'STEP4: verify junctions'
foreach($p in @('C:\Users\ASUS\.workbuddy','C:\Users\ASUS\AppData\Local\Programs\WorkBuddy')){
  if(Test-Path -LiteralPath $p){
    $v = Get-Item -LiteralPath $p -Force
    Log ('VERIFY|' + $p + ' LinkType=' + $v.LinkType + ' Target=' + ($v.Target -join ';'))
  } else { Log ('VERIFY|' + $p + ' MISSING') }
}

# 5) 从 E 盘重启 WorkBuddy
Log 'STEP5: restarting WorkBuddy from E drive'
$exe = 'E:\workbuddy\workbuddy系统盘\Programs-WorkBuddy\WorkBuddy.exe'
if(Test-Path -LiteralPath $exe){
  Start-Process -FilePath $exe
  Log ('OK: launched ' + $exe)
} else {
  # 兜底：若 E 盘不可用，从 C 盘原路径(可能是junction指向E)启动
  $cexe = 'C:\Users\ASUS\AppData\Local\Programs\WorkBuddy\WorkBuddy.exe'
  if(Test-Path -LiteralPath $cexe){ Start-Process -FilePath $cexe; Log ('OK: fallback launched ' + $cexe) }
  else { Log 'FAIL: no WorkBuddy.exe found on E or C' }
}
Log '=== AUTO FINALIZE END ==='
