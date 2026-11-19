import MetaTrader5 as mt5, json, sys
from datetime import datetime, timedelta
if not mt5.initialize():
    print(json.dumps({"connect": False, "err": str(mt5.last_error())})); sys.exit(0)
ai = mt5.account_info()
acc = {"login": ai.login, "server": ai.server, "balance": ai.balance, "equity": ai.equity,
       "trade_allowed": bool(ai.trade_allowed)} if ai else None
poss = mt5.positions_get() or []
positions = [{"ticket": p.ticket, "symbol": p.symbol, "type": "BUY" if p.type==0 else "SELL",
              "volume": p.volume, "price_open": p.price_open, "price_current": p.price_current,
              "sl": p.sl, "tp": p.tp, "profit": p.profit,
              "time": datetime.fromtimestamp(p.time).strftime("%Y-%m-%d %H:%M:%S")} for p in poss]
frm = datetime.now() - timedelta(days=2)
deals = mt5.history_deals_get(frm, datetime.now()+timedelta(hours=3)) or []
dl = [{"ticket": d.ticket, "symbol": d.symbol, "type": d.type, "entry": d.entry,
       "volume": d.volume, "price": d.price, "profit": d.profit,
       "time": datetime.fromtimestamp(d.time).strftime("%Y-%m-%d %H:%M:%S")} for d in deals if d.symbol]
print(json.dumps({"connect": True, "account": acc, "positions": positions, "deals_2d": dl}, ensure_ascii=False, indent=1))
mt5.shutdown()
