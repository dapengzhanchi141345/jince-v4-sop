import json, datetime as dt
from collections import defaultdict
import MetaTrader5 as mt5

mt5.initialize()
now = dt.datetime.now()
res = {}
for label, days in (('30d', 30), ('45d', 45), ('60d', 60)):
    ds = mt5.history_deals_get(now - dt.timedelta(days=days), now) or []
    closes = [d for d in ds if d.entry == 1]
    per = defaultdict(lambda: {'n': 0, 'win': 0, 'gp': 0.0, 'gl': 0.0, 'net': 0.0})
    for d in closes:
        p = d.profit + d.commission + d.swap
        r = per[d.symbol]
        r['n'] += 1
        r['net'] += p
        if p > 0:
            r['win'] += 1
            r['gp'] += p
        else:
            r['gl'] += -p
    tot = {'n': 0, 'win': 0, 'gp': 0.0, 'gl': 0.0}
    for s, r in per.items():
        r['net'] = round(r['net'], 2)
        r['gp'] = round(r['gp'], 2)
        r['gl'] = round(r['gl'], 2)
        r['pf'] = round(r['gp'] / r['gl'], 4) if r['gl'] > 0 else None
        r['wr'] = round(r['win'] / r['n'], 4) if r['n'] else None
        tot['n'] += r['n']; tot['win'] += r['win']; tot['gp'] += r['gp']; tot['gl'] += r['gl']
    tot['pf'] = round(tot['gp'] / tot['gl'], 4) if tot['gl'] > 0 else None
    tot['wr'] = round(tot['win'] / tot['n'], 4) if tot['n'] else None
    tot['net'] = round(tot['gp'] - tot['gl'], 2)
    res[label] = {'total': tot, 'per_symbol': dict(per)}
    if label == '30d':
        res['30d_closes_detail'] = [
            {'time': str(dt.datetime.fromtimestamp(d.time)), 'sym': d.symbol,
             'pnl': round(d.profit + d.commission + d.swap, 2)} for d in closes]
mt5.shutdown()
print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
