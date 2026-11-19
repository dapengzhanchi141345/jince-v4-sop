import numpy as np, os, datetime as dt, glob
CACHE = "E:/GoldstrategyEngine/data/tf_cache"
def r(t):
    return dt.datetime.utcfromtimestamp(int(t[0])), dt.datetime.utcfromtimestamp(int(t[-1]))
print("=== .tmp.npz (claimed 11-14 refresh) ===")
for p in sorted(glob.glob(os.path.join(CACHE,"*_M30.npz.tmp.npz"))):
    s = os.path.basename(p).replace("_M30.npz.tmp.npz","")
    z = np.load(p); t = z["t"]; t0,t1=r(t); print(f"{s:8s} n={len(t):6d}  {t0:%Y-%m-%d %H:%M} -> {t1:%Y-%m-%d %H:%M} UTC"); z.close()
print("=== base .npz ===")
for s in ["XAUUSD","EURUSD","BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD","KSMUSD"]:
    p=os.path.join(CACHE,f"{s}_M30.npz")
    z=np.load(p);t=z["t"];t0,t1=r(t);print(f"{s:8s} n={len(t):6d}  {t0:%Y-%m-%d %H:%M} -> {t1:%Y-%m-%d %H:%M} UTC");z.close()
