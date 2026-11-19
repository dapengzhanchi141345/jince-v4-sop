# sweep_range_params.py — 区间模块参数扫描 (P2-A)
"""
对区间模块做随机参数扫描, 在 XAUUSD/EURUSD/GBPUSD (真正产生区间单的品种)
上求全局更优的 RANGE 常量。RR_MIN 锁死 2.0 (双铁律不可破)。
仅读 MT5, 不下单。
"""
import json
import datetime as dt
import numpy as np
import MetaTrader5 as mt5
import continuous_evolution_v2 as ce

ADX_FLOOR = 20
MAX_HOLD_BARS = 240
TEST_LOT = 0.01
M5_BARS = 10000
H1_BARS = 1500

# 固定 (不可扫)
RANGE_RR_MIN = 2.0
RANGE_KC_MULT = 1.5

SYMS = ["XAUUSD", "EURUSD", "GBPUSD"]  # 真正产生区间单的品种


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
    up = high[1:] - high[:-1]; dn = low[:-1] - low[1:]
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.zeros(n)
    tr[1:] = np.maximum(high[1:] - low[1:],
             np.maximum(np.abs(high[1:] - close[:-1]),
                        np.abs(low[1:] - close[:-1])))
    atr = np.zeros(n); atr[p] = np.mean(tr[1:p + 1])
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
    adx = np.zeros(n); adx[2 * p] = np.mean(dx[p:2 * p + 1])
    for i in range(2 * p + 1, n):
        adx[i] = (adx[i - 1] * (p - 1) + dx[i]) / p
    return adx


def fitness_from_trades(pnls):
    if not pnls or len(pnls) < 5:
        return {'fitness': 0.0, 'pf': 0.0, 'wr': 0.0, 'trades': len(pnls)}
    r = np.array(pnls, float)
    wins = r[r > 0]; losses = r[r < 0]
    wr = len(wins) / len(r)
    gp = wins.sum(); gl = -losses.sum()
    pf = (gp / gl) if gl > 0 else 3.0
    mean = r.mean(); std = r.std()
    sharpe = float(np.clip(mean / std, 0, 3)) if std > 0 else 0.0
    fit = wr * 40 + min(pf, 3) / 3 * 30 + sharpe / 3 * 30
    return {'fitness': round(fit, 3), 'pf': round(float(pf), 3),
            'wr': round(float(wr), 3), 'trades': len(r)}


def backtest(glyph, params):
    sym, data, h1_adx, h1_t = glyph
    cfg = ce.SYMBOL_CONFIG[sym]; pip = cfg['pip']; ppl = cfg['pip_usd_per_lot']
    period = params['bb_period']
    t = data['t']; o = data['o']; h = data['h']; l = data['l']; c = data['c']
    atr = data['atr']; n = len(c)
    pnls = []; in_trade = False; entry = sl = tp = 0.0; direction = 0; eidx = 0
    for i in range(period + 5, n - 1):
        if in_trade:
            exit_price = None
            for j in range(eidx + 1, min(eidx + 1 + MAX_HOLD_BARS, n)):
                if direction == 1:
                    if l[j] <= sl: exit_price = sl; break
                    if h[j] >= tp: exit_price = tp; break
                else:
                    if h[j] >= sl: exit_price = sl; break
                    if l[j] <= tp: exit_price = tp; break
            if exit_price is None:
                exit_price = c[min(eidx + 1 + MAX_HOLD_BARS, n - 1)]
            pnls.append(direction * (exit_price - entry) / pip * ppl * TEST_LOT)
            in_trade = False; continue
        idx = int(np.searchsorted(h1_t, t[i], side='right') - 1)
        if idx < 0 or np.isnan(h1_adx[idx]) or h1_adx[idx] >= ADX_FLOOR:
            continue
        if np.isnan(atr[i]):
            continue
        window = c[i - period + 1:i + 1]
        ma = float(np.mean(window)); sd = float(np.std(window))
        bb_up = ma + params['bb_std'] * sd
        bb_dn = ma - params['bb_std'] * sd
        price = c[i]; mid = (bb_up + bb_dn) / 2.0
        ebuf = params['entry_buf'] * pip; slbuf = params['sl_buf'] * pip
        if bb_up - ebuf <= price <= bb_up:
            direction = -1; sl = bb_up + slbuf; sl_dist = sl - price
            tp_dist = max(sl_dist * RANGE_RR_MIN, (price - mid)); tp = price - tp_dist
        elif bb_dn <= price <= bb_dn + ebuf:
            direction = 1; sl = bb_dn - slbuf; sl_dist = price - sl
            tp_dist = max(sl_dist * RANGE_RR_MIN, (mid - price)); tp = price + tp_dist
        else:
            continue
        sl_pts = abs(sl - price) / pip; tp_pts = abs(tp - price) / pip
        if tp_pts / sl_pts < RANGE_RR_MIN - 1e-6:
            continue
        entry = o[i + 1]; eidx = i; in_trade = True
    if in_trade:
        exit_price = c[min(eidx + 1 + MAX_HOLD_BARS, n - 1)]
        pnls.append(direction * (exit_price - entry) / pip * ppl * TEST_LOT)
    return fitness_from_trades(pnls)


def main():
    if not mt5.initialize():
        print(json.dumps({'error': 'MT5 init failed'})); return
    glyphs = []
    for sym in SYMS:
        m5 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, M5_BARS)
        h1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, H1_BARS)
        m5 = np.array(m5); h1 = np.array(h1)
        data = {'t': m5['time'].astype('int64'), 'o': m5['open'].astype(float),
                'h': m5['high'].astype(float), 'l': m5['low'].astype(float),
                'c': m5['close'].astype(float),
                'atr': wilder_atr(m5['high'].astype(float), m5['low'].astype(float),
                                  m5['close'].astype(float), 14)}
        h1_adx = compute_adx(h1['high'].astype(float), h1['low'].astype(float),
                             h1['close'].astype(float), 14)
        glyphs.append((sym, data, h1_adx, h1['time'].astype('int64')))
    mt5.shutdown()

    rng = np.random.default_rng(20260709)
    results = []
    N = 160
    for _ in range(N):
        p = {'bb_period': int(rng.integers(15, 29)),
             'bb_std': float(rng.choice([1.5, 1.8, 2.0, 2.2, 2.5])),
             'entry_buf': float(rng.choice([0.1, 0.2, 0.3, 0.5, 0.8, 1.0])),
             'sl_buf': float(rng.choice([0.3, 0.5, 0.8, 1.0, 1.5]))}
        stats = {sym: backtest(g, p) for sym, g in zip(SYMS, glyphs)}
        # 约束: 每个品种 pf>=1.0, XAU pf>=1.1, 各>=20笔; 否则淘汰
        ok = all(s['pf'] >= 1.0 and s['trades'] >= 20 for s in stats.values()) \
             and stats['XAUUSD']['pf'] >= 1.1
        if not ok:
            continue
        mean_fit = np.mean([s['fitness'] for s in stats.values()])
        results.append({'params': p, 'mean_fitness': round(mean_fit, 3),
                        'XAU': stats['XAUUSD'], 'EUR': stats['EURUSD'],
                        'GBP': stats['GBPUSD']})
    results.sort(key=lambda r: r['mean_fitness'], reverse=True)
    out = {'generated': dt.datetime.now().isoformat(timespec='seconds'),
           'n_valid': len(results), 'top': results[:10]}
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
