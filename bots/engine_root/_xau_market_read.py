
import MetaTrader5 as mt5, time
assert mt5.initialize(), "mt5 init failed"
s = mt5.symbol_info("XAUUSD")
now=time.time()
d1 = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_D1, 0, 22)
hi=float(max(r["high"] for r in d1)); lo=float(min(r["low"] for r in d1))
last5=[float(r["close"]) for r in d1[-6:-1]]
yfloat=float(d1[-2]["close"])
print("现价 bid=%.2f ask=%.2f" % (s.bid, s.ask))
print("20日 high=%.1f low=%.1f | 现价距20日低=%.1f点" % (hi, lo, s.bid-lo))
print("近5日收盘:", [round(x,1) for x in last5])
print("24h: 昨收=%.1f -> 现价=%.1f  变化=%.2f%%" % (yfloat, s.bid, (s.bid-yfloat)/yfloat*100))
# ATR(14) D1 供 RR 质检
import numpy as np
hi_=np.array([float(r["high"]) for r in d1]); lo_=np.array([float(r["low"]) for r in d1]); c_=np.array([float(r["close"]) for r in d1])
tr=np.maximum(hi_[1:]-lo_[1:], np.maximum(abs(hi_[1:]-c_[:-1]), abs(lo_[1:]-c_[:-1])))
atr14=float(tr[-14:].mean())
print("D1 ATR14=%.1f | 趋势腿SL<=2.5xATR=%.1f" % (atr14, 2.5*atr14))
mt5.shutdown()
