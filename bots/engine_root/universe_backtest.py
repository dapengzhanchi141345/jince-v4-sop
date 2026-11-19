# universe_backtest.py — 金策宗师团 · 全品种回测 + 多策略择优 + 盈利排名
"""
遍历 symbol_universe.UNIVERSE 全部品种, 对每个品种并行跑 5 个先进策略
(SDP / ICT / VP / DIV / MR), 用**合约正确 PnL** 计算盈亏, 按 PF 择优选出该品种
"最适合的策略", 再跨品种按净盈利排名, 给出 KEEP / COLLECT / CUT 筛选决策。

数据来源优先级:
  1. 本地 CSV (data/<SYM>_H1/H4/D1.csv) → 离线回测 (主路径, 无需 MT5)
  2. 若缺失且 MT5 可用 → 自动下载 (需本机运行 MT5 终端 + 已装 MetaTrader5)
  3. 都失败 → 标记 NO_DATA, 留待直播"收集模式"积累实盘数据

输出:
  data/universe_backtest_report.csv   机器可读排名 (含最优策略)
  data/universe_backtest_report.json  完整指标 (含每策略分项)
  data/universe_backtest_report.md    人类可读筛选报告
"""
import sys, os, json, warnings
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')
BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
os.makedirs(DATA_DIR, exist_ok=True)
sys.path.insert(0, BASE)

import symbol_universe as su
import advanced_strategies as ast

COMMISSION_PER_LOT = 3.0   # 单边 $/手, 来回 ×2 (与 continuous_evolution_v2 一致)
TF = {'M15': 15, 'H1': 16385, 'H4': 16388, 'D1': 16408}
ALL_STRATEGIES = ast.ALL_STRATEGIES
STRATEGY_NAMES = {"SDP": "供需区(SDP)", "ICT": "智能资金(ICT/SMC)", "VP": "成交量分布(VP)",
                  "DIV": "背离(DIV)", "MR": "均值回归(MR)"}


