
import json, os, datetime
d = "E:/GoldstrategyEngine/data"
print("=== rd_decisions KSM 僵尸单行 ===")
rd = json.load(open(d+"/rd_decisions.json", encoding="utf-8"))
arr = rd.get("decisions", rd if isinstance(rd, list) else [])
for row in arr:
    s = json.dumps(row, ensure_ascii=False)
    if "zombie" in s.lower() or "606433838" in s:
        print(s[:1500])
print("=== edge_tracker 金银腿 ===")
et = json.load(open(d+"/edge_tracker.json", encoding="utf-8"))
syms = et.get("symbols", {})
for k in syms:
    if "XAU" in k or "XAG" in k or "GOLD" in k.upper():
        e = syms[k]
        print(k, "retired=%s n=%s wr=%s pf=%s reason=%s" % (e.get("retired"), e.get("n"), e.get("wr"), e.get("pf"), str(e.get("retired_reason") or e.get("note") or "")[:200]))
print("=== event_risk ===")
er = json.load(open(d+"/event_risk.json", encoding="utf-8"))
print("level=%s scale=%s halt=%s updated_iso=%s" % (er.get("level"), er.get("new_entry_scale"), er.get("halt_new_entries"), datetime.datetime.fromtimestamp(er.get("updated",0)).strftime("%m-%d %H:%M")))
print("=== MT5 活体 orders_get ===")
try:
    import MetaTrader5 as mt5
    ok = mt5.initialize()
    print("init:", ok)
    if ok:
        ords = mt5.orders_get() or []
        print("pending 总数:", len(ords))
        for o in ords:
            print("ticket=%s %s %s entry=%.2f SL=%s TP=%s vol=%s placed=%s" % (o.ticket, o.symbol, "SELL_LIMIT" if o.type==1 else "BUY_LIMIT", o.price, o.sl, o.tp, o.volume, datetime.datetime.fromtimestamp(o.time).strftime("%m-%d %H:%M")))
        acc = mt5.account_info()
        print("equity=%s balance=%s" % (round(acc.equity,2), round(acc.balance,2)))
        mt5.shutdown()
except Exception as ex:
    print("MT5 直读失败:", ex)
print("=== 撤单闸源 xau_break_cancel_gate.json 在盘? ===")
gp = d+"/xau_break_cancel_gate.json"
print("exists:", os.path.exists(gp))
if os.path.exists(gp):
    print(open(gp, encoding="utf-8").read()[:600])
# 606433838 expiry_ts 换算
import datetime as dt2
print("606433838 expiry_ts=1792108881 =>", dt2.datetime.fromtimestamp(1792108881).strftime("%Y-%m-%d %H:%M"), " now:", dt2.datetime.now().strftime("%Y-%m-%d %H:%M"))
print("606433838 placed_ts=1791936081 =>", dt2.datetime.fromtimestamp(1791936081).strftime("%Y-%m-%d %H:%M"))
