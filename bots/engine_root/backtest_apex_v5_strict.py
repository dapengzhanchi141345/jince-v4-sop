# -*- coding: utf-8 -*-
"""
backtest_apex_v5_strict.py — 修正退出逻辑后的 Apex 验证
退出模型改为「前高跟随下移 + breakeven 锁本」(还原朋友 EA 的 SL 4692->4654 阶梯下移),
替代之前错误的吊灯(win_high+1.5ATR 永远高于成本->82%到期)。
进场逻辑不变(仍用 generate_apex_signals_rolling 滚动防前视)。
跑: 纯空(bidirectional=False) + 双向(bidirectional=True), 对比 PF/胜率/退出原因。
"""
import json, time, datetime, numpy as np, pandas as pd, MetaTrader5 as mt5
from apex_strategy_v5 import DEFAULT_CFG
from backtest_apex_v5 import get_rates, generate_apex_signals_rolling, LOT, OZ_PER_LOT
from apex_strategy_v5 import _atr

SYMBOL = "XAUUSD"
TRAIL_LOOKBACK = 30      # H1 根, 约1.25天窗口找前高
SL_BUFFER = 2.0          # 跟随位 = 前高 + 2.0 (XAUUSD 价格单位, 即200点缓冲)
BE_ACT = 2.5             # 浮盈 >= 2.5*ATR 激活 breakeven
BE_BUF = 1.0             # breakeven 移到 成本 +/- 1.0 (100点)
MAX_HOLD_H1 = 480


def simulate_v2(h1, sig, spread_adj, atr_series, lot, swap_short, swap_long):
    side = int(sig.get('side', -1))
    sl = sig['sl']
    op = h1['open'].values.astype(float)
    hi = h1['high'].values.astype(float)
    lo = h1['low'].values.astype(float)
    cl = h1['close'].values.astype(float)
    tm = h1['time'].values.astype(float)
    i = sig['bar']; n = len(hi)
    if i + 1 >= n:
        return None
    if side < 0:
        entry = op[i + 1] - spread_adj; swap = swap_short
    else:
        entry = op[i + 1] + spread_adj; swap = swap_long
    start = i + 1; end = min(i + 1 + MAX_HOLD_H1, n)
    if end <= start:
        return None
    H = hi[start:end]; L = lo[start:end]; C = cl[start:end]
    ATR = atr_series[start:end]
    sl_cur = sl
    pk = None
    exit_px = None; exit_reason = None; last_k = 0
    for k in range(len(H)):
        ch = H[k]; cl_ = L[k]; cc = C[k]
        atr_k = ATR[k] if (k < len(ATR) and not np.isnan(ATR[k])) else (np.nanmean(ATR) if not np.isnan(np.nanmean(ATR)) else 1.0)
        # 极值(空头记最高/多头记最低)
        if pk is None:
            pk = ch if side < 0 else cl_
        else:
            if side < 0 and ch > pk: pk = ch
            if side > 0 and cl_ < pk: pk = cl_
        fav = (entry - cl_) if side < 0 else (ch - entry)
        # ── 前高跟随(只下移/上移) ──
        look = max(0, k - TRAIL_LOOKBACK + 1)
        win = H[look:k + 1] if side < 0 else L[look:k + 1]
        ext = float(np.max(win)) if side < 0 else float(np.min(win))
        if side < 0:
            trail = ext + SL_BUFFER
            if trail < sl_cur: sl_cur = trail
        else:
            trail = ext - SL_BUFFER
            if trail > sl_cur: sl_cur = trail
        # ── breakeven 锁本 ──
        if fav >= BE_ACT * atr_k:
            be = entry + (BE_BUF if side < 0 else -BE_BUF)
            if side < 0 and be < sl_cur: sl_cur = be
            if side > 0 and be > sl_cur: sl_cur = be
        # ── 退出检查 ──
        if side < 0 and ch >= sl_cur:
            exit_px = sl_cur
            exit_reason = 'BE' if sl_cur <= entry + BE_BUF + 0.05 else 'TRAIL'
            last_k = k; break
        if side > 0 and cl_ <= sl_cur:
            exit_px = sl_cur
            exit_reason = 'BE' if sl_cur >= entry - BE_BUF - 0.05 else 'TRAIL'
            last_k = k; break
        if k == len(H) - 1:
            exit_px = cc; exit_reason = 'EXPIRY'; last_k = k; break
    if exit_px is None:
        return None
    pnl_price = (entry - exit_px) if side < 0 else (exit_px - entry)
    pnl_usd = pnl_price * lot * OZ_PER_LOT
    days = (last_k + 1) / 24.0
    pnl_usd -= abs(swap) * days
    return {'pnl_usd': float(pnl_usd), 'hold_bars': int(last_k) + 1,
            'reason': exit_reason, 'entry': float(entry), 'exit': float(exit_px)}


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
        'win_rate': round(len(wins) / n, 4),
        'profit_factor': round(pf, 3) if isinstance(pf, float) else pf,
        'net_pnl_usd': round(net, 2),
        'avg_win_usd': round(np.mean([t['pnl_usd'] for t in wins]), 2) if wins else 0,
        'avg_loss_usd': round(np.mean([t['pnl_usd'] for t in losses]), 2) if losses else 0,
        'avg_hold_bars': round(float(np.mean([t['hold_bars'] for t in trades])), 1),
        'expectancy_usd': round(net / n, 2),
        'max_drawdown_usd': round(mdd, 2),
        'exit_reasons': reasons,
    }


def run(mode):
    t0 = time.time()
    mt5.initialize(timeout=30000)
    cfg = dict(DEFAULT_CFG)
    cfg['bidirectional'] = (mode == 'bidir')
    h1 = get_rates(SYMBOL, mt5.TIMEFRAME_H1)
    h4 = get_rates(SYMBOL, mt5.TIMEFRAME_H4)
    info = mt5.symbol_info(SYMBOL)
    point = info.point if info else 0.01
    spread_adj = (info.spread if (info and info.spread > 0) else 25) * point
    swap_short = abs(info.swap_short) * point * LOT * OZ_PER_LOT if info else 0.0
    swap_long = abs(info.swap_long) * point * LOT * OZ_PER_LOT if info else 0.0
    atr_series = _atr(h1['high'].values.astype(float), h1['low'].values.astype(float),
                      h1['close'].values.astype(float), 14)
    fmt = lambda t: datetime.datetime.utcfromtimestamp(t).strftime('%Y-%m-%d')
    print(f"[{mode}] {SYMBOL} H1={len(h1)} {fmt(h1['time'].iloc[0])}..{fmt(h1['time'].iloc[-1])}")
    sigs = generate_apex_signals_rolling(h1, h4, cfg)
    print(f"[{mode}] 信号数={len(sigs)} (空={sum(1 for s in sigs if s['side']<0)} 多={sum(1 for s in sigs if s['side']>0)})")
    trades = [simulate_v2(h1, s, spread_adj, atr_series, LOT, swap_short, swap_long) for s in sigs]
    trades = [t for t in trades if t]
    res = aggregate(trades)
    res['elapsed_s'] = round(time.time() - t0, 1)
    mt5.shutdown()
    return res


if __name__ == "__main__":
    out = {
        'short_only': run('short'),
        'bidirectional': run('bidir'),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    with open('apex_v5_strict_result.json', 'w') as f:
        json.dump(out, f, indent=2, default=str)
    print("saved -> apex_v5_strict_result.json")
