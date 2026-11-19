# -*- coding: utf-8 -*-
"""
backtest_apex_v5_bidir.py — Apex 双向版验证
一次生成(bidirectional=True) -> 拆出 纯空 / 纯多 / 双向合计, 对比 PF/净值。
核心问题: 朋友的纯空在牛市里亏; 改成「跌段做空+涨段做多」能否翻正?
"""
import json
import time
import datetime
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

from apex_strategy_v5 import DEFAULT_CFG
from backtest_apex_v5 import (
    get_rates, generate_apex_signals_rolling, simulate_trade,
    LOT, OZ_PER_LOT,
)

SYMBOL = "XAUUSD"


def aggregate(trades):
    n = len(trades)
    if n == 0:
        return {'n_trades': 0}
    wins = [t for t in trades if t['pnl_usd'] >= 0]
    losses = [t for t in trades if t['pnl_usd'] < 0]
    gw = sum(t['pnl_usd'] for t in wins)
    gl = sum(-t['pnl_usd'] for t in losses)
    pf = (gw / gl) if gl > 1e-9 else (float('inf') if gw > 0 else 0.0)
    net = gw - gl
    eq = 0.0; peak = 0.0; mdd = 0.0
    for t in trades:
        eq += t['pnl_usd']; peak = max(peak, eq); mdd = max(mdd, peak - eq)
    reasons = {}
    for t in trades:
        reasons[t['reason']] = reasons.get(t['reason'], 0) + 1
    return {
        'n_trades': n, 'wins': len(wins), 'losses': len(losses),
        'win_rate': round(len(wins)/n, 4),
        'profit_factor': round(pf, 3) if isinstance(pf, float) else pf,
        'net_pnl_usd': round(net, 2),
        'avg_win_usd': round(np.mean([t['pnl_usd'] for t in wins]), 2) if wins else 0,
        'avg_loss_usd': round(np.mean([t['pnl_usd'] for t in losses]), 2) if losses else 0,
        'avg_hold_bars': round(float(np.mean([t['hold_bars'] for t in trades])), 1),
        'expectancy_usd': round(net/n, 2),
        'max_drawdown_usd': round(mdd, 2),
        'exit_reasons': reasons,
    }


def main():
    t0 = time.time()
    mt5.initialize(timeout=30000)
    cfg = dict(DEFAULT_CFG)
    cfg['bidirectional'] = True
    h1 = get_rates(SYMBOL, mt5.TIMEFRAME_H1)
    h4 = get_rates(SYMBOL, mt5.TIMEFRAME_H4)
    info = mt5.symbol_info(SYMBOL)
    point = info.point if info else 0.01
    spread_pts = info.spread if (info and info.spread > 0) else 25
    spread_adj = spread_pts * point
    swap_short = abs(info.swap_short) * point * LOT * OZ_PER_LOT if info else 0.0
    swap_long = abs(info.swap_long) * point * LOT * OZ_PER_LOT if info else 0.0
    from apex_strategy_v5 import _atr
    atr_series = _atr(h1['high'].values.astype(float), h1['low'].values.astype(float),
                      h1['close'].values.astype(float), 14)
    fmt = lambda t: datetime.datetime.utcfromtimestamp(t).strftime('%Y-%m-%d')
    print(f"[BIDIR] {SYMBOL} H1={len(h1)} window {fmt(h1['time'].iloc[0])}..{fmt(h1['time'].iloc[-1])}")

    sigs = generate_apex_signals_rolling(h1, h4, cfg)
    print(f"[BIDIR] 双向信号数={len(sigs)}")
    short_s = [s for s in sigs if s['side'] < 0]
    long_s = [s for s in sigs if s['side'] > 0]
    print(f"[BIDIR] 其中 空={len(short_s)} 多={len(long_s)}")

    # 模拟(激进追踪以锁定利润)
    import backtest_apex_v5 as B
    B.ATR_MULT = 1.5; B.TRAIL_ACTIVATE = 1.0; B.MAX_HOLD_H1 = 480
    both = [simulate_trade(h1, s, spread_adj, atr_series, LOT, swap_short, swap_long) for s in sigs]
    both = [t for t in both if t]
    sh = [simulate_trade(h1, s, spread_adj, atr_series, LOT, swap_short, swap_long) for s in short_s]
    sh = [t for t in sh if t]
    lo = [simulate_trade(h1, s, spread_adj, atr_series, LOT, swap_short, swap_long) for s in long_s]
    lo = [t for t in lo if t]

    out = {
        'elapsed_s': round(time.time()-t0, 1),
        'bidirectional_both': aggregate(both),
        'short_only': aggregate(sh),
        'long_only': aggregate(lo),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    with open('apex_v5_bidir_result.json', 'w') as f:
        json.dump(out, f, indent=2, default=str)
    print("[BIDIR] saved -> apex_v5_bidir_result.json")
    mt5.shutdown()


if __name__ == "__main__":
    main()
