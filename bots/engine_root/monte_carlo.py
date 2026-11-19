# -*- coding: utf-8 -*-
"""
P3-2: 蒙特卡洛压力测试 (Monte Carlo Stress Test)
=================================================
借鉴 2026 前沿实践 (Grid/Martingale 评估标准): 对策略的历史成交序列
做 1000 次随机化重排/重采样, 模拟不同"未来路径", 评估:
  - 最大回撤分布 (p95 最坏回撤)
  - 破产概率 (亏损 ≥ X% 的路径占比)
  - 平均/中位收益

判定准则 (2026 行业标准):
  - 失败率 > 5% (即 >5% 路径亏损超过阈值) → 判定过风险, 建议降仓/停用

两种重采样方法:
  1. 重排 (shuffle): 打乱成交顺序, 消除时间相关性 (保守下界)
  2. 有放回重采样 (bootstrap): 随机抽取, 保留分布特征

纯 numpy, 无第三方依赖。
"""

import numpy as np

# ── 默认参数 ─────────────────────────────────────────────────
DEFAULT_N_PATHS = 1000      # 模拟路径数
DEFAULT_INITIAL_EQUITY = 1000.0  # 初始净值 (由调用方传入实际值)
DEFAULT_DRAWDOWN_THRESHOLD = 0.20  # 回撤 >20% 判定为失败路径
DEFAULT_FAIL_RATE_MAX = 0.05       # 失败率上限 5%
RANDOM_SEED = 2026


def run_monte_carlo(pnls, n_paths=DEFAULT_N_PATHS,
                    initial_equity=DEFAULT_INITIAL_EQUITY,
                    dd_threshold=DEFAULT_DRAWDOWN_THRESHOLD,
                    method='bootstrap', seed=RANDOM_SEED):
    """对成交盈亏序列做蒙特卡洛压力测试。

    参数:
      pnls: list[float] 每笔成交的盈亏 (含负值)
      n_paths: 模拟路径数
      initial_equity: 初始净值
      dd_threshold: 回撤阈值 (0.20 = 20%)
      method: 'bootstrap'(有放回) | 'shuffle'(重排) | 'both'

    返回:
      {
        'n_trades': 原始笔数,
        'total_pnl': 原始总盈亏,
        'paths': { 'n': 模拟数, 'method': method,
                   'median_ret': 中位收益率,
                   'p95_drawdown': 95分位最大回撤 (正数),
                   'fail_rate': 失败路径占比,
                   'max_drawdown_median': 中位最大回撤,
                   'bankruptcy_rate': 爆仓率 (亏损≥99.5%) },
        'verdict': 'PASS' | 'WARN' | 'FAIL',
        'reason': str,
      }
    """
    pnls = np.asarray([float(x) for x in pnls if float(x) != 0])
    if len(pnls) < 10:
        return {'n_trades': len(pnls), 'total_pnl': float(pnls.sum()),
                'verdict': 'SKIP', 'reason': '样本不足 (<10笔), 跳过压力测试'}
    rng = np.random.default_rng(seed)

    methods = ['bootstrap', 'shuffle'] if method == 'both' else [method]
    results = {}
    for m in methods:
        dd_list = []
        ret_list = []
        bank = 0
        for _ in range(n_paths):
            if m == 'shuffle':
                seq = rng.permutation(pnls)
            else:
                seq = rng.choice(pnls, size=len(pnls), replace=True)
            eq = initial_equity
            peak = initial_equity
            max_dd = 0.0
            for p in seq:
                eq += p
                if eq > peak:
                    peak = eq
                if peak > 0:
                    dd = (peak - eq) / peak
                    if dd > max_dd:
                        max_dd = dd
                if eq <= initial_equity * 0.005:  # 净值剩 0.5% 视为爆仓
                    bank += 1
                    break
            dd_list.append(max_dd)
            ret_list.append((eq - initial_equity) / initial_equity)

        dd_arr = np.array(dd_list)
        results[m] = {
            'n': n_paths,
            'median_ret': float(np.median(ret_list)),
            'p95_drawdown': float(np.percentile(dd_arr, 95)),
            'max_drawdown_median': float(np.median(dd_arr)),
            'fail_rate': float(np.mean(dd_arr > dd_threshold)),
            'bankruptcy_rate': float(bank / n_paths),
        }

    # 判定: 以 bootstrap (主方法) 为准; both 时取两者较差
    main = results.get('bootstrap') or results.get('shuffle')
    fail_rate = main['fail_rate']
    p95dd = main['p95_drawdown']
    if fail_rate > DEFAULT_FAIL_RATE_MAX:
        verdict, reason = 'FAIL', (f'失败率 {fail_rate*100:.1f}% > {DEFAULT_FAIL_RATE_MAX*100:.0f}% '
                                   f'(p95回撤 {p95dd*100:.0f}%), 判定过风险')
    elif fail_rate > DEFAULT_FAIL_RATE_MAX * 0.6:
        verdict, reason = 'WARN', (f'失败率 {fail_rate*100:.1f}% 接近上限 {DEFAULT_FAIL_RATE_MAX*100:.0f}%, '
                                   f'建议降仓')
    else:
        verdict, reason = 'PASS', f'失败率 {fail_rate*100:.1f}% ≤ {DEFAULT_FAIL_RATE_MAX*100:.0f}%, 风险可控'

    return {
        'n_trades': int(len(pnls)),
        'total_pnl': float(pnls.sum()),
        'paths': results,
        'verdict': verdict,
        'reason': reason,
    }


