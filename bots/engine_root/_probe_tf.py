
import numpy as np, time
a = np.load("E:/GoldstrategyEngine/data/tf_cache/BTCUSD_M30.npz")
print({k: len(a[k]) for k in a.keys()})
SYMS = ["BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD"]
f0 = time.time()
import numpy as np
h = np.load("E:/GoldstrategyEngine/data/tf_cache/BTCUSD_M30.npz")["h"].astype(float)
n = len(h)
hi = np.empty(n); lo = np.empty(n)
cmax = np.maximum.accumulate(h[:0]); 
import numpy.lib.stride_tricks as st
sl = st.sliding_window_view(h, 20)
hi2 = sl.max(axis=1)  # hi2[i] = max of h[i:i+20]
print("donchian sliding_window_view over M30:", round(time.time()-f0,3), "s")
for sym in SYMS:
    a = np.load(f"E:/GoldstrategyEngine/data/tf_cache/{sym}_M30.npz")
    print(sym, len(a["c"]), int(a["t"][0]), int(a["t"][-1]), end=" ")
    d = np.load(f"E:/GoldstrategyEngine/data/tf_cache/{sym}_D1.npz")
    print(len(d["c"]), int(d["t"][0]), int(d["t"][-1]))
