
import numpy as np, MetaTrader5 as mt5
sys = None
mt5.initialize(); assert mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
import sys as _s; _s.path.insert(0, "E:/GoldstrategyEngine/multi_agent/trading")
import intraday_swing as isw
sym = "BTCUSD"
d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 3000)
h1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 50000)
print("d1:", 0 if d1 is None else len(d1), "h1:", 0 if h1 is None else len(h1))
if d1 is None or h1 is None:
    mt5.shutdown(); raise SystemExit
d1t = d1["time"].astype(np.int64); d1h = d1["high"].astype(float); d1l = d1["low"].astype(float)
t1 = h1["time"].astype(np.int64); h1h = h1["high"].astype(float); h1l = h1["low"].astype(float); h1c = h1["close"].astype(float)
day_of = (t1 // 86400).astype(np.int64)
i = 100
dts = int(d1t[i])
idxs = np.where(day_of == dts // 86400)[0]
print(f"d1[{i}] dts={dts} daybars={len(idxs)}")
idx_end = int(np.searchsorted(t1, dts + 86400, side="left"))
seg = slice(max(0, idx_end-30), idx_end)
print("seg len:", len(h1c[seg]))
a = isw.atr(h1h[seg], h1l[seg], h1c[seg])
print("atr tail:", a[-3:], "last>0:", a[-1] > 0)
mt5.shutdown()
