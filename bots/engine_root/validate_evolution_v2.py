# -*- coding: utf-8 -*-
"""validate_evolution_v2.py — 用真实 MT5 数据验证 V2 进化层 + 组合回测
不登录朋友账户、不碰实盘 60043976。只读市场数据 + 离线信号生成。
"""
import sys, os, json, time
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import MetaTrader5 as mt5
import evolution_engine as evo
import advanced_strategies_v4 as ast

OUT = {}
np.random.seed(0)

def pull(symbol, tf, n):
    r = mt5.copy_rates_from_pos(symbol, tf, 0, n)
    if r is None: return None
    df = pd.DataFrame(r)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

print("=== 1. 多品种波动率目标化 (真实数据) ===")
if not mt5.initialize(timeout=30000):
    print("MT5 INIT_FAIL", mt5.last_error()); sys.exit(1)
print("MT5 ok, account:", (mt5.account_info().login if mt5.account_info() else None))
vol_row = {}
for sym in ["XAUUSD", "BTCUSD", "EURUSD", "GBPUSD", "USDJPY"]:
    h1 = pull(sym, mt5.TIMEFRAME_H1, 2000)
    if h1 is None or len(h1) < 30:
        print(f"  {sym}: 数据不足, 跳过"); continue
    dv = evo.ev2_symbol_daily_vol_from_h1(h1['close'].values)
    sc = evo.ev2_vol_target_scale(dv)
    vol_row[sym] = {"daily_vol": round(dv, 4) if dv else None, "vol_scale": sc}
    print(f"  {sym:7s} 日波动={dv:.4f}  →  波动率目标乘数={sc:.3f}")
OUT["vol_target"] = vol_row

print("\n=== 2. Regime 检测 (XAUUSD 滚动, 看状态序列) ===")
h1 = pull("XAUUSD", mt5.TIMEFRAME_H1, 4000)
h4 = pull("XAUUSD", mt5.TIMEFRAME_H4, 1500)
d1 = pull("XAUUSD", mt5.TIMEFRAME_D1, 400)
c = h1['close'].values.astype(float)
rets = np.diff(np.log(c))
seq = []
win = 240
for i in range(win, len(rets), 120):
    vnow = float(np.std(rets[i-win:i]))
    vhist = rets[:i]
    adx = 20.0 + min(25, abs((d1['close'].values[-1]-d1['close'].values[0])/d1['close'].values[0])*200)
    vs, ts = __import__('regime_router').detect_regime(vnow, vhist, adx)
    seq.append((vs, ts))
from collections import Counter
cnt = Counter(seq)
print(f"  状态分布(每120根采样): {dict(cnt)}")
print(f"  末态: {seq[-1]}")
OUT["regime_seq"] = [list(x) for x in seq[-10:]]

print("\n=== 3. Meta 置信度硬闸 行为自检 ===")
cases = [
    ("有统计高置信", evo.ev2_composite_confidence(wr=55, pf=2.1), 1.0, "mid"),
    ("无统计", None, 1.0, "mid"),
    ("低置信", evo.ev2_composite_confidence(wr=40, pf=1.1), 1.0, "mid"),
    ("波动尖峰", 0.8, 3.0, "mid"),
    ("高波动regime", 0.8, 1.0, "high"),
]
for name, conf, spike, rv in cases:
    ok, why = evo.ev2_meta_gate(conf, spike, rv)
    print(f"  {name:12s} conf={str(conf):>6} spike={spike} {rv:4s} -> accept={ok} ({why})")
OUT["gate_cases"] = [[n, ok, w] for (n, conf, spike, rv, (ok, w)) in
                      [(c[0], c[1], c[2], c[3], evo.ev2_meta_gate(c[1], c[2], c[3])) for c in cases]]

print("\n=== 4. 组合层风险集中度 (波动率目标化的真价值, 跨品种) ===")
# 真实验证: 波动率目标化让每个品种对组合波动的贡献拉平,
# 否则高波动品种(吞噬风险预算)会主导, 降低有效分散 (forexexperts: 有效下注数暴跌).
# 用当前实盘宇宙近似: XAUUSD/BTCUSD/GBPUSD/USDJPY/EURUSD
univ = {}
for sym in ["XAUUSD", "BTCUSD", "EURUSD", "GBPUSD", "USDJPY"]:
    hh = pull(sym, mt5.TIMEFRAME_H1, 1500)
    if hh is None: continue
    dv = evo.ev2_symbol_daily_vol_from_h1(hh['close'].values)
    univ[sym] = dv
print(f"  宇宙日波动: { {k: round(v,4) for k,v in univ.items()} }")

def concentration(vols, sizes):
    # 组合波动贡献 ~ (size*vol)^2; Herfindahl 指数 (0=完全分散,1=单一集中)
    contrib = np.array([ (sizes[s] * univ[s])**2 for s in univ ])
    tot = contrib.sum()
    if tot <= 0: return 1.0
    w = contrib / tot
    return float((w**2).sum())

# 基线: 等风险% → 各品种 size 相同(=1)
base_sizes = {s: 1.0 for s in univ}
# 进化: 波动率目标化 size = vol_target_scale(daily_vol)
evo_sizes = {s: evo.ev2_vol_target_scale(univ[s]) for s in univ}
H_base = concentration(univ, base_sizes)
H_evo = concentration(univ, evo_sizes)
print(f"  基线等风险% 集中度 HHI = {H_base:.3f} (有效下注数≈{1/H_base:.1f})")
print(f"  进化波动率目标 HHI = {H_evo:.3f} (有效下注数≈{1/H_evo:.1f})")
print(f"  改善: 有效分散度 ×{ (1/H_evo)/(1/H_base):.2f}")
OUT["risk_concentration"] = {
    "base_hhi": round(H_base,3), "evo_hhi": round(H_evo,3),
    "base_eff_bets": round(1/H_base,1), "evo_eff_bets": round(1/H_evo,1),
    "sizes_evo": {s: round(evo_sizes[s],3) for s in evo_sizes},
}

json.dump(OUT, open("evolution_v2_validation.json", "w"), ensure_ascii=False, indent=2, default=str)
print("\n✅ 验证结果 -> evolution_v2_validation.json")
mt5.shutdown()
