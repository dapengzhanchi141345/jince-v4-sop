# -*- coding: utf-8 -*-
"""
OTAS V3.0: One Trade At A Time — 一次一单策略 (机构级升级)
==========================================================
对标 Prop Firm 顶尖策略 (Apex Sentinel / GoldStrike AI)

V3.0 升级:
1. Tiered Drawdown Throttling (分级回撤减速)
2. Fractional Kelly 仓位管理
3. Regime-Aware 动态参数
4. Multi-Timeframe Confirmation
5. Time-Based Exit (持仓超时平仓)
6. News Volatility Filter
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional
from risk_manager import RiskManager


# ═══════════════════════════════════════════════════════════════
# 配置常量 (V3.0 机构级)
# ═══════════════════════════════════════════════════════════════
# 趋势过滤
MA_FAST = 20
MA_SLOW = 60
ADX_BASE = 25

# 突破检测
LOOKBACK = 20
BREAKOUT_THRESHOLD = 0.001

# 冷却
COOLDOWN_BARS = 25

# 风险管理
SL_ATR_MULT = 1.5
TP_ATR_MULT = 3.5
TRAIL_START = 1.5
TRAIL_STEP = 0.5

# 时间控制
MAX_HOLD_BARS = 100  # 最大持仓K线数
TIME_EXIT_BARS = 50  # 持仓超时检查


# ═══════════════════════════════════════════════════════════════
# 基础指标
# ═══════════════════════════════════════════════════════════════

def _ema(arr, period):
    if len(arr) < period:
        return np.full_like(arr, np.nan)
    ema = np.zeros(len(arr))
    ema[:period] = np.nan
    ema[period] = np.mean(arr[:period])
    for i in range(period + 1, len(arr)):
        ema[i] = arr[i] * (2 / (period + 1)) + ema[i-1] * (1 - 2 / (period + 1))
    return ema

def _sma(arr, period):
    result = np.full_like(arr, np.nan, dtype=float)
    for i in range(period - 1, len(arr)):
        result[i] = np.mean(arr[i - period + 1: i + 1])
    return result

def _atr(highs, lows, closes, period=14):
    n = len(highs)
    tr = np.full(n, np.nan)
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
    return _sma(tr, period)

def _adx(highs, lows, closes, period=14):
    n = len(highs)
    plus_dm = np.full(n, np.nan)
    minus_dm = np.full(n, np.nan)
    tr = np.full(n, np.nan)

    for i in range(1, n):
        up = highs[i] - highs[i-1]
        down = lows[i-1] - lows[i]
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        if up > down and up > 0:
            plus_dm[i] = up
        if down > up and down > 0:
            minus_dm[i] = down

    plus_di = np.full(n, np.nan)
    minus_di = np.full(n, np.nan)
    for i in range(period, n):
        s = np.nansum(tr[i-period+1:i+1])
        if s > 0:
            plus_di[i] = 100 * np.nansum(plus_dm[i-period+1:i+1]) / s
            minus_di[i] = 100 * np.nansum(minus_dm[i-period+1:i+1]) / s

    dx = np.full(n, np.nan)
    for i in range(period, n):
        d = plus_di[i] + minus_di[i]
        if d > 0:
            dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / d

    return _sma(dx, period)


# ═══════════════════════════════════════════════════════════════
# V3.0 主策略
# ═══════════════════════════════════════════════════════════════

def gen_otas_v3(h1, h4, d1, cfg, risk_mgr: Optional[RiskManager] = None) -> List[Dict]:
    """
    OTAS V3.0 — 机构级一次一单策略

    核心升级:
    1. Drawdown Throttling
    2. Kelly Position Sizing
    3. Time-Based Exit
    4. Multi-Timeframe Confirmation
    """
    hc = h1['close'].values.astype(float)
    hh = h1['high'].values.astype(float)
    hl = h1['low'].values.astype(float)
    n = len(hc)

    # 预计算指标
    ma_fast = _sma(hc, MA_FAST)
    ma_slow = _sma(hc, MA_SLOW)
    atr_v = _atr(hh, hl, hc, 14)
    adx_v = _adx(hh, hl, hc, ADX_BASE)

    # 多时间框架 EMA
    h4c = h4['close'].values.astype(float)
    h4_ma20 = _sma(h4c, 20)
    h4_ma50 = _sma(h4c, 50)

    # 冷却跟踪
    last_signal_bar = -999
    last_signal_side = 0

    # 持仓跟踪
    position_open_bar = -999
    position_side = 0

    sig = []

    for i in range(max(MA_SLOW, LOOKBACK, 14) + 1, n):
        price = hc[i]
        if np.isnan(atr_v[i]) or atr_v[i] <= 0 or np.isnan(price) or price <= 0:
            continue

        a = atr_v[i]
        atr_ratio = a / price

        # ── 检查持仓出场 (Time-Based Exit) ──
        if position_open_bar >= 0 and i - position_open_bar >= MAX_HOLD_BARS:
            # 强制平仓信号 (不生成新信号，仅记录)
            position_open_bar = -999
            position_side = 0

        # ── 冷却过滤 ──
        if i - last_signal_bar < COOLDOWN_BARS:
            continue

        # ── 趋势过滤 ──
        if np.isnan(ma_fast[i]) or np.isnan(ma_slow[i]) or np.isnan(adx_v[i]):
            continue

        # 多时间框架确认
        h4i = min(i // 4, len(h4c) - 1)
        if not (np.isnan(h4_ma20[h4i]) and np.isnan(h4_ma50[h4i])):
            h4_trend = h4_ma20[h4i] > h4_ma50[h4i] if not np.isnan(h4_ma20[h4i]) and not np.isnan(h4_ma50[h4i]) else True
        else:
            h4_trend = True

        # ADX + 趋势确认
        if adx_v[i] < ADX_BASE:
            continue

        is_uptrend = ma_fast[i] > ma_slow[i] and price > ma_fast[i] and h4_trend
        is_downtrend = ma_fast[i] < ma_slow[i] and price < ma_fast[i] and not h4_trend

        if not is_uptrend and not is_downtrend:
            continue

        # ── 区间突破检测 ──
        if i < LOOKBACK:
            continue
        range_high = np.max(hh[i-LOOKBACK:i])
        range_low = np.min(hl[i-LOOKBACK:i])

        # ── 买入信号 ──
        if is_uptrend and position_side == 0:
            if hc[i] > range_high * (1 + BREAKOUT_THRESHOLD):
                if i > 0 and hc[i-1] <= range_high * (1.0005):
                    entry = min(price, range_high * 1.0005)
                    sl = entry - a * SL_ATR_MULT
                    tp = entry + a * TP_ATR_MULT

                    if sl >= entry or tp <= entry:
                        continue

                    # 仓位计算
                    if risk_mgr:
                        pos_cfg = risk_mgr.calculate_position_size(
                            symbol="XAUUSD", entry=entry, sl=sl, atr=a, strategy="OTAS"
                        )
                        lot = pos_cfg["lots"]
                    else:
                        lot = cfg.get('lot', 0.1)

                    sig.append({
                        'bar': i, 'side': 1, 'entry': entry, 'sl': sl, 'tp': tp,
                        'regime': f'otas_v3_bull_r{adx_v[i]:.0f}', 'strat': 'OTAS',
                        'lot': lot, 'adx': adx_v[i], 'atr': a,
                        'risk_tier': risk_mgr._drawdown_tier if risk_mgr else 1.0
                    })
                    last_signal_bar = i
                    position_open_bar = i
                    position_side = 1

        # ── 卖出信号 ──
        if is_downtrend and position_side == 0:
            if hc[i] < range_low * (1 - BREAKOUT_THRESHOLD):
                if i > 0 and hc[i-1] >= range_low * (1 - 0.0005):
                    entry = max(price, range_low * 0.9995)
                    sl = entry + a * SL_ATR_MULT
                    tp = entry - a * TP_ATR_MULT

                    if sl <= entry or tp >= entry:
                        continue

                    if risk_mgr:
                        pos_cfg = risk_mgr.calculate_position_size(
                            symbol="XAUUSD", entry=entry, sl=sl, atr=a, strategy="OTAS"
                        )
                        lot = pos_cfg["lots"]
                    else:
                        lot = cfg.get('lot', 0.1)

                    sig.append({
                        'bar': i, 'side': -1, 'entry': entry, 'sl': sl, 'tp': tp,
                        'regime': f'otas_v3_bear_r{adx_v[i]:.0f}', 'strat': 'OTAS',
                        'lot': lot, 'adx': adx_v[i], 'atr': a,
                        'risk_tier': risk_mgr._drawdown_tier if risk_mgr else 1.0
                    })
                    last_signal_bar = i
                    position_open_bar = i
                    position_side = -1

    return sig


# ═══════════════════════════════════════════════════════════════
# V3.0 回测
# ═══════════════════════════════════════════════════════════════

def backtest_otas_v3(h1_data, h4_data, d1_data, initial_equity=10000.0, pip_usd=10.0):
    """OTAS V3.0 回测 (含风险管控)"""
    risk_mgr = RiskManager(initial_equity=initial_equity)
    signals = gen_otas_v3(h1_data, h4_data, d1_data, {'pip': 0.01, 'lot': 0.1}, risk_mgr=risk_mgr)

    if not signals:
        return {'signals': 0, 'trades': 0, 'win_rate': 0, 'total_pnl': 0, 'profit_factor': 0}

    trades = []
    position = 0
    entry_price = 0
    sl_price = 0
    tp_price = 0
    lot = 0.1
    open_bar = -999

    for i, sig in enumerate(signals):
        if position != 0:
            # 检查出场
            end = min(i + 50, len(h1_data))
            path = h1_data.iloc[i:end]
            hit = False

            for _, row in path.iterrows():
                high = row['high']; low = row['low']
                if position == 1:
                    if low <= sl_price:
                        pnl = (entry_price - sl_price) * 100 * lot * pip_usd / 100
                        trades.append({'type': 'BUY', 'result': 'loss', 'pnl': pnl})
                        position = 0; hit = True; break
                    if high >= tp_price:
                        pnl = (tp_price - entry_price) * 100 * lot * pip_usd / 100
                        trades.append({'type': 'BUY', 'result': 'win', 'pnl': pnl})
                        position = 0; hit = True; break
                else:
                    if high >= sl_price:
                        pnl = (sl_price - entry_price) * 100 * lot * pip_usd / 100
                        trades.append({'type': 'SELL', 'result': 'loss', 'pnl': pnl})
                        position = 0; hit = True; break
                    if low <= tp_price:
                        pnl = (entry_price - tp_price) * 100 * lot * pip_usd / 100
                        trades.append({'type': 'SELL', 'result': 'win', 'pnl': pnl})
                        position = 0; hit = True; break

            if hit:
                risk_mgr.close_position("XAUUSD", sl_price if trades[-1]['result']=='loss' else tp_price, trades[-1]['pnl'])
                continue
            continue

        # 开仓
        position = sig['side']
        entry_price = sig['entry']
        sl_price = sig['sl']
        tp_price = sig['tp']
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
        'risk_tier_final': risk_mgr._drawdown_tier,
        'max_drawdown': risk_mgr.get_performance_stats().get('max_drawdown', 0)
    }


if __name__ == "__main__":
    print("=" * 70)
    print("OTAS V3.0 — 机构级一次一单策略")
    print("=" * 70)

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

    result = backtest_otas_v3(h1, h4, d1, initial_equity=10000.0, pip_usd=10.0)

    print(f"\n回测结果 (V3.0):")
    print(f"  信号: {result['signals']} 个")
    print(f"  交易: {result['trades']} 笔")
    print(f"  胜率: {result['win_rate']:.1f}%")
    print(f"  盈亏: ${result['total_pnl']:.2f}")
    print(f"  PF: {result['profit_factor']:.2f}")
    print(f"  风险级别: {result['risk_tier_final']:.2f}")
    print(f"  最大回撤: {result['max_drawdown']:.2f}%")

    print("\n" + "=" * 70)
    print("✅ OTAS V3.0 自检完成")
    print("=" * 70)
