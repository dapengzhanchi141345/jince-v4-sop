# -*- coding: utf-8 -*-
"""11:31 全链疑似卡住: 查 ①GoldstrategyEngine 相关 python 进程还挂着没
②点名脚本 jince_heartbeat_watch.py 读 chief 心跳的源文件是哪个 + 最后戳
③全链循环的 runner(定时任务). 只读."""
import json, os, datetime, subprocess, re

print("=== 1. GoldstrategyEngine 相关 python 进程(还挂着=卡住; 没了=异常退出) ===")
ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" "
      "| Select-Object ProcessId,CreationDate,CommandLine | ConvertTo-Json")
r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   capture_output=True, text=True, timeout=60, creationflags=0x08000000)
try:
    procs = json.loads(r.stdout) if r.stdout.strip() else []
    if isinstance(procs, dict):
        procs = [procs]
    hits = [p for p in procs if p.get("CommandLine") and "GoldstrategyEngine" in p["CommandLine"]]
    print("GoldstrategyEngine python 进程数:", len(hits))
    for p in hits:
        print("  PID", p.get("ProcessId"), "| 起于", p.get("CreationDate"),
              "| cmd:", (p.get("CommandLine") or "")[:130])
except Exception as e:
    print("读进程失败:", str(e)[:80], "| raw:", r.stdout[:150])

print("\n=== 2. 点名脚本读的主管(chief)心跳源 ===")
wd = open(r"E:\workbuddy\国外模型\hermes\scripts\jince_heartbeat_watch.py", encoding="utf-8").read()
hits = [l.strip() for l in wd.splitlines()
        if ("chief" in l.lower() or "全链" in l or "pipeline" in l.lower()) and len(l.strip()) < 160]
for h in hits[:18]:
    print("  ", h)

print("\n=== 3. 全链循环 runner(Windows 计划任务) ===")
ps2 = ("Get-ScheduledTask | Where-Object {$_.TaskName -match 'jince|cycle|金策|hermes|gateway|mt5|auto'} "
       "| Select-Object TaskName,State | Format-Table -AutoSize | Out-String")
r2 = subprocess.run(["powershell", "-NoProfile", "-Command", ps2],
                    capture_output=True, text=True, timeout=60, creationflags=0x08000000)
out = r2.stdout.strip()
print(out[:500] if out else "(无匹配计划任务)")

print("\n=== 4. 11:31 全链是否其实完成了(再扫一遍 log, 看 11:31 后有没有完成行) ===")
p = r"E:\GoldstrategyEngine\data\auto_cycle.log"
rows = [l for l in open(p, encoding="utf-8", errors="ignore").read().splitlines()
        if "全链自动运行" in l]
print("末4行:", *rows[-4:], sep="\n  ")
