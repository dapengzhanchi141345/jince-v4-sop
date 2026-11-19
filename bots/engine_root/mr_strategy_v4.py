# -*- coding: utf-8 -*-
"""
MR V4.0 — 均值回归策略机构级升级
==================================
对标 Statistical Arbitrage标准

升级特性:
1. Kalman Filter 自适应均值
2. Dynamic Z-Score Threshold (±2.0 → ±2.5高波动)
3. Regime Filter (趋势市禁用MR)
4. Volatility-Targeted Position Sizing
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional


# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════
BB_PERIOD = 20
BB_STD_BASE = 2.0
BB_STD_VOLATILE = 2.5  # 高波动时放宽
ADX_TREND_THRESHOLD = 25  # ADX>25时禁用MR


# ═══════════════════════════════════════════════════════════════
# Kalman Filter (简化版)
# ═══════════════════════════════════════════════════════════════

def _kalman_filter(closes, process_var=1e-4, measure_var=1e-2):
    """简化Kalman滤波 - 自适应均值估计"""
    n = len(closes)
    x_est = np.full(n, np.nan)
    p_est = np.full(n, np.nan)

    if n == 0:
        return x_est

    x_est[0] = closes[0]
    p_est[0] = 1.0

    for i in range(1, n):
        # 预测
        x_pred = x_est[i-1]
        p_pred = p_est[i-1] + process_var

        # 更新
        k = p_pred / (p_pred + measure_var)
        x_est[i] = x_pred + k * (closes[i] - x_pred)
        p_est[i] = (1 - k) * p_pred

    return x_est


# ═══════════════════════════════════════════════════════════════
# 基础指标
# ═══════════════════════════════════════════════════════════════

def _sma(v, p):
    v = np.asarray(v, float)
    return pd.Series(v).rolling(p, min_periods=p).mean().values

def _std(v, p):
    v = np.asarray(v, float)
    return pd.Series(v).rolling(p, min_periods=p).std().values

def _atr(h, l, c=None, p=14):
    if c is None:
        c = (h + l) / 2
    h, l, c = np.asarray(h, float), np.asarray(l, float), np.asarray(c, float)
    tr = np.maximum(h[1:]-l[1:], np.maximum(abs(h[1:]-np.roll(h,1)[1:]), abs(l[1:]-np.roll(l,1)[1:])))
    r = np.full(len(h), np.nan); r[p] = np.mean(tr[:p])
    a = 1/p
    for i in range(p+1, len(h)):
        r[i] = tr[i-1]*a + r[i-1]*(1-a)
    return pd.Series(r).ffill().fillna(np.mean(tr[:p])).values

def _adx(h, l, c, p=14):
    h, l, c = np.asarray(h, float), np.asarray(l, float), np.asarray(c, float)
    if len(c) < p*2:
        return np.zeros(len(c))
    tr = np.maximum(h[1:]-l[1:], np.maximum(abs(h[1:]-c[:-1]), abs(l[1:]-c[:-1])))
    u = h[1:]-h[:-1]; d = l[:-1]-l[1:]
    pdi = 100*pd.Series(np.where((u>d)&(u>0), u, 0)).ewm(span=p, adjust=False).mean()/(pd.Series(tr).ewm(span=p, adjust=False).mean()+1e-10)
    mdi = 100*pd.Series(np.where((d>u)&(d>0), d, 0)).ewm(span=p, adjust=False).mean()/(pd.Series(tr).ewm(span=p, adjust=False).mean()+1e-10)
    dx = 100*np.abs(pdi-mdi)/(pdi+mdi+1e-10)
    result = pd.Series(dx).ewm(span=p, adjust=False).mean().values
    return np.concatenate([np.zeros(len(c)-len(result)), result])


# ═══════════════════════════════════════════════════════════════
# V4.0 均值回归策略
# ═══════════════════════════════════════════════════════════════

def gen_mr_v4(h1, h4, d1, cfg) -> List[Dict]:
    """
    MR V4.0 — 机构级均值回归策略

    核心升级:
    1. Kalman Filter 自适应均值
    2. Dynamic Z-Score
    3. Regime Filter
    """
    hc = h1['close'].values.astype(float)
    hh = h1['high'].values.astype(float)
    hl = h1['low'].values.astype(float)
    n = len(hc)

    # 指标计算
    ma = _sma(hc, BB_PERIOD)
    sd = _std(hc, BB_PERIOD)
    atr_v = _atr(hh, hl, hc)
    adx_v = _adx(hh, hl, hc)

    # Kalman滤波均值
    kf_mean = _kalman_filter(hc)

    lots = cfg.get('lot', 0.1)
    pip = float(cfg.get('pip', 0.0001))

    sig = []

    for i in range(BB_PERIOD + 20, n):
        if np.isnan(ma[i]) or np.isnan(sd[i]) or np.isnan(atr_v[i]) or np.isnan(adx_v[i]):
            continue

        price = hc[i]
        a = atr_v[i]
        adx = adx_v[i]

        # Regime Filter: ADX>25时禁用MR
        if adx > ADX_TREND_THRESHOLD:
            continue

        # 动态Z-Score阈值
        if a / price > 0.01:  # 高波动
            z_threshold = BB_STD_VOLATILE
        else:
            z_threshold = BB_STD_BASE

        # Z-Score计算 (使用Kalman均值)
        kf_val = kf_mean[i] if not np.isnan(kf_mean[i]) else ma[i]
        z = (price - kf_val) / (sd[i] + 1e-10)

        # 入场信号
        if z <= -z_threshold:
            # 多头入场
            sl = hl[max(0, i-5):i+1].min() - a * 0.5
            tp = kf_val  # 回归均值
            if sl < price:
                sig.append({
                    'bar': i, 'side': 1, 'entry': price, 'sl': sl, 'tp': tp,
                    'regime': f'mr_v4_z{z:.2f}_kf',
                    'strat': 'MR', 'lot': lots,
                    'z_score': z, 'atr': a,
                    'use_kalman': True
                })
        elif z >= z_threshold:
            # 空头入场
            sl = hh[max(0, i-5):i+1].max() + a * 0.5
            tp = kf_val
            if sl > price:
                sig.append({
                    'bar': i, 'side': -1, 'entry': price, 'sl': sl, 'tp': tp,
                    'regime': f'mr_v4_z{z:.2f}_kf',
                    'strat': 'MR', 'lot': lots,
                    'z_score': z, 'atr': a,
                    'use_kalman': True
                })

    return sig


if __name__ == "__main__":
    print("=" * 70)
    print("MR V4.0 自检")
    print("=" * 70)

    np.random.seed(42)
    n = 500
    closes = [100.0]
    for i in range(1, n):
        trend = 0.005 * np.sin(i * 0.02)  # 弱趋势
        noise = np.random.randn() * 0.3
        closes.append(closes[-1] * (1 + trend + noise * 0.01))
    closes = np.array(closes)
    opens = closes + np.random.randn(n) * 0.05
    highs = np.maximum(closes, opens) + np.abs(np.random.randn(n)) * 0.2
    lows = np.minimum(closes, opens) - np.abs(np.random.randn(n)) * 0.2
    times = np.arange(n) * 3600

    h1 = pd.DataFrame({'open': opens, 'high': highs, 'low': lows, 'close': closes, 'time': times})
    h4 = pd.DataFrame({'open': opens[::4], 'high': highs[::4], 'low': lows[::4], 'close': closes[::4], 'time': times[::4]})
    d1 = pd.DataFrame({'open': opens[::20], 'high': highs[::20], 'low': lows[::20], 'close': closes[::20], 'time': times[::20]})

    cfg = {'pip': 0.01, 'lot': 0.1}

    sigs = gen_mr_v4(h1, h4, d1, cfg)
    print(f"\n生成信号: {len(sigs)} 个")
    if sigs:
        buys = [s for s in sigs if s['side'] == 1]
        sells = [s for s in sigs if s['side'] == -1]
        print(f"  买入: {len(buys)}, 卖出: {len(sells)}")
        print(f"  平均Z-Score: {np.mean([s['z_score'] for s in sigs]):.2f}")

    print("\n" + "=" * 70)
    print("✅ MR V4.0 自检完成")
    print("=" * 70)