# ════════════════════════════════════════════════════════════════
# 共享执行引擎: 风控 / 仓位 / 点差 / 连亏冷却 (所有策略共用)
# ════════════════════════════════════════════════════════════════
def execute_signals(signals: List[Dict], cfg: Dict, h1, sym: str,
                    start_equity: float = None, risk_pct: float = None) -> Tuple[List, float]:
    """把候选信号列表按统一风控执行成成交序列。

    风控: 同时仅 1 仓; 当日上限 max_daily; 连亏 3/5 次冷却 30min/4h/24h;
          交易时段 session 过滤; 合约正确 PnL (点差 + 佣金)。

    仓位模式:
      account_mode (start_equity 给定): 手数 = 当前净值 × risk_pct% / (SL点数 × 每pip美元),
        受券商真实 vol_min/vol_step 约束; 最小手风险仍超 2× 目标 -> 跳过该笔(真实账户开不起)。
      legacy: 固定 cfg['lot'], 起始 $10,000。
    """
    hc = h1['close'].values.astype(float); hh = h1['high'].values.astype(float); hl = h1['low'].values.astype(float)
    ht = h1['time'].values
    sig_sorted = sorted(signals, key=lambda x: x['bar'])
    pip = cfg['pip']; pip_usd = cfg['pip_usd']
    spread_price = cfg.get('spread_price', 0.0001); ss, se = cfg['session']
    spread_pts = spread_price / pip

    acct = start_equity is not None and start_equity > 0
    init_bal = float(start_equity) if acct else 10000.0
    rpct = float(risk_pct) if risk_pct else 1.0
    fixed_lots = cfg.get('lot', 0.1)

    def pnl_net(ep, entry, side, lots):
        raw = (ep - entry) / pip * side
        net = raw - spread_pts
        return net * pip_usd * lots - COMMISSION_PER_LOT * lots * 2.0

    trades: List[Dict] = []; bal = init_bal; pos = None
    skipped_risk = 0          # 因最小手风险超限被放弃的信号数
    daily_t = 0; last_d = None; cool_until = None; consec_l = 0; idx = 0
    for i in range(len(h1)):
        while idx < len(sig_sorted) and sig_sorted[idx]['bar'] < i:
            idx += 1          # 丢弃已过期信号
        bt = pd.Timestamp(ht[i])
        if pos:
            hit_sl = (pos['side'] == 1 and hl[i] <= pos['sl']) or (pos['side'] == -1 and hh[i] >= pos['sl'])
            hit_tp = (pos['side'] == 1 and hh[i] >= pos['tp']) or (pos['side'] == -1 and hl[i] <= pos['tp'])
            if hit_sl or hit_tp:
                ep = pos['sl'] if hit_sl else pos['tp']
                profit = pnl_net(ep, pos['entry'], pos['side'], pos['lot'])
                trades.append({'symbol': sym, 'profit': round(profit, 2),
                               'result': 'WIN' if profit > 0 else 'LOSS',
                               'holding_bars': i - pos['signal_bar'], 'entry': round(pos['entry'], 5),
                               'exit': round(ep, 5), 'sl': round(pos['sl'], 5), 'tp': round(pos['tp'], 5),
                               'regime': pos['regime'], 'lot': pos['lot'], 'strat': pos['strat'],
                               'risk': pos.get('risk', 0.0), 'equity': round(bal, 2)})
                bal += profit
                if profit < 0:
                    consec_l += 1
                    if consec_l >= 5:
                        cool_until = bt + timedelta(hours=24)
                    elif consec_l >= 3:
                        cool_until = bt + timedelta(hours=4)
                    else:
                        cool_until = bt + timedelta(minutes=30)
                else:
                    consec_l = 0
                pos = None
        if pos is None:
            if last_d != bt.date():
                last_d = bt.date(); daily_t = 0
            if not (cool_until and bt < cool_until):
                while idx < len(sig_sorted) and sig_sorted[idx]['bar'] == i:
                    sg = sig_sorted[idx]; idx += 1
                    if daily_t >= cfg.get('max_daily', 8):
                        continue
                    if not (ss <= bt.hour < se):
                        continue
                    # ── 仓位: 账户资金驱动 (真实) 或 固定手 (legacy) ──
                    if acct:
                        sl_pips = abs(sg['entry'] - sg['sl']) / pip
                        lot_i, risk_i, ok = su.risk_lot(cfg, sl_pips, bal, rpct)
                        if not ok or lot_i <= 0 or bal <= 0:
                            skipped_risk += 1
                            continue          # 真实账户开不起这一笔
                    else:
                        lot_i, risk_i = sg.get('lot', fixed_lots), 0.0
                    pos = {'side': sg['side'], 'entry': sg['entry'], 'sl': sg['sl'], 'tp': sg['tp'],
                           'signal_bar': i, 'regime': sg.get('regime', ''),
                           'lot': lot_i, 'risk': round(risk_i, 2), 'strat': sg.get('strat', '?')}
                    daily_t += 1
                    break
    if pos:
        ep = hc[-1]; profit = pnl_net(ep, pos['entry'], pos['side'], pos['lot'])
        trades.append({'symbol': sym, 'profit': round(profit, 2),
                       'result': 'WIN' if profit > 0 else 'LOSS', 'strat': pos['strat'],
                       'lot': pos['lot'], 'risk': pos.get('risk', 0.0)})
        bal += profit
    if trades:
        trades[0]['_skipped_risk'] = skipped_risk
    return trades, bal


# ════════════════════════════════════════════════════════════════
# 统计 + 最大回撤
# ════════════════════════════════════════════════════════════════
def calc_stats(trades, bal, initial=10000):
    closed = [t for t in trades if t.get('result') in ('WIN', 'LOSS')]
    if not closed:
        return {'trades': 0, 'error': 'no trades'}
    wins = [t for t in closed if t['profit'] > 0]
    losses = [t for t in closed if t['profit'] < 0]
    total = sum(t['profit'] for t in closed)
    wr = len(wins)/len(closed)*100
    avg_w = np.mean([t['profit'] for t in wins]) if wins else 0
    avg_l = abs(np.mean([t['profit'] for t in losses])) if losses else 0
    pf = (sum(t['profit'] for t in wins) / max(abs(sum(t['profit'] for t in losses)), 1)
          if wins and losses else (float('inf') if wins else 0))
    pf = min(pf, 99.0) if pf != float('inf') else 99.0
    b = initial; peak = initial; max_dd = 0
    for t in closed:
        b += t['profit']
        if b > peak:
            peak = b
        max_dd = max(max_dd, (peak - b)/peak)
    expectancy = total/len(closed)
    holds = [t.get('holding_bars', 0) for t in closed if 'holding_bars' in t]
    avg_hold = (sum(holds)/len(holds)) if holds else 0
    return {'trades': len(closed), 'wins': len(wins), 'losses': len(losses),
            'wr': round(wr, 1), 'pnl': round(total, 2), 'avg_w': round(avg_w, 2),
            'avg_l': round(avg_l, 2), 'pf': round(pf, 2), 'final': round(bal, 2),
            'ret': round(total/initial*100, 2), 'max_dd': round(max_dd*100, 2),
            'expectancy': round(expectancy, 2), 'avg_hold': round(avg_hold, 1)}


