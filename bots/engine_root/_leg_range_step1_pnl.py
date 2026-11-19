# -*- coding: utf-8 -*-
# Step 1: P&L解剖 — 震荡层(range)已平仓单亏损归因分桶. 只读, 不碰交易代码.
import json, os, time
import numpy as np
import MetaTrader5 as mt5

ROOT = "E:/GoldstrategyEngine"
MAGICS = [20260902, 20260903, 20260904]
STATE_FILES = {
    20260902: ROOT + "/data/pending_orders_state.json",
    20260903: ROOT + "/data/crypto_pending_state.json",
    20260904: ROOT + "/data/equity_pending_state.json",
}

print("[OK] init=%s" % mt5.initialize())
acc = mt5.account_info()
print("[OK] acct=%s" % acc.login)

# 已平仓单 = state filled 里 status=closed + 全部历史 deals
state_range = []   # (src, ticket, sym, side, entry, sl, tp, lots, pnl, regime, layer)
for mg, f in STATE_FILES.items():
    d = json.load(open(f, encoding="utf-8"))
    for tk, v in (d.get("filled") or {}).items():
        if v.get("layer") == "range" and v.get("status") == "closed":
            state_range.append((mg, tk, v.get("sym"), v.get("side"), v.get("entry"),
                                v.get("sl"), v.get("tp"), v.get("lots"),
                                v.get("last_pnl") or v.get("pnl"), v.get("regime"), "range"))

# MT5 deals: 全部平仓 deal (out/deal closed), magic 匹配
ts = int(time.time())
deals = mt5.history_deals_get(0, ts) or []
print("[OK] total deals=%d" % len(deals))
closed = {}  # ticket -> dict
for dl in deals:
    if dl.entry != mt5.DEAL_ENTRY_OUT:
        continue
    magic = int(getattr(dl, "magic", 0))
    closed.setdefault(dl.order, {"magic": magic, "sym": dl.symbol, "type": dl.type,
                                  "profit": 0.0, "volume": 0.0, "ts": dl.time,
                                  "comment": dl.comment, "price": 0.0, "sl": 0.0, "tp": 0.0})
    c = closed[dl.order]
    c["profit"] += (dl.profit or 0) + (dl.swap or 0) + (dl.commission or 0)
    c["volume"] += dl.volume
    c["price"] = dl.price

# deals 里 dl.order 即 ticket; orders 键是 position_by_id (与 deal.order 同源)
otxs = {o.position_by_id: o for o in (mt5.history_orders_get(0, ts) or [])}
otxs2 = {o.ticket: o for o in (mt5.history_orders_get(0, ts) or [])}
mt5_range = []
for ot, c in closed.items():
    if c["magic"] not in MAGICS:
        continue
    o = otxs.get(ot) or otxs2.get(ot)
    if o is None:
        continue
    is_range = (o.type in (mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT))
    if not is_range:
        continue
    entry = o.price_open
    sl, tp = o.sl, o.tp
    lots = c["volume"]
    pnl = c["profit"]
    mt5_range.append(dict(magic=c["magic"], sym=c["sym"], side="BUY" if o.type == mt5.ORDER_TYPE_BUY_LIMIT else "SELL",
                          entry=entry, sl=sl, tp=tp, lots=lots, pnl=pnl, ts=c["ts"],
                          comment=c["comment"], regime="mt5"))

print("[OK] state range closed=%d, mt5 range closed=%d" % (len(state_range), len(mt5_range)))

# 合并 (MT5 优先, state 补充)
rows = []
seen = set()
for r in mt5_range:
    key = (r["sym"], r["ts"], r["entry"])
    seen.add(key)
    rows.append(r)
for s in state_range:
    key = (s[2], s[8], s[4])
    if key in seen:
        continue
    rows.append(dict(magic=s[0], sym=s[2], side=s[3], entry=s[4], sl=s[5], tp=s[6],
                     lots=s[7], pnl=(s[8] or 0.0), ts=s[8] if isinstance(s[8], int) else 0,
                     comment="state", regime="state"))

print("[OK] merged range closed=%d" % len(rows))

# 归因分桶
def bucket(r):
    e, sl, tp = r["entry"], r["sl"], r["tp"]
    if not sl or not tp:
        return "no_sltp"
    risk = abs(e - sl)
    rew = abs(tp - e)
    rr = rew / risk if risk > 0 else 99
    spread_cost = 0.0
    pnl = r["pnl"]
    gross = (rew * r.get("lots", 0)) if pnl > 0 else (-risk * r.get("lots", 0))
    b = []
    if rr < 1.5:
        b.append("RR<1.5负期望")
    if pnl < 0 and (sl and ((r["side"] == "BUY" and sl <= e) or (r["side"] == "SELL" and sl >= e))):
        b.append("止损打掉")
    if rr < 0.6:
        b.append("贴脸成交")
    return ("|".join(b) if b else "正常盈利")

from collections import defaultdict
buckets = defaultdict(lambda: {"n": 0, "pnl": 0.0})
for r in rows:
    b = bucket(r)
    buckets[b]["n"] += 1
    buckets[b]["pnl"] += r["pnl"]

out = {
    "range_closed_n": len(rows),
    "buckets": {k: {"n": v["n"], "pnl": round(v["pnl"], 2)} for k, v in buckets.items()},
    "total_pnl": round(sum(r["pnl"] for r in rows), 2),
    "mt5_deals_total": len(deals),
    "mt5_range_closed": len(mt5_range),
    "state_range_closed": len(state_range),
}
jpath = ROOT + "/data/_leg_range_pnl_buckets.json"
json.dump(out, open(jpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("[OK] wrote %s" % jpath)
print(json.dumps(out, ensure_ascii=False, indent=2))
