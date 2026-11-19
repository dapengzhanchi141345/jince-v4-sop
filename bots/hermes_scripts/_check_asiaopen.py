# -*- coding: utf-8 -*-
"""asia_open 08:05 节点: 正文落盘了吗 / 实际进群了吗 / 该销账还是补投(防刷两遍)"""
import json, datetime, os

D = r"E:\GoldstrategyEngine\data"
BJT = datetime.timezone(datetime.timedelta(hours=8))

print("=== 1. asia_open 节点正文是否落 discussion_log ===")
LOG = D + r"\discussion_log.jsonl"
hits = []
for line in open(LOG, encoding="utf-8", errors="ignore"):
    if "asia_open" in line:
        try:
            rec = json.loads(line)
            ts = rec.get("ts")
            d = datetime.datetime.fromtimestamp(int(float(ts)), BJT).strftime("%m-%d %H:%M")
            content = str(rec.get("content") or rec.get("note") or rec.get("msg") or "")[:80]
            hits.append((d, rec.get("node"), content))
        except Exception:
            pass
print("asia_open 落盘记录:", len(hits), "条, 末3:")
for h in hits[-3:]:
    print("  ", h[0], h[1], "|", h[2])

print("\n=== 2. 08:30 巡检是否报了 asia_open 节点已生成(生成层对账) ===")
# 巡检 08:30 输出是 "6节点已发['asia_open','us_close']" = asia_open 生成层已确认
print("(引用 08:30 巡检: 6节点已发['asia_open','us_close'] -> 生成层 OK, 正文已出)")

print("\n=== 3. 判定: 台账 delivery_failed vs 实际进群 ===")
# 关键反证链: 本会话 08:30 巡检报 asia_open 已发 + 08:56 东京开评报(94aa7617fc68 last_status=ok 实读)
# 看 94aa7617fc68(jince-node-ny-open-2100 名下跑的东京开评) 台账: last_status=ok
JOBS = r"E:\workbuddy\国外模型\hermes\cron\jobs.json"
d = json.load(open(JOBS, encoding="utf-8"))
jobs = d.get("jobs") or d
if isinstance(jobs, dict):
    jobs = list(jobs.values())
for j in jobs:
    nm = j.get("name") or ""
    if "ny-open-2100" in nm or "asia_open" in nm.lower() or "tokyo-open" in nm:
        print("  job:", j.get("id"), "|", nm, "| last_status:", j.get("last_status"),
              "| last_run:", j.get("last_run_at"), "| unverified:", j.get("last_delivery_unverified"))

print("\n=== 4. 结论 ===")
print("若 08:05 正文已落 discussion_log + 08:30 巡检确认生成层 OK + 08:56 东京开评报(last_status=ok)已进群")
print("  -> asia_open delivery_failed 是回执未销账(消息到群但 ack 没回), 应销账, 不补投")
