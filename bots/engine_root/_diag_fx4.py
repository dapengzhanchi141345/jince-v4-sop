import sys, pickle, json
import numpy as np, pandas as pd
sys.path.insert(0, r"E:\GoldstrategyEngine")
import analyze248_all as A
import symbol_universe as su
import pasd_fusion as PF
out = {}
for sym in ('AUDNZD','EURTRY','USDTRY','SOLUSD'):
    pkt = pickle.load(open(f"data/cache248/{sym}.pkl", "rb"))
    cfg = dict(su.UNIVERSE.get(sym, {}))
    h1 = pkt['h1']
    sigs = PF.gen_pasd(h1, pkt['h4'], pkt['d1'], cfg)
    for s in sigs: s['tp'] = s['entry'] + s['side']*A.RR*abs(s['entry']-s['sl'])
    zs = PF._detect_supply_demand_zones(h1['high'].values, h1['low'].values, h1['close'].values)
    rows=[]
    for s in sigs:
        r = A.sim(pkt, h1, s, A.add_levels(s, zs['demand'], zs['supply'], 'A'), cfg)
        if r: rows.append(r)
    R=[x['R'] for x in rows]; top=sorted(rows,key=lambda x:-abs(x['R']))[:4]
    out[sym]=dict(n=len(rows), cumR=round(sum(R),1), worst=[f"{x['R']:.0f}R/{x['pnl']:.1f}usd/adds{x['adds']}" for x in top],
                  pip=cfg.get('pip'), point=pkt['point'], spread=pkt['spread'])
    print(sym, json.dumps(out[sym], ensure_ascii=False), flush=True)
json.dump(out, open('data/_fx4_diagnosis.json','w',encoding='utf-8'), ensure_ascii=False, indent=1)
print("DONE", flush=True)
