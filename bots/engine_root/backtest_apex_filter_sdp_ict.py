# -*- coding: utf-8 -*-
"""
backtest_apex_filter_sdp_ict.py — Apex 结构门控是否提升现有 SDP/ICT?
=====================================================================
问题: Apex 本身验证为负, 但其「结构区+拒绝线」能否作为质量过滤器,
      提升我们已有的双向策略 (SDP / ICT) 的信号质量?

方法:
  - 用 STRATEGY_REGISTRY_V4 生成 SDP/ICT 在 XAUUSD 的信号(它们自带 TP>0)。
  - Apex 门控: 仅保留「方向与 Apex 结构上下文一致」的信号:
      * 空单 -> bearish_ctx 且价格回抽进入供给区
      * 多单 -> bullish_ctx 且价格回踩进入需求区
  - Walk-Forward: 前 70% 为 IS, 后 30% 为 OOS, 分别算 PF/胜率。
  - 对比 基线(不过滤) vs 门控(过滤) 在 IS/OOS 的 PF。
  - 退出用通用 simulate_signal(真实成本, 固定 TP/SL)。
"""
import json
import time
import datetime
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

from apex_strategy_v5 import DEFAULT_CFG
from backtest_apex_v5 import get_rates, build_struct_map, h4_index_for_times
from backtest_engine import simulate_signal
from advanced_strategies_v4 import STRATEGY_REGISTRY_V4

SYMBOL = "XAUUSD"
STRATS = ["SDP", "ICT", "PASD"]


def apply_apex_gate(h1, signals, structs, h4_idx, cfg):
    """仅保留方向与 Apex 结构上下文一致的信号。"""
    hi = h1['high'].values.astype(float)
    lo = h1['low'].values.astype(float)
    cl = h1['close'].values.astype(float)
    kept = []
    for s in signals:
        i = s['bar']
        if i < 2 or i >= len(hi) - 1:
            continue
        k = int(h4_idx[i])
        st = structs[k]
        if st is None:
            continue
        side = int(s.get('side', -1))
        if side < 0:
            if not st.get('bearish_ctx'):
                continue
            zt = st['zone_top']; zb = st['zone_bottom']; inv = st['invalidation']
            if cl[i] >= inv:
                continue
            if not (hi[i] >= zb and hi[i] <= zt + 40 and cl[i] <= zt):
                continue
        else:
            if not st.get('bullish_ctx'):
                continue
            zt = st['demand_top']; zb = st['demand_bottom']; inv = st['invalidation_low']
            if cl[i] <= inv:
                continue
            if not (lo[i] <= zt and lo[i] >= zb - 40 and cl[i] >= zb):
                continue
        kept.append(s)
    return kept


def sim_set(h1, sigs, spread_pts, point, swap_long, swap_short, lot, pip, pip_usd):
    out = []
    for s in sigs:
        p = simulate_signal(h1, s, spread_pts, point, swap_long, swap_short, lot, pip, pip_usd)
        if p is not None:
            out.append((s, p))
    return out


def aggregate_tagged(tagged, h1, split_time):
    """tagged: list of (sig, pnl). 按 IS/OOS 切分聚合 PF。"""
    def agg(items):
        n = len(items)
        if n == 0:
            return {'n': 0, 'wins': 0, 'wr': 0, 'pf': 0, 'net': 0}
        wins = [p for _, p in items if p >= 0]
        losses = [p for _, p in items if p < 0]
        gw = sum(wins); gl = sum(-p for p in losses)
        pf = (gw / gl) if gl > 1e-9 else (float('inf') if gw > 0 else 0.0)
        return {'n': n, 'wins': len(wins), 'wr': round(len(wins)/n, 4),
                'pf': round(pf, 3) if isinstance(pf, float) else pf,
                'net': round(gw - gl, 2)}
    is_items = [x for x in tagged if h1['time'].values[int(x[0]['bar'])] <= split_time]
    oos_items = [x for x in tagged if h1['time'].values[int(x[0]['bar'])] > split_time]
    return {'IS': agg(is_items), 'OOS': agg(oos_items), 'ALL': agg(tagged)}


def main():
    t0 = time.time()
    mt5.initialize(timeout=30000)
    cfg = dict(DEFAULT_CFG)
    h1 = get_rates(SYMBOL, mt5.TIMEFRAME_H1)
    h4 = get_rates(SYMBOL, mt5.TIMEFRAME_H4)
    d1 = get_rates(SYMBOL, mt5.TIMEFRAME_D1)
    info = mt5.symbol_info(SYMBOL)
    spread_pts = info.spread if (info and info.spread > 0) else 25
    point = info.point if info else 0.01
    swap_long = info.swap_long if info else 0
    swap_short = info.swap_short if info else 0
    lot = 1.0; pip = 0.01; pip_usd = 10.0
    fmt = lambda t: datetime.datetime.utcfromtimestamp(t).strftime('%Y-%m-%d')
    print(f"[FILTER] {SYMBOL} H1={len(h1)} {fmt(h1['time'].iloc[0])}..{fmt(h1['time'].iloc[-1])}")

    structs = build_struct_map(h4, cfg)
    h4_idx = h4_index_for_times(h4['time'].values, h1['time'].values)
    split_idx = int(len(h1) * 0.7)
    split_time = h1['time'].values[split_idx]

    result = {'symbol': SYMBOL, 'split_date': fmt(split_time), 'strategies': {}}
    for name in STRATS:
        gen = STRATEGY_REGISTRY_V4.get(name)
        if gen is None:
            print(f"[FILTER] {name} not in registry, skip"); continue
        try:
            raw = gen(h1, h4, d1, cfg)
        except Exception as e:
            print(f"[FILTER] {name} gen err: {e}"); raw = []
        if not raw:
            print(f"[FILTER] {name}: 0 raw signals"); continue
        gated = apply_apex_gate(h1, raw, structs, h4_idx, cfg)
        raw_sim = sim_set(h1, raw, spread_pts, point, swap_long, swap_short, lot, pip, pip_usd)
        gated_sim = sim_set(h1, gated, spread_pts, point, swap_long, swap_short, lot, pip, pip_usd)
        result['strategies'][name] = {
            'raw_n': len(raw), 'gated_n': len(gated),
            'raw': aggregate_tagged(raw_sim, h1, split_time),
            'gated': aggregate_tagged(gated_sim, h1, split_time),
        }
        print(f"[FILTER] {name}: raw={len(raw)} -> gated={len(gated)}")

    result['elapsed_s'] = round(time.time() - t0, 1)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    with open('apex_filter_sdp_ict_result.json', 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print("[FILTER] saved -> apex_filter_sdp_ict_result.json")
    mt5.shutdown()


if __name__ == "__main__":
    main()
