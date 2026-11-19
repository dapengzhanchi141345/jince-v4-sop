# -*- coding: utf-8 -*-
"""11:40 点名 @chief 三项排查(看门狗给的顺序): gateway 活? / chief 全链心跳源? / 429 撞墙?
只读核验, 不动交易配置."""
import json, os, datetime, subprocess, glob

print("=== 1. gateway 活不活 ===")
HERMES_PY = r"E:\workbuddy\国外模型\hermes\hermes-agent\venv\Scripts\python.exe"
r = subprocess.run([HERMES_PY, "-m", "hermes_cli.main", "gateway", "status"],
                   capture_output=True, text=True, timeout=90, creationflags=0x08000000)
for ln in (r.stdout or "").splitlines():
    if "PID" in ln or "running" in ln.lower() or "Gateway" in ln:
        print("  ", ln.strip()[:100])
if r.returncode != 0:
    print("   status 异常 rc=", r.returncode, r.stderr[:120])

print("\n=== 2. chief 全链心跳源 ===")
try:
    d = json.load(open(r"E:\GoldstrategyEngine\data\chief_pipeline_last.json", encoding="utf-8"))
    ts = d.get("ts")
    print("  chief_pipeline_last.ts =", ts, "| all_ok =", d.get("all_ok"))
except Exception as e:
    print("  chief_pipeline_last 读不出:", e)
p = r"E:\GoldstrategyEngine\data\auto_cycle.log"
if os.path.exists(p):
    lines = [l for l in open(p, encoding="utf-8", errors="ignore").read().splitlines() if l.strip()]
    print("  auto_cycle.log 末2行:")
    for l in lines[-2:]:
        print("   ", l[:130])
    print("  auto_cycle.log mtime:",
          datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%m-%d %H:%M:%S"))

print("\n=== 3. 429 撞墙没(chief profile cron 最近跑) ===")
try:
    jd = json.load(open(r"E:\workbuddy\国外模型\hermes\cron\jobs.json", encoding="utf-8"))
    jobs = jd.get("jobs") or jd
    if isinstance(jobs, dict):
        jobs = list(jobs.values())
    for j in jobs:
        nm = j.get("name") or ""
        if "chief" in nm or "全链" in nm:
            print("  job:", j.get("id"), "|", nm[:30], "| last_status:", j.get("last_status"),
                  "| last_run:", j.get("last_run_at"), "| last_error:", str(j.get("last_error"))[:60])
except Exception as e:
    print("  jobs.json 读不出:", e)

print("\n=== 4. 判定 ===")
print("chief 全链心跳 30min 一轮, 11:02 出心跳后下一轮 ~11:31-11:32; 点名 11:40 距 11:02 = 38min,")
print("若此刻 auto_cycle.log 末行已更到 11:31+ 或 chief_pipeline_last.ts 已刷 11:31+ -> 已追上, 点名是窗口误报")
print("若仍停在 11:02 且无 429 -> 查 30min 循环是否卡住(全链某步超时), 该唤醒/介入")
