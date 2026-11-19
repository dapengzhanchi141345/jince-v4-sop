
import time
import MetaTrader5 as mt5
assert mt5.initialize(), "mt5 init failed"
info = mt5.terminal_info()
print("terminal build:", getattr(info, "build", None))
orders = mt5.orders_get() or []
print("orders_get 现值:", len(orders))
for o in orders:
    print("  order:", o.ticket, o.symbol, "type", o.type, "vol", o.volume_current,
          "price", o.price_open, "sl", o.sl, "tp", o.tp, "magic", o.magic, "comment", (o.comment or "")[:30])
pos = mt5.positions_get() or []
print("positions_get:", len(pos))
for p in pos:
    print("  pos:", p.ticket, p.symbol, p.type, p.volume, p.price_open, p.sl, p.tp, p.magic)
mt5.shutdown()
