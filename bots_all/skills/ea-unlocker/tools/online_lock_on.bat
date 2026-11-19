@echo off
rem ============================================================
rem 一键破解在线验证锁 (hosts + 用户级 CA + 本地443 + 重启MT5)
rem 用法: 右键"以管理员身份运行"  厂商域名在 VENDOR 改
rem 还原: 跑同目录 rollback_online_lock.bat
rem 先报后动: 本脚本改系统 hosts + 装用户级证书, 留一键还原
rem ============================================================
setlocal
set VENDOR=www.eabang.com
set BASE=%~dp0

echo [1/5] 改 hosts: %VENDOR% -> 127.0.0.1
powershell -NoProfile -Command "
$line = '127.0.0.1 %VENDOR% #ea-unlocker'
$h = [System.Environment]::GetEnvironmentVariable('windir') + '\System32\drivers\etc\hosts'
if (-not (Select-String -Path $h -Pattern 'ea-unlocker' -Quiet)) {
  Add-Content -Path $h -Value $line
  Write-Host '  hosts 已追加'
} else {
  (Get-Content $h) -replace '127\.0\.0\.1 .*ea-unlocker','' | Set-Content $h
  Add-Content -Path $h -Value $line
  Write-Host '  hosts 已更新'
}
"

echo [2/5] 装 CA 进 CurrentUser\Root (用户级, 无需管理员即可装; 系统级需管理员)
if not exist "%BASE%mitm\ca.crt" (
  echo ca.crt 不存在, 先跑 python gen_ca.py
  pause & exit /b
)
powershell -NoProfile -Command "Import-Certificate -FilePath '%BASE%mitm\ca.crt' -CertStoreLocation Cert:\CurrentUser\Root"
echo   CA 已装用户级根信任

echo [3/5] 启动本地 443 劫持服务
start /B python "%BASE%local443_server.py"
timeout /t 2 /nob1 >nul
echo   local443 已起 (日志 tools\local443.log)

echo [4/5] 提示: 若 MT5 仍走真实证书校验拒载, 需把 CA 进系统级根信任(管理员):
echo   certutil -addstore -enterprise Root "%BASE%mitm\ca.crt"

echo [5/5] 重启 MT5 (关开终端一次)
echo   请手动关掉 MT5 再重开, 让 WebRequest 重连本地 443

echo.
echo 完成。要还原跑 rollback_online_lock.bat
pause
