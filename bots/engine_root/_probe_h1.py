
import numpy as np, time
SYMS = ["BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD"]
t0=time.time()
for sym in SYMS:
    h = np.load(f"E:/GoldstrategyEngine/data/tf_cache/{sym}_H1.npz")
    print(sym, len(h["c"]), int(h["t"][0]), int(h["t"][-1]))
print("load time", round(time.time()-t0,2))
