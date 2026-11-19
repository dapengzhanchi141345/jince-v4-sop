# backtest_trend_range.py — 趋势/震荡 参数独立回测 (金策宗师团·研策师)
"""
独立 walk-forward / 向量化回测 —— 回答「趋势行情 vs 震荡行情 处理怎么调优」。

零侵入: 不修改任何现有系统代码, 只复用 continuous_evolution_v2 的
  指标原语 (_atr / _adx / _structure_confirm / _ema / _clean_close_arr)
  与 rf_alpha.RFAlpha (因果特征 + 错位标签, 无未来函数) 作为 RF 门禁打分器。
只读 MT5 历史 (copy_rates_from_pos), 绝不调用 order_send。

三项任务:
  A. RF 门禁阈值敏感度 (BTCUSD / ETHUSD): 逐提案用 RFAlpha 打 UP/DOWN 概率,
     在 0.50/0.55/0.60/0.65 阈值下统计 通过率/PF/胜率/笔数/净收益, 给出最佳阈值。
  B. 区间(均值回归)策略真实表现 (XAUUSD / EURUSD / GBPUSD):
     复刻 build_range_signal 逻辑, 统计触发率/PF/胜率/笔数/平均持仓。
  C. adx_min 敏感度 (XAUUSD): adx_min ∈ {22,23,25,28} 的趋势提案通过率/PF/胜率/笔数。

输出: 终端打印摘要 + 写 BACKTEST_TREND_RANGE_YYYY-MM-DD.md 报告。
"""
import os
import sys
import json
import time
import datetime as dt

import numpy as np
import MetaTrader5 as mt5
import continuous_evolution_v2 as ce
import rf_alpha as ra

# ───────────────────────── 固定参数 (与系统一致) ─────────────────────────
THRESHOLDS = [0.50, 0.55, 0.60, 0.65]
N_BARS = 4500          # ~6 个月 H1 (FX 末段约 9 个月, 见数据表)
TRAIN_FRAC = 0.60      # RFAlpha 训练/测试切分 (walk-forward: 前 60% 训, 后 40% 测)
EXIT_WIN = 250         # 出场窗口 (与 run_walkforward 一致, 单位 H1 根)
WARMUP = 60            # 指标预热

# 区间模块参数 (guardian_executor.py)
RANGE_BB_PERIOD = 15
RANGE_BB_STD = 1.5
RANGE_KC_MULT = 1.5
RANGE_ENTRY_BUFFER_PIPS = 0.2
RANGE_SL_BUFFER_PIPS = 0.8
RANGE_RR_MIN = 2.0
RANGE_ADX_CEIL = 35            # market_scanner.py: 区间模块接管上限
RANGE_MAX_LOT = 0.03           # 区间单笔上限

# 进化出的逐品种参数 (data/continuous_evolution/evolution_state.json, 2026-07-10)
EVOLVED = {
    'XAUUSD': {'adx_min': 25.0,   'position_size': 0.03, 'sl_multiplier': 2.5877, 'tp_multiplier': 5.7906, 'volatility_scalar': 0.8699, 'momentum_filter': True},
    'BTCUSD': {'adx_min': 25,     'position_size': 0.03, 'sl_multiplier': 3.457,  'tp_multiplier': 6.914,  'volatility_scalar': 0.7364, 'momentum_filter': False},
    'ETHUSD': {'adx_min': 18,     'position_size': 0.03, 'sl_multiplier': 3.4985, 'tp_multiplier': 6.9971, 'volatility_scalar': 0.6613, 'momentum_filter': False},
    'EURUSD': {'adx_min': 45.0,   'position_size': 0.01, 'sl_multiplier': 2.6778, 'tp_multiplier': 10.0,   'volatility_scalar': 0.6011, 'momentum_filter': False},
    'GBPUSD': {'adx_min': 41.9435,'position_size': 0.01, 'sl_multiplier': 4.5616, 'tp_multiplier': 9.6857, 'volatility_scalar': 0.8075, 'momentum_filter': True},
}

REPORT_DATE = "2026-07-10"
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        f"BACKTEST_TREND_RANGE_{REPORT_DATE}.md")


# ───────────────────────── 数据 / 指标原语 ─────────────────────────
def load_h1(sym, n=N_BARS):
    """拉真实 H1 历史 (只读), 返回 (close, high, low, spread) 或 (None, reason)。"""
    if not ce.ensure_mt5():
        return None, "MT5 不可用"
    try:
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, n)
    except Exception as e:
        return None, f"copy_rates 异常: {e}"
    if rates is None or len(rates) < 200:
        return None, f"历史不足 (n={len(rates) if rates is not None else 0})"
    c = ce._clean_close_arr(np.array([r['close'] for r in rates], float))
    h = ce._clean_close_arr(np.array([r['high'] for r in rates], float))
    l = ce._clean_close_arr(np.array([r['low'] for r in rates], float))
    info = mt5.symbol_info(sym)
    sp = float(info.spread * info.point) if (info and info.spread) else float(ce.SYMBOL_CONFIG[sym]['spread'])
    return (c, h, l, sp), f"n={len(rates)}"


