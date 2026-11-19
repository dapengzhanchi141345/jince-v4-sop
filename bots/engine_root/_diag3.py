import sys, pickle
import numpy as np
sys.path.insert(0, r"E:\GoldstrategyEngine")
import analyze248_all as A
import symbol_universe as su
import pasd_fusion as PF

for sym in ('AUDNZD','XLMUSD'):
    pkt = pickle.load(open(f"data/cache248/{sym}.pkl","rb"))
    cfg = dict(su.UNIVERSE.get(sym, {})); h1=pkt['h1']
    sigs = PF.gen_pasd(h1, pkt['h4'], pkt['d1'], cfg)
    for s in sigs: s['tp']=s['entry']+s['side']*A.RR*abs(s['entry']-s['sl'])
    zs = PF._detect_supply_demand_zones(h1['high'].values,h1['low'].values,h1['close'].values)
    res=[]
    for s in sigs:
        r=A.sim(pkt,h1,s,A.add_levels(s,zs['demand'],zs['supply'],'A'),cfg)
        if r: res.append((r['R'],r['pnl'],s))
    Rvals=[x[0] for x in res]
    k=int(np.argmax(np.abs(np.array(Rvals))))
    R,pnl,s = res[k]
    i=int(s['bar']); e=float(h1['open'].iloc[i+1])
    slabs=abs(s['entry']-s['sl'])
    end=min(i+1+A.MAXH,len(h1))
    seg=h1.iloc[i+1:end]
    print(f"== {sym} worst R={R:.0f} pnl={pnl:.2f}USD entry~{e} sl_dist={slabs} side={s['side']}")
    print("   window:", h1['time'].iloc[i+1], "->", h1['time'].iloc[end-1], "bars:", len(seg))
    print("   bar-gap median/max(h):", int(np.median(np.diff(seg['time'].values)/3.6e6)), int(np.max(np.diff(seg['time'].values)/3.6e6)))
    print("   seg range low/high:", seg['low'].min(), seg['high'].max(), "| entry-side move vs sl_dist:", abs((e-seg['low'].min()) if s['side']>0 else (seg['high'].max()-e)), "sl:", slabs)
