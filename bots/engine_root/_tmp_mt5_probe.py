import MetaTrader5 as mt5
from datetime import datetime, timedelta
import sys
if not mt5.initialize():
    print("INIT_FAIL", mt5.last_error()); sys.exit(1)
ai = mt5.account_info()
print(f"ACCOUNT={ai.login} BAL={ai.balance:.2f} EQ={ai.equity:.2f} FREE={ai.margin_free:.2f} TRADE_ALLOWED={ai.trade_allowed} SERVER={ai.server}")
pos = mt5.positions_get()
print("POSITIONS=", 0 if pos is None else len(pos))
if pos:
    for p in pos:
        print(f"  {p.symbol} {'BUY' if p.type==0 else 'SELL'} vol={p.volume:.2f} open={p.price_open} cur={p.price_current} pnl={p.profit:.2f}")
now = datetime.now()
for days,label in [(2,'2D'),(7,'7D'),(14,'14D'),(45,'45D')]:
    dl = mt5.history_deals_get(now - timedelta(days=days), now + timedelta(hours=6))
    n = 0 if dl is None else len([d for d in dl if d.entry in (0,1)])
    print(f"DEALS_{label}={n}")
dl = mt5.history_deals_get(now - timedelta(days=60), now + timedelta(hours=6))
if dl:
    outs=[d for d in dl if d.entry==1]
    if outs:
        last=outs[-1]
        t=datetime.fromtimestamp(last.time)
        print(f"LAST_CLOSE={last.symbol} {t} pnl={last.profit:.2f}")
        delta=now-t
        print(f"HOURS_SINCE_LAST={delta.total_seconds()/3600:.2f} DAYS={delta.days}")
        # PF/WR over closed deals
        wins=[d.profit for d in outs if d.profit>0]; loss=[d.profit for d in outs if d.profit<=0]
        gp=sum(wins); gl=abs(sum(loss))
        print(f"60D_CLOSED={len(outs)} WR={len(wins)/len(outs)*100:.2f}% GP={gp:.2f} GL={gl:.2f} PF={(gp/gl if gl else 0):.4f}")
mt5.shutdown()