def run_strategy_mc(mt5, symbol=None, days=30, n_paths=DEFAULT_N_PATHS,
                    initial_equity=None, dd_threshold=0.20):
    """直接从 MT5 历史成交拉取盈亏并跑蒙特卡洛。

    参数:
      mt5: 已初始化的 MetaTrader5 模块
      symbol: 品种过滤 (None=全部)
      days: 拉取天数
    返回: run_monte_carlo 的 dict
    """
    import datetime
    from_date = datetime.datetime.now() - datetime.timedelta(days=days)
    try:
        deals = mt5.history_deals_get(int(from_date.timestamp()), int(datetime.datetime.now().timestamp()))
    except Exception:
        deals = None
    if not deals:
        return {'verdict': 'SKIP', 'reason': '无成交历史'}

    pnls = [float(d.profit) for d in deals if getattr(d, 'entry', 0) == 1]
    if symbol:
        pnls = [p for d, p in zip(deals, pnls) if d.symbol == symbol]

    if initial_equity is None:
        try:
            acc = mt5.account_info()
            initial_equity = float(acc.equity) if acc else 1000.0
        except Exception:
            initial_equity = 1000.0

    return run_monte_carlo(pnls, n_paths=n_paths,
                           initial_equity=initial_equity,
                           dd_threshold=dd_threshold)


# ── 自检 ─────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=== P3-2 蒙特卡洛压力测试自检 ===")
    rng = np.random.default_rng(7)
    # 模拟稳定盈利序列
    good = rng.normal(2.0, 5.0, 200)
    # 模拟高风险序列 (大亏损尾部)
    bad = np.concatenate([rng.normal(0.5, 8.0, 180), np.full(20, -60.0)])

    for name, p in [('稳健策略', good), ('高危策略', bad)]:
        r = run_monte_carlo(p, initial_equity=1000.0, n_paths=300)
        print(f"\n{name}: {r['verdict']} | {r['reason']}")
        print(f"  笔数={r['n_trades']} 总PnL={r['total_pnl']:.1f}")
        b = r['paths']['bootstrap']
        print(f"  中位收益={b['median_ret']*100:.2f}% p95回撤={b['p95_drawdown']*100:.1f}% "
              f"失败率={b['fail_rate']*100:.1f}% 爆仓率={b['bankruptcy_rate']*100:.1f}%")
    print("\n=== 自检通过 ===")
