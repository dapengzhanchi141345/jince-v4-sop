import sys, pickle, numpy as np
sys.path.insert(0, '.')
import sd_opt_grid_20261115 as G
grids = {}
for sym in ['XAUUSD','EURUSD','BTCUSD','ETHUSD','SOLUSD','XRPUSD','LTCUSD','BNBUSD']:
    d = pickle.load(open('ev_cache/' + sym + '.pkl','rb'))
    t,c,h,l,o,ev = d['t'],d['c'],d['h'],d['l'],d['o'],d['ev']
    G.attach_zone_h(t,h,l,ev)
    grids[sym] = (t,c,h,l,o,ev)
for combo in ['E3+S1','E3+S7','E2+S1']:
    E, S = combo.split('+')
    allrs = []
    for sym,(t,c,h,l,o,ev) in grids.items():
        allrs.extend(G.settle(ev,t,c,h,l,o,E,S,sym))
    allrs = [r for r in allrs if r != 0]
    mx_consec, cur = 0, 0
    for r in allrs:
        cur = cur + 1 if r < 0 else 0
        mx_consec = max(mx_consec, cur)
    eq, peak, mdd = 0, 0, 0.0
    for r in allrs:
        eq += r
        peak = max(peak, eq)
        mdd = max(mdd, peak - eq)
    print('%s: 有效单=%d 净R=%.0f 最大连亏=%d笔 最大回撤=%.1fR 亏损单占比=%.1f%%' % (
        combo, len(allrs), float(np.sum(allrs)), mx_consec, mdd, 100*sum(1 for r in allrs if r<0)/len(allrs)))