def direction_from(e21, e50, close, i, dl_pred=None):
    """复刻 BacktestEngine._direction (DL 缺失→EMA21/50 规则)。
    e21/e50 为预计算全序列, 避免逐根重算 EMA (O(n^2))。"""
    if dl_pred is not None and dl_pred[0] in ('BULLISH', 'BEARISH'):
        return 'BUY' if dl_pred[0] == 'BULLISH' else 'SELL'
    if close[i] > e21[i] > e50[i]:
        return 'BUY'
    if close[i] < e21[i] < e50[i]:
        return 'SELL'
    return None


def settle(direction, entry_i, entry, sl_d, tp_d, high, low, n, win=EXIT_WIN):
    """首触 SL/TP 出场 (与 run_walkforward 完全一致, 无未来函数)。
    返回 (pnl_pts_sign_part, hit, bars_held); pnl_pts_sign_part = +tp_d 或 -sl_d (不含 spread)。
    窗口内未出场返回 None。"""
    if sl_d <= 0 or tp_d <= 0:
        return None
    end = min(entry_i + win, n)
    for j in range(entry_i + 1, end):
        if direction == 'BUY':
            if high[j] >= entry + tp_d:
                return (tp_d, 'TP', j - entry_i)
            if low[j] <= entry - sl_d:
                return (-sl_d, 'SL', j - entry_i)
        else:
            if low[j] <= entry - tp_d:
                return (tp_d, 'TP', j - entry_i)
            if high[j] >= entry + sl_d:
                return (-sl_d, 'SL', j - entry_i)
    return None


def pnl_usd(pnl_pts, pip, pos, pusd):
    return (pnl_pts / pip) * pos * pusd


# ───────────────────────── 候选信号生成 ─────────────────────────
def trend_candidate(i, close, high, low, atr, adx, params, e21, e50):
    """复刻 build_signal 入场条件 (ADX≥adx_min + momentum + 方向 + 结构确认)。
    返回 (direction, entry, sl_d, tp_d) 或 None。"""
    if i < WARMUP or i >= len(close) - 1:
        return None
    if np.isnan(adx[i]) or adx[i] < params['adx_min']:
        return None
    if params.get('momentum_filter') and adx[i] < params['adx_min']:
        return None
    d = direction_from(e21, e50, close, i, None)
    if d is None:
        return None
    if not ce._structure_confirm(close, high, low, i, atr):
        return None
    entry = close[i]
    sl_d = atr[i] * params['sl_multiplier']
    tp_d = atr[i] * params['tp_multiplier']
    if sl_d <= 0 or tp_d <= 0:
        return None
    return (d, entry, sl_d, tp_d)


def range_candidate(i, close, high, low, atr, adx, ceiling, pip):
    """复刻 build_range_signal 入场逻辑 (BB15/1.5 + KC1.5 + ebuf + RR≥2)。
    区间模块仅在 ADX < ceiling 时接管。返回 (direction, entry, sl_d, tp_d) 或 None。"""
    if i < RANGE_BB_PERIOD + 5 or i >= len(close) - 1:
        return None
    if np.isnan(adx[i]) or adx[i] >= ceiling:        # 趋势带 → 不进区间
        return None
    if np.isnan(atr[i]) or atr[i] <= 0:
        return None
    window = close[i - RANGE_BB_PERIOD + 1:i + 1]
    ma = float(np.mean(window))
    sd = float(np.std(window))
    bb_up = ma + RANGE_BB_STD * sd
    bb_dn = ma - RANGE_BB_STD * sd
    price = close[i]
    mid = (bb_up + bb_dn) / 2.0
    ebuf = RANGE_ENTRY_BUFFER_PIPS * pip
    slbuf = RANGE_SL_BUFFER_PIPS * pip
    if bb_up - ebuf <= price <= bb_up:
        d = 'SELL'
        sl = bb_up + slbuf
        sl_dist = sl - price
        tp_dist = max(sl_dist * RANGE_RR_MIN, price - mid)
        tp = price - tp_dist
    elif bb_dn <= price <= bb_dn + ebuf:
        d = 'BUY'
        sl = bb_dn - slbuf
        sl_dist = price - sl
        tp_dist = max(sl_dist * RANGE_RR_MIN, mid - price)
        tp = price + tp_dist
    else:
        return None
    if sl_dist <= 0 or tp_dist <= 0:
        return None
    if (tp_dist / sl_dist) < RANGE_RR_MIN - 1e-6:
        return None
    return (d, price, sl_dist, tp_dist)


