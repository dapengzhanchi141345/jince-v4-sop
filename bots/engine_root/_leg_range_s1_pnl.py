# -*- coding: utf-8 -*-
# 震荡腿(波段)打磨五验 step1: P&L解剖 — 三state + MT5 history_deals 提取 range 已平仓单
# 只读, 不碰交易.py, 不下单. 结果 append 到 data/leg_range_polish.json['pnl归因']
import json, os, time
import numpy as np
import MetaTrader5 as mt5

ROOT = "E:/GoldstrategyEngine"
MAGICS = [20260902, 20260903, 20260904, 20260708]  # 20260708=magic占位旧批单
STATE_FILES = {
    20260902: ROOT + "/data/pending_orders_state.json",
    20260903: ROOT + "/data/crypto_pending_state.json",
    20260904: ROOT + "/data/equity_pending_state.json",
}
JP = ROOT + "/data/leg_range_polish.json"
def merge_out(rec):
    d = {}
    if os.path.exists(JP):
        try:
            d = json.load(open(JP, encoding="utf-8"))
        except Exception:
            d = {}
    d.update(rec)
    json.dump(d, open(JP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("[OK] init=%s" % mt5.initialize())
print("[OK] acct=%s" % mt5.account_info().login)

rows = []
seen = set()

# 1) MT5 history: range = LIMIT 单 (BUY/SELL_LIMIT)
ts = 0
deals = mt5.history_deals_get(ts, int(time.time())) or []
orders = mt5.history_orders_get(ts, int(time.time())) or []
o1_cache = orders
by_pos = {o.position_by_id: o for o in orders}
by_tk = {o.ticket: o for o in orders}
closed = {}
for dl in deals:
    c = closed.setdefault(dl.order, {"profit": 0.0, "vol": 0.0, "ts": dl.time,
                                     "sym": dl.symbol, "price": 0.0, "comment": dl.comment})
    c["profit"] += (dl.profit or 0) + (dl.swap or 0) + (dl.commission or 0)
    c["vol"] += dl.volume
    c["price"] = dl.price
n_mt5 = 0
# POSITION_CLOSED 单: 平仓单本身无 LIMIT 类型, 通过 comment/state 的 range 标记判腿型
STATE_RANGE_TICKETS = set()
for mg, f in STATE_FILES.items():
    if not os.path.exists(f):
        continue
    st = json.load(open(f, encoding="utf-8"))
    for tk, v in (st.get("filled") or {}).items():
        if v.get("layer") == "range":
            STATE_RANGE_TICKETS.add(str(tk))

for ot, c in closed.items():
    o = by_pos.get(ot) or by_tk.get(ot)
    is_pos_closed = o is not None and o.type in (mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL)
    is_limit = o is not None and o.type in (mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT)
    if not (is_pos_closed or is_limit):
        continue
    key = ("mt5", o.symbol, o.price_open, c["ts"])
    if key in seen:
        continue
    # POSITION_CLOSED 的平仓单 price_open=0, 开仓信息在对应 LIMIT 单里: 按 symbol+时间匹配
    if is_pos_closed:
        lim_match = next((x for x in o1_cache if x.type in (mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT)
                          and x.symbol == o.symbol and abs(int(getattr(x, "time", 0) or 0) - c["ts"]) < 86400), None)
        entry, sl, tp = float(o.price_open), float(o.sl or 0), float(o.tp or 0)
        if o.price_open == 0.0 and lim_match is not None:
            entry, sl, tp = float(lim_match.price_open), float(lim_match.sl or 0), float(lim_match.tp or 0)
    else:
        entry, sl, tp = float(o.price_open), float(o.sl or 0), float(o.tp or 0)
    key = ("mt5", o.symbol, entry, c["ts"])
    if key in seen:
        continue
    seen.add(key)
    n_mt5 += 1
    side = "BUY" if o.type in (mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_BUY_LIMIT) else "SELL"
    rows.append(dict(src="mt5", magic=int(getattr(o, "magic", 0)), sym=o.symbol,
                     side=side,
                     entry=entry, sl=sl, tp=tp, lots=float(c["vol"]),
                     pnl=round(float(c["profit"]), 4), ts=int(c["ts"]),
                     out_px=c["price"], comment=c["comment"],
                     regime=("range" if is_limit else "mt5-posclosed")))

# 2) state filled: layer==range (MT5 对不上的补进来)
n_st = 0
for mg, f in STATE_FILES.items():
    if not os.path.exists(f):
        continue
    d = json.load(open(f, encoding="utf-8"))
    for tk, v in (d.get("filled") or {}).items():
        if v.get("layer") != "range":
            continue
        st = v.get("status")
        # 只收已平仓: status==closed 或 pnl 已有且 MT5 查无此单(孤儿账)
        if st not in ("closed", None):
            continue
        key = ("mt5", v.get("sym"), v.get("fill_px") or v.get("entry"), None)
        if key in seen or (v.get("mt5_ticket") and ("mt5", v.get("mt5_ticket")) in seen):
            continue
        # 与 MT5 行按 ticket 去重
        if v.get("mt5_ticket") and any(r.get("src") == "mt5" and str(r.get("ts")) == str(v.get("mt5_ticket")) for r in rows):
            continue
        e = float(v.get("entry") or v.get("fill_px") or 0)
        sl = float(v.get("sl") or 0); tp = float(v.get("tp") or 0)
        pnl = v.get("last_pnl") if st == "closed" else None
        rows.append(dict(src="state", magic=mg, sym=v.get("sym"), side=v.get("side"),
                         entry=e, sl=sl, tp=tp, lots=float(v.get("lots") or 0),
                         pnl=(round(float(pnl), 4) if pnl is not None else None),
                         ts=int(v.get("filled_ts") or 0), out_px=None,
                         comment="state:%s" % st, regime=v.get("regime", "state")))
        n_st += 1
print("[OK] mt5_range_closed=%d state_extra=%d merged=%d" % (n_mt5, n_st, len(rows)))

# ── 分桶归因 ──
def bucket(r):
    e, sl, tp, pnl = r["entry"], r["sl"], r["tp"], r["pnl"]
    if not sl or not tp or e <= 0:
        return "无SLTP"
    risk = abs(e - sl); rew = abs(tp - e)
    rr = rew / risk if risk > 0 else 99
    tags = []
    if rr < 1.5:
        tags.append("RR<1.5负期望")
    if pnl is not None and pnl < 0:
        if r["side"] == "BUY" and sl <= e:
            tags.append("止损打掉")
        elif r["side"] == "SELL" and sl >= e:
            tags.append("止损打掉")
    if r.get("out_px") and abs(r["out_px"] - e) <= 3 * (e * 1e-6 + 1e-12) and pnl is not None and pnl < 0:
        tags.append("贴脸成交")
    if pnl is not None and pnl > 0 and rr < 0.6:
        tags.append("点差侵蚀")
    return "|".join(tags) if tags else "正常盈利"

from collections import defaultdict
buckets = defaultdict(lambda: {"n": 0, "pnl": 0.0, "pnl_set": 0})
for r in rows:
    b = bucket(r)
    buckets[b]["n"] += 1
    if r["pnl"] is not None:
        buckets[b]["pnl"] += r["pnl"]
        buckets[b]["pnl_set"] += 1

closed_rows = [r for r in rows if r["pnl"] is not None]
pnl_bucket = {k: {"n": v["n"], "pnl": round(v["pnl"], 2), "pnl_set": v["pnl_set"]} for k, v in buckets.items()}
out = {
    "ts": int(time.time()),
    "range_closed_n": len(rows),
    "range_closed_pnl_set": len(closed_rows),
    "buckets": pnl_bucket,
    "total_pnl": round(sum(r["pnl"] for r in closed_rows), 2),
    "mt5_deals_total": len(deals),
    "mt5_range_closed": n_mt5,
    "state_extra": n_st,
    "note": "MT5 LIMIT单为主, state补孤儿; pnl_set=有已实现盈亏的票数",
}
merge_out({"pnl归因": out})
print("[OK] wrote %s" % JP)
print(json.dumps(out, ensure_ascii=False))
mt5.shutdown()
