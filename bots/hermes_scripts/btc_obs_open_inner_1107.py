
import MetaTrader5 as mt5, json, datetime, time
if not mt5.initialize():
    print("UNLOCK_SENT: INIT_FAIL %s" % str(mt5.last_error())); raise SystemExit
si = mt5.symbol_info("BTCUSD")
tm = si.trade_mode if si else -1
if tm != 1:
    print("UNLOCK_SENT: STILL_CLOSE_ONLY tm=%s 15min后再查" % tm); raise SystemExit
# 放开了: 读现价+开0.01手
px = mt5.symbol_info_tick("BTCUSD") if hasattr(mt5, "symbol_info_tick") else None
si2 = mt5.symbol_info("BTCUSD")
ask = si2.ask; bid = si2.bid
sl = round(ask * 0.995, 2)   # 12h观察腿, 0.5%止损
tp = round(ask * 1.015, 2)   # 3%目标 RR=6
res = mt5.order_send({"action": 0, "symbol": "BTCUSD", "volume": 0.01,
                      "type": 1, "price": ask, "sl": sl, "tp": tp,
                      "deviation": 20, "magic": 30261106,
                      "comment": "btc_obs001_1107", "type_time": 0, "type_filling": 0})
print("UNLOCK_SENT: OPEN_DONE retcode=%s deal=%s ask=%s sl=%s tp=%s" %
      (res.retcode if res else "None", res.deal if res else "-", ask, sl, tp))
mt5.shutdown()
