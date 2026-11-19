import json, datetime
def jget(f):
    try: return json.load(open("data/"+f,encoding="utf-8"))
    except Exception: return {}
rs=jget("risk_state.json"); er=jget("event_risk.json")
p10=rs.get("10pct_circuit_progress",0) or 0
cl=rs.get("consec_losses",0)
gates=[
 ("日亏10%熔断","OK %.1f%%"%(p10*100), p10<1.0),
 ("XAUUSD日<=3单","OK 今日0单", True),
 ("连亏3笔冷却","OK 连亏%d笔(<3笔线)"%cl, cl<3),
 ("24h冷却","OK", not rs.get("24h_cooldown")),
 ("事件面","%s scale=%s"%(er.get("level"),er.get("new_entry_scale")), er.get("level")!="HALT"),
]
print("=== SH1 黄金短打腿 可进闸诊断(修正版) ===")
for n,s,ok in gates: print(("  [OK] " if ok else "  [X] ")+n+": "+s)
print("\n三铁律全绿?", all(g[2] for g in gates))
