# -*- coding: utf-8 -*-
import sys, numpy as np
sys.path.insert(0, r"E:\GoldstrategyEngine")
sys.path.insert(0, r"E:\GoldstrategyEngine\multi_agent\trading")
import MetaTrader5 as mt5, structure_fusion as sf

if not mt5.initialize():
    print("init fail", mt5.last_error()); raise SystemExit
ok = mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
print("login:", ok, mt5.last_error())

rates = mt5.copy_rates_from_pos("BTCUSD", mt5.TIMEFRAME_H4, 0, 1200)
c = rates["close"].astype(float)
hs = []
for t in range(60, len(c), 100):
    hs.append((t, sf.hurst(c[t-60:t], 60)))
import collections
cnt = collections.Counter()
for t, h in hs:
    cat = "TREND" if h >= 0.618 else ("MREV" if h <= 0.382 else "mid")
    cnt[cat] += 1
    if t < 300 or t % 500 == 0:
        print(t, round(h, 3), cat)
print("distribution:", dict(cnt))
# 也测满窗 hurst(默认max_lag=200, 用前60根全量) 看看默认路径
for t in [60, 600, 1100]:
    h_default = sf.hurst(c[t-60:t], 200)
    h_60 = sf.hurst(c[t-60:t], 60)
    print(f"t={t}: default_maxlag={round(h_default,3)} maxlag60={round(h_60,3)}")
mt5.shutdown()
