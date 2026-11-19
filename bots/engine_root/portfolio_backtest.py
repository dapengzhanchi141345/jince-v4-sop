# -*- coding: utf-8 -*-
"""
portfolio_backtest.py — 组合级真实账户回测

解决单品种回测的致命失真:
  单品种回测中每个品种都独立从 $961.54 起跑、各吃 1% 风险。
  但真实交易是 N 个品种共用同一个账户 -> 风险叠加、资金竞争、回撤共振。

本脚本用「单一共享账户」重放全部品种:
  - 共享 equity, 每笔按当前 equity × risk_pct 定手 (复利)
  - 全局约束: 同时持仓数上限 / 总风险敞口上限 / 每品种最多 1 仓
  - 信号冲突时按信号质量(R:R)优先
  - 输出真实权益曲线 / 总收益 / 最大回撤 / 夏普 / 月度分布

用法:
  python portfolio_backtest.py                 # 用 KEEP 品种
  python portfolio_backtest.py KEEP,COLLECT    # 用 KEEP+COLLECT
  python portfolio_backtest.py KEEP 5 1.0 6.0  # 决策集 最大持仓 单笔风险% 总风险上限%
"""
import os, sys, json
from datetime import timedelta
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import symbol_universe as su
import advanced_strategies as ast
import universe_backtest as ub

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
COMM = ub.COMMISSION_PER_LOT


def build_events(decisions=("KEEP",), verbose=True):
    """为每个入选品种生成 (最佳策略) 信号 + H1 行情索引。"""
    part = json.load(open(os.path.join(DATA_DIR, "_ub_partial.json"), "r", encoding="utf-8"))
    picks = []
    for sym, r in part.items():
        if r.get("decision") in decisions and r.get("status") == "OK" and r.get("best"):
            picks.append((sym, r["best"], r.get("stats", {})))
    picks.sort(key=lambda x: -(x[2].get("pnl") or 0))
    if verbose:
        print(f"  入选品种: {len(picks)} 个 -> {', '.join(f'{s}({b})' for s, b, _ in picks[:14])}"
              + (" ..." if len(picks) > 14 else ""))

    bars = {}      # sym -> DataFrame(h1)
    signals = []   # 全局信号列表
    for sym, best, _ in picks:
        cfg = su.UNIVERSE.get(sym)
        d = ub.load_local(sym)
        if cfg is None or d is None:
            continue
        h1, h4, d1 = d
        try:
            sigs = ast.STRATEGY_REGISTRY[best](h1, h4, d1, cfg)
        except Exception as e:
            if verbose:
                print(f"    {sym}: 信号生成失败 {e}")
            continue
        t = pd.to_datetime(h1['time'])
        bars[sym] = {
            'time': t.values, 'high': h1['high'].values.astype(float),
            'low': h1['low'].values.astype(float), 'close': h1['close'].values.astype(float),
            'cfg': cfg, 'strat': best,
        }
        for s in sigs:
            b = s['bar']
            if b >= len(t):
                continue
            rr = abs(s['tp'] - s['entry']) / max(abs(s['entry'] - s['sl']), 1e-9)
            signals.append({'ts': t.values[b], 'sym': sym, 'bar': b, 'side': s['side'],
                            'entry': s['entry'], 'sl': s['sl'], 'tp': s['tp'],
                            'strat': best, 'rr': rr, 'regime': s.get('regime', '')})
    signals.sort(key=lambda x: (x['ts'], -x['rr']))
    if verbose:
        print(f"  行情品种: {len(bars)} | 候选信号总数: {len(signals):,}")
    return bars, signals


