# walk_forward_validator.py — 金策宗师团 · 样本外 Walk-Forward 验证 (B方案治本·真)
"""
回测台(backtest_engine)被证明是"过拟合神谕": 与实盘pf相关系数=-0.178(反相关),
15个实盘>=20样本品种回测全说pf>=1(4~565), 实盘全<1(0~0.39). 全样本内优化=幻觉.

本模块用 WALK-FORWARD (滚动训练/测试) 只报**样本外(未来)** pf, 剔除过拟合:
  - 把 H1 历史切成 K 折(时间顺序, 不洗牌)
  - 第 j 折做测试时, 训练窗 = 之前所有折(只用过去数据)
  - 训练窗网格搜参(adx_min/sl_mult/rr_mult) 最大化训练pf(样本>=MIN)
  - 用最优参在测试折(未来, 未参与调参)评估 -> 得到样本外pnl
  - 聚合所有测试折的样本外pnl -> WFO pf / WFO wr / n
  - 只信 WFO(样本外)pf; 它才是策略真实 edge 的无偏估计.
"""
import time, datetime, json, os
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
import symbol_universe as su
import advanced_strategies as ast
import backtest_engine as be

FOLDS = 5
MIN_TRADES = 20
PF_PASS = 1.0
WFO_TARGET_BARS = 20000

# 网格: 三个策略可读参数
ADX_GRID = [15, 20, 25]
SL_GRID = [1.0, 1.5, 2.0]
RR_GRID = [1.2, 1.5, 2.0]


def _trunc(df, end_time):
    return df[df['time'] <= end_time].reset_index(drop=True).copy()


def _sim_agg(gen, h1, h4, d1, cfg, spread_pts, point, swap_long, swap_short, lot, pip, pip_usd):
    """对给定 (gen, rates, cfg) 跑信号+模拟, 返回 (gw, gl, n, wins)."""
    try:
        sigs = gen(h1, h4, d1, cfg)
    except Exception:
        return 0.0, 0.0, 0, 0
    if not sigs:
        return 0.0, 0.0, 0, 0
    gw = gl = n = wins = 0
    for s in sigs:
        pnl = be.simulate_signal(h1, s, spread_pts, point, swap_long, swap_short, lot, pip, pip_usd)
        if pnl is None:
            continue
        n += 1
        if pnl >= 0:
            wins += 1; gw += pnl
        else:
            gl += -pnl
    return gw, gl, n, wins


