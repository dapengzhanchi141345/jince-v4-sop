# -*- coding: utf-8 -*-
"""11:31 全链没完成行 + 无可见 python 进程, 深挖: ①任务结果码 ②是否 SYSTEM 进程看不全
③auto_cycle 是否有 error/traceback 落盘 ④11:31 那轮卡在什么(全链完成行缺失)"""
import json, os, datetime, subprocess, re

def ps(script, timeout=60):
    cmd = "chcp 65001 | Out-Null; " + script
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                       capture_output=True, text=True, timeout=timeout, creationflags=0x08000000)
    return (r.stdout or "").strip()

print("=== 1. JinCeAutoCycle 任务最近运行结果 ===")
out = ps("Get-ScheduledTaskInfo -TaskName JinCeAutoCycle | Select-Object LastRunTime,LastTaskResult,NextRunTime,State | Format-List | Out-String")
print(out[:400] if out else "(读不出)")

print("\n=== 2. 全部 python.exe / pythonw.exe 进程(PID+启动时刻; CommandLine 无权限则为空) ===")
out = ps("Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" "
         "| Select-Object ProcessId,Name,CreationDate,CommandLine | ConvertTo-Json")
try:
    procs = json.loads(out) if out else []
    if isinstance(procs, dict):
        procs = [procs]
    print("python 进程总数:", len(procs))
    for p in procs:
        print("  PID", p.get("ProcessId"), p.get("Name"), "| 起于", p.get("CreationDate"),
              "| cmd:", ((p.get("CommandLine") or "<无权限读>")[:120]))
except Exception as e:
    print("解析失败:", str(e)[:60])

print("\n=== 3. auto_cycle 出错落盘(traceback/error 文件) ===")
D = r"E:\GoldstrategyEngine\data"
for fn in os.listdir(D):
    if re.search(r"error|trace|crash|fail", fn, re.I) and fn.endswith((".log", ".json", ".txt")):
        p = os.path.join(D, fn)
        print(" ", fn, "| mtime:", datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%m-%d %H:%M"),
              "| size:", os.path.getsize(p))
# 全链主脚本在哪 + 有无自己的日志
for cand in (r"E:\GoldstrategyEngine\auto_cycle.py", r"E:\GoldstrategyEngine\data\auto_cycle.py",
             r"E:\GoldstrategyEngine\auto_run_cycle.py"):
    if os.path.exists(cand):
        print("全链脚本:", cand)
        break

print("\n=== 4. auto_cycle.log 11:31 那轮正文(看最后写了到哪一步) ===")
raw = open(D + r"\auto_cycle.log", encoding="utf-8", errors="ignore").read()
i = raw.rfind("全链自动运行] 2026-10-08 11:31:03")
seg = raw[i:i+3000] if i >= 0 else raw[-3000:]
print(seg[:1800])
