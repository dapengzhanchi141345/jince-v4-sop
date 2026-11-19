
import json, os
d = "E:/GoldstrategyEngine/data"
# 1) pending_orders_state: 606433838 真身(挂单源/时间/撤单历史)
pos = json.load(open(d+"/pending_orders_state.json", encoding="utf-8"))
hits = []
def walk(o, path=""):
    if isinstance(o, dict):
        s = json.dumps(o, ensure_ascii=False)
        if "606433838" in s or ("XAUUSD" in s and ("SELL_LIMIT" in s or "sell" in s.lower())):
            hits.append((path, o))
        for k, v in o.items(): walk(v, path+"/"+k)
    elif isinstance(o, list):
        for i, v in enumerate(o): walk(v, path+"[%d]"%i)
walk(pos)
print("=== pending_orders_state: 606433838 相关记录 ===")
seen=set()
for p,o in hits:
    key=json.dumps(o,ensure_ascii=False)[:200]
    if key in seen: continue
    seen.add(key)
    print(p, ":", json.dumps(o, ensure_ascii=False)[:400])
print("=== 6) rd_decisions KSM 僵尸单行(触发器A/B判据) ===")
rd = json.load(open(d+"/rd_decisions.json", encoding="utf-8"))
arr = rd.get("decisions", rd if isinstance(rd,list) else [])
for row in arr:
    if "zombie" in json.dumps(row, ensure_ascii=False).lower() or "606433838" in json.dumps(row, ensure_ascii=False):
        print(json.dumps(row, ensure_ascii=False, indent=1)[:1200])
print("=== 7) edge_tracker 金银腿 ===")
et = json.load(open(d+"/edge_tracker.json", encoding="utf-8"))
syms = et.get("symbols", {})
for s in ("XAUUSD","XAGUSD"):
    e = syms.get(s, {})
    print(s, "retired=%s n=%s wr=%s pf=%s note=%s" % (e.get("retired"), e.get("n"), e.get("wr"), e.get("pf"), str(e.get("retired_reason") or e.get("note"))[:150]))
print("gate_flags:", json.dumps(et.get("gate_flags",{}), ensure_ascii=False)[:300])
print("=== 8) event_risk ===")
er = json.load(open(d+"/event_risk.json", encoding="utf-8"))
print("level=%s scale=%s halt=%s updated=%s" % (er.get("level"), er.get("new_entry_scale"), er.get("halt_new_entries"), er.get("updated")))
print("=== 9) MT5 活体 orders_get 试读(606433838 是否在盘) ===")
try:
    import MetaTrader5 as mt5
    ok = mt5.initialize(r"C:\Program Files\MetaTrader 5\terminal64.exe") if os.path.exists(r"C:\Program Files\MetaTrader 5\terminal64.exe") else mt5.initialize()
    print("mt5 init:", ok)
    if ok:
        ords = mt5.orders_get() or []
        print("pending orders 总数:", len(ords))
        for o in ords:
            if o.ticket == 606433838 or o.symbol in ("XAUUSD","XAGUSD"):
                print("ticket=%s %s %s %.2f price=%s SL=%s TP=%s vol=%s opened=%s" % (o.ticket, o.symbol, "SELL" if o.type==1 else "BUY", o.price, o.sl, o.tp, o.volume, o.time))
        acc = mt5.account_info()
        print("equity=%s balance=%s" % (acc.equity, acc.balance))
        mt5.shutdown()
except Exception as ex:
    print("MT5 直读失败(改走12:00循环口径):", ex)
