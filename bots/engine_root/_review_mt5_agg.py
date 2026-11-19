import json, time, sys
import MetaTrader5 as mt5
ok = mt5.initialize(timeout=15000)
if not ok:
    print("MT5_INIT_FAIL:" + mt5.last_error().__str__()); sys.exit(3)
now = int(time.time()); from_d = now - 2*24*3600
deals = mt5.history_deals_get(from_d, now)
magic = 20260708
agg = {}
types = {0:"BUY",1:"SELL"}
wins = 0; losses = 0; total = 0
if deals:
    for d in deals:
        if d.magic != magic: continue
        s = d.symbol
        a = agg.setdefault(s, {"count":0,"net":0.0,"buy":0,"sell":0,"closed_pnl":0.0})
        a["count"] += 1
        a["net"] += d.profit
        if d.type == 0: a["buy"] += 1
        else: a["sell"] += 1
        # closing deals have profit != 0 typically
        if d.profit != 0.0:
            a["closed_pnl"] += d.profit
            if d.profit > 0: wins += 1
            else: losses += 1
            total += 1
out = {"per_symbol": {k:{"count":v["count"],"net":round(v["net"],2),"buy":v["buy"],"sell":v["sell"],"closed_pnl":round(v["closed_pnl"],2)} for k,v in sorted(agg.items(), key=lambda x:-x[1]["net"])},
       "closed_total": total, "wins": wins, "losses": losses}
print(json.dumps(out, ensure_ascii=False))
