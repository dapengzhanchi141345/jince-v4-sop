<#
 .SYNOPSIS  Self-heal Hermes desktop "会话控制不可用" (401 storm).
 .DESCRIPTION
   Hermes desktop shows "会话控制不可用" when the gateway's native-HTTP auth gate
   (_native_store in dashboard_auth/native_http.py) permanently fails because the
   gateway's in-memory ticket store / runtime descriptor / session authorities
   drift out of sync (instance_id or served_profiles mismatch). A plain desktop
   restart cannot fix it -- only a clean GATEWAY restart rebuilds that state.
   This script detects a sustained 401 storm in desktop.log while the gateway
   process is alive, then restarts the gateway (rebuilds consistent state) and
   signals the desktop (its supervisor relaunches it against the live gateway).
#>
param(
  [switch]$DetectOnly
)
$ErrorActionPreference='SilentlyContinue'
$root='E:\workbuddy\国外模型\hermes'
$py="$root\tools\python-3.14.9+20261021-win32-x64\python.exe"
$cwd="$root\hermes-agent"
$recoverLog="$root\logs\selfheal.log"
$desktopLog="$root\logs\desktop.log"
$stateFile="$root\gateway_state.json"
$ts=Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

function Log($m){ Add-Content -Path $recoverLog -Value ("$ts  $m") }

# --- Detect a 401/unauthorized storm in the last 3 minutes ---
$cutoff=(Get-Date).AddMinutes(-3)
$recent = Get-Content $desktopLog -Tail 600 -ErrorAction SilentlyContinue | Where-Object {
  if($_ -match '^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'){
    try { [datetime]::ParseExact($Matches[1],'yyyy-MM-dd HH:mm:ss',$null) -ge $cutoff } catch { $false }
  } else { $false }
}
$c401 = ($recent | Where-Object { $_ -match '401:|Unauthorized' }).Count

# --- Gateway process ---
$gw = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'hermes_cli\.main.*gateway run' }
$gwAlive = [bool]$gw
$gwPid = if($gw){ $gw.ProcessId } else { $null }

if($DetectOnly){
  Log("DETECT c401=$c401 gwAlive=$gwAlive gwPid=$gwPid (no action)")
  exit 0
}

if($c401 -lt 5){
  Log("OK c401=$c401 gwAlive=$gwAlive (no storm, no action)")
  exit 0
}

# Storm detected.
if(-not $gwAlive){
  Log("STORM c401=$c401 but gateway not running -> relaunch only")
} else {
  Log("STORM c401=$c401 gwPid=$gwPid -> restart gateway + desktop")
  foreach($p in $gw){ $id=$p.ProcessId; taskkill /F /T /PID $id >$null 2>&1; Log("killed gateway tree $id") }
  Start-Sleep -Seconds 3
}

# Relaunch gateway with the exact env it was originally started with
$env:HERMES_HOME=$root
$env:TMPDIR='E:/workbuddy/tmp'; $env:TEMP='E:/workbuddy/tmp'; $env:TMP='E:/workbuddy/tmp'
$env:PATH = "$root\node;$root\bin;$root\git\cmd;" + $env:PATH
New-Item -ItemType Directory -Force -Path 'E:/workbuddy/tmp' >$null
Start-Process -FilePath $py -ArgumentList '-m','hermes_cli.main','--profile','default','gateway','run','--quiet' -WorkingDirectory $cwd -WindowStyle Hidden -RedirectStandardOutput "$root\logs\gateway_relaunch.log" -RedirectStandardError "$root\logs\gateway_relaunch.err"
Log("gateway relaunch issued")

# Wait for ready (new pid + gateway_state running), so the desktop relaunches against a live gateway
$newpid=$null
for($i=0;$i -lt 40;$i++){
  Start-Sleep -Seconds 2
  $g = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'hermes_cli\.main.*gateway run' }
  if($g -and (-not $gwPid -or $g.ProcessId -ne $gwPid)){
    $newpid=$g.ProcessId
    $st = (Get-Content $stateFile -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json)
    if($st.gateway_state -eq 'running' -and $st.pid -eq $newpid){ Log("gateway ready pid=$newpid (try $i)"); break }
  }
}
if(-not $newpid){ Log("WARN gateway did not start; see gateway_relaunch logs") }

# Restart desktop (its supervisor relaunches it against the now-live gateway)
taskkill /F /IM Hermes.exe >$null 2>&1
Log("desktop restart signal sent")
Log("RECOVER complete")
