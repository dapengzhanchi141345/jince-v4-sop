@echo off
chcp 65001 >nul 2>&1
REM =====================================================================
REM  一次性设置: 注册 Hermes 401 看门狗 + 立即修复当前 "不能打开" 故障
REM ---------------------------------------------------------------------
REM  用法: 右键本文件 -> "以管理员身份运行" (只需一次)
REM
REM  它会做两件事:
REM   1) 注册计划任务 "Hermes401Watchdog" (每 5 分钟检测一次 desktop.log,
REM      发现持续 401 风暴时自动干净重启 Hermes, 以后再也不会卡死你)
REM   2) 立即执行 restart_hermes.bat, 把当前这场 401 风暴一次性修掉
REM =====================================================================
setlocal
title Hermes 看门狗安装 + 立即修复

REM 1) 注册计划任务 (每 5 分钟运行一次看门狗)
echo [1/2] 注册 401 看门狗计划任务...
schtasks /create /tn "Hermes401Watchdog" ^
  /tr "cmd /c E:\workbuddy\hermes_watchdog\run_watchdog.bat" ^
  /sc minute /mo 5 /rl highest /f
if errorlevel 1 (
  echo [!] 计划任务注册失败 (可能需要以管理员身份运行本文件)。
  echo     自动自愈将不可用, 但下面的手动修复仍然有效。
) else (
  echo [OK] 看门狗已注册: 今后每 5 分钟自动检测, 401 风暴会自己修好。
)

REM 2) 立即修复当前故障
echo.
echo [2/2] 立即干净重启 Hermes, 修复当前 "不能打开 bot 聊天" 故障...
echo       (Hermes 会闪退重开, 几秒后会话控制恢复)
timeout /t 2 /nobreak >nul
call "E:\workbuddy\restart_hermes.bat"

echo.
echo 完成。若 Hermes 重新打开后仍有问题, 等约 10 秒再双击一次 restart_hermes.bat。
pause
endlocal
