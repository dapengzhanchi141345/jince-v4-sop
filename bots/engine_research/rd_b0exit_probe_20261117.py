# -*- coding: utf-8 -*-
"""rd_b0exit_probe_20261117.py — MT5 只读探测: 连通性/品种名/history_orders 计数(红线前置)/deals 20261105
纯只读: 无任何 order_send / 改设置 / 改引擎. 输出 JSON 到 stdout."""
import os, json, datetime as dt, time
os.environ['MT5_TERMINAL'] = r'C:\Program Files\TMGM MT5 Terminal\terminal64.exe'
os.environ['MT5_LOGIN'] = '60137964'
import MetaTrader5 as mt5

ok = mt5.initialize(timeout=15000)
out = {'ok': bool(ok), 'now_local': dt.datetime.now().strftime('%F %T')}
if ok:
    try:
        acc = mt5.account_info()
        out['login'] = acc.login if acc else None
        out['equity'] = acc.equity if acc else None
    except Exception as e:
        out['acc_err'] = str(e)
    # 品种实查
    names = ['XAUUSD','EURUSD','GBPUSD','US30','US30USD','US30.US','BTCUSD','ETHUSD','SOLUSD','XRPUSD',
             'BLK.NYS','KLAC.NAS','AVGO.NAS','TSLA.NAS']
    found = {}
    for n in names:
        si = mt5.symbol_info(n)
        if si is not None:
            found[n] = {'digits': si.digits, 'point': si.point, 'visible': si.visible}
    # 模糊找 US30 族
    syms = mt5.symbols_get() or []
    us30s = [s.name for s in syms if 'US30' in s.name]
    found['US30_family_probe'] = us30s[:20]
    out['symbols'] = found
    # 红线前置计数: history_orders_get (只读)
    now = dt.datetime.now()
    start = now - dt.timedelta(days=60)
    orders = mt5.history_orders_get(start, now) or []
    out['history_orders_n_60d'] = len(orders)
    # K线通道核验: 枚举值 M15=15, M30=30, D1=1440 (MQL5 ENUM_TIMEFRAMES)
    for label, tfv, sym in (('M15_XAUUSD', 15, 'XAUUSD'), ('M30_XAUUSD', 30, 'XAUUSD'), ('D1_XAUUSD', 1440, 'XAUUSD')):
        try:
            rr = mt5.copy_rates_range(sym, tfv, start, now)
            if rr is None:
                out['kline_'+label] = {'err': mt5.last_error(), 'n': 0}
            else:
                out['kline_'+label] = {'n': len(rr), 'first': int(rr[0]['time']), 'last': int(rr[-1]['time'])}
        except Exception as e:
            out['kline_'+label] = {'err': str(e)}
    mt5.shutdown()
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
