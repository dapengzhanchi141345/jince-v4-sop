# fast targeted: AUDNZD only, no XLMUSD (gen_pasd O(n^2) too slow here)
import sys, pickle, time
import numpy as np
sys.path.insert(0, r"E:\GoldstrategyEngine")
import analyze248_all as A
import symbol_universe as su
import pasd_fusion as PF
t0=time.time()
sym='AUDNZD'
pkt = pickle.load(open(f"data/cache248/{sym}.pkl","rb"))
cfg = dict(su.UNIVERSE[sym]); h1=pkt['h1']
print("h1 bars:", len(h1), "range:", h1['time'].iloc[0], "->", h1['time'].iloc[-1], "| close sample:", round(float(h1['close'].iloc[10]),5), flush=True)
sigs = PF.gen_pasd(h1, pkt['h4'], pkt['d1'], cfg)
for s in sigs: s['tp']=s['entry']+s['side']*A.RR*abs(s['entry']-s['sl'])
print("sigs:", len(sigs), "elapsed", round(time.time()-t0,1), flush=True)
zs = PF._detect_supply_demand_zones(h1['high'].values,h1['low'].values,h1['close'].values)
res=[]
for s in sigs:
    r=A.sim(pkt,h1,s,A.add_levels(s,zs['demand'],zs['supply'],'A'),cfg)
    if r: res.append((r['R'],r['pnl'],r['adds'],s))
k=int(np.argmax(np.abs(np.array([x[0] for x in res]))))
R,pnl,adds,s=res[k]
i=int(s['bar']); e=float(h1['open'].iloc[i+1]); slabs=abs(s['entry']-s['sl'])
print(f"worst: R={R:.1f} pnl={pnl:.2f}USD adds={adds} side={s['side']} entry_sig={s['entry']} exec_e={e:.5f} sl_dist={slabs} n_sigs={len(res)}", flush=True)
print("sl price:", s['sl'], "exec SL:", e-s['side']*slabs, "exit would need to move:", R*slabs, "from exec entry", flush=True)
end=min(i+1+A.MAXH,len(h1)); seg=h1.iloc[i+1:end]
print("window:", h1['time'].iloc[i+1], "->", h1['time'].iloc[end-1], "| seg low/high:", seg['low'].min(), seg['high'].max(), flush=True)
gap=np.diff(seg['time'].values)/3.6e6
print("bar gap med/max hours:", int(np.median(gap)), int(np.max(gap)), flush=True)
# biggest single-bar move in window
mv=np.maximum(seg['high']-seg['open'], seg['open']-seg['low'])
print("max single-bar move:", float(mv.max()), "at bar", int(mv.idxmax()), flush=True)