def wfv_symbol(symbol, cfg):
    h1 = be.get_rates(symbol, mt5.TIMEFRAME_H1, WFO_TARGET_BARS)
    if h1 is None or len(h1) < FOLDS * 300:
        return None, "H1不足"
    h4 = be.get_rates(symbol, mt5.TIMEFRAME_H4, 6000)
    d1 = be.get_rates(symbol, mt5.TIMEFRAME_D1, 6000)
    if h4 is None or d1 is None:
        return None, "H4/D1缺失"
    info = mt5.symbol_info(symbol)
    spread_pts = info.spread if info and info.spread > 0 else 10
    point = info.point if info else 1e-5
    swap_long = info.swap_long if info else 0
    swap_short = info.swap_short if info else 0
    lot = float(cfg.get('lot', 1.0))
    pip = float(cfg.get('pip', 0.0001))
    pip_usd = float(cfg.get('pip_usd', 10.0))

    N = len(h1)
    edges = int(N / FOLDS)
    folds_idx = [(k * edges, min((k + 1) * edges, N)) for k in range(FOLDS)]

    per_strat = {s: {'gw': 0.0, 'gl': 0.0, 'n': 0, 'wins': 0,
                     'train_best_pf': [], 'oos_pf_folds': []}
                 for s in ast.ALL_STRATEGIES}

    for j in range(1, FOLDS):  # 测试折需有训练折在前
        a, b = folds_idx[j]
        test_h1 = h1.iloc[a:b].reset_index(drop=True)
        test_end = h1['time'].iloc[b - 1]
        train_h1 = h1.iloc[:a].reset_index(drop=True)
        if len(train_h1) < 300 or len(test_h1) < 100:
            continue
        train_end = h1['time'].iloc[a - 1]
        train_h4 = _trunc(h4, train_end); train_d1 = _trunc(d1, train_end)
        test_h4 = _trunc(h4, test_end); test_d1 = _trunc(d1, test_end)

        for name in ast.ALL_STRATEGIES:
            gen = ast.STRATEGY_REGISTRY[name]
            # 训练窗网格搜参
            best = None
            for ax in ADX_GRID:
                for slm in SL_GRID:
                    for rrm in RR_GRID:
                        cc = dict(cfg); cc['adx_min'] = ax; cc['sl_mult'] = slm; cc['rr_mult'] = rrm
                        gw, gl, n, w = _sim_agg(gen, train_h1, train_h4, train_d1, cc,
                                                spread_pts, point, swap_long, swap_short, lot, pip, pip_usd)
                        if n >= MIN_TRADES:
                            pf = gw / gl if gl > 1e-9 else (999.0 if gw > 0 else 0.0)
                            if best is None or pf > best[0]:
                                best = (pf, cc)
            if best is None:
                continue
            per_strat[name]['train_best_pf'].append(round(best[0], 2))
            # 测试折(样本外)评估最优参
            cc = best[1]
            gw, gl, n, w = _sim_agg(gen, test_h1, test_h4, test_d1, cc,
                                    spread_pts, point, swap_long, swap_short, lot, pip, pip_usd)
            if n > 0:
                per_strat[name]['gw'] += gw; per_strat[name]['gl'] += gl
                per_strat[name]['n'] += n; per_strat[name]['wins'] += w
                pf = gw / gl if gl > 1e-9 else (999.0 if gw > 0 else 0.0)
                per_strat[name]['oos_pf_folds'].append(round(pf, 2))

    # 汇总 WFO(样本外)
    summary = {}
    for name, d in per_strat.items():
        if d['n'] >= MIN_TRADES:
            pf = d['gw'] / d['gl'] if d['gl'] > 1e-9 else (999.0 if d['gw'] > 0 else 0.0)
            summary[name] = {'n': d['n'], 'wr': round(d['wins'] / d['n'], 3),
                             'wfo_pf': round(pf, 3),
                             'train_pf_med': round(float(np.median(d['train_best_pf'])), 2) if d['train_best_pf'] else 0.0,
                             'oos_folds': len(d['oos_pf_folds'])}
    # 该品种最佳策略(按 WFO pf)
    best = None
    for name, d in summary.items():
        if best is None or d['wfo_pf'] > best[1]['wfo_pf']:
            best = (name, d)
    return {'summary': summary, 'best': best, 'h1': N}, f"H1={N}"


def run_wfv(symbols=None, out_json="data/wfv_edge.json"):
    if not mt5.initialize():
        raise RuntimeError("MT5 init 失败")
    if symbols is None:
        symbols = [k for k, v in su.UNIVERSE.items() if v.get('tradable', True)]
    out_rows = {}
    cands = []
    t0 = time.time()
    for idx, sym in enumerate(symbols):
        cfg = su.UNIVERSE.get(sym, {})
        try:
            res, note = wfv_symbol(sym, cfg)
        except Exception as e:
            res, note = None, "EXC:" + str(e)[:60]
        if res is None:
            out_rows[sym] = {'note': note}
            continue
        out_rows[sym] = {'note': note, **res}
        if res.get('best'):
            nm, d = res['best']
            cands.append((sym, nm, d['wfo_pf'], d['n'], d['wr'], d['train_pf_med']))
        if (idx + 1) % 5 == 0:
            print(f"  [{idx+1}/{len(symbols)}] {sym} 最佳WFO pf={res['best'][1]['wfo_pf'] if res.get('best') else 0}")
    cands.sort(key=lambda x: -x[2])
    out = {'generated': datetime.datetime.now().isoformat(), 'method': 'walk_forward_oos',
           'folds': FOLDS, 'min_trades': MIN_TRADES, 'pf_pass': PF_PASS,
           'symbols_tested': len(symbols), 'elapsed_s': round(time.time() - t0, 1),
           'per_symbol': out_rows}
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, 'w') as f:
        json.dump(out, f, indent=2, default=str)
    return out, cands


if __name__ == "__main__":
    import sys
    syms = sys.argv[1].split(',') if len(sys.argv) > 1 and sys.argv[1] else None
    out, cands = run_wfv(syms)
    print("=== WFO 样本外 正 edge 候选 (前25) ===")
    for c in cands[:25]:
        print(f"  {c[0]:10} {c[1]:6} WFO_pf={c[2]:.2f} n={c[3]:4} wr={c[4]:.2f} 训练pf中位={c[5]:.1f}")
    print(f"WFO正 edge 候选总数: {len(cands)} / 测试 {out['symbols_tested']} 品种")
    if not cands:
        print(">> 无任何样本外正 edge: 7策略在当前市况全军覆没, 需新策略研究.")
