import sys, datetime
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')
try:
    import MetaTrader5 as mt5
except Exception as e:
    print("IMPORT_FAIL:"+repr(e)); sys.exit(2)
ok = mt5.initialize()
if not ok:
    print("INIT_FAIL last_error=", mt5.last_error()); sys.exit(3)
acct = mt5.account_info()
if acct:
    d = acct._asdict()
    print("ACCOUNT balance=%.2f equity=%.2f trade_allowed=%s login=%s server=%s" % (d.get('balance'), d.get('equity'), d.get('trade_allowed'), d.get('login'), d.get('server')))
pos = mt5.positions_get()
print("OPEN_POSITIONS_COUNT:", len(pos) if pos else 0)
for p in (pos or []):
    print("POS ticket=%d symbol=%s type=%s volume=%.2f open=%.5f sl=%.5f tp=%.5f profit=%.2f" % (p.ticket, p.symbol, p.type, p.volume, p.price_open, p.sl, p.tp, p.profit))
now = datetime.datetime.now()
from_ts = int((now - datetime.timedelta(days=2)).timestamp())
to_ts = int(now.timestamp())
deals = mt5.history_deals_get(from_ts, to_ts)
print("DEALS_2D_COUNT:", len(deals) if deals else 0)
agg = defaultdict(lambda: {'pnl':0.0,'cnt':0,'won':0})
last_time=0
for dl in (deals or []):
    agg[dl.symbol]['cnt']+=1; agg[dl.symbol]['pnl']+=dl.profit
    if dl.profit>0: agg[dl.symbol]['won']+=1
    if int(dl.time)>last_time: last_time=int(dl.time)
for s,v in agg.items():
    print("DEAL symbol=%s cnt=%d pnl=%.2f won=%d" % (s, v['cnt'], v['pnl'], v['won']))
if last_time: print("LAST_DEAL_TIME:", datetime.datetime.fromtimestamp(last_time).isoformat())
mt5.shutdown()
print("DONE")
