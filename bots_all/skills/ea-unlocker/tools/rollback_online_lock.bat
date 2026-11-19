@echo off
rem 一键还原: 撤 hosts 那行 + 删用户级 CA + 杀 local443
setlocal
set BASE=%~dp0

echo [1/3] 撤 hosts 里 ea-unlocker 那行
powershell -NoProfile -Command "
$h = [System.Environment]::GetEnvironmentVariable('windir') + '\System32\drivers\etc\hosts'
if (Test-Path $h) {
  (Get-Content $h) | Where-Object { $_ -notmatch 'ea-unlocker' } | Set-Content $h
  Write-Host '  hosts 已清理'
}
"

echo [2/3] 删用户级 CA
powershell -NoProfile -Command "
Get-ChildItem Cert:\CurrentUser\Root | Where-Object { $_.Subject -like '*LocalMITM*' } | ForEach-Object {
  Remove-Item $_.PSPath -ErrorAction SilentlyContinue
  Write-Host '  已删' $_.Subject
}
"

echo [3/3] 杀 local443 服务 (Python 监听 443/80 的)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr \":443 \" ^| findstr LISTENING') do (
  for /f "tokens=1" %%b in ('netstat -ano ^| findstr \":443 \" ^| findstr LISTENING') do (
    taskkill /PID %%b /F 2>nul
  )
)
echo   local443 已停

echo 还原完成。
pause
