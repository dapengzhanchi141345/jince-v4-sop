
import MetaTrader5 as mt5, numpy as np, datetime
mt5.initialize(); assert mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
d1 = mt5.copy_rates_from_pos("BTCUSD", mt5.TIMEFRAME_D1, 0, 100)
h1 = mt5.copy_rates_from_pos("BTCUSD", mt5.TIMEFRAME_H1, 0, 50000)
print("D1 t[0]..t[2]:", [int(x) for x in d1["time"][:3]])
print("D1 start:", datetime.datetime.utcfromtimestamp(int(d1["time"][0])))
print("H1 t[0]:", datetime.datetime.utcfromtimestamp(int(h1["time"][0])))
# 日界检查
print("D1 time % 86400:", [int(x) % 86400 for x in d1["time"][:5]])
print("H1 time % 86400 sample:", [int(x) % 86400 for x in h1["time"][:3]])
# 匹配检查
t1 = h1["time"].astype(np.int64); d1t = d1["time"].astype(np.int64)
for i in [50, 100, 500]:
    dts = int(d1t[i])
    n_match = int(((t1 // 86400) == (dts // 86400)).sum())
    print(f"d1[{i}] dts={dts} utcday_start={datetime.datetime.utcfromtimestamp(dts)} H1同UTC日bars={n_match}")
mt5.shutdown()
