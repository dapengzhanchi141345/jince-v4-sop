# Exness 233144570 深度分析 - 第2步：全量历史成交 + 资金流水
import MetaTrader5 as mt5
import json, datetime, sys, time
from collections import defaultdict

LOGIN = 233144570
PW = "aA123@321"
ok = False
for _try in range(6):
    ok = mt5.initialize(login=LOGIN, password=PW, server="Exness-Real5", timeout=30000)
    if ok:
        break
    print(f"retry {_try} {mt5.last_error()}", file=sys.stderr)
    time.sleep(10)
assert ok, mt5.last_error()

out = {}

# 全量历史成交
all_deals = []
end = time.time() + 10
while True:
    deals = mt5.history_deals_get(0, end)
    if deals is None:
        print("history_deals_get ERR", mt5.last_error(), file=sys.stderr)
        break
    if not len(deals):
        break
    all_deals.extend(deals)
    end = deals[0].time - 1
    print(f"fetched total={len(all_deals)} oldest={datetime.datetime.fromtimestamp(deals[0].time)}", file=sys.stderr)
    if deals[0].time <= 0:
        break
    time.sleep(0.1)

out["deals"] = []
for d in all_deals:
    out["deals"].append({k: getattr(d, k) for k in ["ticket", "time", "type", "symbol", "volume",
        "price", "profit", "swap", "commission", "magic", "reason", "order", "position", "comment"]})

# 历史订单
all_orders = []
end = time.time() + 10
while True:
    ods = mt5.history_orders_get(0, end)
    if ods is None:
        break
    if not len(ods):
        break
    all_orders.extend(ods)
    end = ods[0].time - 1
    print(f"orders total={len(all_orders)} oldest={datetime.datetime.fromtimestamp(ods[0].time)}", file=sys.stderr)
    time.sleep(0.1)

out["orders"] = []
for o in all_orders:
    out["orders"].append({k: getattr(o, k) for k in ["ticket", "time_setup", "type", "symbol", "volume",
        "price_open", "sl", "tp", "state", "comment"]})

# 资金流水
all_h = []
end = time.time() + 10
while True:
    hs = mt5.history_deals_get(0, end)  # placeholder, use account history below
    break

bal_h = mt5.history_deals_get(0, time.time()+10)  # will redo properly
# 直接用 deals 中的 DEAL_TYPE_BUY/SELL 之外的 type (DEAL_TYPE_DEPOSIT=5, WITHDRAW=6, CORRECTION, PROFIT)
dep = [d for d in out["deals"] if d["type"] in (5, 6, 7, 8, 9, 10)]
out["money_events"] = [{k: d[k] for k in ["ticket","time","type","profit","commission","comment"]} for d in dep]

fn = r"E:\GoldstrategyEngine\data\exness_233144570_history.json"
with open(fn, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
print("SAVED", fn, "deals=", len(out["deals"]), "orders=", len(out["orders"]))
mt5.shutdown()
