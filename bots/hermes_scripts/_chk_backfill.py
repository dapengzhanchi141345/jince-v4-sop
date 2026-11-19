# -*- coding: utf-8 -*-
import json, os, datetime
D = r"E:\GoldstrategyEngine\data"
p = D + r"\node_backfill_queue.json"
if os.path.exists(p):
    d = json.load(open(p, encoding="utf-8", errors="ignore"))
    print("node_backfill_queue.json 在位 | mtime:",
          datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%m-%d %H:%M:%S"))
    print("内容:", json.dumps(d, ensure_ascii=False)[:400])
else:
    print("node_backfill_queue.json 尚不存在(补发机制首次触发时才建=正常空态)")
log = D + r"\auto_cycle.log"
rows = [l for l in open(log, encoding="utf-8", errors="ignore").read().splitlines() if "全链自动运行" in l]
print("\n全链日志末4行(验 12:01 那轮衔接):")
for l in rows[-4:]:
    print("  ", l[:90])
print("log mtime:", datetime.datetime.fromtimestamp(os.path.getmtime(log)).strftime("%H:%M:%S"))
