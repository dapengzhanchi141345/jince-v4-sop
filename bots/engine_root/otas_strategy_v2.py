# -*- coding: utf-8 -*-
"""
OTAS V2.0: One Trade At A Time — 一次一单强趋势突破策略 (深度优化版)
=====================================================================
V2.0 升级要点:
1. 动态ADX阈值 (20-35基于波动率调整)
2. ATR动态冷却 (高波动时延长冷却)
3. Trailing Stop (盈利1.5×ATR后启动移动止损)
4. 收盘确认二次过滤 (突破后等收盘确认)
5. 独立沙盒隔离 (不影响其他策略)

核心改进:
- 减少假突破亏损
- 提高信号质量
- 锁定部分利润
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional
from dataclasses import dataclass
import json
import os

# ═══════════════════════════════════════════════════════════════
# 配置常量 (V2.0 动态参数)
# ═══════════════════════════════════════════════════════════════
# 趋势过滤基础
MA_FAST = 20
MA_SLOW = 60
ADX_BASE_THRESHOLD = 25
ATR_LOOKBACK = 14

# 突破检测
LOOKBACK_BARS = 20
BREAKOUT_THRESHOLD_MIN = 0.0005   # 0.05%
BREAKOUT_THRESHOLD_MAX = 0.002     # 0.2%

# 冷却参数
SIGNAL_COOLDOWN_BASE = 20          # 基础冷却
POSITIVE_COOLDOWN_BASE = 40        # 基础品种冷却

# 风险管理 (V2.0 动态)
SL_ATR_BASE = 1.5
TP_ATR_BASE = 3.5
TRAIL_START = 1.5                  # 移动止损启动点
TRAIL_STEP = 0.5                   # 移动止损步进

# 质量门槛
MIN_ADX = 20                       # 最低ADX
MAX_ADX = 35                       # 最高ADX动态上限
MIN_ATR_RATIO = 0.001              # 最小波动率


# ═══════════════════════════════════════════════════════════════
# 基础指标函数
# ═══════════════════════════════════════════════════════════════

def _ema(arr: np.ndarray, period: int) -> np.ndarray:
    """指数移动平均"""
    if len(arr) < period:
        return np.full_like(arr, np.nan)
    ema = np.zeros(len(arr))
    ema[:period] = np.nan
    ema[period] = np.mean(arr[:period])
    for i in range(period + 1, len(arr)):
        ema[i] = arr[i] * (2 / (period + 1)) + ema[i-1] * (1 - 2 / (period + 1))
    return ema

def _sma(arr: np.ndarray, period: int) -> np.ndarray:
    """简单移动平均"""
    result = np.full_like(arr, np.nan, dtype=float)
    for i in range(period - 1, len(arr)):
        result[i] = np.mean(arr[i - period + 1: i + 1])
    return result

def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    """平均真实波动范围"""
    n = len(highs)
    tr = np.full(n, np.nan)
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
    return _sma(tr, period)

def _adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    """平均方向指数"""
    n = len(highs)
    plus_dm = np.full(n, np.nan)
    minus_dm = np.full(n, np.nan)
    tr = np.full(n, np.nan)

    for i in range(1, n):
        up_move = highs[i] - highs[i-1]
        down_move = lows[i-1] - lows[i]
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))

        if up_move > down_move and up_move > 0:
            plus_dm[i] = up_move
        if down_move > up_move and down_move > 0:
            minus_dm[i] = down_move

    plus_di = np.full(n, np.nan)
    minus_di = np.full(n, np.nan)

    for i in range(period, n):
        atr_sum = np.nansum(tr[i-period+1:i+1])
        if atr_sum > 0:
            plus_di[i] = 100 * np.nansum(plus_dm[i-period+1:i+1]) / atr_sum
            minus_di[i] = 100 * np.nansum(minus_dm[i-period+1:i+1]) / atr_sum

    dx = np.full(n, np.nan)
    for i in range(period, n):
        denom = plus_di[i] + minus_di[i]
        if denom > 0:
            dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / denom

    return _sma(dx, period)


# ═══════════════════════════════════════════════════════════════
# V2.0 新增: 动态参数计算
# ═══════════════════════════════════════════════════════════════

def _calc_dynamic_adx(atr_ratio: float, base: int = ADX_BASE_THRESHOLD) -> int:
    """根据波动率动态调整ADX阈值
    高波动 → 提高阈值(更严格)
    低波动 → 降低阈值(更宽松)
    """
    if atr_ratio > 0.01:      # 高波动
        return min(base + 5, MAX_ADX)
    elif atr_ratio < 0.003:   # 低波动
        return max(base - 5, MIN_ADX)
    return base

def _calc_dynamic_cooldown(atr_ratio: float, base: int = SIGNAL_COOLDOWN_BASE) -> int:
    """根据波动率动态调整冷却期
    高波动 → 延长冷却(避免密集入场)
    """
    if atr_ratio > 0.01:
        return int(base * 1.5)
    return base

def _calc_dynamic_sl_tp(atr: float, atr_ratio: float) -> tuple:
    """动态计算SL/TP倍数
    高波动 → 宽SL大TP
    低波动 → 窄SL小TP
    """
    if atr_ratio > 0.008:
        return 2.0, 4.0  # SL=2×ATR, TP=4×ATR
    elif atr_ratio < 0.003:
        return 1.2, 2.5
    return 1.5, 3.5


# ═══════════════════════════════════════════════════════════════
# OTAS V2.0 主策略函数
# ═══════════════════════════════════════════════════════════════

def gen_otas(h1: pd.DataFrame, h4: pd.DataFrame, d1: pd.DataFrame, cfg: dict) -> List[Dict]:
    """
    OTAS V2.0 — 一次一单策略 (深度优化版)

    核心改进:
    1. 动态ADX阈值
    2. ATR动态冷却
    3. Trailing Stop
    4. 收盘确认二次过滤
    """
    hc = h1['close'].values.astype(float)
    hh = h1['high'].values.astype(float)
    hl = h1['low'].values.astype(float)
    n = len(hc)

    # 预计算指标
    ma_fast = _sma(hc, MA_FAST)
    ma_slow = _sma(hc, MA_SLOW)
    atr_v = _atr(hh, hl, hc, ATR_LOOKBACK)
    adx_v = _adx(hh, hl, hc, ADX_BASE_THRESHOLD)

    # 动态参数缓存
    last_dynamic_adx = ADX_BASE_THRESHOLD
    last_dynamic_cooldown = SIGNAL_COOLDOWN_BASE

    # 冷却跟踪
    last_signal_bar = -999
    last_signal_side = 0
    trailing_stops = {}  # bar_index -> trailing_stop_price

    sig = []

    for i in range(max(MA_SLOW, LOOKBACK_BARS, ATR_LOOKBACK) + 1, n):
        price = hc[i]
        if np.isnan(atr_v[i]) or atr_v[i] <= 0 or np.isnan(price) or price <= 0:
            continue

        a = atr_v[i]
        atr_ratio = a / price

        # ── V2.0: 动态参数计算 ──
        dynamic_adx = _calc_dynamic_adx(atr_ratio, last_dynamic_adx)
        dynamic_cooldown = _calc_dynamic_cooldown(atr_ratio, last_dynamic_cooldown)
        last_dynamic_adx = dynamic_adx
        last_dynamic_cooldown = dynamic_cooldown

        sl_mult, tp_mult = _calc_dynamic_sl_tp(a, atr_ratio)

        # ── 冷却过滤 (动态) ──
        if i - last_signal_bar < dynamic_cooldown:
            continue

        # ── 趋势过滤 ──
        if np.isnan(ma_fast[i]) or np.isnan(ma_slow[i]) or np.isnan(adx_v[i]):
            continue

        # V2.0: 使用动态ADX阈值
        if adx_v[i] < dynamic_adx:
            continue

        # ATR 波动率过滤
        if atr_ratio < MIN_ATR_RATIO:
            continue

        # ── 方向判定 ──
        is_uptrend = ma_fast[i] > ma_slow[i] and price > ma_fast[i]
        is_downtrend = ma_fast[i] < ma_slow[i] and price < ma_fast[i]

        if not is_uptrend and not is_downtrend:
            continue

        # ── 区间突破检测 ──
        if i < LOOKBACK_BARS:
            continue
        range_high = np.max(hh[i-LOOKBACK_BARS:i])
        range_low = np.min(hl[i-LOOKBACK_BARS:i])
        range_height = range_high - range_low

        if range_height <= 0:
            continue

        # V2.0: 动态突破阈值
        dynamic_breakout_threshold = BREAKOUT_THRESHOLD_MIN + (BREAKOUT_THRESHOLD_MAX - BREAKOUT_THRESHOLD_MIN) * min(1.0, atr_ratio * 500)

        # ── 买入信号 ──
        if is_uptrend:
            # 收盘价突破区间高点 + 收盘确认
            if hc[i] > range_high * (1 + dynamic_breakout_threshold):
                # 二次确认: 前一根K线在区间内或刚突破
                if i > 0 and hc[i-1] <= range_high * (1 + 0.0005):
                    entry = min(price, range_high * 1.0005)
                    sl = entry - a * sl_mult
                    tp = entry + a * tp_mult

                    if sl >= entry or tp <= entry:
                        continue

                    # V2.0: 记录移动止损起点
                    trailing_stops[i] = entry + a * TRAIL_START

                    sig.append({
                        'bar': i, 'side': 1, 'entry': entry, 'sl': sl, 'tp': tp,
                        'regime': f'otas_v2_bull_r{adx_v[i]:.0f}', 'strat': 'OTAS',
                        'lot': cfg.get('lot', 0.1),
                        'adx': adx_v[i], 'atr': a, 'range_high': range_high,
                        'sl_mult': sl_mult, 'tp_mult': tp_mult,
                        'trailing_start': entry + a * TRAIL_START
                    })
                    last_signal_bar = i
                    last_signal_side = 1

        # ── 卖出信号 ──
        if is_downtrend:
            if hc[i] < range_low * (1 - dynamic_breakout_threshold):
                if i > 0 and hc[i-1] >= range_low * (1 - 0.0005):
                    entry = max(price, range_low * 0.9995)
                    sl = entry + a * sl_mult
                    tp = entry - a * tp_mult

                    if sl <= entry or tp >= entry:
                        continue

                    trailing_stops[i] = entry - a * TRAIL_START

                    sig.append({
                        'bar': i, 'side': -1, 'entry': entry, 'sl': sl, 'tp': tp,
                        'regime': f'otas_v2_bear_r{adx_v[i]:.0f}', 'strat': 'OTAS',
                        'lot': cfg.get('lot', 0.1),
                        'adx': adx_v[i], 'atr': a, 'range_low': range_low,
                        'sl_mult': sl_mult, 'tp_mult': tp_mult,
                        'trailing_start': entry - a * TRAIL_START
                    })
                    last_signal_bar = i
                    last_signal_side = -1

    return sig


# ═══════════════════════════════════════════════════════════════
# OTAS V2.0 回测函数 (含Trailing Stop)
# ═══════════════════════════════════════════════════════════════

def backtest_otas_v2(h1_data: pd.DataFrame, h4_data: pd.DataFrame, d1_data: pd.DataFrame,
                     initial_equity: float = 10000.0, pip_usd: float = 10.0) -> Dict:
    """
    OTAS V2.0 回测 — 含移动止损
    """
    signals = gen_otas(h1_data, h4_data, d1_data, {'pip': 0.01, 'lot': 0.1})
    if not signals:
        return {'signals': 0, 'trades': 0, 'win_rate': 0, 'total_pnl': 0.0, 'profit_factor': 0.0}

    equity = initial_equity
    trades = []
    position = 0  # 0=空仓, 1=多, -1=空
    entry_price = 0
    sl_price = 0
    tp_price = 0
    trailing_stop = 0
    lot = 0.1
    trail_active = False

    for i, sig in enumerate(signals):
        entry = sig['entry']
        sl = sig['sl']
        tp = sig['tp']
        side = sig['side']
        lot = sig.get('lot', 0.1)
        trail_start_price = sig.get('trailing_start', 0)

        # ── 一次一单检查 ──
        if position != 0:
            # 检查当前持仓是否被止损/止盈
            end = min(i + 50, len(h1_data))
            path = h1_data.iloc[i:end]
            hit = False

            for _, row in path.iterrows():
                high = row['high']; low = row['low']; close = row['close']
                a = sig.get('atr', 0)

                if position == 1:  # 多单
                    # 移动止损逻辑
                    if trail_active and trailing_stop > 0:
                        effective_sl = max(sl_price, trailing_stop)
                    else:
                        effective_sl = sl_price

                    if low <= effective_sl:
                        pnl = (entry_price - effective_sl) * 100 * lot * pip_usd / 100
                        trades.append({'type': 'BUY', 'result': 'loss', 'pnl': pnl, 'bar': i, 'reason': 'sl'})
                        position = 0; hit = True; break

                    if high >= tp_price:
                        pnl = (tp_price - entry_price) * 100 * lot * pip_usd / 100
                        trades.append({'type': 'BUY', 'result': 'win', 'pnl': pnl, 'bar': i, 'reason': 'tp'})
                        position = 0; hit = True; break

                    # 检查是否启动移动止损
                    if not trail_active and close > trail_start_price:
                        trail_active = True
                        trailing_stop = entry_price + a * TRAIL_START

                    # 更新移动止损
                    if trail_active and close > trailing_stop:
                        trailing_stop = max(trailing_stop, close - a * TRAIL_STEP)

                else:  # 空单
                    if trail_active and trailing_stop > 0:
                        effective_sl = min(sl_price, trailing_stop)
                    else:
                        effective_sl = sl_price

                    if high >= effective_sl:
                        pnl = (effective_sl - entry_price) * 100 * lot * pip_usd / 100
                        trades.append({'type': 'SELL', 'result': 'loss', 'pnl': pnl, 'bar': i, 'reason': 'sl'})
                        position = 0; hit = True; break

                    if low <= tp_price:
                        pnl = (entry_price - tp_price) * 100 * lot * pip_usd / 100
                        trades.append({'type': 'SELL', 'result': 'win', 'pnl': pnl, 'bar': i, 'reason': 'tp'})
                        position = 0; hit = True; break

                    # 检查是否启动移动止损
                    if not trail_active and close < trail_start_price:
                        trail_active = True
                        trailing_stop = entry_price - a * TRAIL_START

                    # 更新移动止损
                    if trail_active and close < trailing_stop:
                        trailing_stop = min(trailing_stop, close + a * TRAIL_STEP)

            if hit:
                trail_active = False
                trailing_stop = 0
                continue
            else:
                continue

        # 开新仓
        position = side
        entry_price = entry
        sl_price = sl
        tp_price = tp
        trail_active = False
        trailing_stop = 0
        lot = lot

    # 统计
    if not trades:
        return {'signals': len(signals), 'trades': 0, 'win_rate': 0.0, 'total_pnl': 0.0, 'profit_factor': 0.0}

    wins = [t for t in trades if t['result'] == 'win']
    losses = [t for t in trades if t['result'] == 'loss']
    total_pnl = sum(t['pnl'] for t in trades)
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    gross_profit = sum(t['pnl'] for t in wins) if wins else 0
    gross_loss = abs(sum(t['pnl'] for t in losses)) if losses else 1
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    return {
        'signals': len(signals),
        'trades': len(trades),
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'profit_factor': pf,
        'wins': len(wins),
        'losses': len(losses),
        'avg_pnl': total_pnl / len(trades) if trades else 0,
        'avg_win': np.mean([t['pnl'] for t in wins]) if wins else 0,
        'avg_loss': np.mean([t['pnl'] for t in losses]) if losses else 0,
    }


# ═══════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("OTAS V2.0 — 深度优化版自检")
    print("=" * 70)

    # 创建测试数据
    np.random.seed(42)
    n = 1000
    closes = [100.0]
    for i in range(1, n):
        trend = 0.02 * np.sin(i * 0.01)
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

    signals = gen_otas(h1, h4, d1, {'pip': 0.01, 'lot': 0.1})
    print(f"\n生成信号: {len(signals)} 个")
    if signals:
        buys = [s for s in signals if s['side'] == 1]
        sells = [s for s in signals if s['side'] == -1]
        print(f"  买入: {len(buys)}, 卖出: {len(sells)}")
        print(f"  平均ADX: {np.mean([s['adx'] for s in signals]):.1f}")
        print(f"  平均ATR: {np.mean([s['atr'] for s in signals]):.2f}")
        print(f"  SL/TP倍数: {np.mean([s['sl_mult'] for s in signals]):.2f}× / {np.mean([s['tp_mult'] for s in signals]):.2f}×")

    result = backtest_otas_v2(h1, h4, d1, initial_equity=10000.0, pip_usd=10.0)
    print(f"\n回测结果 (V2.0):")
    print(f"  信号: {result['signals']} 个")
    print(f"  交易: {result['trades']} 笔")
    print(f"  胜率: {result['win_rate']:.1f}%")
    print(f"  盈亏: ${result['total_pnl']:.2f}")
    print(f"  PF: {result['profit_factor']:.2f}")
    if result['trades'] > 0:
        print(f"  平均盈亏: ${result['avg_pnl']:.2f}")

    print("\n" + "=" * 70)
    print("✅ OTAS V2.0 自检完成")
    print("=" * 70)