# ════════════════════════════════════════════════════════════════
# 单品种多策略择优
# ════════════════════════════════════════════════════════════════
def run_backtest(sym: str, cfg: Dict, h1, h4, d1,
                 strategies: List[str] = ALL_STRATEGIES,
                 min_trades_for_best: int = 10,
                 start_equity: float = None, risk_pct: float = None) -> Dict:
    """对单品种跑全部策略, 按 PF 择优。返回 {'best','stats','all'}。

    start_equity 给定时进入"真实账户模式": 起始净值=账户余额, 按 risk_pct% 复利定手。
    """
    initial = float(start_equity) if (start_equity and start_equity > 0) else 10000.0
    all_stats: Dict[str, Dict] = {}
    for name in strategies:
        gen = ast.STRATEGY_REGISTRY[name]
        try:
            sigs = gen(h1, h4, d1, cfg)
        except Exception as e:
            all_stats[name] = {'trades': 0, 'error': f'{name} gen err: {e}'}
            continue
        trades, bal = execute_signals(sigs, cfg, h1, sym,
                                      start_equity=start_equity, risk_pct=risk_pct)
        st = calc_stats(trades, bal, initial=initial)
        st['n_signals'] = len(sigs)
        st['skipped_risk'] = (trades[0].get('_skipped_risk', 0) if trades else 0)
        if trades:
            lots_used = [t.get('lot', 0) for t in trades if t.get('lot')]
            st['avg_lot'] = round(float(np.mean(lots_used)), 4) if lots_used else 0
        all_stats[name] = st
    # 择优: 样本≥min 者取 PF 最高; 否则取成交最多者
    best = None; best_pf = -1
    for name, st in all_stats.items():
        if st.get('trades', 0) >= min_trades_for_best:
            pf = st.get('pf', 0) or 0
            if pf > best_pf:
                best_pf = pf; best = name
    if best is None:
        cand = [n for n, s in all_stats.items() if s.get('trades', 0) > 0]
        if cand:
            best = max(cand, key=lambda n: all_stats[n]['trades'])
    if best is None:
        return {'best': None, 'stats': {'trades': 0, 'error': 'no trades'}, 'all': all_stats}
    return {'best': best, 'stats': all_stats[best], 'all': all_stats}


# ════════════════════════════════════════════════════════════════
# 数据加载 (本地 CSV / 可选 MT5)
# ════════════════════════════════════════════════════════════════
def load_local(sym):
    paths = {tf: os.path.join(DATA_DIR, f"{sym}_{tf}.csv") for tf in ('H1', 'H4', 'D1')}
    if all(os.path.exists(p) for p in paths.values()):
        return (pd.read_csv(paths['H1'], parse_dates=['time']),
                pd.read_csv(paths['H4'], parse_dates=['time']),
                pd.read_csv(paths['D1'], parse_dates=['time']))
    return None

def try_mt5_download(sym):
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return None
        for tf_name, tf_mt5 in [('H1', TF['H1']), ('H4', TF['H4']), ('D1', TF['D1'])]:
            f = os.path.join(DATA_DIR, f"{sym}_{tf_name}.csv")
            if os.path.exists(f):
                continue
            rates = mt5.copy_rates_range(sym, tf_mt5,
                                         int(datetime(2025, 7, 1).timestamp()),
                                         int(datetime(2026, 7, 1).timestamp()))
            if rates is not None and len(rates) > 0:
                df = pd.DataFrame(rates); df['time'] = pd.to_datetime(df['time'], unit='s')
                df.to_csv(f, index=False)
        mt5.shutdown()
        return load_local(sym)
    except Exception as e:
        return f"MT5_ERR:{e}"


