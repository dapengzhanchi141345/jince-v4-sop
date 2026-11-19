# -*- coding: utf-8 -*-
"""手动补跑 11:31 被掐断的那轮全链 + 验证完成行落地 + 查任务终止设置"""
import subprocess, time, datetime, os

def ps(script, timeout=60):
    r = subprocess.run(["powershell", "-NoProfile", "-Command", "chcp 65000 | Out-Null; " + script],
                       capture_output=True, text=True, timeout=timeout, creationflags=0x08000000)
    return (r.stdout or "").strip()

print("=== 1. JinCeAutoCycle 任务执行参数 + 时限设置(判 0xC000013A 是不是到点被停) ===")
out = ps("Get-ScheduledTask -TaskName JinCeAutoCycle | Select-Object -ExpandProperty Actions | "
         "ForEach-Object {\"EXE=\"+ $_.Execute + \" ARGS=\"+ $_.Arguments} | Out-String")
print(out[:300] or "(读不出)")
out2 = ps("(Get-ScheduledTask -TaskName JinCeAutoCycle).Settings | "
          "Select-Object ExecutionTimeLimit,AllowStartIfOnBatteries,DisallowStartIfOnBatteries,StopIfGoingOnBatteries,MultiSession | Out-String")
print(out2[:300] or "(读不出)")

print("\n=== 2. 手动补跑一轮全链(schtasks /run, 绕 12:01 等 30min 盲区) ===")
r = subprocess.run("schtasks /run /tn JinCeAutoCycle", shell=True, capture_output=True, text=True, timeout=60, creationflags=0x08000000)
print("schtasks /run rc=", r.returncode, "|", (r.stdout + r.stderr)[:150])

print("=== 3. 等全链跑完(前两轮实测 53~73s, 等 150s 留裕量) ===")
LOG = r"E:\GoldstrategyEngine\data\auto_cycle.log"
before = open(LOG, encoding="utf-8", errors="ignore").read()
marker = before.rfind("全链自动运行] 2026-10-08 11:31:03")
time.sleep(150)
after = open(LOG, encoding="utf-8", errors="ignore").read()
new_lines = after[marker:].splitlines()
new_lines = [l for l in new_lines if "全链自动运行" in l or "完成" in l][:8]
print("补跑后日志新增的关键行:")
for l in new_lines:
    print("  ", l[:110])
print("log mtime:", datetime.datetime.fromtimestamp(os.path.getmtime(LOG)).strftime("%H:%M:%S"))
