@echo off
chcp 65001 >nul 2>&1
REM =====================================================
REM  Hermes 401 one-click fix (2026-11-18)
REM  Problem: gateway restarted 18:52 -> desktop holds dead
REM           boot-bound tickets -> all profiles dial fail/401.
REM           Watchdog task HermesGateway401SelfHeal is DISABLED.
REM  Fix: (1) enable watchdog task  (2) clean restart desktop
REM  Usage: right-click -> Run as administrator (once)
REM =====================================================
setlocal
title Hermes 401 Fix

echo [1/3] Enable watchdog scheduled task...
schtasks /change /tn "HermesGateway401SelfHeal" /enable >nul 2>&1
if errorlevel 1 (
    echo       enable failed, try full re-create...
    schtasks /create /tn "HermesGateway401SelfHeal" ^
      /tr "cmd /c E:\workbuddy\hermes_watchdog\run_watchdog.bat" ^
      /sc minute /mo 5 /rl highest /f >nul 2>&1
    if errorlevel 1 (
        echo [!] Task registration failed. Right-click this file and choose
        echo     "Run as administrator", then run again.
    ) else (
        echo [OK] Watchdog re-created, runs every 5 minutes.
    )
) else (
    echo [OK] Watchdog task enabled, runs every 5 minutes.
)

echo.
echo [2/3] Clean restart Hermes desktop (fix dead tickets)...
call "E:\workbuddy\restart_hermes.bat"

echo.
echo [3/3] Done. Wait ~10 seconds for desktop + gateway to come back.
echo       If chat still fails, wait 10s and double-click restart_hermes.bat again.
echo       Verify: gateway_state.json updated + desktop.log has no new 401.
pause
endlocal
