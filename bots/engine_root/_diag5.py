import sys, pickle
import numpy as np
sys.path.insert(0, r"E:\GoldstrategyEngine")
import analyze248_all as A
import symbol_universe as su
import pasd_fusion as PF
sym='AUDNZD'
pkt = pickle.load(open(f"data/cache248/{sym}.pkl","rb"))
cfg = dict(su.UNIVERSE[sym]); h1=pkt['h1']
sigs = PF.gen_pasd(h1, pkt['h4'], pkt['d1'], cfg)
# stats on sl_dist
d=[abs(s['entry']-s['sl']) for s in sigs]
d=np.array(d)
print("sl_dist: min", float(d.min()), "max", float(d.max()), "| count <1e-5:", int((d<1e-5).sum()), "of", len(d))
# the tiny ones
tiny=[s for s in sigs if abs(s['entry']-s['sl'])<1e-5]
print("tiny-sldist sigs:", len(tiny))
for s in tiny[:5]:
    print(f"  side={s['side']} entry={s['entry']:.7f} sl={s['sl']:.7f} dist={abs(s['entry']-s['sl']):.3e} bar={s['bar']} sigkeys={list(s.keys())}")
