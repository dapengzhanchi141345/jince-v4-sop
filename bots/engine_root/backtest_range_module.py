# backtest_range_module.py — 区间/均值回归模块 历史回测验证 (P2-A)
"""
忠实复刻 guardian_executor.build_range_signal 的成交逻辑, 用 MT5 历史数据
逐品种模拟成交, 计算区间模块的 fitness / PF / WR / expectancy, 判断其是否真有 edge。

设计要点 (与线上一致):
  - BB(20, 2σ) 定义区间上下轨
  - KC(MA ± 1.5×ATR) 仅作 squeeze 标注, 不硬拒
  - 价格接近 BB 上沿(未突破) → SELL; 接近下沿(未突破) → BUY
  - RR≥2.0 硬守 (双铁律), SL 在边界外 0.8 pip 缓冲
  - 低波动门禁: 仅当 H1 ADX<20 (线上 ADX 硬禁处分支接管) 才允许区间信号
  - 同时报告 "全样本(无 ADX 门禁)" 版作为对照

fitness 口径与 continuous_evolution_v2.evaluate_fitness 一致:
  fitness = win_rate*40 + min(pf,3)/3*30 + clip(sharpe,0,3)/3*30

仅读 MT5, 不下单 (DRY-RUN)。
"""
import json
import math
import datetime as dt
import numpy as np
import MetaTrader5 as mt5

import continuous_evolution_v2 as ce

# ── 区间参数 (与 guardian_executor 完全一致) ──
# [P2-A 进化] 2026-07-09 扫描优化 #3: BB15 / std1.5 / entry0.2 / sl0.8
RANGE_BB_PERIOD = 15
RANGE_BB_STD = 1.5
RANGE_KC_MULT = 1.5
RANGE_SQUEEZE_THR = 0.9
RANGE_ENTRY_BUFFER_PIPS = 0.2
RANGE_SL_BUFFER_PIPS = 0.8
RANGE_RR_MIN = 2.0
RANGE_MAX_LOT = 0.03
ADX_FLOOR = 20          # H1 ADX<20 才走区间分支 (线上 ADX 硬禁)
MAX_HOLD_BARS = 240     # 单笔最长持仓 (M5 根) ≈ 20h
TEST_LOT = 0.01         # 固定手数便于跨品种比较 edge


def wilder_atr(high, low, close, p=14):
    n = len(close)
    tr = np.zeros(n)
    tr[1:] = np.maximum(high[1:] - low[1:],
             np.maximum(np.abs(high[1:] - close[:-1]),
                        np.abs(low[1:] - close[:-1])))
    atr = np.zeros(n)
    atr[p] = np.mean(tr[1:p + 1])
    for i in range(p + 1, n):
        atr[i] = (atr[i - 1] * (p - 1) + tr[i]) / p
    return atr


def compute_adx(high, low, close, p=14):
    n = len(close)
    up = high[1:] - high[:-1]
    dn = low[:-1] - low[1:]
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.zeros(n)
    tr[1:] = np.maximum(high[1:] - low[1:],
             np.maximum(np.abs(high[1:] - close[:-1]),
                        np.abs(low[1:] - close[:-1])))
    atr = np.zeros(n)
    atr[p] = np.mean(tr[1:p + 1])
    for i in range(p + 1, n):
        atr[i] = (atr[i - 1] * (p - 1) + tr[i]) / p
    pdm = np.zeros(n); mdm = np.zeros(n)
    pdm[p] = np.mean(plus_dm[:p]); mdm[p] = np.mean(minus_dm[:p])
    for i in range(p + 1, n):
        pdm[i] = (pdm[i - 1] * (p - 1) + plus_dm[i - 1]) / p
        mdm[i] = (mdm[i - 1] * (p - 1) + minus_dm[i - 1]) / p
    pdi = np.where(atr > 0, pdm / atr * 100, 0.0)
    mdi = np.where(atr > 0, mdm / atr * 100, 0.0)
    dx = np.where((pdi + mdi) > 0, np.abs(pdi - mdi) / (pdi + mdi) * 100, 0.0)
    adx = np.zeros(n)
    adx[2 * p] = np.mean(dx[p:2 * p + 1])
    for i in range(2 * p + 1, n):
        adx[i] = (adx[i - 1] * (p - 1) + dx[i]) / p
    return adx


def fitness_from_trades(pnls):
    """复刻 evaluate_fitness 的复合公式 (无 TC/DL 裁判, 纯统计)。"""
    if not pnls or len(pnls) < 5:
        return {'fitness': 0.0, 'pf': 0.0, 'wr': 0.0, 'sharpe': 0.0,
                'trades': len(pnls), 'expectancy': 0.0}
    r = np.array(pnls, float)
    wins = r[r > 0]; losses = r[r < 0]
    wr = len(wins) / len(r)
    gp = wins.sum(); gl = -losses.sum()
    pf = (gp / gl) if gl > 0 else 3.0
    mean = r.mean(); std = r.std()
    sharpe = (mean / std) if std > 0 else 0.0
    sharpe = float(np.clip(sharpe, 0, 3))
    fit = wr * 40 + min(pf, 3) / 3 * 30 + sharpe / 3 * 30
    return {'fitness': round(fit, 3), 'pf': round(float(pf), 3),
            'wr': round(float(wr), 3), 'sharpe': round(sharpe, 3),
            'trades': len(r),
            'expectancy': round(float(mean), 2)}


