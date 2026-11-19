
import numpy as np, numpy.lib.stride_tricks as st
T_START = 1759323600
FILL_WINDOW = 4

def load(sym, tf):
    a = np.load(f"E:/GoldstrategyEngine/data/tf_cache/{sym}_{tf}.npz")
    return dict(t=a["t"].astype(np.int64), h=a["h"].astype(np.float64),
                l=a["l"].astype(np.float64), c=a["c"].astype(np.float64))

d1 = load("BTCUSD", "D1"); m = load("BTCUSD", "M30")
hh, ll, cc, tt = m["h"], m["l"], m["c"], m["t"]
hi = st.sliding_window_view(hh, 20).max(axis=1)[:-19]
lo = st.sliding_window_view(ll, 20).min(axis=1)[:-19]
i = 33145
ts = int(tt[i])
ok = d1["t"] + 86400 <= ts
idx = np.where(ok)[0]
j = int(idx[-1])
g = 1 if d1["c"][j] > d1["c"][j-1] else 0
hi_i, lo_i, cc_i = hi[i], lo[i], cc[i]
print("gate", g, "cc<trig?", cc_i < hi_i*1.003, "g==0 cond?", cc_i > lo_i/1.003)
# now the fill test
j0 = i + 1
seg_h = hh[j0:j0+FILL_WINDOW]; seg_l = ll[j0:j0+FILL_WINDOW]
trig = hi_i * 1.003
f = np.where(seg_h >= trig)[0]
print("seg_h:", seg_h, "trig:", trig, "n_fill:", len(f))
trig2 = lo_i / 1.003
f2 = np.where(seg_l <= trig2)[0]
print("seg_l:", seg_l, "trig2:", trig2, "n_fill2:", len(f2))
