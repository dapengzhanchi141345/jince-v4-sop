
import MetaTrader5 as mt5
mt5.initialize(); assert mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
for tf,name in [(mt5.TIMEFRAME_H1,"H1"),(mt5.TIMEFRAME_H4,"H4"),(mt5.TIMEFRAME_M30,"M30"),(mt5.TIMEFRAME_M15,"M15")]:
    r = mt5.copy_rates_from_pos("BTCUSD", tf, 0, 50000)
    import datetime
    first = datetime.datetime.utcfromtimestamp(r["time"][0]) if r is not None and len(r) else None
    print(name, 0 if r is None else len(r), "bars", first)
mt5.shutdown()
