@echo off
chcp 65001 >nul 2>&1
REM =====================================================================
REM  Hermes 干净重启工具  (v1.0)
REM ---------------------------------------------------------------------
REM  重要：请在【你自己的终端 / 双击运行】本文件，千万不要让 AI 沙箱终端
REM  去重启网关——沙箱里执行重启等于让网关"杀自己"，会导致进程异常
REM  （这是官方排查文档明确写的坑）。
REM
REM  作用：彻底关闭 Hermes 桌面 + 其网关，再以干净状态重新拉起 Hermes。
REM  桌面重新启动后会用【正确的 venv Python 3.14.9】拉起全新网关，
REM  并重置桌面自己的票据层，从而清除：
REM       "会话控制不可用"  /  "Gateway ticket bootstrap failed"
REM
REM  如仍遇到重复 401 风暴，等待 10 秒后再次双击本文件即可。
REM =====================================================================
setlocal
title Hermes 干净重启

REM 1) 尽量建立 ASCII 软链 E:\workbuddy\hermes-models -> E:\workbuddy\国外模型
REM    目的：彻底绕开中文路径隐患（失败不影响后续步骤）
set "JK=E:\workbuddy\hermes-models"
if not exist "%JK%" (
    cmd /c mklink /J "%JK%" "E:\workbuddy\国外模型" >nul 2>&1
)

REM 2) 关闭 Hermes 桌面（含其 Electron 主/子进程）
echo [1/3] 关闭 Hermes 桌面与网关...
taskkill /F /IM Hermes.exe >nul 2>&1

REM 3) 清理被孤儿化的网关 python 进程（按命令行精确匹配，绝不误杀其它 python）
powershell -NoProfile -Command "try { Get-CimInstance Win32_Process -Filter \"CommandLine like '%%hermes_cli.main gateway%%'\" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } } catch {}" >nul 2>&1

timeout /t 3 /nobreak >nul

REM 4) 重新拉起 Hermes 桌面（桌面会自动用正确的 venv Python 拉起全新网关 + 干净票据层）
echo [2/3] 重新启动 Hermes 桌面...
if exist "%JK%\hermes\hermes-agent\apps\desktop\release\win-unpacked\Hermes.exe" (
    start "" "%JK%\hermes\hermes-agent\apps\desktop\release\win-unpacked\Hermes.exe"
) else (
    start "" "E:\workbuddy\国外模型\hermes\hermes-agent\apps\desktop\release\win-unpacked\Hermes.exe"
)

echo [3/3] 完成。Hermes 正在启动，请稍候几秒，会话控制即可恢复。
echo 若仍提示不可用，请等待约 10 秒后再次双击本文件。
endlocal
