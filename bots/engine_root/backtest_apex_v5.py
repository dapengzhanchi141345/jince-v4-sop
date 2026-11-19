# -*- coding: utf-8 -*-
"""
backtest_apex_v5.py — Godking Apex Short (V5) 专用回测
=======================================================
为什么不用通用 backtest_engine.simulate_signal:
  通用引擎要求 tp>0，但 Apex 是 TP=0(无止损止盈、趋势退出) -> 直接跳过。
  这里自定义退出模拟:
    1. 硬止损 = 结构失效位 (invalidation)
    2. 吊灯追踪止损 (chandelier, short): 持仓后价格有利移动 >= trail_activate 后启动,
       止损位 = 近 N 根最高价 + atr_mult*ATR (随趋势下移)
    3. 到期平仓: 持仓超过 max_hold 根 H1 按市价平

防前视:
  - 结构(invalidation/zone)用「截至信号 bar 的 H4 历史」滚动计算, 不用未来数据。
  - 每根 H1 信号只用其之前的数据。
  - 入场取信号下一根 H1 开盘 - 点差(不给当根免费成交)。
"""

import json
import time
import datetime
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

from apex_strategy_v5 import (
    _derive_structure, _is_rejection_bar, _is_bullish_rejection_bar, _atr, DEFAULT_CFG,
)

SYMBOL = "XAUUSD"
LOT = 0.01                     # 与朋友一致: 每笔 0.01 手 (scale-in)
OZ_PER_LOT = 100.0            # XAUUSD 1 lot = 100 oz
MAX_HOLD_H1 = 480            # ~20 交易日
TRAIL_LOOKBACK = 20          # 吊灯回看 H1 根数
ATR_MULT = 2.5               # 吊灯 ATR 倍数
TRAIL_ACTIVATE = 1.5         # 有利移动 >= 1.5*ATR 启动追踪 (ATR 倍数)
MIN_BARS_H1 = 200


def get_rates(symbol, tf, target=20000):
    frames = []
    pos = 0
    while True:
        chunk = mt5.copy_rates_from_pos(symbol, tf, pos, 5000)
        if chunk is None or len(chunk) == 0:
            break
        frames.append(pd.DataFrame(chunk))
        if len(chunk) < 5000:
            break
        pos += len(chunk)
        if pos >= target:
            break
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=['time']).sort_values('time').reset_index(drop=True)
    return df


def build_struct_map(h4, cfg):
    """对每根 H4 bar k, 计算截至 k 的结构(无前视)。返回 structs[k]。"""
    structs = []
    n = len(h4)
    for k in range(n):
        w = h4.iloc[:k + 1]
        try:
            st = _derive_structure(w, cfg)
        except Exception:
            st = None
        structs.append(st)
    return structs


def h4_index_for_times(h4_times, h1_times):
    """返回每根 H1 对应的管辖 H4 bar 下标(最后一根 time <= h1_time)。"""
    h4t = np.asarray(h4_times, dtype=np.int64)
    h1t = np.asarray(h1_times, dtype=np.int64)
    idx = np.searchsorted(h4t, h1t, side='right') - 1
    idx = np.clip(idx, 0, len(h4t) - 1)
    return idx


def generate_apex_signals_rolling(h1, h4, cfg):
    """
    滚动生成 Apex 信号 (无前视, 全局 scale-in 状态)。
    返回 list of dict: {bar, sl, entry_ref, zone_top, zone_bottom, major_high}
    """
    hi = h1['high'].values.astype(float)
    lo = h1['low'].values.astype(float)
    op = h1['open'].values.astype(float)
    cl = h1['close'].values.astype(float)
    n = len(hi)
    if n < MIN_BARS_H1:
        return []

    structs = build_struct_map(h4, cfg)
    h4_idx = h4_index_for_times(h4['time'].values, h1['time'].values)

    bidir = bool(cfg.get("bidirectional", False))
    max_scale = int(cfg.get("max_scale_in", 5))
    gap = int(cfg.get("scale_in_gap_bars", 3))
    scale_state = {}   # (side, zone_key) -> {'count','last'}

    signals = []
    for i in range(2, n - 1):   # 留一根给下一根开盘入场
        k = int(h4_idx[i])
        st = structs[k]
        if st is None:
            continue
        # ── 空头分支 (Apex Short) ──
        if st.get("bearish_ctx"):
            inv = st["invalidation"]
            if cl[i] < inv:
                zt = st["zone_top"]; zb = st["zone_bottom"]
                in_zone = (hi[i] >= zb) and (hi[i] <= zt + 40) and (cl[i] <= zt)
                if in_zone:
                    row = {'open': op[i], 'high': hi[i], 'low': lo[i], 'close': cl[i]}
                    if _is_rejection_bar(row, cfg):
                        zkey = (-1, round(zt / 10.0))
                        zs = scale_state.setdefault(zkey, {'count': 0, 'last': -999})
                        if zs['count'] < max_scale and (i - zs['last']) >= gap:
                            signals.append({'bar': int(i), 'side': -1, 'sl': float(inv),
                                            'entry_ref': float(min(hi[i], zt)),
                                            'zone_top': float(zt), 'zone_bottom': float(zb),
                                            'major_high': float(st['major_high'])})
                            zs['count'] += 1; zs['last'] = i
        # ── 多头分支 (仅双向: Apex Long, 镜像) ──
        if bidir and st.get("bullish_ctx"):
            inv = st["invalidation_low"]
            if cl[i] > inv:
                zt = st["demand_top"]; zb = st["demand_bottom"]
                in_zone = (lo[i] <= zt) and (lo[i] >= zb - 40) and (cl[i] >= zb)
                if in_zone:
                    row = {'open': op[i], 'high': hi[i], 'low': lo[i], 'close': cl[i]}
                    if _is_bullish_rejection_bar(row, cfg):
                        zkey = (1, round(zt / 10.0))
                        zs = scale_state.setdefault(zkey, {'count': 0, 'last': -999})
                        if zs['count'] < max_scale and (i - zs['last']) >= gap:
                            signals.append({'bar': int(i), 'side': 1, 'sl': float(inv),
                                            'entry_ref': float(max(lo[i], zb)),
                                            'zone_top': float(zt), 'zone_bottom': float(zb),
                                            'major_high': float(st['major_high']),
                                            'major_low': float(st['major_low'])})
                            zs['count'] += 1; zs['last'] = i
    return signals


