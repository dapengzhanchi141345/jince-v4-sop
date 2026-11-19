
import MetaTrader5 as mt5, datetime
ok = mt5.initialize()
before = [(o.ticket, o.symbol) for o in (mt5.orders_get() or [])]
print("现在 pending:", before)
acc = mt5.account_info()
print("equity=%s balance=%s positions=%s" % (round(acc.equity,2), round(acc.balance,2), mt5.positions_total()))
print("=== 撤单 deal 留痕(DEAL_TYPE_DELETE, 账实唯一源验) ===")
t0 = int(datetime.datetime(2026,10,14).timestamp()); t1 = int(datetime.datetime.now().timestamp())
deals = mt5.history_deals_get(t0, t1) or []
dels = [d for d in deals if getattr(d, "type", -1) == mt5.DEAL_TYPE_DELETE]
for d in dels:
    print("DELETE deal: ticket=%s symbol=%s reason=%s time=%s" % (d.ticket, d.symbol, d.reason, datetime.datetime.fromtimestamp(d.time).strftime("%m-%d %H:%M:%S")))
if not dels:
    print("(无 DELETE 留痕 => 撤单可能未成交, 需查 res.retcode)")
print("606433838 还在不在 pending:", any(o.ticket==606433838 for o in (mt5.orders_get() or [])))
mt5.shutdown()