# ════════════════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════════════════
def _partial_path():
    return os.path.join(DATA_DIR, "_ub_partial.json")

def _load_partial():
    p = _partial_path()
    if os.path.exists(p):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_partial(results):
    with open(_partial_path(), 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, default=str)

def run(symbols=None, allow_mt5=False, min_trades=su.COLLECT_MIN_TRADES,
        strategies=ALL_STRATEGIES, rebuild=False,
        account=True, risk_pct=1.0, equity=None):
    """全宇宙回测。

    account=True: 用 data/account_specs.json 的真实券商规格 + 真实账户余额,
                  按 risk_pct% 复利定手 (小账户会因最小手风险超限而跳过部分信号)。
    """
    symbols = symbols or list(su.UNIVERSE.keys())
    # ① 外汇汇率推导标定 (兜底: 无 MT5 规格时使用)
    try:
        n_cal, _cal = su.calibrate_forex_pip_usd(DATA_DIR)
        if n_cal:
            print(f"  [标定] {n_cal} 个外汇品种 pip_usd 已按真实汇率重新标定 (修正 exotic 放大)")
    except Exception as e:
        print(f"  [标定] 跳过 (无数据/异常): {e}")
    # ② MT5 真实合约规格覆盖 (最高优先级)
    start_equity = None
    if account:
        try:
            n_sp, ch_sp = su.apply_account_specs(DATA_DIR)
            if n_sp:
                start_equity = float(equity) if equity else float(su.ACCOUNT.get('balance') or 0) or None
                big = {k: v for k, v in ch_sp.items() if v[0] > 0 and abs(v[1]/v[0]-1) > 0.5}
                if big:
                    print(f"  [规格] 点值大幅修正 {len(big)} 个 (>50%): "
                          + ", ".join(f"{k}({v[0]:.2f}->{v[1]:.2f})" for k, v in list(big.items())[:8])
                          + (" ..." if len(big) > 8 else ""))
        except Exception as e:
            print(f"  [规格] 注入失败, 回退估算值: {e}")
    partial = {} if rebuild else _load_partial()
    results = dict(partial)   # 续跑: 已完成的品种直接复用
    print("="*72)
    print("  A.T.E. 全品种宇宙回测 + 多策略择优 + 盈利排名")
    print(f"  品种数: {len(symbols)} | 策略: {','.join(strategies)} | 数据: {DATA_DIR}")
    if start_equity:
        print(f"  ★ 真实账户模式: 起始净值 ${start_equity:.2f} | 单笔风险 {risk_pct}% | "
              f"券商真实最小手/步长/点差")
    else:
        print(f"  仓位模式: 固定手 (legacy, 起始 $10,000)")
    print(f"  续跑缓存: {len(partial)} 已完成 | rebuild={rebuild}")
    print("="*72)

    for sym in symbols:
        if sym in results and not rebuild:
            continue
        cfg = su.UNIVERSE.get(sym)
        if cfg is None:
            results[sym] = {'status': 'UNKNOWN_SYMBOL', 'best': None, 'stats': None}
            _save_partial(results)
            continue
        data = load_local(sym)
        src = 'CSV'
        if data is None:
            if allow_mt5:
                data = try_mt5_download(sym)
                if isinstance(data, str):
                    results[sym] = {'status': 'NO_DATA', 'reason': data, 'best': None, 'stats': None}
                    print(f"  {sym:<10} ({cfg['name']}): NO_DATA ({data})")
                    _save_partial(results)
                    continue
                src = 'MT5'
            if data is None:
                results[sym] = {'status': 'NO_DATA', 'reason': '无本地CSV且未启用MT5', 'best': None, 'stats': None}
                print(f"  {sym:<10} ({cfg['name']}): NO_DATA (无本地数据)")
                _save_partial(results)
                continue
        h1, h4, d1 = data
        try:
            rb = run_backtest(sym, cfg, h1, h4, d1, strategies,
                              start_equity=start_equity, risk_pct=risk_pct)
            best = rb['best']; st = rb['stats']
            if best is None or 'error' in st:
                results[sym] = {'status': 'NO_TRADES', 'src': src, 'best': None, 'stats': st,
                                'all': rb['all'], 'decision': 'NO_DATA', 'reason': '无成交',
                                'cfg': cfg}
                print(f"  {sym:<10} ({cfg['name']:<8}) [{src}]: 0 笔成交 (5策略均未触发)")
                _save_partial(results)
                continue
            decision, reason = su.classify_filter(st, min_trades)
            results[sym] = {'status': 'OK', 'src': src, 'best': best, 'stats': st,
                            'all': rb['all'], 'decision': decision, 'reason': reason, 'cfg': cfg}
            s = st
            skp = s.get('skipped_risk', 0)
            print(f"  {sym:<10} ({cfg['name']:<8}) [{src}] 优:{STRATEGY_NAMES.get(best,best):<10} "
                  f"{int(s.get('trades',0)):>3d}笔 | 胜率{s.get('wr',0):>5.1f}% | 净${s.get('pnl',0):>9.2f} | "
                  f"PF{s.get('pf',0):>5.2f} | 手{s.get('avg_lot',0):<5} | {decision}"
                  + (f" | 跳过{skp}(风险超限)" if skp else ""))
        except Exception as e:
            results[sym] = {'status': 'ERROR', 'reason': str(e), 'best': None, 'stats': None}
            print(f"  {sym:<10} ({cfg['name']}): ERROR - {e}")
        _save_partial(results)

    ranked = sorted(
        [(s, r) for s, r in results.items()
         if r.get('status') == 'OK' and isinstance(r.get('stats'), dict) and 'pnl' in r['stats']],
        key=lambda x: x[1]['stats'].get('pnl', -1e9), reverse=True)

    try:
        _write_reports(results, ranked, min_trades, strategies)
    except Exception as e:
        print(f"  [警告] 报告写入失败(数据已存盘): {e}")
    return results, ranked


