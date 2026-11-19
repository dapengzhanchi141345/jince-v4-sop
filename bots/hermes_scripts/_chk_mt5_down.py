# -*- coding: utf-8 -*-
"""MT5 终端挂没(17:50 IPC timeout): terminal64 进程在不在 / 18:10 看板 9路全挂是另一码事(git 443 墙, 已知)
判清 MT5 终端进程 + 拉活方案."""
import subprocess, json, datetime, os

def ps(script, timeout=60):
    r = subprocess.run(["powershell", "-NoProfile", "-Command", "chcp 65000 | Out-Null; " + script],
                       capture_output=True, text=True, timeout=timeout, creationflags=0x08000000)
    return (r.stdout or "").strip()

print("=== 1. terminal64.exe 进程在不在 ===")
out = ps("(Get-Process terminal64 -ErrorAction SilentlyContinue | Select-Object Id,StartTime | Format-List | Out-String)")
print(out[:200] if out else "  -> terminal64 进程不存在(挂了)")

print("=== 2. 终端配置(TMG/账户路径) ===")
# 找 MT5 安装目录 + terminal64 启动方式
out2 = ps("Get-ChildItem 'C:/Program Files/TMGM MT5 Terminal/terminal64.exe' -ErrorAction SilentlyContinue | Select-Object FullName | Out-String")
print(out2.strip()[:150] if out2.strip() else "  -> TMGM 路径没探到, 查别的 broker")
for cand in (r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe",
             r"C:\Program Files\ICMarkets SC\MetaTrader 5\terminal64.exe",
             r"C:\Program Files (x86)\TMGM MT5 Terminal\terminal64.exe"):
    if os.path.exists(cand):
        print("  找到:", cand)

print("=== 3. 拉活 MT5 终端(看门狗 autostart bat 或 直接起 terminal64) ===")
# 先找看门狗用的 autostart bat
for bat in (r"E:\GoldstrategyEngine\autostart_mt5.bat",
            r"E:\workbuddy\国外模型\hermes\scripts\autostart_mt5.bat",
            r"C:\Users\ASUS\workbuddy\autostart_mt5.bat"):
    if os.path.exists(bat):
        print("  autostart bat:", bat)

