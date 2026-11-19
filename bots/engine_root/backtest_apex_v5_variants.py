# -*- coding: utf-8 -*-
"""
backtest_apex_v5_variants.py — Apex V5 多情景回测(同一次 MT5 会话复用结构与信号)
目的: 区分「策略本身不行」还是「只在特定 regime/参数下不行」。
"""
import json
import time
import datetime
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

from apex_strategy_v5 import _derive_structure, _is_rejection_bar, _atr, DEFAULT_CFG
from backtest_apex_v5 import (
    get_rates, build_struct_map, h4_index_for_times,
    generate_apex_signals_rolling, simulate_trade,
    LOT, OZ_PER_LOT, MAX_HOLD_H1 as BASE_MAXHOLD, TRAIL_LOOKBACK as BASE_TL,
)

SYMBOL = "XAUUSD"


def aggregate(trades):
    n = len(trades)
    wins = [t for t in trades if t['pnl_usd'] >= 0]
    losses = [t for t in trades if t['pnl_usd'] < 0]
    gw = sum(t['pnl_usd'] for t in wins)
    gl = sum(-t['pnl_usd'] for t in losses)
    pf = (gw / gl) if gl > 1e-9 else (float('inf') if gw > 0 else 0.0)
    net = gw - gl
    eq = 0.0; peak = 0.0; mdd = 0.0
    for t in trades:
        eq += t['pnl_usd']
        peak = max(peak, eq); mdd = max(mdd, peak - eq)
    reasons = {}
    for t in trades:
        reasons[t['reason']] = reasons.get(t['reason'], 0) + 1
    return {
        'n_trades': n, 'wins': len(wins), 'losses': len(losses),
        'win_rate': round(len(wins)/n, 4) if n else 0,
        'profit_factor': round(pf, 3) if isinstance(pf, float) else pf,
        'net_pnl_usd': round(net, 2),
        'avg_win_usd': round(np.mean([t['pnl_usd'] for t in wins]), 2) if wins else 0,
        'avg_loss_usd': round(np.mean([t['pnl_usd'] for t in losses]), 2) if losses else 0,
        'avg_hold_bars': round(float(np.mean([t['hold_bars'] for t in trades])), 1) if trades else 0,
        'expectancy_usd': round(net/n, 2) if n else 0,
        'max_drawdown_usd': round(mdd, 2),
        'exit_reasons': reasons,
    }


def simulate_all(h1, signals, spread_adj, atr_series, swap_usd,
                 trail_mult, trail_activate, max_hold):
    # 动态覆盖退出参数 (monkey-patch 模块级常量)
    import backtest_apex_v5 as B
    old_mult, old_act, old_hold = B.ATR_MULT, B.TRAIL_ACTIVATE, B.MAX_HOLD_H1
    B.ATR_MULT = trail_mult; B.TRAIL_ACTIVATE = trail_activate; B.MAX_HOLD_H1 = max_hold
    out = []
    for s in signals:
        r = simulate_trade(h1, s, spread_adj, atr_series, LOT, swap_usd)
        if r:
            out.append(r)
    B.ATR_MULT, B.TRAIL_ACTIVATE, B.MAX_HOLD_H1 = old_mult, old_act, old_hold
    return out


def main():
    t0 = time.time()
    mt5.initialize(timeout=30000)
    cfg = dict(DEFAULT_CFG)
    h1 = get_rates(SYMBOL, mt5.TIMEFRAME_H1)
    h4 = get_rates(SYMBOL, mt5.TIMEFRAME_H4)
    info = mt5.symbol_info(SYMBOL)
    point = info.point if info else 0.01
    spread_pts = info.spread if (info and info.spread > 0) else 25
    spread_adj = spread_pts * point
    swap_usd = abs(info.swap_short) * point * LOT * OZ_PER_LOT if info else 0.0
    atr_series = _atr(h1['high'].values.astype(float), h1['low'].values.astype(float),
                      h1['close'].values.astype(float), 14)
    # 结构与基准信号(默认 cfg) — 最贵的一步, 只算一次
    print("[VAR] building struct map + base signals ...")
    base_signals = generate_apex_signals_rolling(h1, h4, cfg)
    print(f"[VAR] base signals={len(base_signals)}")

    h1t = h1['time'].values.astype(float)
    def since(sig_years):
        thr = [datetime.datetime(y, 1, 1) for y in sig_years]
        # 用 unix 阈值
        import calendar
        out = []
        for s in base_signals:
            t = h1t[s['bar']]
            dt = datetime.datetime.utcfromtimestamp(t)
            if dt.year >= sig_years[0]:
                out.append(s)
        return out

    scenarios = {}

    # S1: 近期窗口 2023+ (复用基准信号, 只过滤时间)
    sig23 = since([2023])
    tr = simulate_all(h1, sig23, spread_adj, atr_series, swap_usd, 2.5, 1.5, MAX_HOLD_H1_BASE:=BASE_MAXHOLD)
    scenarios['S1_recent_2023plus_defaultExit'] = {'n_signals': len(sig23), **aggregate(tr)}

    # S2: 全窗口 + 激进追踪 (更快锁定利润)
    tr2 = simulate_all(h1, base_signals, spread_adj, atr_series, swap_usd, 1.5, 1.0, BASE_MAXHOLD)
    scenarios['S2_full_aggressiveTrail'] = {'n_signals': len(base_signals), **aggregate(tr2)}

    # S3: 近期 2023+ + 激进追踪
    tr3 = simulate_all(h1, sig23, spread_adj, atr_series, swap_usd, 1.5, 1.0, BASE_MAXHOLD)
    scenarios['S3_recent_aggressiveTrail'] = {'n_signals': len(sig23), **aggregate(tr3)}

    # S4: 全窗口 + 激进追踪 + 短持仓(120H1 到期, 砍掉长期漂单)
    tr4 = simulate_all(h1, base_signals, spread_adj, atr_series, swap_usd, 1.5, 1.0, 120)
    scenarios['S4_full_aggrTrail_shortHold120'] = {'n_signals': len(base_signals), **aggregate(tr4)}

    # S5: 收紧进场区 zone_height=60 (重新生成信号, 较贵)
    cfg5 = dict(DEFAULT_CFG); cfg5['zone_height_pts'] = 60
    sig5 = generate_apex_signals_rolling(h1, h4, cfg5)
    tr5 = simulate_all(h1, sig5, spread_adj, atr_series, swap_usd, 1.5, 1.0, BASE_MAXHOLD)
    scenarios['S5_tightZone_aggrTrail'] = {'n_signals': len(sig5), **aggregate(tr5)}

    result = {'elapsed_s': round(time.time()-t0, 1), 'scenarios': scenarios}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    with open('apex_v5_variants_result.json', 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print("[VAR] saved -> apex_v5_variants_result.json")
    mt5.shutdown()


if __name__ == "__main__":
    main()