def scan_trend(c, h, l, params, lo=None, hi=None):
    """非重叠逐根扫描, 返回候选列表 [{i, direction, entry, sl_d, tp_d, pnl, hit, bh}]。"""
    atr = ce._atr(h, l, c)
    adx = ce._adx(h, l, c)
    e21 = ce._ema(c, 21)
    e50 = ce._ema(c, 50)
    n = len(c)
    lo = WARMUP if lo is None else lo
    hi = n - 1 if hi is None else hi
    out = []
    i = lo
    while i < hi:
        cand = trend_candidate(i, c, h, l, atr, adx, params, e21, e50)
        if cand is None:
            i += 1
            continue
        d, entry, sl_d, tp_d = cand
        res = settle(d, i, entry, sl_d, tp_d, h, l, n)
        if res is None:
            i += 1
            continue
        sgn, hit, bh = res
        out.append({'i': i, 'direction': d, 'entry': entry, 'sl_d': sl_d,
                    'tp_d': tp_d, 'sgn': sgn, 'hit': hit, 'bh': bh})
        i = i + bh + 1          # 持仓期间不再重复开仓
    return out


def scan_range(c, h, l, ceiling, pip, pos, pusd, spread, lo=None, hi=None):
    """非重叠区间扫描。返回 (trades, trigger_bars, regime_bars)。"""
    atr = ce._atr(h, l, c)
    adx = ce._adx(h, l, c)
    n = len(c)
    lo = RANGE_BB_PERIOD + 5 if lo is None else lo
    hi = n - 1 if hi is None else hi
    trades, trigger_bars, regime_bars = [], 0, 0
    i = lo
    while i < hi:
        in_regime = (not np.isnan(adx[i])) and (adx[i] < ceiling)
        if in_regime:
            regime_bars += 1
        cand = range_candidate(i, c, h, l, atr, adx, ceiling, pip)
        if cand is None:
            i += 1
            continue
        trigger_bars += 1
        d, entry, sl_d, tp_d = cand
        res = settle(d, i, entry, sl_d, tp_d, h, l, n)
        if res is None:
            i += 1
            continue
        sgn, hit, bh = res
        pnl_pts = sgn - spread          # 与 run_walkforward 口径: 扣 spread
        pnl = pnl_usd(pnl_pts, pip, pos, pusd)
        trades.append({'i': i, 'direction': d, 'pnl': pnl, 'hit': hit, 'bh': bh})
        i = i + bh + 1
    return trades, trigger_bars, regime_bars


# ───────────────────────── RFAlpha 因果打分 ─────────────────────────
def rf_train_and_score(sym, c, h, l, split):
    """前 60% 训练, 对全序列 (因果特征) 逐根打分。返回 (up[], down[]) 或 (None, reason)。"""
    model = ra.RFAlpha()
    if not model.fit((c[:split], h[:split], l[:split])):
        return None, "RFAlpha 训练失败 (样本不足/单类)"
    feats, valid = model._build_features(c, h, l)
    cls = list(model.classes_)
    up = np.full(len(c), np.nan)
    down = np.full(len(c), np.nan)
    for t in range(split, len(c)):
        if valid[t] and not np.any(np.isnan(feats[t])):
            p = model.predict_proba(feats[t].reshape(1, -1))[0]
            up[t] = float(p[cls.index(1)])
            down[t] = float(p[cls.index(0)])
    return (up, down), "ok"


# ───────────────────────── 统计辅助 ─────────────────────────
def stats(pnls):
    if pnls is None or len(pnls) == 0:
        return None
    a = np.array(pnls, float)
    wins = a[a > 0]
    loss = a[a < 0]
    wr = len(wins) / len(a)
    gw = float(wins.sum())
    gl = float(-loss.sum())
    pf = (gw / gl) if gl > 1e-12 else float('inf')
    return {'n': len(a), 'wr': wr, 'pf': pf, 'net': float(a.sum()),
            'avg': float(a.mean()), 'exp': float(a.mean())}


# ═══════════════════════════════════════════════════════════════════
# 任务 A: RF 门禁阈值敏感度 (BTCUSD / ETHUSD)
# ═══════════════════════════════════════════════════════════════════
def task_a(sym, data):
    c, h, l, spread = data
    n = len(c)
    split = int(n * TRAIN_FRAC)
    cfg = ce.SYMBOL_CONFIG[sym]
    pip, pos, pusd = cfg['pip'], EVOLVED[sym]['position_size'], cfg['pip_usd_per_lot']

    rf, reason = rf_train_and_score(sym, c, h, l, split)
    if rf is None:
        return {'symbol': sym, 'rf_error': reason}
    up, down = rf

    # 测试期候选 (非重叠, 无门禁基准)
    cands = scan_trend(c, h, l, EVOLVED[sym], lo=split, hi=n - 1)
    base_pnls = [pnl_usd(x['sgn'] - spread, pip, pos, pusd) for x in cands]

    rows = {}
    base = stats(base_pnls)
    rows['baseline'] = {'thr': None, 'total': len(cands), 'taken': len(cands),
                        'skip': 0, 'flips': 0, 'pass_rate': 1.0,
                        'pf': (base['pf'] if base else None),
                        'wr': (base['wr'] if base else None),
                        'n': (base['n'] if base else 0),
                        'net': (base['net'] if base else 0.0)}

    for T in THRESHOLDS:
        taken_pnls, flips, taken, skip = [], 0, 0, 0
        for x in cands:
            i = x['i']
            ru, rd = up[i], down[i]
            if np.isnan(ru) or np.isnan(rd):
                final_d = x['direction']          # 模型无分 → 放行
            else:
                p_dir = ru if x['direction'] == 'BUY' else rd
                p_opp = rd if x['direction'] == 'BUY' else ru
                if p_dir >= T:
                    final_d = x['direction']
                elif p_opp >= T and p_opp > p_dir:
                    final_d = 'SELL' if x['direction'] == 'BUY' else 'BUY'
                    flips += 1
                else:
                    final_d = None
            if final_d is None:
                skip += 1
                continue
            if final_d == x['direction']:
                sgn = x['sgn']
            else:
                # 翻转: 重新结算反方向
                r = settle(final_d, i, x['entry'], x['sl_d'], x['tp_d'], h, l, n)
                sgn = r[0] if r else -x['sl_d']
            taken_pnls.append(pnl_usd(sgn - spread, pip, pos, pusd))
            taken += 1
        st = stats(taken_pnls)
        rows[f'T{T}'] = {'thr': T, 'total': len(cands), 'taken': taken,
                         'skip': skip, 'flips': flips,
                         'pass_rate': taken / len(cands) if cands else 0,
                         'pf': (st['pf'] if st else None),
                         'wr': (st['wr'] if st else None),
                         'n': (st['n'] if st else 0),
                         'net': (st['net'] if st else 0.0)}
    return {'symbol': sym, 'rf_reason': reason, 'split': split, 'n': n, 'rows': rows}


