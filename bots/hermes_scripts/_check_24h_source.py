# -*- coding: utf-8 -*-
"""24h 点名脚本查 chief 心跳的源 + 全链是否真推进(判真卡 or 戳滞后误报). 只读."""
import json, os, datetime, glob

# 1. 找"金策24h心跳看门狗·每5min点名" job 的 script
jd = json.load(open(r"E:\workbuddy\国外模型\hermes\cron\jobs.json", encoding="utf-8"))
jobs = jd.get("jobs") or jd
if isinstance(jobs, dict):
    jobs = list(jobs.values())
for j in jobs:
    nm = j.get("name") or ""
    if "24h" in nm or "点名" in nm or "心跳看门狗" in nm:
        print("job:", j.get("id"), "|", nm, "| script:", j.get("script"),
              "| last_status:", j.get("last_status"))

print("\n=== 2. auto_cycle.log 最近 6 行时间戳(全链 30min 循环推进到哪) ===")
p = r"E:\GoldstrategyEngine\data\auto_cycle.log"
rows = [l for l in open(p, encoding="utf-8", errors="ignore").read().splitlines()
        if "全链自动运行" in l]
print("全链完成行(末6):")
for l in rows[-6:]:
    print("  ", l[:80])
print("auto_cycle.log mtime:", datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%m-%d %H:%M:%S"))

print("\n=== 3. 找 chief 30min 心跳戳候选文件 + 各自值/mtime ===")
for fn in ("chief_pipeline_last.json", "chief_heartbeat.json", "fullchain_heartbeat.json",
           "auto_cycle_heartbeat.json", "chief_30min.json", "heartbeat.json"):
    pp = r"E:\GoldstrategyEngine\data" + "\\" + fn
    if os.path.exists(pp):
        mt = datetime.datetime.fromtimestamp(os.path.getmtime(pp)).strftime("%m-%d %H:%M:%S")
        try:
            d = json.load(open(pp, encoding="utf-8"))
            val = d.get("ts") or d.get("heartbeat") or d.get("last") or (list(d.values())[:2] if isinstance(d, dict) else None)
        except Exception:
            val = "(非json)"
        print("  ", fn, "| mtime:", mt, "| 值:", str(val)[:80])
    else:
        print("  ", fn, "(不存在)")
