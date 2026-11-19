# -*- coding: utf-8 -*-
"""11:31 全链疑似卡住: 2)点名脚本读chief心跳源 3)runner 4)11:31后有无完成行
1)python进程: 避开powershell中文(GBK崩), 失败不阻塞."""
import json, os, datetime, subprocess, re

print("=== 1. GoldstrategyEngine python 进程(chcp 65001 防中文崩, 失败跳过不阻塞) ===")
ps = ("chcp 65001 | Out-Null; "
      "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" "
      "| Select-Object ProcessId,CreationDate,CommandLine | ConvertTo-Json")
r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   capture_output=True, text=True, timeout=60,
                   env={**os.environ, "PYTHONIOENCODING": "utf-8"}, creationflags=0x08000000)
raw = r.stdout or ""
try:
    procs = json.loads(raw) if raw.strip() else []
    if isinstance(procs, dict):
        procs = [procs]
    hits = [p for p in procs if p.get("CommandLine") and "GoldstrategyEngine" in p["CommandLine"]]
    print("GoldstrategyEngine python 进程数:", len(hits))
    for p in hits:
        print("  PID", p.get("ProcessId"), "| 起于", p.get("CreationDate"),
              "| cmd:", (p.get("CommandLine") or "")[:130])
except Exception as e:
    print("读进程跳过(不影响2-4):", str(e)[:60])

print("\n=== 2. 点名脚本读的主管(chief)心跳源 ===")
wd = open(r"E:\workbuddy\国外模型\hermes\scripts\jince_heartbeat_watch.py", encoding="utf-8").read()
for l in wd.splitlines():
    s = l.strip()
    if s and (re.search(r"chief|全链|pipeline|auto_cycle", s, re.I)) and len(s) < 160:
        print("  ", s)

print("\n=== 3. 全链循环 runner(Windows 计划任务, 只看英文taskname防崩) ===")
ps2 = ("chcp 65001 | Out-Null; Get-ScheduledTask "
       "| Where-Object {$_.TaskName -match 'jince|cycle|hermes|gateway|mt5|auto'} "
       "| Select-Object TaskName,State | Format-Table -AutoSize | Out-String")
r2 = subprocess.run(["powershell", "-NoProfile", "-Command", ps2], capture_output=True, text=True, timeout=60, creationflags=0x08000000)
print((r2.stdout or "").strip()[:400] or "(无匹配计划任务)")

print("\n=== 4. 11:31 全链是否其实完成了(再扫 log) ===")
p = r"E:\GoldstrategyEngine\data\auto_cycle.log"
rows = [l for l in open(p, encoding="utf-8", errors="ignore").read().splitlines()
        if "全链自动运行" in l]
print("末5行:")
for l in rows[-5:]:
    print("  ", l[:80])
print("log mtime:", datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%H:%M:%S"))
