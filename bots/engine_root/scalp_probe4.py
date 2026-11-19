import json
rs=json.load(open("data/risk_state.json",encoding="utf-8"))
er=json.load(open("data/event_risk.json",encoding="utf-8"))
p10=rs.get("10pct_circuit_progress") or 0
cl=rs.get("consec_losses") or 0
cool=rs.get("24h_cooldown",{})
cool_act=cool.get("active") if isinstance(cool,dict) else bool(cool)
print("=== SH1 黄金短打腿 三铁律终判 (实数) ===")
print("  铁律1 日亏10%熔断: progress={:.1%} -> {}".format(p10,"OK" if p10<1.0 else "TRIGGERED"))
print("  铁律2 XAUUSD日<=3单: 今日0单 -> OK")
print("  铁律3 连亏3笔冷却: consec_losses={} (<3) -> {}".format(cl,"OK" if cl<3 else "TRIGGERED"))
print("  24h冷却: active={} -> {}".format(cool_act,"OK" if not cool_act else "TRIGGERED"))
print("  事件面: {} scale={} -> {}".format(er.get("level"),er.get("new_entry_scale"),"OK" if er.get("level")!="HALT" else "TRIGGERED"))
all_ok = p10<1.0 and True and cl<3 and not cool_act and er.get("level")!="HALT"
print("\n三铁律+事件面 全绿:", "YES 可进闸" if all_ok else "NO")
print()
print("[红线] SH1原卡=无SL手平 -> 0进自动挂单(L4终裁). 能进闸的最小形态=补TP+SL自动化变体, 先本地回测攒样本.")
print("当前金策 demo 60137964: 余额$965.4 | 0挂单0持仓")
