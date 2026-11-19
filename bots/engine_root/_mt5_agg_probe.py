import json
from collections import Counter, defaultdict
try:
    import MetaTrader5 as mt5
except Exception as e:
    print(json.dumps({"error":str(e)})); raise SystemExit
mt5.initialize()
from datetime import datetime, timedelta
now = datetime.now()
t2 = now - timedelta(days=2)
deals = mt5.history_deals_get(t2, now) or []
by_sym = Counter()
by_magic = Counter()
open_deals = 0
closed_pnl = 0.0
for d in deals:
    sym = d.symbol
    by_sym[sym]+=1
    by_magic[str(d.magic)]+=1
    if d.entry==1:  # 1=closed/entry in, 0=out... use entry flag
        pass
    closed_pnl += d.profit
# 区分开平仓: entry 0=BUY/SELL open, 1=close. 简化: profit累计=已实现
out = {
  "deals_total": len(deals),
  "by_symbol_top": by_sym.most_common(20),
  "by_magic": dict(by_magic),
  "realized_pnl_2d": round(closed_pnl,2),
  "window": [t2.strftime("%Y-%m-%d %H:%M"), now.strftime("%Y-%m-%d %H:%M")]
}
print(json.dumps(out, ensure_ascii=False))