def run_portfolio(decisions=("KEEP",), max_pos=5, risk_pct=1.0, max_total_risk=6.0,
                  start_equity=None, verbose=True):
    su.calibrate_forex_pip_usd(DATA_DIR)
    su.apply_account_specs(DATA_DIR, verbose=verbose)
    eq0 = float(start_equity or su.ACCOUNT.get('balance') or 961.54)

    print("=" * 88)
    print(f"  组合级真实账户回测 | 账户 {su.ACCOUNT.get('login')} @ {su.ACCOUNT.get('server')}")
    print(f"  起始净值 ${eq0:.2f} | 单笔风险 {risk_pct}% | 总风险上限 {max_total_risk}% | "
          f"最大同时持仓 {max_pos} | 决策集 {'+'.join(decisions)}")
    print("=" * 88)

    bars, signals = build_events(decisions, verbose)
    if not signals:
        print("  无信号, 退出")
        return None

    # 全局时间轴: 所有品种 H1 时间戳并集
    all_ts = np.unique(np.concatenate([b['time'] for b in bars.values()]))
    all_ts.sort()
    # 每品种 时间戳 -> bar index 映射
    tidx = {s: {t: i for i, t in enumerate(b['time'])} for s, b in bars.items()}

    sig_by_ts = {}
    for s in signals:
        sig_by_ts.setdefault(s['ts'], []).append(s)

    equity = eq0
    peak = eq0
    max_dd = 0.0
    positions = {}          # sym -> pos dict
    trades = []
    curve = []              # (ts, equity)
    skipped_cap = 0         # 因组合风险上限被拒
    skipped_risk = 0        # 因最小手风险超限被拒
    cool = {}               # sym -> cooldown until
    consec_loss = {}

    def open_risk():
        return sum(p['risk'] for p in positions.values())

    for ts in all_ts:
        tsp = pd.Timestamp(ts)
        # ── 1. 先结算已有持仓 ──
        for sym in list(positions.keys()):
            b = bars[sym]
            i = tidx[sym].get(ts)
            if i is None:
                continue
            p = positions[sym]
            hit_sl = (p['side'] == 1 and b['low'][i] <= p['sl']) or (p['side'] == -1 and b['high'][i] >= p['sl'])
            hit_tp = (p['side'] == 1 and b['high'][i] >= p['tp']) or (p['side'] == -1 and b['low'][i] <= p['tp'])
            if not (hit_sl or hit_tp):
                continue
            ep = p['sl'] if hit_sl else p['tp']
            cfg = b['cfg']
            pip = cfg['pip']
            spread_pts = cfg.get('spread_price', 0.0001) / pip
            raw = (ep - p['entry']) / pip * p['side'] - spread_pts
            profit = raw * cfg['pip_usd'] * p['lot'] - COMM * p['lot'] * 2.0
            equity += profit
            trades.append({'ts': str(tsp), 'sym': sym, 'strat': p['strat'], 'side': p['side'],
                           'lot': p['lot'], 'risk': p['risk'], 'profit': round(profit, 2),
                           'result': 'WIN' if profit > 0 else 'LOSS', 'equity': round(equity, 2),
                           'R': round(profit / p['risk'], 2) if p['risk'] else 0})
            if profit < 0:
                consec_loss[sym] = consec_loss.get(sym, 0) + 1
                n = consec_loss[sym]
                cool[sym] = tsp + (timedelta(hours=24) if n >= 5 else
                                   timedelta(hours=4) if n >= 3 else timedelta(minutes=30))
            else:
                consec_loss[sym] = 0
            del positions[sym]
            peak = max(peak, equity)
            if peak > 0:
                max_dd = max(max_dd, (peak - equity) / peak)

        # ── 2. 再处理新信号 ──
        for sg in sig_by_ts.get(ts, []):
            sym = sg['sym']
            if equity <= 0:
                break
            if sym in positions:
                continue
            if len(positions) >= max_pos:
                skipped_cap += 1
                continue
            if sym in cool and tsp < cool[sym]:
                continue
            cfg = bars[sym]['cfg']
            ss, se = cfg['session']
            if not (ss <= tsp.hour < se):
                continue
            sl_pips = abs(sg['entry'] - sg['sl']) / cfg['pip']
            lot, risk, ok = su.risk_lot(cfg, sl_pips, equity, risk_pct)
            if not ok or lot <= 0:
                skipped_risk += 1
                continue
            if open_risk() + risk > equity * max_total_risk / 100.0:
                skipped_cap += 1
                continue
            positions[sym] = {'side': sg['side'], 'entry': sg['entry'], 'sl': sg['sl'],
                              'tp': sg['tp'], 'lot': lot, 'risk': risk, 'strat': sg['strat'],
                              'ts': tsp}
        curve.append((tsp, equity))

    # ── 统计 ──
    closed = trades
    if not closed:
        print("  无成交")
        return None
    wins = [t for t in closed if t['profit'] > 0]
    losses = [t for t in closed if t['profit'] < 0]
    gp = sum(t['profit'] for t in wins)
    gl = abs(sum(t['profit'] for t in losses))
    pf = gp / gl if gl > 0 else 99.0
    total = equity - eq0
    cdf = pd.DataFrame(curve, columns=['ts', 'eq']).set_index('ts')
    daily = cdf['eq'].resample('D').last().dropna()
    rets = daily.pct_change().dropna()
    sharpe = (rets.mean() / rets.std() * np.sqrt(252)) if len(rets) > 2 and rets.std() > 0 else 0
    days = (cdf.index[-1] - cdf.index[0]).days or 1
    cagr = ((equity / eq0) ** (365.0 / days) - 1) * 100 if equity > 0 else -100

    print(f"\n{'='*88}")
    print(f"  ★ 组合真实业绩")
    print(f"{'='*88}")
    print(f"  期间          : {cdf.index[0].date()} -> {cdf.index[-1].date()}  ({days} 天 / {days/365:.1f} 年)")
    print(f"  起始净值      : ${eq0:,.2f}")
    print(f"  期末净值      : ${equity:,.2f}")
    print(f"  净盈亏        : ${total:,.2f}   ({total/eq0*100:+.1f}%)")
    print(f"  年化 CAGR     : {cagr:+.1f}%")
    print(f"  最大回撤      : {max_dd*100:.1f}%")
    print(f"  夏普比率      : {sharpe:.2f}")
    print(f"  总成交        : {len(closed):,} 笔  (胜 {len(wins)} / 负 {len(losses)})")
    print(f"  胜率          : {len(wins)/len(closed)*100:.1f}%")
    print(f"  盈利因子 PF   : {pf:.2f}")
    print(f"  平均 R 倍数   : {np.mean([t['R'] for t in closed]):.3f}")
    print(f"  期望值/笔     : ${total/len(closed):.2f}")
    print(f"  被拒信号      : 组合上限 {skipped_cap:,} | 风险超限 {skipped_risk:,}")

    # 按品种归因
    print(f"\n  ── 品种盈亏归因 (TOP 15 / BOTTOM 5) ──")
    bysym = {}
    for t in closed:
        d = bysym.setdefault(t['sym'], {'pnl': 0, 'n': 0, 'w': 0, 'strat': t['strat']})
        d['pnl'] += t['profit']; d['n'] += 1; d['w'] += 1 if t['profit'] > 0 else 0
    sl = sorted(bysym.items(), key=lambda x: -x[1]['pnl'])
    for s, v in sl[:15]:
        print(f"    {s:<9} {v['strat']:<4} ${v['pnl']:>9.2f}  {v['n']:>4}笔  胜率{v['w']/v['n']*100:>5.1f}%")
    if len(sl) > 20:
        print("    ...")
        for s, v in sl[-5:]:
            print(f"    {s:<9} {v['strat']:<4} ${v['pnl']:>9.2f}  {v['n']:>4}笔  胜率{v['w']/v['n']*100:>5.1f}%")

    # 按策略归因
    print(f"\n  ── 策略盈亏归因 ──")
    byst = {}
    for t in closed:
        d = byst.setdefault(t['strat'], {'pnl': 0, 'n': 0, 'w': 0})
        d['pnl'] += t['profit']; d['n'] += 1; d['w'] += 1 if t['profit'] > 0 else 0
    for s, v in sorted(byst.items(), key=lambda x: -x[1]['pnl']):
        print(f"    {ub.STRATEGY_NAMES.get(s,s):<14} ${v['pnl']:>9.2f}  {v['n']:>5}笔  胜率{v['w']/v['n']*100:>5.1f}%")

    # 年度
    print(f"\n  ── 年度收益 ──")
    yr = cdf['eq'].resample('YE').last().dropna()
    prev = eq0
    for ts_, v in yr.items():
        print(f"    {ts_.year}: ${prev:>9,.2f} -> ${v:>9,.2f}   {(v/prev-1)*100:>+7.1f}%")
        prev = v

    out = {
        'account': su.ACCOUNT, 'params': {'decisions': list(decisions), 'max_pos': max_pos,
                                          'risk_pct': risk_pct, 'max_total_risk': max_total_risk},
        'start_equity': eq0, 'final_equity': round(equity, 2), 'net': round(total, 2),
        'ret_pct': round(total / eq0 * 100, 2), 'cagr': round(cagr, 2),
        'max_dd': round(max_dd * 100, 2), 'sharpe': round(float(sharpe), 2),
        'trades': len(closed), 'wr': round(len(wins) / len(closed) * 100, 1), 'pf': round(pf, 2),
        'by_symbol': {s: {'pnl': round(v['pnl'], 2), 'n': v['n'], 'strat': v['strat']} for s, v in bysym.items()},
        'by_strategy': {s: {'pnl': round(v['pnl'], 2), 'n': v['n']} for s, v in byst.items()},
        'days': days,
    }
    tag = "_".join(decisions)
    with open(os.path.join(DATA_DIR, f"portfolio_result_{tag}.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    pd.DataFrame(closed).to_csv(os.path.join(DATA_DIR, f"portfolio_trades_{tag}.csv"),
                                index=False, encoding="utf-8-sig")
    cdf.to_csv(os.path.join(DATA_DIR, f"portfolio_equity_{tag}.csv"), encoding="utf-8-sig")
    print(f"\n  saved -> data/portfolio_result_{tag}.json / portfolio_trades_{tag}.csv / portfolio_equity_{tag}.csv")
    return out


if __name__ == "__main__":
    dec = tuple((sys.argv[1] if len(sys.argv) > 1 else "KEEP").split(","))
    mp = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    rp = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
    mt = float(sys.argv[4]) if len(sys.argv) > 4 else 6.0
    run_portfolio(dec, mp, rp, mt)
