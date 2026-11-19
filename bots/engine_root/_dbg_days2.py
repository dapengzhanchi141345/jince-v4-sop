
import sys, numpy as np, MetaTrader5 as mt5
sys.path.insert(0, "E:/GoldstrategyEngine/multi_agent/trading")
import intraday_swing as isw
import inspect
# 看 isw.atr 实现
src = inspect.getsource(isw.atr)
print(src[:800])
mt5.initialize(); mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
sym="BTCUSD"
d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 3000)
h1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 50000)
d1t=d1["time"].astype(np.int64); d1c=d1["close"].astype(float)
t1=h1["time"].astype(np.int64); h1h=h1["high"].astype(float); h1l=h1["low"].astype(float); h1c=h1["close"].astype(float)
# 复现主脚本逻辑, 看 i=100 时 h1a 到底是多少
i=100
dts=int(d1t[i])
idx_end=int(np.searchsorted(t1, dts, side="left"))
seg=slice(max(0,idx_end-30), idx_end)
print("i=100 idx_end=", idx_end, "segbars=", len(h1c[seg]))
a=isw.atr(h1h[seg], h1l[seg], h1c[seg])
print("a[-1]=", a[-1] if len(a) else "empty", "len=", 0 if a is None else len(a))
mt5.shutdown()
