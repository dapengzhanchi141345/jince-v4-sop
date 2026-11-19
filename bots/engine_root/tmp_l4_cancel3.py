
import MetaTrader5 as mt5, datetime
ok = mt5.initialize()
print("mt5 init:", ok)
before = [(o.ticket, o.symbol) for o in (mt5.orders_get() or [])]
print("撤单前 pending:", before)
res = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": 606433838, "magic": 0})
print("retcode:", res.retcode, "|", mt5.result_retcode_description(res.retcode), "| order:", res.order)
after = [(o.ticket, o.symbol) for o in (mt5.orders_get() or [])]
print("撤单后 pending:", after)
acc = mt5.account_info()
print("equity=%s balance=%s positions=%s" % (round(acc.equity,2), round(acc.balance,2), mt5.positions_total()))
# deal 验撤单留痕(账实唯一源)
deals = mt5.history_deals_get(int(datetime.datetime(2026,10,14).timestamp()), int(datetime.datetime.now().timestamp())) or []
xd = [x for x in deals if x.entry == mt5.DEAL_ENTRY_OUT or getattr(x, "type", -1) == mt5.DEAL_TYPE_DELETE]
print("今日 DEAL_TYPE_DELETE 留痕:", [ (d.ticket, d.symbol, d.reason, d.time) for d in deals if getattr(d, "type", -1) == mt5.DEAL_TYPE_DELETE ])
mt5.shutdown()
