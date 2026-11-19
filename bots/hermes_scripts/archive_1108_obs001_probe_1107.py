# 重启终端后验开关 + 试单 (李彦明11-07令: 全部解冻落地)
import MetaTrader5 as mt5
if not mt5.initialize():
    print("INIT_FAIL:", mt5.last_error()); raise SystemExit
ti = mt5.terminal_info()
print("终端: trade_allowed=%s tradeapi_disabled=%s connected=%s" % (ti.trade_allowed, ti.tradeapi_disabled, ti.connected))
si = mt5.symbol_info("BTCUSD")
ask = si.ask; sl = round(ask * 0.995, si.digits); tp = round(ask * 1.015, si.digits)
r = mt5.order_send({"action": 0, "symbol": "BTCUSD", "volume": 0.01, "type": 1,
                    "price": ask, "sl": sl, "tp": tp, "deviation": 20,
                    "magic": 30261106, "comment": "obs001_1107", "type_time": 0, "type_filling": 1})
print("BTC 0.01手: retcode=%s deal=%s | %s" % (r.retcode, r.deal, r.comment))
if r.retcode in (10008, 10009, 10010):
    si2 = mt5.symbol_info("ETHUSD"); a2 = si2.ask
    r2 = mt5.order_send({"action": 0, "symbol": "ETHUSD", "volume": 0.01, "type": 1,
                         "price": a2, "sl": round(a2 * 0.995, si2.digits),
                         "tp": round(a2 * 1.015, si2.digits), "deviation": 20,
                         "magic": 30261106, "comment": "obs002_1107", "type_time": 0, "type_filling": 1})
    print("ETH 0.01手: retcode=%s deal=%s | %s" % (r2.retcode, r2.deal, r2.comment))
mt5.shutdown()
