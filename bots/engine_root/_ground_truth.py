
# -*- coding: utf-8 -*-
# Ground-truth 裁判: MT5 全历史成交单(按magic全量扫) + state 账本对账
import json, datetime, os
import MetaTrader5 as mt5
mt5.initialize(); assert mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
now = int(datetime.datetime.now().timestamp())
start = now - 120*86400
deals = mt5.history_deals_get(start, now)
print(f"MT5 成交单总数(120天): {0 if deals is None else len(deals)}")
OUT = 2
by_magic = {}
if deals:
    for d in deals:
        m = d.magic
        g = by_magic.setdefault(m, {"n_all":0, "n_closed":0, "pnl_closed":0.0, "syms":set()})
        g["n_all"] += 1
        g["syms"].add(d.symbol)
        if d.entry == OUT:
            g["n_closed"] += 1
            g["pnl_closed"] += d.profit + d.swap + d.commission
for m, g in sorted(by_magic.items()):
    print(f"magic={m}: 单{g['n_all']} 平仓{g['n_closed']} 平仓P&L={g['pnl_closed']:+.2f} 品种={sorted(g['syms'])[:8]}")
# 本系统 magic 明细
mine = [d for d in (deals or []) if d.magic == 20260903]
print(f"\n本系统(magic=20260903) 成交单: {len(mine)}")
for d in sorted(mine, key=lambda x: x.time)[:60]:
    tag = "OUT" if d.entry == OUT else "IN"
    print(f"  {tag} {d.symbol} {d.type} px={d.price:.5g} pnl={d.profit:+.2f} {datetime.datetime.utcfromtimestamp(d.time)} cmt={d.comment!r}")
# state 账本
p = "E:/GoldstrategyEngine/data/crypto_pending_state.json"
if os.path.exists(p):
    st = json.load(open(p, encoding="utf-8"))
    filled = st.get("filled", {})
    from collections import defaultdict
    agg = defaultdict(lambda: [0, 0.0])
    for f in filled.values():
        layer = f.get("layer", "?")
        s = f.get("status", "?")
        agg[(layer, s)][0] += 1
        agg[(layer, s)][1] += float(f.get("last_pnl") or 0)
    print("\nstate 账本 filled 分桶 (layer, status): n / 末次浮盈亏")
    for k in sorted(agg): print("  ", k, agg[k])
print("\n当前持仓:", [f"{p_.symbol}{p_.volume}" for p_ in (mt5.positions_get() or [])][:20])
mt5.shutdown()
