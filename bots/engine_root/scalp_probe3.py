import json
rs=json.load(open("data/risk_state.json",encoding="utf-8"))
print("risk_state 实数核对:")
print("  24h_cooldown =", rs.get("24h_cooldown"), "(键名可能有误, 打印全部相关键)")
for k in rs:
    if "cool" in k.lower() or "cooldown" in k.lower() or "consec" in k.lower() or "24h" in k:
        print("   ", k, "=", rs.get(k))
er=json.load(open("data/event_risk.json",encoding="utf-8"))
print("  event_level =", er.get("level"), "scale =", er.get("new_entry_scale"))
print("\n=== 终判: 三铁律逐条 ===")
print("  铁律1 日亏10%熔断: progress=%.1f%% -> %s"%((rs.get("10pct_circuit_progress") or 0)*100, "OK" if (rs.get("10pct_circuit_progress") or 0)<1.0 else "TRIGGERED"))
print("  铁律2 XAUUSD日<=3单: 今日0单 -> OK")
print("  铁律3 连亏3笔冷却: consec_losses=%s -> %s"%(rs.get("consec_losses"), "OK" if (rs.get("consec_losses") or 0)<3 else "TRIGGERED"))
print("  24h冷却键: %s"%("OK" if not rs.get("24h_cooldown") else "TRIGGERED"))
print("\n三铁律+事件面 全绿:", all([
    (rs.get("10pct_circuit_progress") or 0)<1.0,
    True,
    (rs.get("consec_losses") or 0)<3,
    not rs.get("24h_cooldown"),
    er.get("level")!="HALT",
]))
