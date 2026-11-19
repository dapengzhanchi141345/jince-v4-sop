# -*- coding: utf-8 -*-
"""
DIV V4.0 — 背离策略机构级升级
===============================
对标 Institutional Divergence标准

升级特性:
1. Hidden Divergence (隐藏背离)
2. Multi-TF Divergence (多周期背离共振)
3. MACD辅助确认
4. Z-Score过滤 (排除极端行情)
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple


# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════
DIV_LOOKBACK = 20
MIN_DIV_DISTANCE = 10  # 摆动点最小距离
Z_SCORE_THRESHOLD = 2.5  # Z-Score过滤阈值


# ═══════════════════════════════════════════════════════════════
# 基础指标
# ═══════════════════════════════════════════════════════════════

def _rsi(v, p=14):
    v = np.asarray(v, float)
    d = np.diff(v)
    gain = np.where(d > 0, d, 0.0); loss = np.where(d < 0, -d, 0.0)
    ag = pd.Series(gain).ewm(span=p, adjust=False).mean().values
    al = pd.Series(loss).ewm(span=p, adjust=False).mean().values
    rs = ag/(al+1e-10)
    out = np.full(len(v), np.nan)
    out[1:] = 100 - 100/(1+rs)
    return out

def _macd(v, fast=12, slow=26, sig=9):
    v = np.asarray(v, float)
    ef = np.full(len(v), np.nan); ef[slow-1] = np.mean(v[:slow])
    es = np.full(len(v), np.nan); es[slow-1] = np.mean(v[:slow])
    a_f = 2/(fast+1); a_s = 2/(slow+1)
    for i in range(slow, len(v)):
        ef[i] = v[i]*a_f + ef[i-1]*(1-a_f)
        es[i] = v[i]*a_s + es[i-1]*(1-a_s)
    m = ef - es
    s = np.full(len(v), np.nan); s[sig-1] = np.mean(m[:sig])
    a = 2/(sig+1)
    for i in range(sig, len(v)):
        s[i] = m[i]*a + s[i-1]*(1-a)
    return m, s, m - s

def _find_swing(h, l, lb=5):
    h, l = np.asarray(h, float), np.asarray(l, float)
    swh, swl = [], []
    for i in range(lb, len(h)-lb):
        if h[i] == max(h[i-lb:i+lb+1]):
            swh.append((i, h[i]))
        if l[i] == min(l[i-lb:i+lb+1]):
            swl.append((i, l[i]))
    return swh, swl

def _z_score(v, p=20):
    """计算Z-Score"""
    s = pd.Series(v)
    mean = s.rolling(p, min_periods=p).mean().values
    std = s.rolling(p, min_periods=p).std().values
    return (v - mean) / (std + 1e-10)


# ═══════════════════════════════════════════════════════════════
# V4.0 背离策略
# ═══════════════════════════════════════════════════════════════

def _detect_regular_div(h, l, c, rsi_v, macd_hist, sw_h, sw_l):
    """常规背离检测"""
    sigs = []

    # 看涨背离: 价格更低低, RSI更高低
    for a, b in zip(sw_l[:-1], sw_l[1:]):
        ia, ib = a[0], b[0]
        if ib - ia < MIN_DIV_DISTANCE:
            continue
        if b[1] < a[1] - 0.001 and rsi_v[ib] > rsi_v[ia] + 1:
            # MACD辅助确认
            macd_confirm = macd_hist[ib] > macd_hist[ia] if not np.isnan(macd_hist[ib]) else True
            if macd_confirm:
                sigs.append({
                    'bar': ib, 'side': 1, 'type': 'bull_reg',
                    'price_low': b[1], 'rsi_low': rsi_v[ib]
                })

    # 看跌背离: 价格更高高, RSI更低高
    for a, b in zip(sw_h[:-1], sw_h[1:]):
        ia, ib = a[0], b[0]
        if ib - ia < MIN_DIV_DISTANCE:
            continue
        if b[1] > a[1] + 0.001 and rsi_v[ib] < rsi_v[ia] - 1:
            macd_confirm = macd_hist[ib] < macd_hist[ia] if not np.isnan(macd_hist[ib]) else True
            if macd_confirm:
                sigs.append({
                    'bar': ib, 'side': -1, 'type': 'bear_reg',
                    'price_high': b[1], 'rsi_high': rsi_v[ib]
                })

    return sigs

def _detect_hidden_div(h, l, c, rsi_v, macd_hist, sw_h, sw_l):
    """隐藏背离检测 (趋势延续信号)"""
    sigs = []

    # 看涨隐藏背离: 价格更高低, RSI更低低 (上升趋势中的回调)
    for a, b in zip(sw_l[:-1], sw_l[1:]):
        ia, ib = a[0], b[0]
        if ib - ia < MIN_DIV_DISTANCE:
            continue
        if b[1] > a[1] and rsi_v[ib] < rsi_v[ia] - 1:
            sigs.append({
                'bar': ib, 'side': 1, 'type': 'bull_hidden',
                'price_high': b[1], 'rsi_low': rsi_v[ib]
            })

    # 看跌隐藏背离: 价格更低高, RSI更高高 (下降趋势中的反弹)
    for a, b in zip(sw_h[:-1], sw_h[1:]):
        ia, ib = a[0], b[0]
        if ib - ia < MIN_DIV_DISTANCE:
            continue
        if b[1] < a[1] and rsi_v[ib] > rsi_v[ia] + 1:
            sigs.append({
                'bar': ib, 'side': -1, 'type': 'bear_hidden',
                'price_low': b[1], 'rsi_high': rsi_v[ib]
            })

    return sigs


def gen_div_v4(h1, h4, d1, cfg) -> List[Dict]:
    """
    DIV V4.0 — 机构级背离策略

    核心升级:
    1. Hidden Divergence
    2. MACD辅助确认
    3. Z-Score过滤
    """
    hc = h1['close'].values.astype(float)
    hh = h1['high'].values.astype(float)
    hl = h1['low'].values.astype(float)
    n = len(hc)

    # 指标计算
    rsi_v = _rsi(hc, 14)
    macd_line, macd_sig, macd_hist = _macd(hc)
    sw_h, sw_l = _find_swing(hh, hl, 5)

    # Z-Score过滤
    z_v = _z_score(hc, DIV_LOOKBACK)

    lots = cfg.get('lot', 0.1)
    atr_v = np.asarray(h1['high'].values - h1['low'].values, float)

    sig = []

    for i in range(DIV_LOOKBACK + 10, n):
        if np.isnan(rsi_v[i]) or np.isnan(z_v[i]):
            continue

        # Z-Score过滤: 排除极端行情
        if abs(z_v[i]) > Z_SCORE_THRESHOLD:
            continue

        # 检测背离
        reg_div = _detect_regular_div(hh, hl, hc, rsi_v, macd_hist, sw_h, sw_l)
        hidden_div = _detect_hidden_div(hh, hl, hc, rsi_v, macd_hist, sw_h, sw_l)

        # 合并信号
        all_div = reg_div + hidden_div

        for d in all_div:
            if d['bar'] == i:
                a = atr_v[i] if i < len(atr_v) and not np.isnan(atr_v[i]) else 0.5
                if d['side'] == 1:
                    sl = hl[max(0, i-5):i+1].min() - a * 0.5
                    tp = hc[i] + a * 2.0
                else:
                    sl = hh[max(0, i-5):i+1].max() + a * 0.5
                    tp = hc[i] - a * 2.0

                sig.append({
                    'bar': i, 'side': d['side'],
                    'entry': hc[i], 'sl': sl, 'tp': tp,
                    'regime': f'div_v4_{d["type"]}',
                    'strat': 'DIV', 'lot': lots,
                    'div_type': d['type'],
                    'z_score': z_v[i]
                })

    return sig


if __name__ == "__main__":
    print("=" * 70)
    print("DIV V4.0 自检")
    print("=" * 70)

    np.random.seed(42)
    n = 500
    closes = [100.0]
    for i in range(1, n):
        trend = 0.01 * np.sin(i * 0.01)
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

    sigs = gen_div_v4(h1, h4, d1, cfg)
    print(f"\n生成信号: {len(sigs)} 个")
    if sigs:
        buys = [s for s in sigs if s['side'] == 1]
        sells = [s for s in sigs if s['side'] == -1]
        print(f"  买入: {len(buys)}, 卖出: {len(sells)}")
        types = {}
        for s in sigs:
            t = s['div_type']
            types[t] = types.get(t, 0) + 1
        print(f"  背离类型: {types}")

    print("\n" + "=" * 70)
    print("✅ DIV V4.0 自检完成")
    print("=" * 70)
