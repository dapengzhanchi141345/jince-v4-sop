
import numpy as np, numpy.lib.stride_tricks as st, time
T_START = 1759323600
FILL_WINDOW = 4
SYMS = ["BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD"]

def load(sym, tf):
    a = np.load(f"E:/GoldstrategyEngine/data/tf_cache/{sym}_{tf}.npz")
    return dict(t=a["t"].astype(np.int64), h=a["h"].astype(np.float64),
                l=a["l"].astype(np.float64), c=a["c"].astype(np.float64))

for sym in SYMS:
    d1 = load(sym, "D1"); m = load(sym, "M30")
    hh, ll, cc, tt = m["h"], m["l"], m["c"], m["t"]
    hi = st.sliding_window_view(hh, 20).max(axis=1)[:-19]
    lo = st.sliding_window_view(ll, 20).min(axis=1)[:-19]
    d1t, d1c = d1["t"], d1["c"]
    t0_i = int(np.searchsorted(tt, T_START))
    hi_n = len(hi)
    i = t0_i
    ts = int(tt[i])
    ok = d1t + 86400 <= ts
    idx = np.where(ok)[0]
    print(f"{sym} t0_i={i} ts={ts} n_ok={len(idx)} j={idx[-1] if len(idx) else None}")
    if len(idx) == 0:
        print(f"{sym} d1+86400 <= ts all False; max d1+86400={ (d1t+86400).max() }, ts={ts}")
        print(f"  last few d1t: {d1t[-3:]}  -> +86400: {d1t[-3:]+86400}")
        print(f"  last few tt: {tt[-3:]}")
        continue
    j = int(idx[-1])
    g = 1 if d1c[j] > d1c[j-1] else 0
    print(f"{sym} j={j} d1c[j]={d1c[j]:.4f} d1c[j-1]={d1c[j-1]:.4f} gate={g}")
    print(f"  hi[i]*1.003={hi[i]*1.003:.4f} cc[i]={cc[i]:.4f} cond1={cc[i] < hi[i]*1.003}")
    print(f"  lo[i]/1.003={lo[i]/1.003:.4f} cond2={cc[i] > lo[i]/1.003}")
    j0 = i + 1
    seg_h = hh[j0:j0+FILL_WINDOW]; seg_l = ll[j0:j0+FILL_WINDOW]
    print(f"  j0={j0} seg_h={seg_h[:4]} seg_l={seg_l[:4]}")
    # fill test with original trigger from cc[i]
    if g == 1 and cc[i] < hi[i]*1.003:
        trig = hi[i]*1.003
        f = np.where(seg_h >= trig)[0]
        print(f"  side=BUY trig={trig:.4f} fill_n={len(f)} f={f[:5]}")
    elif g == 0 and cc[i] > lo[i]/1.003:
        trig = lo[i]/1.003
        f = np.where(seg_l <= trig)[0]
        print(f"  side=SELL trig={trig:.4f} fill_n={len(f)} f={f[:5]}")
    else:
        print("  no side triggered")
