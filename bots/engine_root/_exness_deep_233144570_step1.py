# Exness 实盘 233144570 只读深度分析 - 第1步：登录 + 账户快照
import MetaTrader5 as mt5
import json, datetime, sys, time

LOGIN = 233144570
PW = "aA123@321"
SERVERS = ["Exness-Real5", "Exness-Real4", "Exness-Real3", "Exness-Real2", "Exness-Real1", "Exness-MT5"]

res = {}
connected = False
for srv in SERVERS:
    ok = mt5.initialize(login=LOGIN, password=PW, server=srv, timeout=15000)
    print(f"server {srv}: init={ok} err={mt5.last_error()}", file=sys.stderr)
    if ok:
        connected = True
        break

if not connected:
    print(json.dumps({"error": "login_failed_all_servers"}))
    sys.exit(1)

acct = mt5.account_info()
res["account"] = {k: getattr(acct, k) for k in ["login", "name", "server", "currency", "balance", "equity", "credit", "margin", "margin_free", "leverage", "profit", "trade_mode", "trade_allowed"]}
res["trade_mode_map"] = {0:"full",1:"limited",2:"closed",4:"counter_only"}

pos = mt5.positions_get()
res["positions"] = []
if pos:
    for p in pos:
        res["positions"].append({k: getattr(p, k) for k in ["ticket", "symbol", "type", "volume", "price_open", "sl", "tp", "price_current", "profit", "swap", "time", "comment"]})

od = mt5.orders_get()
res["pending_orders"] = []
if od:
    for o in od:
        res["pending_orders"].append({k: getattr(o, k) for k in ["ticket", "symbol", "type", "volume", "price", "sl", "tp", "time", "state", "comment"]})

# symbols info
syms = set([p["symbol"] for p in res["positions"]]) | set([o["symbol"] for o in res["pending_orders"]])
res["symbols"] = []
for s in sorted(syms):
    si = mt5.symbol_info(s)
    if si:
        res["symbols"].append({"symbol": s, "spread": si.spread, "digits": si.digits, "point": si.point, "min_volume": si.volume_min, "max_volume": si.volume_max})

out = r"E:\GoldstrategyEngine\data\exness_233144570_snapshot.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=1, default=str)
print("SNAPSHOT_SAVED", out)
mt5.shutdown()
