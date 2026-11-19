
import sys, numpy as np, MetaTrader5 as mt5
sys.path.insert(0, "E:/GoldstrategyEngine/multi_agent/trading")
import intraday_swing as isw
mt5.initialize(); assert mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
sym = "BTCUSD"
d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 3000)
h1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 50000)
d1t = d1["time"].astype(np.int64); d1h = d1["high"].astype(float); d1l = d1["low"].astype(float); d1c = d1["close"].astype(float)
t1 = h1["time"].astype(np.int64); h1h = h1["high"].astype(float); h1l = h1["low"].astype(float); h1c = h1["close"].astype(float)
day_of = (t1 // 86400).astype(np.int64)
n_total = n_badclose = n_h1a0 = n_nobars = n_ok = 0
sample_nobars, sample_ok = [], []
for i in range(60, len(d1)-1):
    dts = int(d1t[i])
    if d1c[i-1] <= 0:
        n_badclose += 1; continue
    idx_end = int(np.searchsorted(t1, dts, side="left"))
    seg = slice(max(0, idx_end-30), idx_end)
    a = isw.atr(h1h[seg], h1l[seg], h1c[seg])
    h1a = float(a[-1]) if len(a) > 0 and a[-1] > 0 else 1e-9
    if h1a < 1e-6:
        n_h1a0 += 1
        if len(sample_nobars) < 3: sample_nobars.append((dts, "idx_end=", idx_end, "seglen=", len(h1c[seg]), "atr_tail=", None if len(a)==0 else a[-1]))
        continue
    idxs = np.where(day_of == dts // 86400)[0]
    if len(idxs) == 0:
        n_nobars += 1
        if len(sample_nobars) < 6: sample_nobars.append((dts, "idx_end=", idx_end, "seglen=", len(h1c[seg]), "daybars=0"))
        continue
    n_ok += 1
    if len(sample_ok) < 3: sample_ok.append((dts, "idx_end=", idx_end, "daybars=", len(idxs)))
n_total = len(d1)-61
print(f"total={n_total} badclose={n_badclose} h1a0={n_h1a0} noH1bars={n_nobars} OK={n_ok}")
print("skip samples:", sample_nobars)
print("ok samples:", sample_ok)
mt5.shutdown()
