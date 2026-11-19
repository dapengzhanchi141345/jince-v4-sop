# -*- coding: utf-8 -*-
"""
portfolio_sweep.py — 组合参数扫描, 找风险调整后最优配置

不只看收益, 用 Calmar (CAGR/最大回撤) 与 Sharpe 综合评判。
"""
import os, sys, json, io, contextlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portfolio_backtest as pb

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

GRID = [
    # (决策集, 最大持仓, 单笔风险%, 总风险上限%)
    (("KEEP",), 3, 0.5, 2.0),
    (("KEEP",), 3, 0.5, 3.0),
    (("KEEP",), 3, 1.0, 3.0),
    (("KEEP",), 5, 0.5, 3.0),
    (("KEEP",), 5, 0.5, 5.0),
    (("KEEP",), 5, 1.0, 6.0),
    (("KEEP",), 8, 0.5, 5.0),
    (("KEEP",), 8, 1.0, 8.0),
    (("KEEP", "COLLECT"), 5, 0.5, 5.0),
    (("KEEP", "COLLECT"), 5, 1.0, 6.0),
]

rows = []
for dec, mp, rp, mt in GRID:
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            r = pb.run_portfolio(dec, mp, rp, mt, verbose=False)
    except Exception as e:
        print(f"FAIL {dec} mp={mp} rp={rp} mt={mt}: {e}")
        continue
    if not r:
        continue
    calmar = (r['cagr'] / r['max_dd']) if r['max_dd'] > 0 else 0
    rows.append({**r['params'], 'final': r['final_equity'], 'ret': r['ret_pct'],
                 'cagr': r['cagr'], 'dd': r['max_dd'], 'sharpe': r['sharpe'],
                 'calmar': round(calmar, 3), 'pf': r['pf'], 'wr': r['wr'], 'n': r['trades']})
    print(f"  done: {'+'.join(dec):<14} pos={mp} risk={rp}% cap={mt}% -> "
          f"${r['final_equity']:>9,.0f} CAGR{r['cagr']:>7.1f}% DD{r['max_dd']:>5.1f}% "
          f"Sharpe{r['sharpe']:>5.2f} Calmar{calmar:>5.2f} PF{r['pf']:>5.2f}")

rows.sort(key=lambda x: -x['calmar'])
print("\n" + "=" * 108)
print("  ★ 参数扫描结果 (按 Calmar = CAGR/最大回撤 排序, 风险调整后最优在最上)")
print("=" * 108)
h = (f"{'决策集':<16} {'持仓':>4} {'单笔%':>6} {'总险%':>6} {'期末$':>10} {'总收益%':>9} "
     f"{'CAGR%':>8} {'回撤%':>7} {'夏普':>6} {'Calmar':>7} {'PF':>6} {'胜率':>6} {'笔数':>6}")
print(h)
print("-" * 108)
for r in rows:
    print(f"{'+'.join(r['decisions']):<16} {r['max_pos']:>4} {r['risk_pct']:>6} {r['max_total_risk']:>6} "
          f"{r['final']:>10,.0f} {r['ret']:>9.1f} {r['cagr']:>8.1f} {r['dd']:>7.1f} "
          f"{r['sharpe']:>6.2f} {r['calmar']:>7.2f} {r['pf']:>6.2f} {r['wr']:>6.1f} {r['n']:>6,}")

with open(os.path.join(DATA_DIR, "portfolio_sweep.json"), "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=1)
print(f"\n  saved -> data/portfolio_sweep.json")
