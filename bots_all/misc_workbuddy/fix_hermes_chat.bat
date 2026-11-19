@echo off
chcp 65001 >nul
setlocal
title Hermes Chat Fix - Clean Restart
REM ============================================================
REM  Hermes chat stuck in "Gateway starting (deadline)" boot loop.
REM  Gateway is healthy, but the desktop holds a stale ticket and
REM  keeps failing the handshake after the source-completion run.
REM  Fix = clean restart of desktop + gateway so they re-handshake.
REM  Reuses the proven restart_hermes.bat. No admin needed.
REM ============================================================
set "LOG=E:\workbuddy\国外模型\hermes\logs\chat_fix.log"

echo === %date% %time% > "%LOG%"
echo [1/3] Calling proven restart_hermes.bat ... >> "%LOG%" 2>&1
echo.
echo Cleaning up Hermes desktop + gateway, then relaunching...
call "E:\workbuddy\restart_hermes.bat" >> "%LOG%" 2>&1

echo [2/3] Waiting 25s for gateway handshake ... >> "%LOG%" 2>&1
timeout /t 25 /nobreak >nul

echo [3/3] Checking gateway status ... >> "%LOG%" 2>&1
echo === status %date% %time% >> "%LOG%" 2>&1
hermes gateway status >> "%LOG%" 2>&1

echo === done %date% %time% >> "%LOG%" 2>&1
echo.
echo [OK] Hermes relaunched. Check the chat window now.
echo      If still stuck, wait 20s and double-click this file once more.
echo      Details: %LOG%
pause
endlocal
