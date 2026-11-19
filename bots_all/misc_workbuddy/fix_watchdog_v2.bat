@echo off
chcp 65001 >nul
setlocal
title Hermes Gateway 401 Watchdog - Enable v2

rem === Constants (absolute paths, quoted) ===
set "TASKNAME=\HermesGateway401SelfHeal"
set "TRIGGER=cmd /c E:\workbuddy\hermes_watchdog\run_watchdog.bat"
set "LOG=E:\workbuddy\hermes_watchdog\watchdog_enable_result.log"

echo ============================================================
echo  Hermes Gateway 401 Watchdog - Enable / Repair (v2)
echo  Target task : HermesGateway401SelfHeal
echo  Action      : %TRIGGER%
echo  Success rule: STATE=Ready AND ACTION contains run_watchdog.bat
echo  Failure sign: STATE=Disabled
echo ============================================================
echo.

rem === Step 1: self-elevate (one UAC prompt, unavoidable) ===
net session >nul 2>&1
if errorlevel 1 (
  echo Requesting administrator privileges, please accept the UAC prompt...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
echo [STEP 1] Administrator token confirmed.

rem === Step 2: back up current task XML (error NOT swallowed) ===
echo [STEP 2] Backing up task XML to "%~dp0watchdog_before.xml" ...
schtasks /query /tn "%TASKNAME%" /xml > "%~dp0watchdog_before.xml"

rem === Step 3: change first, create only if task is absent (errors NOT swallowed) ===
schtasks /query /tn "%TASKNAME%" >nul 2>&1
if errorlevel 1 (
  echo [STEP 3] Task not found. Creating it...
  schtasks /create /tn "%TASKNAME%" /tr "%TRIGGER%" /sc minute /mo 5 /ru "%USERNAME%" /rl highest /f
) else (
  echo [STEP 3] Task found. Enabling it...
  schtasks /change /tn "%TASKNAME%" /enable
  echo [STEP 3] Re-pointing action to new watchdog...
  schtasks /change /tn "%TASKNAME%" /tr "%TRIGGER%"
)
echo.

rem === Step 4: self-check and write log ===
echo [STEP 4] Writing self-check to log: "%LOG%"
echo === %date% %time% > "%LOG%"
schtasks /query /tn "%TASKNAME%" /fo LIST /v >> "%LOG%" 2>&1
powershell -NoProfile -Command "$t=Get-ScheduledTask -TaskName 'HermesGateway401SelfHeal' -ErrorAction Stop; 'STATE='+$t.State; ($t.Actions|ForEach-Object{'ACTION='+$_.Execute+' '+$_.Arguments})" >> "%LOG%" 2>&1
echo.

rem === Step 5: dual verification -> both must hit ===
findstr /i /c:"STATE=Ready" "%LOG%" >nul
if errorlevel 1 goto FAIL
findstr /i /c:"run_watchdog.bat" "%LOG%" >nul
if errorlevel 1 goto FAIL

echo [OK] Watchdog task is Ready and points to run_watchdog.bat.
echo [OK] Full details: "%LOG%"
goto DONE

:FAIL
echo [FAIL] Verification failed. See log: "%LOG%"
echo [FAIL] Need STATE=Ready and ACTION with run_watchdog.bat; STATE=Disabled means failure.

:DONE
echo.
pause
endlocal