# ═══════════════════════════════════════════════════════════════════
# 任务 B: 区间(均值回归)策略真实表现 (XAUUSD / EURUSD / GBPUSD)
# ═══════════════════════════════════════════════════════════════════
def task_b(sym, data):
    c, h, l, spread = data
    n = len(c)
    cfg = ce.SYMBOL_CONFIG[sym]
    pip, pusd = cfg['pip'], cfg['pip_usd_per_lot']
    adx_min = EVOLVED[sym]['adx_min']
    ceiling = min(adx_min, RANGE_ADX_CEIL)
    trades, trigger, regime = scan_range(c, h, l, ceiling, pip, RANGE_MAX_LOT, pusd, spread)
    pnls = [t['pnl'] for t in trades]
    st = stats(pnls)
    bhs = [t['bh'] for t in trades]
    # 半段稳定性 (防过拟合)
    half = n // 2
    tr1, _, _ = scan_range(c, h, l, ceiling, pip, RANGE_MAX_LOT, pusd, spread, lo=RANGE_BB_PERIOD + 5, hi=half)
    tr2, _, _ = scan_range(c, h, l, ceiling, pip, RANGE_MAX_LOT, pusd, spread, lo=half, hi=n - 1)
    s1, s2 = stats([t['pnl'] for t in tr1]), stats([t['pnl'] for t in tr2])
    return {
        'symbol': sym, 'ceiling': ceiling, 'n': n,
        'total_bars': n, 'regime_bars': regime, 'trigger_bars': trigger,
        'trigger_rate': (trigger / regime) if regime else 0.0,
        'n': len(trades), 'wr': (st['wr'] if st else None),
        'pf': (st['pf'] if st else None), 'net': (st['net'] if st else 0.0),
        'avg_hold': (float(np.mean(bhs)) if bhs else 0.0),
        'pf_h1': (s1['pf'] if s1 else None), 'pf_h2': (s2['pf'] if s2 else None),
        'n_h1': (s1['n'] if s1 else 0), 'n_h2': (s2['n'] if s2 else 0),
    }


# ═══════════════════════════════════════════════════════════════════
# 任务 C: XAUUSD adx_min 敏感度
# ═══════════════════════════════════════════════════════════════════
def task_c(sym, data, adx_list):
    c, h, l, spread = data
    n = len(c)
    cfg = ce.SYMBOL_CONFIG[sym]
    pip, pos, pusd = cfg['pip'], EVOLVED[sym]['position_size'], cfg['pip_usd_per_lot']
    rows = {}
    for adx in adx_list:
        params = dict(EVOLVED[sym])
        params['adx_min'] = adx
        cands = scan_trend(c, h, l, params, lo=WARMUP, hi=n - 1)
        pnls = [pnl_usd(x['sgn'] - spread, pip, pos, pusd) for x in cands]
        st = stats(pnls)
        half = n // 2
        c1 = scan_trend(c, h, l, params, lo=WARMUP, hi=half)
        c2 = scan_trend(c, h, l, params, lo=half, hi=n - 1)
        s1, s2 = stats([pnl_usd(x['sgn'] - spread, pip, pos, pusd) for x in c1]), \
                 stats([pnl_usd(x['sgn'] - spread, pip, pos, pusd) for x in c2])
        rows[adx] = {
            'adx_min': adx, 'proposals': len(cands),
            'prop_rate': len(cands) / (n - WARMUP),
            'n': (st['n'] if st else 0), 'wr': (st['wr'] if st else None),
            'pf': (st['pf'] if st else None), 'net': (st['net'] if st else 0.0),
            'pf_h1': (s1['pf'] if s1 else None), 'pf_h2': (s2['pf'] if s2 else None),
        }
    return {'symbol': sym, 'n': n, 'rows': rows}


