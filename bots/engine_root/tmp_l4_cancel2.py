
import MetaTrader5 as mt5
ok = mt5.initialize()
ords = mt5.orders_get() or []
print("撤单前 pending:", [ (o.ticket, o.symbol) for o in ords ])
res = mt5.order_send({"action": mt5.TRADE_ACTION_DEALT, "symbol": "XAUUSD", "volume": 0.0,
                      "type": mt5.ORDER_TYPE_REMOVE, "order": 606433838, "price": 0, "sl": 0, "tp": 0, "comment": "L4 zombie cancel"})
print("retcode:", res.retcode, mt5.result_retcode_description(res.retcode))
ords2 = mt5.orders_get() or []
print("撤单后 pending:", [ (o.ticket, o.symbol) for o in ords2 ])
acc = mt5.account_info()
print("equity=%s balance=%s positions=%s" % (round(acc.equity,2), round(acc.balance,2), len(mt5.positions_total())))
mt5.shutdown()
