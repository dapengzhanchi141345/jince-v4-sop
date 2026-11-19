import json, time, sys
try:
    import MetaTrader5 as mt5
except Exception as e:
    print("MT5_IMPORT_FAIL:" + repr(e)); sys.exit(2)

# initialize WITHOUT shutdown -- attach to live terminal64 (safe per SOP)
ok = mt5.initialize(timeout=15000)
if not ok:
    print("MT5_INIT_FAIL:" + mt5.last_error().__str__()); sys.exit(3)

out = {}
acc = mt5.account_info()
if acc:
    out["account"] = {"login": acc.login, "balance": round(acc.balance,2), "equity": round(acc.equity,2),
                      "margin_level": round(acc.margin_level,2) if acc.margin_level else None}

pos = mt5.positions_get()
positions = []
if pos is not None:
    for p in pos:
        positions.append({"symbol": p.symbol, "type": "BUY" if p.type==0 else "SELL",
                           "volume": round(p.volume,2), "open_price": round(p.price_open,5),
                           "sl": round(p.sl,5), "tp": round(p.tp,5), "profit": round(p.profit,2),
                           "magic": p.magic, "ticket": p.ticket,
                           "open_time": time.strftime("%Y-%m-%d %H:%M", time.gmtime(p.time))})
out["positions"] = positions
out["positions_count"] = len(positions)

now = int(time.time())
from_d = now - 2*24*3600
deals = mt5.history_deals_get(from_d, now)
deals_list = []
magic = 20260708
if deals is not None:
    for d in deals:
        if d.magic == magic:
            deals_list.append({"symbol": d.symbol, "type": d.type, "volume": round(d.volume,2),
                               "price": round(d.price,5), "profit": round(d.profit,2),
                               "time": time.strftime("%Y-%m-%d %H:%M", time.gmtime(d.time)),
                               "comment": (d.comment or "")[:40]})
out["magic_deals_count"] = len(deals_list)
net = round(sum(d["profit"] for d in deals_list),2)
out["magic_deals_net_profit"] = net
out["sample_deals"] = deals_list[:60]

print(json.dumps(out, ensure_ascii=False))
# DO NOT call mt5.shutdown() -- keep live connection intact