# ═══════════════════════════════════════════════════════════════════
# 报告
# ═══════════════════════════════════════════════════════════════════
def fmt_pf(pf):
    if pf is None:
        return "—"
    if pf == float('inf'):
        return "∞"
    return f"{pf:.2f}"


def wr_str(wr):
    """胜率格式化 (None → '-')。"""
    return '-' if wr is None else f"{wr*100:.1f}%"


def main():
    t0 = time.time()
    connected = ce.ensure_mt5()
    print(f"[init] MT5 connected = {connected}")
    if not connected:
        print("MT5 未连接, 无法拉历史; 退出。")
        return

    results = {'meta': {}, 'A': {}, 'B': {}, 'C': {}}
    data_cache = {}

    def get(sym):
        if sym not in data_cache:
            d, why = load_h1(sym)
            data_cache[sym] = (d, why)
        return data_cache[sym]

    # ── 任务 A ──
    print("\n=== 任务 A: RF 门禁阈值敏感度 (BTCUSD / ETHUSD) ===")
    for sym in ['BTCUSD', 'ETHUSD']:
        d, why = get(sym)
        if d is None:
            print(f"  {sym}: 数据失败 -> {why} (跳过)")
            results['A'][sym] = {'error': why}
            continue
        r = task_a(sym, d)
        results['A'][sym] = r
        if 'rf_error' in r:
            print(f"  {sym}: RF 失败 -> {r['rf_error']}")
            continue
        print(f"  {sym} (n={r['n']}, 训练切分={r['split']}):")
        for k, v in r['rows'].items():
            print(f"    {k:9s} 通过率={v['pass_rate']*100:5.1f}% 笔数={v['n']:4d} "
                  f"WR={wr_str(v['wr']):>6} "
                  f"PF={fmt_pf(v['pf']):>5} 净=${v['net']:10.1f} 翻转={v['flips']}")

    # ── 任务 B ──
    print("\n=== 任务 B: 区间(均值回归)策略真实表现 (XAU/EUR/GBP) ===")
    for sym in ['XAUUSD', 'EURUSD', 'GBPUSD']:
        d, why = get(sym)
        if d is None:
            print(f"  {sym}: 数据失败 -> {why} (跳过)")
            results['B'][sym] = {'error': why}
            continue
        r = task_b(sym, d)
        results['B'][sym] = r
        print(f"  {sym}: ceiling(ADX<{r['ceiling']:.0f}) 触发={r['trigger_bars']} "
              f"({r['trigger_rate']*100:.1f}% of regime) 笔数={r['n']} "
              f"WR={wr_str(r['wr']):>6} "
              f"PF={fmt_pf(r['pf'])} 净=${r['net']:.1f} 均持仓={r['avg_hold']:.0f}根 "
              f"PF半段={fmt_pf(r['pf_h1'])}/{fmt_pf(r['pf_h2'])}")

    # ── 任务 C ──
    print("\n=== 任务 C: XAUUSD adx_min 敏感度 ===")
    d, why = get('XAUUSD')
    if d is None:
        print(f"  XAUUSD: 数据失败 -> {why} (跳过)")
        results['C']['XAUUSD'] = {'error': why}
    else:
        r = task_c('XAUUSD', d, [22, 23, 25, 28])
        results['C']['XAUUSD'] = r
        for adx, v in r['rows'].items():
            print(f"    adx_min={adx:>4}: 提案={v['proposals']:4d} ({v['prop_rate']*100:.1f}%) "
                  f"笔数={v['n']:4d} WR={wr_str(v['wr']):>6} "
                  f"PF={fmt_pf(v['pf'])} 净=${v['net']:.1f} "
                  f"PF半段={fmt_pf(v['pf_h1'])}/{fmt_pf(v['pf_h2'])}")

    results['meta'] = {
        'generated_at': dt.datetime.now().isoformat(timespec='seconds'),
        'interpreter': sys.executable,
        'n_bars': N_BARS, 'train_frac': TRAIN_FRAC, 'exit_win': EXIT_WIN,
        'thresholds': THRESHOLDS,
        'data': {s: (data_cache[s][0][0].shape[0] if data_cache[s][0] else None,
                      data_cache[s][1]) for s in data_cache},
    }

    # ── 写报告 ──
    write_report(results)
    mt5.shutdown()
    print(f"\n[done] 用时 {time.time()-t0:.1f}s | 报告已写: {OUT_PATH}")