def backtest_symbol(symbol, use_adx_gate=True, adx_floor=ADX_FLOOR):
    cfg = ce.SYMBOL_CONFIG[symbol]
    pip = cfg['pip']
    ppl = cfg['pip_usd_per_lot']
    # 拉历史
    m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 20000)
    h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 3000)
    if m5 is None or len(m5) < RANGE_BB_PERIOD + 50:
        return {'symbol': symbol, 'error': 'M5 数据不足',
                'm5_bars': 0 if m5 is None else len(m5)}
    m5 = np.array(m5)
    t = m5['time'].astype('int64')
    o = m5['open'].astype(float); h = m5['high'].astype(float)
    l = m5['low'].astype(float); c = m5['close'].astype(float)
    n = len(c)
    atr = wilder_atr(h, l, c, 14)
    h1_adx = None
    if use_adx_gate and h1 is not None and len(h1) > 50:
        h1 = np.array(h1)
        h1_adx = compute_adx(h1['high'].astype(float),
                             h1['low'].astype(float),
                             h1['close'].astype(float), 14)
        h1_t = h1['time'].astype('int64')

    period = RANGE_BB_PERIOD
    pnls = []
    in_trade = False
    entry = sl = tp = 0.0
    direction = 0  # +1 BUY, -1 SELL
    entry_idx = 0

    for i in range(period + 5, n - 1):
        if in_trade:
            # 检查出场
            exit_price = None
            for j in range(entry_idx + 1, min(entry_idx + 1 + MAX_HOLD_BARS, n)):
                if direction == 1:  # BUY
                    if l[j] <= sl:
                        exit_price = sl; break
                    if h[j] >= tp:
                        exit_price = tp; break
                else:  # SELL
                    if h[j] >= sl:
                        exit_price = sl; break
                    if l[j] <= tp:
                        exit_price = tp; break
            if exit_price is None:
                # 超时市价平
                exit_price = c[min(entry_idx + 1 + MAX_HOLD_BARS, n - 1)]
            pnl = direction * (exit_price - entry) / pip * ppl * TEST_LOT
            pnls.append(pnl)
            in_trade = False
            continue

        # 低波动门禁
        if use_adx_gate and h1_adx is not None:
            # 找当前 M5 对应的 H1 ADX
            idx = int(np.searchsorted(h1_t, t[i], side='right') - 1)
            if idx < 0 or np.isnan(h1_adx[idx]) or h1_adx[idx] >= adx_floor:
                continue

        if np.isnan(atr[i]):
            continue
        window = c[i - period + 1:i + 1]
        ma = float(np.mean(window)); sd = float(np.std(window))
        bb_up = ma + RANGE_BB_STD * sd
        bb_dn = ma - RANGE_BB_STD * sd
        kc_ma = ma
        kc_atr = float(np.mean(atr[i - period + 1:i + 1]))
        kc_up = kc_ma + RANGE_KC_MULT * kc_atr
        kc_dn = kc_ma - RANGE_KC_MULT * kc_atr
        bb_w = bb_up - bb_dn; kc_w = kc_up - kc_dn
        squeeze = (kc_w > 0) and (bb_w / kc_w) < RANGE_SQUEEZE_THR
        price = c[i]
        mid = (bb_up + bb_dn) / 2.0
        ebuf = RANGE_ENTRY_BUFFER_PIPS * pip
        slbuf = RANGE_SL_BUFFER_PIPS * pip

        if bb_up - ebuf <= price <= bb_up:
            direction = -1
            sl = bb_up + slbuf
            sl_dist = sl - price
            tp_dist = max(sl_dist * RANGE_RR_MIN, (price - mid))
            tp = price - tp_dist
        elif bb_dn <= price <= bb_dn + ebuf:
            direction = 1
            sl = bb_dn - slbuf
            sl_dist = price - sl
            tp_dist = max(sl_dist * RANGE_RR_MIN, (mid - price))
            tp = price + tp_dist
        else:
            continue
        sl_pts = abs(sl - price) / pip
        tp_pts = abs(tp - price) / pip
        if tp_pts / sl_pts < RANGE_RR_MIN - 1e-6:
            continue
        # 入场用下一根开盘
        entry = o[i + 1]
        entry_idx = i
        in_trade = True
        # 标记 squeeze 命中 (仅记录, 不影响 pnl)

    # 收尾未平
    if in_trade:
        exit_price = c[min(entry_idx + 1 + MAX_HOLD_BARS, n - 1)]
        pnl = direction * (exit_price - entry) / pip * ppl * TEST_LOT
        pnls.append(pnl)

    stats = fitness_from_trades(pnls)
    stats['symbol'] = symbol
    stats['squeeze_only'] = False
    return stats


def main():
    if not mt5.initialize():
        print(json.dumps({'error': 'MT5 init failed'}))
        return
    symbols = list(ce.SYMBOL_CONFIG.keys())
    out = {'generated': dt.datetime.now().isoformat(timespec='seconds'),
           'gated': {}, 'all_bars': {}, 'moderate': {}}
    for sym in symbols:
        try:
            g = backtest_symbol(sym, use_adx_gate=True)
            out['gated'][sym] = g
        except Exception as e:
            out['gated'][sym] = {'symbol': sym, 'error': str(e)}
        try:
            a = backtest_symbol(sym, use_adx_gate=False)
            out['all_bars'][sym] = a
        except Exception as e:
            out['all_bars'][sym] = {'symbol': sym, 'error': str(e)}
        try:
            # 中等趋势带: 把区间模块门禁从 ADX<20 拓宽到 ADX<35,
            # 验证"20<ADX<35 死亡真空带"是否真有 BB 边界反转 edge
            m = backtest_symbol(sym, use_adx_gate=True, adx_floor=35)
            out['moderate'][sym] = m
        except Exception as e:
            out['moderate'][sym] = {'symbol': sym, 'error': str(e)}
    mt5.shutdown()
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
