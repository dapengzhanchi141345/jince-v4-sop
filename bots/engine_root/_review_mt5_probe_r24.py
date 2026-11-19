# -*- coding: utf-8 -*-
"""R24 复盘只读探针: 账户/持仓/近2日成交"""
import sys, json
from datetime import datetime, timedelta
import MetaTrader5 as mt5

out = {"connect": False}
if not mt5.initialize():
    out["error"] = str(mt5.last_error())
    print(json.dumps(out, ensure_ascii=False)); sys.exit(0)
out["connect"] = True
ai = mt5.account_info()
if ai:
    out["account"] = {"login": ai.login, "server": ai.server, "balance": ai.balance,
                      "equity": ai.equity, "margin": ai.margin,
                      "trade_allowed": ai.trade_expert_allowed if hasattr(ai,'trade_expert_allowed') else None}
    ti = mt5.terminal_info()
    out["terminal_trade_allowed"] = ti.trade_allowed if ti else None
pos = mt5.positions_get()
out["positions"] = []
if pos:
    for p in pos:
        out["positions"].append({"ticket": p.ticket, "symbol": p.symbol,
            "type": "BUY" if p.type == 0 else "SELL", "volume": p.volume,
            "price_open": p.price_open, "price_current": p.price_current,
            "sl": p.sl, "tp": p.tp, "profit": p.profit,
            "time": datetime.fromtimestamp(p.time).strftime("%Y-%m-%d %H:%M:%S")})
now = datetime.now()
deals = mt5.history_deals_get(now - timedelta(days=2), now + timedelta(hours=3))
out["deals_2d"] = []
if deals:
    for d in deals:
        if d.symbol:
            out["deals_2d"].append({"ticket": d.ticket, "symbol": d.symbol,
                "type": d.type, "entry": d.entry, "volume": d.volume,
                "price": d.price, "profit": d.profit, "swap": d.swap, "fee": d.commission,
                "time": datetime.fromtimestamp(d.time).strftime("%Y-%m-%d %H:%M:%S")})
mt5.shutdown()
print(json.dumps(out, ensure_ascii=False, indent=1))
