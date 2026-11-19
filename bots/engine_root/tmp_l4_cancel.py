
import json, os, datetime
import MetaTrader5 as mt5
d = "E:/GoldstrategyEngine/data"
ok = mt5.initialize()
print("mt5 init:", ok)
ords = mt5.orders_get() or []
print("撤单前 pending:", len(ords), [o.ticket for o in ords])
res = mt5.order_send({"action": mt5.ORDER_TYPE_BUY, "symbol": "XAUUSD", "volume": 0,
                      "type": mt5.ORDER_TYPE_DELETE, "order": 606433838, "price": 0, "sl": 0, "tp": 0, "comment": "L4 cancel zombie"})
print("order_send 删除结果:", res, "retcode:", res.retcode, mt5.result_retcode_description(res.retcode))
ords2 = mt5.orders_get() or []
print("撤单后 pending:", len(ords2), [o.ticket for o in ords2])
acc = mt5.account_info()
print("equity=%s balance=%s" % (round(acc.equity,2), round(acc.balance,2)))
mt5.shutdown()
