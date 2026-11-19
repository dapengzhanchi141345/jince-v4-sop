import MetaTrader5 as mt5
import json, datetime

LIVE_TERM = r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe"
if not mt5.initialize(path=LIVE_TERM, timeout=10000):
    print("MT5_INIT_FAIL", mt5.last_error())
    raise SystemExit(0)

info = mt5.account_info()
acc = None
if info:
    d = info._asdict()
    acc = {k: d.get(k) for k in ('login','server','balance','equity','margin','margin_level','leverage','trade_mode')}

pos = mt5.positions_get()
positions = []
if pos:
    for p in pos:
        positions.append({
            'ticket': p.ticket, 'symbol': p.symbol,
            'type': 'BUY' if p.type == 0 else 'SELL',
            'volume': round(p.volume, 2), 'open_price': p.price_open,
            'sl': p.sl, 'tp': p.tp, 'profit': round(p.profit, 2),
            'open_time': datetime.datetime.fromtimestamp(p.time).strftime('%Y-%m-%d %H:%M')
        })

# pending orders
ords = mt5.orders_get()
orders = []
if ords:
    for o in ords:
        orders.append({'ticket': o.ticket, 'symbol': o.symbol,
                       'type': o.type, 'volume': round(getattr(o, 'volume_initial', 0) or 0, 2),
                       'price': o.price_open, 'sl': o.sl, 'tp': o.tp})

now = datetime.datetime.now()
from_ts = int((now - datetime.timedelta(days=2)).timestamp())
to_ts = int(now.timestamp())
deals = mt5.history_deals_get(from_ts, to_ts)
agg = {}; net = 0.0; wins = 0; nclose = 0
if deals:
    for d in deals:
        if d.type != 1:
            continue
        nclose += 1; net += d.profit
        if d.profit > 0:
            wins += 1
        a = agg.setdefault(d.symbol, {'n': 0, 'profit': 0.0, 'vol': 0.0})
        a['n'] += 1; a['profit'] += d.profit; a['vol'] += d.volume

# open orders (history_orders) last 2d to see entry activity
horders = mt5.history_orders_get(from_ts, to_ts)
open_act = {}
if horders:
    for o in horders:
        if o.type in (0, 1):  # ORDER_TYPE_BUY / SELL (pending filled or market)
            open_act.setdefault(o.symbol, 0)
            open_act[o.symbol] += 1

# current XAUUSD bid
si = mt5.symbol_info('XAUUSD')
xau_bid = si.bid if si else None

out = {
    'terminal_path': LIVE_TERM,
    'account': acc,
    'positions_count': len(positions),
    'positions': positions,
    'pending_orders': orders,
    'xauusd_bid': xau_bid,
    'deals_2d': {
        'closing_deals': nclose,
        'net_profit': round(net, 2),
        'win_rate': round(wins / nclose, 4) if nclose else None,
        'by_symbol': {k: {'n': v['n'], 'profit': round(v['profit'], 2), 'vol': round(v['vol'], 2)} for k, v in agg.items()}
    },
    'orders_2d_entry_attempts_by_symbol': open_act
}
print("MT5_PROBE_JSON_START")
print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
print("MT5_PROBE_JSON_END")
# intentionally NOT calling mt5.shutdown() — avoid killing live's shared terminal connection
