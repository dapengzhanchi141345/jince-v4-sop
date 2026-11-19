# -*- coding: utf-8 -*-
"""JinCeAutoCycle 任务配置 + 全链主脚本最近改动时间(判 11:31 崩因)"""
import json, os, datetime, subprocess

def ps(script, timeout=60):
    r = subprocess.run(["powershell", "-NoProfile", "-Command", "chcp 65001 | Out-Null; " + script],
                       capture_output=True, text=True, timeout=timeout, creationflags=0x08000000)
    return (r.stdout or "").strip()

print("=== JinCeAutoCycle 任务: 执行命令 + 触发器 + 运行账户 ===")
out = ps("Get-ScheduledTask -TaskName JinCeAutoCycle | Select-Object -ExpandProperty Actions | "
         "ForEach-Object {$_.Execute; $_.Arguments; $_.WorkingDirectory} | Out-String")
print(out[:400] or "(读不出)")
out2 = ps("Get-ScheduledTaskInfo -TaskName JinCeAutoCycle | Select-Object LastRunTime,LastTaskResult | Out-String")
print(out2[:200])

print("=== 全链主脚本 auto_run_cycle.py 最近修改时间(若 11:31 前被改过=改动引入崩) ===")
for f in (r"E:\GoldstrategyEngine\auto_run_cycle.py",):
    if os.path.exists(f):
        print(f, "| mtime:", datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime("%m-%d %H:%M"))
        print("| size:", os.path.getsize(f))
# 全链调用的子步骤里, 11:31 前后被改过的 .py(找嫌疑)
ENG = r"E:\GoldstrategyEngine"
now = datetime.datetime.now()
sus = []
for root, dirs, files in os.walk(ENG):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "venv")]
    for fn in files:
        if fn.endswith(".py"):
            p = os.path.join(root, fn)
            try:
                mt = datetime.datetime.fromtimestamp(os.path.getmtime(p))
                if mt > datetime.datetime(2026, 10, 8, 10, 30):
                    sus.append((mt.strftime("%H:%M"), p))
            except Exception:
                pass
print("10-08 10:30 后被改过的 .py(嫌疑清单):")
for t, p in sorted(sus):
    print(" ", t, p)
