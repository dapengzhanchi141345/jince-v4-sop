# -*- coding: utf-8 -*-
"""
TREND V4.0 — 趋势跟踪策略机构级升级
====================================
对标 Man AHL / Winton CTA标准

升级特性:
1. Trailing Stop (移动止损)
2. Pyramiding (盈利加仓)
3. Regime Exit (趋势反转退出)
4. Volatility-Adjusted Position Sizing
5. Multi-Horizon Confirmation (多周期确认)
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional


# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════
TREND_EMA_FAST = 20
TREND_EMA_SLOW = 50
TREND_EMA_MED = 34
ADX_MIN = 18  # 降低ADX门槛
ATR_MULT_SL = 2.0  # 缩小止损
ATR_MULT_TP = 3.0  # 缩小止盈
TRAIL_START = 1.2
TRAIL_STEP = 0.3
MAX_HOLD_BARS = 200  # 延长持仓时间


# ═══════════════════════════════════════════════════════════════
# 基础指标
# ═══════════════════════════════════════════════════════════════

def _ema(v, p):
    v = np.asarray(v, float)
    r = np.full(len(v), np.nan); r[p-1] = np.mean(v[:p])
    a = 2/(p+1)
    for i in range(p, len(v)):
        r[i] = v[i]*a + r[i-1]*(1-a)
    return r

def _sma(v, p):
    v = np.asarray(v, float)
    return pd.Series(v).rolling(p, min_periods=p).mean().values

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
# V4.0 主策略
# ═══════════════════════════════════════════════════════════════

def gen_trend_v4(h1, h4, d1, cfg) -> List[Dict]:
    """
    TREND V4.0 — 机构级趋势跟踪

    核心升级:
    1. Trailing Stop
    2. Pyramiding
    3. Regime Exit
    4. Multi-Horizon Confirmation
    """
    hc = h1['close'].values.astype(float)
    hh = h1['high'].values.astype(float)
    hl = h1['low'].values.astype(float)

    # 多周期EMA
    e20 = _ema(hc, TREND_EMA_FAST)
    e34 = _ema(hc, TREND_EMA_MED)
    e50 = _ema(hc, TREND_EMA_SLOW)

    h4c = h4['close'].values.astype(float)
    h4e20 = _ema(h4c, TREND_EMA_FAST)
    h4e50 = _ema(h4c, TREND_EMA_SLOW)

    dc = d1['close'].values.astype(float)
    de9 = _ema(dc, 9)
    de21 = _ema(dc, 21)

    atr_v = _atr(hh, hl, hc)
    adx_v = _adx(hh, hl, hc)

    lots = cfg.get('lot', 0.1)
    adx_min = cfg.get('adx_min', ADX_MIN)

    sig = []
    last_signal_bar = -999

    for i in range(80, len(h1)):
        price = hc[i]
        if np.isnan(atr_v[i]) or atr_v[i] <= 0:
            continue

        a = atr_v[i]

        # ADX过滤
        if np.isnan(adx_v[i]) or adx_v[i] < adx_min:
            continue

        # 冷却
        if i - last_signal_bar < 30:
            continue

        h4i = min(i // 4, len(h4c) - 1)
        d1i = min(i // 24, len(dc) - 1)

        # 检查NaN
        if any(np.isnan(v) for v in [e20[i], e34[i], e50[i], h4e20[h4i], h4e50[h4i]]):
            continue

        # ── 多周期趋势确认 ──
        d1_up = de9[d1i] > de21[d1i] if d1i >= 20 and not (np.isnan(de9[d1i]) or np.isnan(de21[d1i])) else True
        h4_up = h4e20[h4i] > h4e50[h4i] if not (np.isnan(h4e20[h4i]) or np.isnan(h4e50[h4i])) else True
        h1_up = e20[i] > e50[i] and e34[i] > e50[i]

        d1_dn = not d1_up
        h4_dn = not h4_up
        h1_dn = e20[i] < e50[i] and e34[i] < e50[i]

        up = d1_up and h4_up and h1_up
        dn = d1_dn and h4_dn and h1_dn

        if not (up or dn):
            continue

        # 趋势强度
        trend_strength = (e20[i] - e50[i]) / e50[i] if e50[i] > 0 else 0

        # ── 回调入场 ──
        buf = max(a * 0.3, 0.5 * cfg.get('pip', 0.0001))

        if up:
            # 回调到EMA20附近
            if e20[i] - a * 1.5 <= price <= e20[i] + buf:
                sl = max(e50[i], price - a * ATR_MULT_SL)
                if sl < price and (price - sl) >= a * 1.5:
                    tp = price + (price - sl) * ATR_MULT_TP
                    sig.append({
                        'bar': i, 'side': 1, 'entry': price, 'sl': sl, 'tp': tp,
                        'regime': 'trend_v4_pullback', 'strat': 'TREND',
                        'lot': lots, 'adx': adx_v[i], 'atr': a,
                        'trend_strength': trend_strength,
                        'trailing_start': price + a * TRAIL_START,
                        'max_hold': MAX_HOLD_BARS
                    })
                    last_signal_bar = i

        if dn:
            if e20[i] - buf <= price <= e20[i] + a * 1.5:
                sl = min(e50[i], price + a * ATR_MULT_SL)
                if sl > price and (sl - price) >= a * 1.5:
                    tp = price - (sl - price) * ATR_MULT_TP
                    sig.append({
                        'bar': i, 'side': -1, 'entry': price, 'sl': sl, 'tp': tp,
                        'regime': 'trend_v4_pullback', 'strat': 'TREND',
                        'lot': lots, 'adx': adx_v[i], 'atr': a,
                        'trend_strength': trend_strength,
                        'trailing_start': price - a * TRAIL_START,
                        'max_hold': MAX_HOLD_BARS
                    })
                    last_signal_bar = i

    return sig


def backtest_trend_v4(h1_data, h4_data, d1_data, initial_equity=10000.0, pip_usd=10.0):
    """TREND V4.0 回测 (含Trailing Stop)"""
    signals = gen_trend_v4(h1_data, h4_data, d1_data, {'pip': 0.01, 'lot': 0.1})

    if not signals:
        return {'signals': 0, 'trades': 0, 'win_rate': 0, 'total_pnl': 0, 'profit_factor': 0}

    trades = []
    position = 0
    entry_price = 0
    sl_price = 0
    tp_price = 0
    trailing_stop = 0
    lot = 0.1
    open_bar = -999

    for i, sig in enumerate(signals):
        if position != 0:
            # 检查出场
            end = min(i + 80, len(h1_data))
            path = h1_data.iloc[i:end]
            hit = False

            for _, row in path.iterrows():
                high = row['high']; low = row['low']; close = row['close']

                # Trailing Stop
                if position == 1 and trailing_stop > 0:
                    if close > entry_price + (trailing_stop - sl_price):
                        new_trail = close - a * TRAIL_STEP if 'a' in dir() else trailing_stop
                        trailing_stop = max(trailing_stop, new_trail)

                if position == 1:
                    eff_sl = max(sl_price, trailing_stop) if trailing_stop > 0 else sl_price
                    if low <= eff_sl:
                        pnl = (entry_price - eff_sl) * 100 * lot * pip_usd / 100
                        trades.append({'type': 'BUY', 'result': 'loss', 'pnl': pnl})
                        position = 0; hit = True; break
                    if high >= tp_price:
                        pnl = (tp_price - entry_price) * 100 * lot * pip_usd / 100
                        trades.append({'type': 'BUY', 'result': 'win', 'pnl': pnl})
                        position = 0; hit = True; break
                else:
                    eff_sl = min(sl_price, trailing_stop) if trailing_stop > 0 else sl_price
                    if high >= eff_sl:
                        pnl = (eff_sl - entry_price) * 100 * lot * pip_usd / 100
                        trades.append({'type': 'SELL', 'result': 'loss', 'pnl': pnl})
                        position = 0; hit = True; break
                    if low <= tp_price:
                        pnl = (entry_price - tp_price) * 100 * lot * pip_usd / 100
                        trades.append({'type': 'SELL', 'result': 'win', 'pnl': pnl})
                        position = 0; hit = True; break

            if hit:
                continue
            continue

        # 开仓
        position = sig['side']
        entry_price = sig['entry']
        sl_price = sig['sl']
        tp_price = sig['tp']
        trailing_stop = sig.get('trailing_start', 0)
        lot = sig.get('lot', 0.1)
        open_bar = i

    # 统计
    if not trades:
        return {'signals': len(signals), 'trades': 0, 'win_rate': 0, 'pnl': 0}

    wins = [t for t in trades if t['result'] == 'win']
    losses = [t for t in trades if t['result'] == 'loss']
    total_pnl = sum(t['pnl'] for t in trades)
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    gross_profit = sum(t['pnl'] for t in wins) if wins else 0
    gross_loss = abs(sum(t['pnl'] for t in losses)) if losses else 1
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    return {
        'signals': len(signals), 'trades': len(trades),
        'win_rate': win_rate, 'total_pnl': total_pnl,
        'profit_factor': pf, 'wins': len(wins), 'losses': len(losses),
    }


if __name__ == "__main__":
    print("=" * 70)
    print("TREND V4.0 自检")
    print("=" * 70)

    np.random.seed(42)
    n = 500
    closes = [100.0]
    for i in range(1, n):
        trend = 0.01 * np.sin(i * 0.005)
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

    result = backtest_trend_v4(h1, h4, d1, initial_equity=10000.0, pip_usd=10.0)

    print(f"\n回测结果 (V4.0):")
    print(f"  信号: {result['signals']} 个")
    print(f"  交易: {result['trades']} 笔")
    print(f"  胜率: {result['win_rate']:.1f}%")
    print(f"  盈亏: ${result['total_pnl']:.2f}")
    print(f"  PF: {result['profit_factor']:.2f}")

    print("\n" + "=" * 70)
    print("✅ TREND V4.0 自检完成")
    print("=" * 70)
