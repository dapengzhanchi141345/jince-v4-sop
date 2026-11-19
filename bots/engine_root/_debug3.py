
import numpy as np, numpy.lib.stride_tricks as st, time
T_START = 1759323600
FILL_WINDOW = 4
LOOK_AHEAD = 42
SYMS = ["BTCUSD"]

def load(sym, tf):
    a = np.load(f"E:/GoldstrategyEngine/data/tf_cache/{sym}_{tf}.npz")
    return dict(t=a["t"].astype(np.int64), h=a["h"].astype(np.float64),
                l=a["l"].astype(np.float64), c=a["c"].astype(np.float64))

t0 = time.time()
fills = 0; evs = 0; skipped_fill = 0
for sym in SYMS:
    d1 = load(sym, "D1"); m = load(sym, "M30")
    hh, ll, cc, tt = m["h"], m["l"], m["c"], m["t"]
    hi = st.sliding_window_view(hh, 20).max(axis=1)[:-19]
    lo = st.sliding_window_view(ll, 20).min(axis=1)[:-19]
    d1t, d1c = d1["t"], d1["c"]
    t0_i = int(np.searchsorted(tt, T_START))
    hi_n = len(hi)
    print(f"{sym} t0_i={t0_i} hi_n={hi_n} len_tt={len(tt)}")
    n_ev = 0; n_fill = 0
    for i in range(max(21, t0_i - 1), min(len(tt) - 1, hi_n)):
        ts = int(tt[i])
        if ts < T_START:
            continue
        ok = d1t + 86400 <= ts
        idx = np.where(ok)[0]
        if len(idx) == 0 or idx[-1] < 1:
            continue
        j = int(idx[-1])
        g = 1 if d1c[j] > d1c[j-1] else 0
        hi_i = hi[i]; lo_i = lo[i]
        side = 0
        trig = 0.0
        if g == 1 and cc[i] < hi_i * 1.003:
            side, trig = 1, hi_i * 1.003
        elif g == 0 and cc[i] > lo_i / 1.003:
            side, trig = -1, lo_i / 1.003
        if side == 0:
            continue
        n_ev += 1
        j0 = i + 1
        if j0 >= len(tt) or j0 + FILL_WINDOW > len(tt):
            continue
        seg_h = hh[j0:j0+FILL_WINDOW]; seg_l = ll[j0:j0+FILL_WINDOW]
        if side == 1:
            f = np.where(seg_h >= trig)[0]
        else:
            f = np.where(seg_l <= trig)[0]
        if len(f) == 0:
            n_fill_skip = 1
            continue
        n_fill_skip = 0
        n_fill += 1
    print(f"{sym} events={n_ev} filled={n_fill} (elapsed {time.time()-t0:.1f}s)")
    # check: what does a real event at T_START look like with trigger from hi[i-1]?
    i = t0_i
    print(f"  i={i} hi[i]*1.003={hi[i]*1.003:.2f} hi[i-1]*1.003={hi[i-1]*1.003:.2f} cc[i]={cc[i]:.2f}")
    print(f"  lo[i]/1.003={lo[i]/1.003:.2f} lo[i-1]/1.003={lo[i-1]/1.003:.2f}")
    print(f"  gate: d1c[j]={d1c[j]:.2f} vs d1c[j-1]={d1c[j-1]:.2f} -> g={g}")
    # find nearest filled event within first 2000 bars
    i2 = t0_i
    while i2 < min(len(tt)-1, hi_n) and i2 - t0_i < 5000:
        ts2 = int(tt[i2])
        ok2 = d1t + 86400 <= ts2
        idx2 = np.where(ok2)[0]
        if len(idx2) == 0 or idx2[-1] < 1:
            i2 += 1; continue
        j2 = int(idx2[-1])
        g2 = 1 if d1c[j2] > d1c[j2-1] else 0
        hi_i2 = hi[i2]; lo_i2 = lo[i2]
        if g2 == 1 and cc[i2] < hi_i2*1.003:
            trig2 = hi_i2*1.003
            j0_2 = i2+1
            f2 = np.where(hh[j0_2:j0_2+4] >= trig2)[0]
            if len(f2) > 0:
                print(f"  FIRST FILLED: i={i2} (+{i2-t0_i} bars from t0) ts={ts2} side=BUY trig={trig2:.2f}")
                break
            i2 += 1
        elif g2 == 0 and cc[i2] > lo_i2/1.003:
            trig2 = lo_i2/1.003
            j0_2 = i2+1
            f2 = np.where(ll[j0_2:j0_2+4] <= trig2)[0]
            if len(f2) > 0:
                print(f"  FIRST FILLED: i={i2} (+{i2-t0_i} bars from t0) ts={ts2} side=SELL trig={trig2:.2f}")
                break
            i2 += 1
        else:
            i2 += 1
    else:
        print(f"  No filled events in first 5000 bars from t0_i")
print(f"total elapsed {time.time()-t0:.1f}s")
