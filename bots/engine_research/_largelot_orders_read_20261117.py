# -*- coding: utf-8 -*-
"""_largelot_orders_read_20261117.py — MT5 只读: 1.0手通道 m20261105 30d 4单 精确开平仓
红线: 只 history_deals_get/account_info, 0下单 0改设置. 产物 data/rd_largelot_orders_mt5_20261117.json
"""
import os, json, datetime as dt
os.environ['MT5_TERMINAL'] = r'C:\Program Files\TMGM MT5 Terminal\terminal64.exe'
os.environ['MT5_LOGIN'] = '60137964'
import MetaTrader5 as mt5

ROOT = "E:/GoldstrategyEngine"
out = {'ts': dt.datetime.now().strftime('%F %T'), 'ok': False}
if mt5.initialize(timeout=15000):
    out['ok'] = True
    acc = mt5.account_info()
    out['equity'] = acc.equity if acc else None
    now = dt.datetime.now()
    start = now - dt.timedelta(days=35)
    deals = mt5.history_deals_get(start, now) or []
    out['deals_total_35d'] = len(deals)
    orders_all = mt5.history_orders_get(start, now) or []
    o_sltp = {int(o.ticket): (float(o.sl) if o.sl else None,
                               float(o.tp) if o.tp else None) for o in orders_all}
    rows = []
    for d in deals:
        if getattr(d, 'magic', 0) == 20261105 and (getattr(d, 'volume', 0) or 0) >= 1.0:
            base = {'ticket': int(d.ticket), 'position': int(getattr(d, 'position', 0)),
                    'order': int(getattr(d, 'order', 0)),
                    'type': 'BUY' if int(d.type) == 0 else 'SELL',
                    'entry': 'IN' if int(getattr(d, 'entry', 0)) == 0 else ('OUT' if int(getattr(d, 'entry', 0)) == 1 else str(getattr(d, 'entry', ''))),
                    'sym': d.symbol, 'vol': float(d.volume), 'px': float(d.price),
                    'profit': float(d.profit), 'time': int(d.time),
                    'bjt': dt.datetime.fromtimestamp(int(d.time)).strftime('%m-%d %H:%M')}
            s_t = o_sltp.get(base['order'])
            if s_t:
                base['sl'], base['tp'] = s_t
            rows.append(base)
    out['orders_1lot'] = rows
    json.dump(out, open(os.path.join(ROOT, 'data/rd_largelot_orders_mt5_20261117.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=float)
    print('WROTE', out['deals_total_35d'], 'deals,', len(rows), '1.0-lot rows')
    for r in rows:
        print(r['bjt'], r['sym'], r['entry'], r['type'], r['px'], 'sl=', r['sl'], 'tp=', r['tp'], 'pnl=', r['profit'])
    mt5.shutdown()
else:
    out['err'] = str(mt5.last_error())
    print('MT5 INIT FAIL', out['err'])
    json.dump(out, open(os.path.join(ROOT, 'data/rd_largelot_orders_mt5_20261117.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
