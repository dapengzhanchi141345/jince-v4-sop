
import numpy as np, numpy.lib.stride_tricks as st, time
SYMS = ["BTCUSD"]
T0 = 1409097600  # start of M30 history

def load(sym, tf):
    a = np.load(f"E:/GoldstrategyEngine/data/tf_cache/{sym}_{tf}.npz")
    return dict(t=a["t"].astype(np.int64), h=a["h"].astype(np.float64),
                l=a["l"].astype(np.float64), c=a["c"].astype(np.float64))

t0 = time.time()
tot_ev, tot_fill = 0, 0
for sym in SYMS:
    d1 = load(sym, "D1"); m = load(sym, "M30")
    hh, ll, cc, tt = m["h"], m["l"], m["c"], m["t"]
    hi = st.sliding_window_view(hh, 20).max(axis=1)[:-19]
    lo = st.sliding_window_view(ll, 20).min(axis=1)[:-19]
    d1t, d1c = d1["t"], d1["c"]
    hi_n = len(hi)
    ev = fill = 0
    for i in range(21, hi_n):
        ts = int(tt[i])
        ok = d1t + 86400 <= ts
        idx = np.where(ok)[0]
        if len(idx) == 0 or idx[-1] < 1:
            continue
        j = int(idx[-1])
        g = 1 if d1c[j] > d1c[j-1] else 0
        hi_i = hi[i]; lo_i = lo[i]
        side = 0
        if g == 1 and cc[i] < hi_i * 1.003:
            side = 1; trig = hi_i * 1.003
        elif g == 0 and cc[i] > lo_i / 1.003:
            side = -1; trig = lo_i / 1.003
        if side == 0:
            continue
        ev += 1
        j0 = i + 1
        if j0 + 4 > len(tt):
            continue
        if side == 1:
            f = np.where(hh[j0:j0+4] >= trig)[0]
        else:
            f = np.where(ll[j0:j0+4] <= trig)[0]
        if len(f) > 0:
            fill += 1
    print(f"{sym} FULL-HIST: events={ev} filled={fill} (rate {fill/max(ev,1):.2f}) elapsed={time.time()-t0:.0f}s")
    tot_ev += ev; tot_fill += fill
    # per-decade fill check
    for yr_start, yr_end in [(2015, 2016), (2019, 2020), (2023, 2024), (2025, 2026)]:
        i_a = int(np.searchsorted(tt, yr_start * 31536000))
        i_b = int(np.searchsorted(tt, yr_end * 31536000))
        ev2 = fl2 = 0
        for i in range(max(21, i_a), min(i_b, hi_n)):
            ts = int(tt[i])
            ok = d1t + 86400 <= ts
            idx = np.where(ok)[0]
            if len(idx) == 0 or idx[-1] < 1: continue
            j = int(idx[-1])
            g = 1 if d1c[j] > d1c[j-1] else 0
            hi_i = hi[i]; lo_i = lo[i]
            side = 0
            if g == 1 and cc[i] < hi_i*1.003: side = 1; trig = hi_i*1.003
            elif g == 0 and cc[i] > lo_i/1.003: side = -1; trig = lo_i/1.003
            if side == 0: continue
            ev2 += 1
            j0 = i+1
            if j0+4 > len(tt): continue
            if side == 1: f = np.where(hh[j0:j0+4] >= trig)[0]
            else: f = np.where(ll[j0:j0+4] <= trig)[0]
            if len(f) > 0: fl2 += 1
        print(f"  {yr_start}-{yr_end}: ev={ev2} fill={fl2} rate={fl2/max(ev2,1):.2f}")
print(f"TOTAL ev={tot_ev} fill={tot_fill}")
