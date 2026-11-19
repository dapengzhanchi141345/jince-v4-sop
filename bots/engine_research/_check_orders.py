import json, glob
import MetaTrader5 as mt5
from collections import Counter
mt5.initialize()
lines = [json.loads(l) for l in open(glob.glob('sd_place_log_*.json')[-1], encoding='utf-8')]
ok = [l for l in lines if l['status']=='placed']
fail = [l for l in lines if l['status']=='failed']
print('挂成功 %d 单:' % len(ok))
for l in ok: print('  %s %s %s SL=%s TP=%s' % (l['sym'], l['side'], l['price'], l['sl'], l['tp']))
print('失败 %d 单 rc 分布:' % len(fail), Counter(l['rc'] for l in fail))
for sym in sorted(set(l['sym'] for l in fail)):
    info = mt5.symbol_info(sym)
    if info:
        print('%-8s stops_level=%s点 point=%.5f' % (sym, info.trade_stops, info.point))
    else:
        print(sym, 'INFO FAIL', mt5.last_error())