def simulate_trade(h1, sig, spread_adj, atr_series, lot, swap_short_usd_per_day, swap_long_usd_per_day=0.0):
    i = sig['bar']
    n = len(h1)
    if i + 1 >= n:
        return None
    op = h1['open'].values.astype(float)
    hi = h1['high'].values.astype(float)
    lo = h1['low'].values.astype(float)
    cl = h1['close'].values.astype(float)
    tm = h1['time'].values.astype(float)

    side = int(sig.get('side', -1))
    sl = sig['sl']
    if side < 0:                          # 空头
        entry = op[i + 1] - spread_adj
        peak = hi[i]; fav = lambda pk, e: pk - e
        pnl_price = lambda e, x: e - x
        swap_usd = swap_short_usd_per_day
    else:                                 # 多头
        entry = op[i + 1] + spread_adj
        peak = lo[i]; fav = lambda pk, e: e - pk
        pnl_price = lambda e, x: x - e
        swap_usd = swap_long_usd_per_day

    start = i + 1
    end = min(i + 1 + MAX_HOLD_H1, n)
    if end <= start:
        return None
    H = hi[start:end]; L = lo[start:end]; C = cl[start:end]; T = tm[start:end]
    ATR = atr_series[start:end]
    trail_active = False
    exit_px = None
    exit_reason = None
    for k in range(len(H)):
        cur_high = H[k]; cur_low = L[k]; cur_close = C[k]
        # 1) 硬止损(失效位)
        if side < 0 and cur_high >= sl:
            exit_px = sl; exit_reason = 'SL'; break
        if side > 0 and cur_low <= sl:
            exit_px = sl; exit_reason = 'SL'; break
        # 更新极值(追踪与有利度量)
        if side < 0 and cur_high > peak:
            peak = cur_high
        if side > 0 and cur_low < peak:
            peak = cur_low
        atr_k = ATR[k] if (k < len(ATR) and not np.isnan(ATR[k])) else np.nanmean(ATR)
        if np.isnan(atr_k):
            atr_k = 1.0
        fav_move = fav(peak, entry)
        # 2) 吊灯追踪
        look = max(0, k - TRAIL_LOOKBACK + 1)
        if side < 0:
            win_ext = float(np.max(H[look:k + 1])) if k > 0 else float(H[0])
            trail_stop = win_ext + ATR_MULT * atr_k
            if fav_move >= TRAIL_ACTIVATE * atr_k:
                trail_active = True
            if trail_active and cur_high >= trail_stop:
                exit_px = trail_stop; exit_reason = 'TRAIL'; break
        else:
            win_ext = float(np.min(L[look:k + 1])) if k > 0 else float(L[0])
            trail_stop = win_ext - ATR_MULT * atr_k
            if fav_move >= TRAIL_ACTIVATE * atr_k:
                trail_active = True
            if trail_active and cur_low <= trail_stop:
                exit_px = trail_stop; exit_reason = 'TRAIL'; break
        # 3) 到期
        if k == len(H) - 1:
            exit_px = cur_close; exit_reason = 'EXPIRY'; break
    if exit_px is None:
        return None
    pnl_usd = pnl_price(entry, exit_px) * lot * OZ_PER_LOT
    hold_days = max(0, int((T[min(k, len(T) - 1)] - T[0]) // 86400)) if k > 0 else 0
    if hold_days > 0 and swap_usd:
        pnl_usd -= abs(swap_usd) * hold_days
    return {
        'pnl_usd': float(pnl_usd),
        'hold_bars': int(k) + 1,
        'reason': exit_reason,
        'entry': float(entry),
        'exit': float(exit_px),
    }


def run_backtest():
    t0 = time.time()
    if not mt5.initialize(timeout=30000):
        raise RuntimeError("MT5 init 失败")
    cfg = dict(DEFAULT_CFG)
    h1 = get_rates(SYMBOL, mt5.TIMEFRAME_H1)
    h4 = get_rates(SYMBOL, mt5.TIMEFRAME_H4)
    d1 = get_rates(SYMBOL, mt5.TIMEFRAME_D1)
    if h1 is None or len(h1) < MIN_BARS_H1 or h4 is None:
        raise RuntimeError("XAUUSD 数据不足")
    info = mt5.symbol_info(SYMBOL)
    point = info.point if info else 0.01
    spread_pts = info.spread if (info and info.spread > 0) else 25
    spread_adj = spread_pts * point
    # swap: 转 USD/天 (近似)
    swap_short_pts = info.swap_short if info else 0
    swap_short_usd_per_day = abs(swap_short_pts) * point * LOT * OZ_PER_LOT if info else 0.0

    # ATR 序列(H1)
    atr_series = _atr(h1['high'].values.astype(float), h1['low'].values.astype(float),
                      h1['close'].values.astype(float), 14)

    win_start = h1['time'].iloc[0]
    win_end = h1['time'].iloc[-1]
    fmt = lambda t: datetime.datetime.utcfromtimestamp(t).strftime('%Y-%m-%d')

    print(f"[APEX BT] {SYMBOL} H1={len(h1)} window {fmt(win_start)}..{fmt(win_end)} "
          f"spread~{spread_pts}pts({spread_adj:.3f}) swap_short~{swap_short_usd_per_day:.3f}$/day")

    signals = generate_apex_signals_rolling(h1, h4, cfg)
    print(f"[APEX BT] 滚动生成信号数: {len(signals)}")

    trades = []
    for s in signals:
        r = simulate_trade(h1, s, spread_adj, atr_series, LOT, swap_short_usd_per_day)
        if r is not None:
            trades.append(r)

    # 聚合
    n = len(trades)
    wins = [t for t in trades if t['pnl_usd'] >= 0]
    losses = [t for t in trades if t['pnl_usd'] < 0]
    gw = sum(t['pnl_usd'] for t in wins)
    gl = sum(-t['pnl_usd'] for t in losses)
    pf = (gw / gl) if gl > 1e-9 else (float('inf') if gw > 0 else 0.0)
    net = gw - gl
    # 权益曲线 & 最大回撤
    eq = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        eq += t['pnl_usd']
        if eq > peak:
            peak = eq
        dd = peak - eq
        if dd > max_dd:
            max_dd = dd
    reasons = {}
    for t in trades:
        reasons[t['reason']] = reasons.get(t['reason'], 0) + 1
    avg_hold = np.mean([t['hold_bars'] for t in trades]) if trades else 0
    avg_win = np.mean([t['pnl_usd'] for t in wins]) if wins else 0
    avg_loss = np.mean([t['pnl_usd'] for t in losses]) if losses else 0

    summary = {
        'symbol': SYMBOL,
        'window': [fmt(win_start), fmt(win_end)],
        'h1_bars': len(h1),
        'cfg': {k: cfg[k] for k in ['zone_height_pts', 'invalidation_buffer', 'max_scale_in',
                                     'scale_in_gap_bars', 'reject_wick_ratio']},
        'exit_model': {'SL': 'invalidation', 'TRAIL': f'chandelier L={TRAIL_LOOKBACK} mult={ATR_MULT}',
                       'EXPIRY': f'{MAX_HOLD_H1}H1', 'lot': LOT},
        'n_signals': len(signals),
        'n_trades': n,
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': round(len(wins) / n, 4) if n else 0,
        'gross_win': round(gw, 2),
        'gross_loss': round(gl, 2),
        'profit_factor': round(pf, 3) if isinstance(pf, float) else pf,
        'net_pnl_usd': round(net, 2),
        'avg_win_usd': round(avg_win, 2),
        'avg_loss_usd': round(avg_loss, 2),
        'avg_hold_bars': round(float(avg_hold), 1),
        'expectancy_usd': round(net / n, 2) if n else 0,
        'max_drawdown_usd': round(max_dd, 2),
        'exit_reasons': reasons,
        'elapsed_s': round(time.time() - t0, 1),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    # 保存
    with open('apex_v5_backtest_result.json', 'w') as f:
        json.dump({'summary': summary, 'trades': trades}, f, indent=2, default=str)
    print("[APEX BT] saved -> apex_v5_backtest_result.json")
    mt5.shutdown()
    return summary


if __name__ == "__main__":
    run_backtest()