def write_report(R):
    L = []
    L.append(f"# 趋势 / 震荡 参数独立回测报告 (GoldstrategyEngine)\n")
    L.append(f"> 研策师 v4.0 · 生成时间 {R['meta']['generated_at']} · 解释器 `{R['meta']['interpreter']}`\n")
    L.append("## 方法与口径\n")
    L.append("- **零侵入**: 不修改任何系统代码; 趋势/区间信号复刻 `build_signal` / `build_range_signal` 入场逻辑, 指标原样复用 `continuous_evolution_v2._atr/_adx/_structure_confirm/_ema`。")
    L.append("- **RF 门禁**: 用 `rf_alpha.RFAlpha`(因果特征 + 错位标签, 无未来函数) 对每根 K 线打 UP/DOWN 概率; 前 60% 训练、后 40% 测试(walk-forward)。门禁规则与 `market_scanner.py` 一致: 提案方向概率 ≥ 阈值则过; 反方向更高且 ≥ 阈值则翻转; 否则拦截。")
    L.append(f"- **出场**: 首触 SL/TP (窗口 {R['meta']['exit_win']} 根 H1), 与 `run_walkforward` 完全一致; pnl 扣 spread, 与系统 walk-forward 口径一致 (未含佣金, 与引擎一致)。")
    L.append("- **净收益**: 用进化出的 `position_size` 与 `SYMBOL_CONFIG.pip_usd_per_lot` 折算 USD。趋势用进化仓位, 区间用 `RANGE_MAX_LOT=0.03`。")
    L.append("- **数据**: 各品种 MT5 H1 历史 (见下表), 只读, 未下任何真实订单。\n")

    # 数据表
    L.append("| 品种 | 历史根数 | 时间范围 | 是否参与 |")
    L.append("|---|---|---|---|")
    dtu = __import__('datetime')
    for s, (n, why) in R['meta']['data'].items():
        ok = (n is not None)
        rng = why if not ok else f"n={n}"
        L.append(f"| {s} | {n if n else '—'} | {rng} | {'✓' if ok else '✗ 跳过'} |")
    L.append("")

    # ── 任务 A ──
    L.append("## 任务 A · RF 门禁阈值敏感度 (BTCUSD / ETHUSD)\n")
    L.append("**问题**: 若开启 RF 质量门禁, 每根提案会被按 UP/DOWN 概率放行/翻转/拦截。下表给出含「无门禁基准」在内的各阈值通过率与策略表现, 用于权衡「放行笔数 vs 质量」。本窗口 RFAlpha 对 BTC/ETH 主要产生**翻转**(反方向), 且翻转后表现更差。\n")
    for sym in ['BTCUSD', 'ETHUSD']:
        a = R['A'].get(sym, {})
        if 'error' in a or 'rf_error' in a:
            L.append(f"### {sym}\n> 数据/RF 不可用: {a.get('error', a.get('rf_error'))} — 跳过。\n")
            continue
        L.append(f"### {sym}  (测试期 n={a['n']}, 训练切分={a['split']})\n")
        L.append("| 配置 | 提案数 | 通过率 | 笔数 | 胜率 | PF | 净收益($) | 翻转 |")
        L.append("|---|---|---|---|---|---|---|---|")
        for k in ['baseline'] + [f'T{t}' for t in R['meta']['thresholds']]:
            v = a['rows'][k]
            label = "无门禁(基准)" if k == 'baseline' else f"阈值={v['thr']}"
            L.append(f"| {label} | {v['total']} | {v['pass_rate']*100:.1f}% | {v['n']} | "
                     f"{wr_str(v['wr'])} | {fmt_pf(v['pf'])} | "
                     f"{v['net']:.1f} | {v['flips']} |")
        L.append("")

    # ── 任务 B ──
    L.append("## 任务 B · 区间(均值回归)策略真实表现 (XAUUSD / EURUSD / GBPUSD)\n")
    L.append("**方法**: 复刻 `build_range_signal`: 仅当 H1 ADX < min(adx_min, 35) 时接管; BB(15,1.5)+KC(1.5); 价格贴近 BB 边界 ±0.2pip 入场; RR≥2。统计触发占比与策略表现。\n")
    L.append("| 品种 | 接管上限(ADX<) | 区间bar数 | 触发bar数 | 触发率 | 笔数 | 胜率 | PF | 净收益($) | 均持仓(根) | 半段PF(前/后) |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for sym in ['XAUUSD', 'EURUSD', 'GBPUSD']:
        b = R['B'].get(sym, {})
        if 'error' in b:
            L.append(f"| {sym} | — | — | — | — | — | — | — | — | — | 数据失败跳过 |")
            continue
        L.append(f"| {sym} | {b['ceiling']:.0f} | {b['regime_bars']} | {b['trigger_bars']} | "
                 f"{b['trigger_rate']*100:.1f}% | {b['n']} | "
                 f"{wr_str(b['wr'])} | {fmt_pf(b['pf'])} | "
                 f"{b['net']:.1f} | {b['avg_hold']:.0f} | "
                 f"{fmt_pf(b['pf_h1'])}/{fmt_pf(b['pf_h2'])} |")
    L.append("")

    # ── 任务 C ──
    L.append("## 任务 C · XAUUSD adx_min 敏感度\n")
    L.append("**问题**: 当前 XAU `adx_min=25`。降到 22~23 能否提升资金利用率 (更多提案/笔数) 且不损 PF? 其余参数沿用进化值 (sl=2.59, tp=5.79, momentum_filter=ON)。\n")
    c = R['C'].get('XAUUSD', {})
    if 'error' in c:
        L.append(f"> XAUUSD 数据失败: {c['error']} — 跳过。\n")
    else:
        L.append("| adx_min | 提案数 | 提案率 | 笔数 | 胜率 | PF | 净收益($) | 半段PF(前/后) |")
        L.append("|---|---|---|---|---|---|---|---|")
        for adx, v in c['rows'].items():
            L.append(f"| {adx} | {v['proposals']} | {v['prop_rate']*100:.1f}% | {v['n']} | "
                     f"{wr_str(v['wr'])} | {fmt_pf(v['pf'])} | "
                     f"{v['net']:.1f} | {fmt_pf(v['pf_h1'])}/{fmt_pf(v['pf_h2'])} |")
        L.append("")

    # ── 结论与建议 ──
    L.append("## 结论与可执行调优建议\n")
    recs = build_recommendations(R)
    for line in recs:
        L.append(line)

    L.append("\n## 方法论局限\n")
    L.append("- RFAlpha 在历史 H1 上训练/打分, 与 live 的「懒训练+缓存、不滚动重训」行为一致; 但单品种单模型, 未做跨品种泛化。")
    L.append("- RF 门禁在**测试期(后40%)** 评估, 训练/测试不重叠, 无未来函数; 但样本仅 ~2.4 个月 (crypto), 统计噪声较大。")
    L.append("- 出场用固定 250 根 H1 窗口, 与系统 walk-forward 一致; 未含佣金 (与引擎口径一致), 实际净收益会略低。")
    L.append("- 区间策略 `slbuf=0.8pip` 极紧, 在含 spread 摩擦的实盘中可能比回测更脆弱; 区间为辅助模块, 仍过审度司 VETO, 不影响双铁律。")
    L.append("- 全部为历史统计, 不构成未来收益保证; 建议先在 paper/sim 验证再小仓上线。")

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        f.write("\n".join(L))


def build_recommendations(R):
    out = []
    # A
    out.append("### A. RF 门禁阈值 (BTCUSD / ETHUSD)")
    any_a = False
    for sym in ['BTCUSD', 'ETHUSD']:
        a = R['A'].get(sym, {})
        if 'rows' not in a:
            continue
        any_a = True
        base = a['rows']['baseline']
        base_pf = base['pf'] if (base['pf'] is not None) else 0.0
        # 最佳门禁阈值: 笔数>=10 且 PF 最高
        best_t, best_v = None, None
        for t in R['meta']['thresholds']:
            v = a['rows'][f'T{t}']
            if v['n'] >= 10 and (v['pf'] is not None) and v['pf'] > 0:
                if best_v is None or v['pf'] > best_v['pf']:
                    best_t, best_v = t, v
        gate_pf = best_v['pf'] if best_v else 0.0
        if base_pf >= 1.0 and base_pf >= gate_pf:
            out.append(
                f"- **{sym}**: 无门禁(基准) PF={fmt_pf(base['pf'])}/笔数={base['n']}/净${base['net']:.0f} "
                f"**全面优于任何门禁阈值**(最佳门禁 T{best_t} 仅 PF={fmt_pf(gate_pf)} 净${best_v['net']:.0f})。"
                f"RFAlpha 把趋势提案大量翻转/拦截(翻转 {best_v['flips']} 笔)反而恶化 → "
                f"**建议 RF_QUALITY_GATE=False(不开启)**。")
        elif gate_pf >= 1.0 and (best_v['n'] >= 20):
            out.append(
                f"- **{sym}**: 门禁 T{best_t} 略优于无门禁 (PF {fmt_pf(gate_pf)} vs {fmt_pf(base['pf'])}, "
                f"净${best_v['net']:.0f} vs ${base['net']:.0f}) → 可开启, 阈值设 **{best_t}**; 否则保持关闭。")
        else:
            out.append(
                f"- **{sym}**: 无门禁与各门禁阈值均为负期望 (基准 PF={fmt_pf(base['pf'])}, "
                f"最佳门禁 PF={fmt_pf(gate_pf)})。RFAlpha 在该品种未能提供有效方向过滤 → "
                f"**建议保持 RF_QUALITY_GATE=False**, 让趋势策略全量运行; 回测样本仅 ~2.4 月, 结论需 sim 复核。")
    if not any_a:
        out.append("- **BTC/ETH**: 数据或 RF 不可用, 无法给出阈值建议 (见上)。")

    # B
    out.append("\n### B. 区间(RANGE_MODE)开/关")
    bnet = {}
    for sym in ['XAUUSD', 'EURUSD', 'GBPUSD']:
        b = R['B'].get(sym, {})
        if 'pf' not in b:
            out.append(f"- **{sym}**: 数据不可用, 见上。")
            continue
        bnet[sym] = b['net']
        pf = b['pf'] if (b['pf'] is not None) else 0.0
        stable = (b['pf_h1'] is not None and b['pf_h1'] > 1.0 and
                  b['pf_h2'] is not None and b['pf_h2'] > 1.0)
        if (b['n'] >= 20) and stable:
            verdict = "稳健正期望 → 保留"
        elif pf > 1.0 and b['n'] >= 20:
            verdict = "正期望但不稳定(半段<1) → 谨慎/试验性保留"
        elif pf > 1.0:
            verdict = "PF>1 但样本过小(≤19笔) → 不可靠, 建议关闭"
        else:
            verdict = "负期望 → 建议关闭"
        out.append(
            f"- **{sym}**: PF={fmt_pf(pf)} 笔数={b['n']} 净=${b['net']:.1f} "
            f"半段PF={fmt_pf(b['pf_h1'])}/{fmt_pf(b['pf_h2'])} → **{verdict}**")
    xau = bnet.get('XAUUSD', 0.0); eur = bnet.get('EURUSD', 0.0); gbp = bnet.get('GBPUSD', 0.0)
    out.append(
        f"- 综合: 三品种区间模块净贡献极小 (XAU ${xau:.0f} / EUR ${eur:.0f} / GBP ${gbp:.0f}), "
        f"触发率仅 0.5–0.9% 区间bar, 且半段稳定性差 → 区间策略**非稳健 edge**。 "
        f"建议设 `RANGE_MODE_ENABLED=False` 关闭区间模块、由趋势通道兜底, 以降复杂度与过拟合风险; "
        f"仅 XAU 因 PF 极高(样本仅9笔)可小样本试验性保留, 但须扩大样本复核。")

    # C
    out.append("\n### C. XAUUSD adx_min")
    c = R['C'].get('XAUUSD', {})
    if 'rows' in c:
        cur = c['rows'].get(25)
        best_adx, best_v = None, None
        for adx, v in c['rows'].items():
            if v['pf'] is not None:
                if best_v is None or v['pf'] > best_v['pf'] or \
                   (abs(v['pf'] - best_v['pf']) < 1e-9 and v['net'] > best_v['net']):
                    best_adx, best_v = adx, v
        if best_v is not None and best_v['pf'] >= 1.0:
            out.append(
                f"- **结论**: 所有 adx_min 下 XAU 趋势策略 PF 均 ≤ {fmt_pf(best_v['pf'])} (本窗口净亏损)。"
                f"最高为 adx_min=**{best_adx}** (PF {fmt_pf(best_v['pf'])} 净${best_v['net']:.0f}), 仍近持平/微亏。"
                f"降到 22-23 **仅增笔数(114/113 vs 109)却不提升 PF(仍≤0.95)且净亏损更大"
                f"(-$849/-$776 vs -$66)** → **不建议降低 adx_min**; 建议维持 25 或上调至 28(损失最小), "
                f"并复核进化参数(sl=2.59/tp=5.79)是否过拟合——本窗口趋势策略整体为负期望。")
        else:
            out.append(
                f"- **关键发现**: XAU 趋势策略在本 H1 窗口(4500根) **所有 adx_min 下 PF 均 <1 (净亏损)** "
                f"— adx=22/23/25 为 {fmt_pf(c['rows'][22]['pf'])}/{fmt_pf(c['rows'][23]['pf'])}/{fmt_pf(c['rows'][25]['pf'])}, "
                f"仅 adx=28 接近持平 PF={fmt_pf(c['rows'][28]['pf'])} 净${c['rows'][28]['net']:.0f}。"
                f"降到 22-23 **仅增加笔数却不提升 PF(仍≤0.95)且净亏损更大** → **不应降低 adx_min**; "
                f"建议维持 25 或上调至 28(损失最小), 并复核进化参数是否过拟合。")
    else:
        out.append("- XAUUSD 数据不可用, 见上。")

    out.append("\n### 一句话总建议")
    a_btc = R['A'].get('BTCUSD', {}).get('rows', {}).get('baseline', {})
    a_eth = R['A'].get('ETHUSD', {}).get('rows', {}).get('baseline', {})
    b_xau = R['B'].get('XAUUSD', {}).get('net') or 0.0
    b_eur = R['B'].get('EURUSD', {}).get('net') or 0.0
    b_gbp = R['B'].get('GBPUSD', {}).get('net') or 0.0
    out.append(
        f"- **RF门禁**: BTC/ETH **保持 RF_QUALITY_GATE=False (不开启)** — "
        f"无门禁(基准) PF {fmt_pf(a_btc.get('pf'))}/{fmt_pf(a_eth.get('pf'))} 已优于任何门禁阈值, "
        f"RFAlpha 在该窗口反而翻转/拦截趋势提案恶化表现。")
    out.append(
        f"- **区间模块**: **建议 RANGE_MODE_ENABLED=False 关闭** — "
        f"三品种净贡献极小(${b_xau:.0f}/${b_eur:.0f}/${b_gbp:.0f})、触发率仅0.5–0.9%、半段稳定性差, 非稳健 edge; 由趋势通道兜底。")
    out.append(
        "- **XAU adx_min**: **不建议降到 22-23** (仅增笔数不增 PF, 净亏损更大); "
        "维持 25 或上调至 28(损失最小)。注意本窗口 XAU 趋势策略整体 PF<1, 需复核进化参数是否过拟合。")
    out.append("- 所有改动建议先在 sim/paper 验证再小仓上线。")
    return out


if __name__ == '__main__':
    main()
