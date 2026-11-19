# -*- coding: utf-8 -*-
# 只读数据探测: MT5 能否登录 + 6主流币 D1/H4 历史深度 (决定验收统计样本)
import MetaTrader5 as mt5

ok = mt5.initialize()
print("init:", ok)
login = mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
print("login:", login, "| equity:", mt5.account_info().equity if login else None)
for sym in ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "BNBUSD", "LTCUSD"]:
    d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 500)
    h4 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, 3000)
    h1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 2000)
    n_d = len(d1) if d1 is not None else 0
    n_h4 = len(h4) if h4 is not None else 0
    n_h1 = len(h1) if h1 is not None else 0
    span = ""
    if d1 is not None and n_d > 1:
        span = f"D1跨{n_d}天({d1[0]['time']}~{d1[-1]['time']})"
    print(f"  {sym:8} D1={n_d:4} H4={n_h4:5} H1={n_h1:5} {span}")
mt5.shutdown()
print("探测完成")