def _write_reports(results, ranked, min_trades, strategies):
    csv_path = os.path.join(DATA_DIR, "universe_backtest_report.csv")
    rows = []
    for sym, r in results.items():
        cfg = su.UNIVERSE.get(sym, {})
        st = r.get('stats') or {}
        allst = r.get('all') or {}
        rows.append({
            'symbol': sym, 'name': cfg.get('name', ''), 'cls': cfg.get('cls', ''),
            'status': r.get('status'), 'src': r.get('src', ''),
            'best_strategy': r.get('best') or '',
            'trades': st.get('trades', 0), 'win_rate': st.get('wr', 0),
            'net_pnl': st.get('pnl', 0), 'pf': st.get('pf', 0),
            'expectancy': st.get('expectancy', 0), 'max_dd': st.get('max_dd', 0),
            'ret_pct': st.get('ret', 0), 'decision': r.get('decision', ''),
            'reason': r.get('reason', ''),
            'SDP_trades': allst.get('SDP', {}).get('trades', 0), 'SDP_pf': allst.get('SDP', {}).get('pf', 0),
            'ICT_trades': allst.get('ICT', {}).get('trades', 0), 'ICT_pf': allst.get('ICT', {}).get('pf', 0),
            'VP_trades': allst.get('VP', {}).get('trades', 0), 'VP_pf': allst.get('VP', {}).get('pf', 0),
            'DIV_trades': allst.get('DIV', {}).get('trades', 0), 'DIV_pf': allst.get('DIV', {}).get('pf', 0),
            'MR_trades': allst.get('MR', {}).get('trades', 0), 'MR_pf': allst.get('MR', {}).get('pf', 0),
        })
    pd.DataFrame(rows).to_csv(csv_path, index=False)

    json_path = os.path.join(DATA_DIR, "universe_backtest_report.json")
    out = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'universe_size': len(su.UNIVERSE),
        'strategies': strategies, 'min_trades': min_trades,
        'results': {s: {k: v for k, v in r.items() if k != 'cfg'} for s, r in results.items()},
    }
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)

    md_path = os.path.join(DATA_DIR, "universe_backtest_report.md")
    lines = [
        "# 全品种宇宙回测 · 多策略择优 · 盈利排名与筛选决策",
        f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- 宇宙规模: {len(su.UNIVERSE)} 个品种 | 策略: {', '.join(STRATEGY_NAMES[s] for s in strategies)} | 样本门槛: {min_trades} 笔",
        f"- 数据源: 本地CSV离线回测 (合约正确 PnL)",
        "",
        "## 排名 (按净盈利, 仅已回测品种, 每品种取最优策略)",
        "",
        "| 排名 | 品种 | 名称 | 类别 | 最优策略 | 笔数 | 胜率 | 净盈亏$ | PF | 期望$ | 最大回撤% | 决策 |",
        "|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for i, (sym, r) in enumerate(ranked, 1):
        s = r['stats']; cfg = su.UNIVERSE[sym]
        lines.append(
            f"| {i} | {sym} | {cfg['name']} | {cfg['cls']} | {STRATEGY_NAMES.get(r['best'], r['best'])} | "
            f"{s['trades']} | {s['wr']}% | {s['pnl']} | {s['pf']} | {s['expectancy']} | {s['max_dd']} | "
            f"**{r['decision']}** |")
    keep = [s for s, r in results.items() if r.get('decision') == 'KEEP']
    collect = [s for s, r in results.items() if r.get('decision') == 'COLLECT']
    cut = [s for s, r in results.items() if r.get('decision') == 'CUT']
    nodata = [s for s, r in results.items()
              if r.get('status') in ('NO_DATA', 'UNKNOWN_SYMBOL', 'NO_TRADES')]
    lines += [
        "",
        "## 筛选汇总",
        "",
        f"- **KEEP (保留)**: {len(keep)} 个 → {', '.join(keep) or '—'}",
        f"- **COLLECT (继续收集)**: {len(collect)} 个 → {', '.join(collect) or '—'}",
        f"- **CUT (剔除)**: {len(cut)} 个 → {', '.join(cut) or '—'}",
        f"- **NO_DATA (待收集/无数据)**: {len(nodata)} 个 (占宇宙 {len(nodata)*100//len(su.UNIVERSE)}%)",
        "",
        "## 决策框架 (拿到数据后筛选)",
        "",
        f"- PF ≥ {su.FILTER['keep_pf']} 且净盈利>0 且样本≥{min_trades} → **KEEP**",
        f"- PF < {su.FILTER['cut_pf']} (负期望) → **CUT**",
        f"- 其余 / 样本<{min_trades} → **COLLECT** (继续积累实盘数据)",
        "",
        "## 先进策略已落地 (全网调研 2025-2026)",
        "",
        "- **SDP**: 原有供需区 + D1方向 + ADX + ATR (基线)",
        "- **ICT**: 订单块(OB)+公平价值缺口(FVG)+流动性扫荡+市场结构转变(MSS)+折扣/溢价多条件共振 (ICT 2026)",
        "- **VP**: 成交量分布 POC/价值区/LVN 均值回归, 剔除 LVN 亏损交易, ADX>20 门禁",
        "- **DIV**: RSI 常规+隐藏背离",
        "- **MR**: 价格 z-score 偏离均线均值回归",
        "",
        "> 下一步: 对 NO_DATA 品种开启 `symbol_universe.DATA_COLLECTION_MODE=True` + "
        "`load_universe_into_ce()`, 让直播引擎放开全品种交易; 或 `python universe_backtest.py --mt5` "
        "下载全宇宙历史数据后重跑, 用最新数据最终定保留清单。",
    ]
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

    print("\n" + "="*72)
    print("  ★ 筛选汇总")
    print("="*72)
    print(f"  KEEP    (保留)  : {len(keep)}  → {', '.join(keep) or '—'}")
    print(f"  COLLECT (收集)  : {len(collect)}  → {', '.join(collect) or '—'}")
    print(f"  CUT     (剔除)  : {len(cut)}  → {', '.join(cut) or '—'}")
    print(f"  NO_DATA (无数据): {len(nodata)}  → 占宇宙 {len(nodata)*100//len(su.UNIVERSE)}%")
    print(f"\n  报告: {csv_path}\n         {json_path}\n         {md_path}")


if __name__ == "__main__":
    allow_mt5 = "--mt5" in sys.argv
    rebuild = "--rebuild" in sys.argv
    run(allow_mt5=allow_mt5, rebuild=rebuild)
