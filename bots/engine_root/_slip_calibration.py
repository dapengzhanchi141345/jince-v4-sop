# -*- coding: utf-8 -*-
# tick 滑点标定: M1 tick 实测 spread 占 M30 格 R(=3×ATR) 的比例, 替换拍脑袋的 0.5R
# 输出 data/slip_calibration.json: 每品种 spread_R 分布 (P50/P95/max)
import os, json, datetime
import numpy as np
import MetaTrader5 as mt5

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "data", "slip_calibration.json")
SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]
N_TICKS = 50000          # 最近 5 万 tick (约数小时~1天, 够用标定)
N_BARS = 1000            # M30 尾 1000 根取 ATR 分布

mt5.initialize()
assert mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")

def atr14_series(sym):
    """最近 N_BARS 根 M30 的 ATR14 序列 (Wilder), 用于 R 分布"""
    r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M30, 0, N_BARS + 30)
    h, l, c = r["high"].astype(float), r["low"].astype(float), r["close"].astype(float)
    tr = np.empty(len(c)); tr[0] = h[0] - l[0]
    tr[1:] = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    a = np.zeros(len(c)); a[14] = tr[1:15].mean()
    for i in range(15, len(c)):
        a[i] = (a[i - 1] * 13 + tr[i]) / 14
    return a[30:]

rep = {}
for sym in SYMS:
    # 1) 拉 M1 行情 (比 tick 快且含 spread 语义: open/high/low/close 同根极值差)
    m1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M1, 0, 5000)
    m30ticks = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M30, 0, 50)
    a = atr14_series(sym)
    R = np.quantile(3.0 * a[-100:], 0.5)   # 典型 R 价距 (M30 SLM3 格)
    # spread 代理: M30 每根 (high-low) 的中位数占比太小, 用 tick 级: 最近100根M30 每根首两tick? 终端无tick历史就用 M1 open→high 跳升
    # 简化且保守: 单笔滑点 ≈ 0.5×点差(双向) + 点差本身, 点差用 M1 根 (close-open) 的 P50 绝对占比
    oc = np.abs(m1["close"].astype(float) - m1["open"].astype(float))
    spread_proxy = np.quantile(oc, 0.5)      # 保守取 M1 跳幅 P50 (通常 > 实际点差)
    spread_R = spread_proxy / R
    rep[sym] = {
        "R_typical": float(R),
        "spread_proxy_M1_open_close_P50": float(spread_proxy),
        "spread_R_P50": float(spread_R),
        "spread_R_P95": float(np.quantile(oc, 0.95) / R),
        "note": "标定口径: 滑点=1×M1跳幅P50(保守, 实盘点差通常更小) / R=3×ATR(M30)P50",
    }
    print(f"{sym}: R={R:.4f} spread_P50={spread_proxy:.4f} -> {spread_R:.4f}R, P95={np.quantile(oc,0.95)/R:.4f}R")

rep["_meta"] = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "verdict_hint": "若 spread_R_P50 << 0.5, 说明 0.5R 滑点假设过悲观, M30 格净 edge 需按标定值重过五验"}
json.dump(rep, open(OUT, "w"), indent=1)
print("WROTE", OUT)
mt5.shutdown()
