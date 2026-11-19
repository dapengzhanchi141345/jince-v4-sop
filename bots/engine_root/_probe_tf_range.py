
import numpy as np, os, datetime as dt
CACHE = "E:/GoldstrategyEngine/data/tf_cache"
syms = ["XAUUSD","EURUSD","BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD","KSMUSD"]
def r(t):
    return dt.datetime.utcfromtimestamp(int(t[0])), dt.datetime.utcfromtimestamp(int(t[-1]))
for s in syms:
    p = os.path.join(CACHE, f"{s}_M30.npz")
    if not os.path.exists(p):
        print(s, "M30 MISSING"); continue
    z = np.load(p); t = z["t"]
    t0,t1 = r(t)
    print(f"{s:8s} M30 n={len(t):6d}  {t0:%Y-%m-%d %H:%M} -> {t1:%Y-%m-%d %H:%M} UTC")
    z.close()
