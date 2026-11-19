# -*- coding: utf-8 -*-
"""核验 11:00 事件面 HIGH: 哪来的 / 降档对不对 / 日内管道是否受牵连(只读)"""
import json, datetime

D = r"E:\GoldstrategyEngine\data"

print("=== 1. event_guard_last.json(HIGH 定级源) ===")
d = json.load(open(D + r"\event_guard_last.json", encoding="utf-8"))
ts = d.get("ts")
try:
    print("  level:", d.get("level"), "| ts:", ts, "=",
          datetime.datetime.fromtimestamp(int(float(ts))).strftime("%m-%d %H:%M") if ts else None)
except Exception:
    print("  level:", d.get("level"), "| ts:", ts)
for k in ("note", "intraday_only", "hold_max_hours", "coin_freeze", "policy", "dst_freeze"):
    if k in d:
        print("  ", k, "=", json.dumps(d[k], ensure_ascii=False)[:200])

print("\n=== 2. event_guard_windows.json(24h 高影响事件明细) ===")
w = json.load(open(D + r"\event_guard_windows.json", encoding="utf-8"))
print("  high_events_in_24h:", json.dumps(w.get("high_events_in_24h"), ensure_ascii=False)[:500])
print("  generated_bjt:", w.get("generated_bjt"), "| fail_open:", w.get("fail_open"), "| fail_why:", str(w.get("fail_why"))[:100])

print("\n=== 3. 日内管道现状(候选源/冻结态, HIGH 不碰这些=对路) ===")
cc = json.load(open(D + r"\discretion_candidates.json", encoding="utf-8"))
print("  advisory_source:", cc.get("advisory_source"), "| candidates:", len(cc.get("candidates", [])),
      "| watch:", len(cc.get("watch", [])), "| coin_frozen:", cc.get("coin_frozen"))
rf = json.load(open(D + r"\risk_freeze_state.json", encoding="utf-8"))
print("  risk_freeze policy.open_new_order:", (rf.get("policy") or {}).get("open_new_order"),
      "| intraday_only:", rf.get("intraday_only"), "| coin_freeze:", rf.get("coin_freeze"),
      "| level:", rf.get("level"))
