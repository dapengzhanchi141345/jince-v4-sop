# -*- coding: utf-8 -*-
# 只读晨报脚本：实读MT5账户与持仓，不写任何交易操作
import sys, io, json, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, r"E:/资料/GoldstrategyEngine/pylibs")
import MetaTrader5 as mt5

ok = mt5.initialize()
if not ok:
    print(json.dumps({"error": "MT5 initialize failed: %s" % str(mt5.last_error())}, ensure_ascii=False))
    sys.exit(1)

acc = mt5.account_info()
info = {
    "server": acc.server if acc else None,
    "login": acc.login if acc else None,
    "balance": acc.balance if acc else None,
    "equity": acc.equity if acc else None,
    "floating": acc.profit if acc else None,
    "margin": acc.margin if acc else None,
}
pos = mt5.positions_get()
plist = []
if pos:
    for p in pos:
        t = mt5.symbol_info_tick(p.symbol)
        cur = (t.bid + t.ask) / 2 if t else None
        plist.append({
            "symbol": p.symbol, "dir": "BUY" if p.type == 0 else "SELL",
            "ticket": p.ticket, "magic": p.magic,
            "entry": p.price_open, "cur": cur,
            "sl": p.sl, "tp": p.tp, "profit": p.profit,
        })
info["positions"] = plist
info["terminal"] = "ok"
print(json.dumps(info, ensure_ascii=False, indent=1))
mt5.shutdown()
