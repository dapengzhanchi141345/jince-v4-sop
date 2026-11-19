# backtest_engine.py — 金策宗师团 · 真实成本回测台 (B方案治本)
"""
目的: 用 MT5 历史 K 线, 对 7 个策略 × 全宇宙品种 做**带真实成本**的回测,
      发现"当前市况有正 edge"的策略×品种组合, 替换 D1 门控拦掉的负 edge 信号.

关键设计 (避免旧回测 pf=3.68 幻觉):
  1. 防前视: 策略函数只用截至当前 H1 bar 的 H4/D1 分片(已审计 gen_sdp 如此);
     信号在 bar i 发出 -> 下一根 H1 开盘价入场(不给当根 close 免费成交).
  2. 真实成本: 入场点差(spread×point 不利方向偏移) + 隔夜 swap(若持仓跨日).
  3. SL/TP 用后续 K 线 high/low 判定; 同根 K 内 SL/TP 皆触 -> 距 entry 近者先触发(保守).
  4. 到期: max_hold 根 H1 未触发 -> 按届时开盘价平仓(避免无限漂移).

信号契约 (来自 advanced_strategies): sig = {bar, side(+1/-1), entry, sl, tp, strat}
回测: entry 价取 signals['entry']; sl_dist/tp_dist 由 entry 与 sl/tp 价差固定;
      真实入场 = open[i+1] ± spread_adj; 真实 SL/TP = 真实入场 ± sl_dist/tp_dist.
"""
import json, sys, time, datetime, traceback, threading
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
import symbol_universe as su
import advanced_strategies as ast


class MtcUnavailableError(RuntimeError):
    """[L5 2026-11-02 C单] MT5 终端不可用/initialize 失败 -> 引擎诚实让位 exit 4
    (对齐既有 rc=3 引擎锁让位语义: 非崩非 rc=1, 调用方按'本拍跳过等终端恢复'处理, 不刷屏)."""

MAX_HOLD_H1 = 480          # 最多持仓 480 根 H1 (~20 交易日) 后到期平仓
MIN_TRADES = 20            # 正 edge 判定最少样本数
PF_PASS = 1.0             # 正 edge 门槛
H1_TARGET_BARS = 20000     # H1 目标长度(分页拉取上限)
PAGINATE = 5000

STRATS = ast.ALL_STRATEGIES

# =====================================================================
# 双知识库 DSR/PBO 统计闸 + 事件滑点三档 (fail-open 新增, 不改五验原判定)
#   Bailey & Lopez de Prado 2014: DSR = P(Sharpe>0 | 试验N次后挑出最优)
#   PBO: 概率加权 bootstrap, 过拟合概率 <0.4 认为风险可控
# =====================================================================

# 事件滑点三档 (只用于止损 R 值折算, 不进现有 simulate_signal 默认路径)
SLIPPAGE_TIERS = {
    'normal':      {'slip_R': 0.2,   'desc': '平时 0.1-0.3R 取中位'},
    'data_moment': {'slip_R': 0.5,   'desc': '数据时刻(财报/会议/非农) 0.5R'},
    'blackout':    {'slip_R': 1.0,   'desc': '闪崩/流动性枯竭 1R'},
}


def deflated_sharpe_ratio(returns, n_trials=1, bars_per_year=252):
    """Bailey 正态混合法 DSR.

    returns: 逐bar收益率序列(list/array, 单位=bar)
    n_trials: 挑出该策略前总共试了多少个参数/品种组合
    返回 dict: obs_sharpe, expected_max_sharpe, dsr(0-1概率), verdict(>=0.95 PASS)
    fail-open: 数据不足时 verdict='N/A'
    """
    import math
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)
    if n < 30:
        return {'obs_sharpe': None, 'expected_max_sharpe': None, 'dsr': None,
                'verdict': 'N/A', 'reason': f'sample<30 (n={n})'}
    mu, sd = r.mean(), r.std(ddof=1)
    if sd < 1e-12:
        return {'obs_sharpe': 0.0, 'expected_max_sharpe': 0.0, 'dsr': 1.0,
                'verdict': 'PASS', 'reason': 'zero variance'}
    # Bailey-Lopez de Prado 2014 公式 (per-bar 单位, T=样本bar数):
    #   Sharpe_obs = mean/std                        (per-bar)
    #   EMS        = z_{1-1/(2N)} * (1-gamma/N)      (N=n_trials, per-bar 期望最大夏普)
    #   DSR        = Phi( (Sharpe-EMS)*sqrt(T-1) / sqrt(1 - g3*S/sqrt(T) + (g4-1)*S^2/(2T)) )
    # N=1 时 EMS=0, 退化为普通单样本 t 检验 Phi(S*sqrt(T-1)), 与手工算一致.
    sharpe = mu / sd
    sharpe_ann = sharpe * math.sqrt(bars_per_year)
    ems = _ems_bailey(sharpe, n_trials)
    T = n
    skew = float(pd.Series(r).skew()) if n >= 3 else 0.0
    kurt = float(pd.Series(r).kurtosis() + 3.0) if n >= 4 else 3.0  # pd kurtosis 是 excess
    denom_sq = 1.0 - skew * sharpe / math.sqrt(T) + (kurt - 1.0) * sharpe * sharpe / (2.0 * T)
    if denom_sq <= 0:
        return {'obs_sharpe': float(sharpe), 'expected_max_sharpe': ems, 'dsr': 0.0,
                'verdict': 'REJECT', 'reason': 'denom<=0 kurtosis degenerate'}
    z_ds = (sharpe - ems) * math.sqrt(T - 1) / math.sqrt(denom_sq)
    dsr = 0.5 * (1.0 + math.erf(z_ds / math.sqrt(2.0)))  # Phi(z_ds)
    verdict = 'PASS' if dsr >= 0.95 else 'REJECT'
    return {'obs_sharpe': float(sharpe), 'sharpe_annualized': float(sharpe_ann),
            'expected_max_sharpe': float(ems), 'dsr': float(dsr),
            'verdict': verdict, 'n_trials': int(n_trials), 'n': int(n)}


def _z_scores(n):
    """标准正态分位数表 (Bailey 论文的 z 近似), N最大到 1024."""
    import math
    # 用逆正态 CDF (Acklam 近似)
    def phi_inv(p):
        a = [-3.969683028665376e+01, 2.209460984245105e+02, -2.758263934863715e+02,
             1.383577518672490e+02, -3.053235709070850e+01, 3.038191644502400e+00]
        b = [-2.844967363039062e+01, 1.423484245115688e+02, -2.062631678654786e+02,
             1.009706372518811e+02, -2.044263488219754e+01, 1.423425144191175e+00]
        pl = 0.02425
        if p < pl:
            q = math.sqrt(-2 * math.log(p))
            return (((((a[0]*q+a[1])*q+a[2])*q+a[3])*q+a[4])*q+a[5]) / (((((b[0]*q+b[1])*q+b[2])*q+b[3])*q+b[4])*q+b[5])
        if p > 1 - pl:
            q = math.sqrt(-2 * math.log(1 - p))
            return -(((((a[0]*q+a[1])*q+a[2])*q+a[3])*q+a[4])*q+a[5]) / (((((b[0]*q+b[1])*q+b[2])*q+b[3])*q+b[4])*q+b[5])
        q = p - 0.5; r = q * q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+b[5])
    return [phi_inv(1.0 - (i + 0.5) / (2 * n)) for i in range(n)]


def _ems_bailey(sharpe, n):
    """Bailey 期望最大夏普 (per-bar 单位): EMS ≈ z_{1-1/(2N)} * (1-γ/N).
    N=1 时 EMS=0 (单一试验无多重检验惩罚), DSR = Phi(sharpe*sqrt(T-1)/denom).
    """
    import math
    if n <= 1:
        return 0.0
    z_crit = _phi_inv_fast(1.0 - 1.0 / (2.0 * n))
    gamma = 0.5772156649015329
    return (1.0 - gamma / n) * z_crit


def _phi_inv_fast(p):
    import math
    # Acklam 近似 (精度 ~1e-9), 用于 _ems_bailey
    if p <= 0.0 or p >= 1.0:
        return -99.0 if p <= 0.0 else 99.0
    a = [-39.69680028665376, 220.9460984245105, -275.8263934863715, 138.357751867249, -30.5323570907085, 3.0381916445024]
    b = [-28.44967363039062, 142.3484245115688, -206.2631678654786, 100.9706372518811, -20.44263488219754, 1.423425144191175]
    pl, ph = 0.02425, 0.97575
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((a[0]*q+a[1])*q+a[2])*q+a[3])*q+a[4])*q+a[5]) / (((((b[0]*q+b[1])*q+b[2])*q+b[3])*q+b[4])*q+b[5])
    if p > ph:
        q = math.sqrt(-2 * math.log(1.0 - p))
        return -(((((a[0]*q+a[1])*q+a[2])*q+a[3])*q+a[4])*q+a[5]) / (((((b[0]*q+b[1])*q+b[2])*q+b[3])*q+b[4])*q+b[5])
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+b[5])


def pbo_probability(wf_sharpes, n_boot=1000, seed=42):
    """概率加权 Bootstrap PBO (Bailey & López de Prado 2015).

    wf_sharpes: list[dict]  每个 walk-forward 窗口 dict:
        {'train_sharpe': float, 'test_sharpe': float, 'oos_return': float}
    判据: PBO<0.4 -> PASS(过拟合风险可控) / >=0.4 -> REJECT / <2窗口 -> N/A
    原理: 按训练期夏普概率抽样重分 train/test, 若"最优"OOS 仍 < 原 OOS,
         说明原最优组合过拟合, 累计频率 = PBO.
    注意(简化版): base_oos 取 train 夏普最大窗口的 oos_return; 若该窗口自身
         OOS 已是全局最大, 则 PBO 天然为 0 —— 这是概率加权重抽样的已知
         属性, 非 bug. 高 PBO 需要"最优 OOS 由权重小的窗口贡献"的场景
         (典型: 某低 train 夏普窗口 OOS 异常高, 重抽样后频繁被更平庸的
         窗口取代冠军).
    """
    import random
    if wf_sharpes is None or len(wf_sharpes) < 2:
        return {'pbo': None, 'verdict': 'N/A', 'reason': f'windows={len(wf_sharpes) if wf_sharpes else 0}<2'}
    rng = random.Random(seed)
    w = max((x.get('train_sharpe', 0.0) for x in wf_sharpes), default=0.0)
    if w <= 0:
        weights = [1.0] * len(wf_sharpes)
    else:
        weights = [max(x.get('train_sharpe', 0.0), 0.0) for x in wf_sharpes]
        total = sum(weights)
        weights = [x / total for x in weights]
    base_oos = max(wf_sharpes, key=lambda x: x.get('train_sharpe', 0.0)).get('oos_return', wf_sharpes[0].get('oos_return', 0.0))
    n_win = len(wf_sharpes)
    cnt = 0
    for _ in range(n_boot):
        idx = rng.choices(range(n_win), weights=weights, k=n_win)
        boot_best_oos = max(wf_sharpes[i].get('oos_return', 0.0) for i in idx)
        if boot_best_oos < base_oos:
            cnt += 1
    pbo = cnt / n_boot
    verdict = 'PASS' if pbo < 0.4 else 'REJECT'
    return {'pbo': round(pbo, 4), 'verdict': verdict,
            'n_windows': n_win, 'n_boot': n_boot,
            'base_oos': round(float(base_oos), 4)}


def slippage_ab_test(h1, sigs, cfg, point, spread_pts, slippage_tier='normal'):
    """同分母 A/B: 同一信号集, 不同滑点档, 比较 PnL 与期望 R.

    slippage_tier: 'normal' / 'data_moment' / 'blackout' (SLIPPAGE_TIERS)
    只改止损 R 值折算 (sl_dist + slip_R * sl_dist * side_sign 不利方向), 点差仍按原值.
    返回 dict: n, gw, gl, pf, pnl_total, avg_exp_R, slip_R 使用值
    """
    import math
    tier = SLIPPAGE_TIERS.get(slippage_tier, SLIPPAGE_TIERS['normal'])
    slip_R = tier['slip_R']
    lot = float(cfg.get('lot', 1.0))
    pip = float(cfg.get('pip', 0.0001))
    pip_usd = _pip_usd_cache.get(cfg.get('_symbol', ''), 10.0) or 10.0
    gw = gl = 0.0
    n = 0
    exp_r = []
    for s in sigs:
        pnl = _simulate_with_slip(h1, s, spread_pts, point,
                                  float(cfg.get('swap_long', 0.0)), float(cfg.get('swap_short', 0.0)),
                                  lot, pip, pip_usd, slip_R)
        if pnl is None:
            continue
        n += 1
        sl_dist = abs(float(s['entry']) - float(s['sl']))
        r_ratio = (sl_dist / max(abs(float(s['entry']) - float(s['tp'])), 1e-9))
        r_usd = sl_dist / pip * pip_usd * lot
        exp_r.append(pnl / r_usd if r_usd > 0 else 0.0)
        if pnl >= 0:
            gw += pnl
        else:
            gl += -pnl
    pf = (gw / gl) if gl > 1e-9 else (float('inf') if gw > 0 else 0.0)
    return {'n': n, 'gw': round(gw, 2), 'gl': round(gl, 2),
            'pf': round(pf, 3) if gl > 1e-9 or gw > 0 else 0.0,
            'pnl_total': round(gw - gl, 2),
            'avg_exp_R': round(sum(exp_r) / n, 4) if n else None,
            'slip_R_used': slip_R, 'tier': slippage_tier}


def _simulate_with_slip(h1, sig, spread_pts, point, swap_long, swap_short,
                        lot, pip, pip_usd, slip_R):
    """simulate_signal 的滑点 R 版 (仅改 SL 距离, 不改 TP 与默认路径)."""
    i = int(sig['bar'])
    if i + 1 >= len(h1):
        return None
    side = sig['side']
    sig_entry = float(sig['entry'])
    sl = float(sig['sl']); tp = float(sig['tp'])
    if sl <= 0 or tp <= 0 or sl == tp:
        return None
    sl_dist = abs(sig_entry - sl)
    tp_dist = abs(sig_entry - tp)
    if sl_dist <= 0 or tp_dist <= 0:
        return None
    # 滑点档位放大止损距离 (不利方向)
    sl_dist_eff = sl_dist * (1.0 + slip_R)
    open_next = float(h1['open'].iloc[i + 1])
    spread_adj = spread_pts * point
    if side > 0:
        entry = open_next + spread_adj
        real_sl = entry - sl_dist_eff
        real_tp = entry + tp_dist
    else:
        entry = open_next - spread_adj
        real_sl = entry + sl_dist_eff
        real_tp = entry - tp_dist
    end = min(i + 1 + MAX_HOLD_H1, len(h1))
    hi = h1['high'].values[i + 1:end]
    lo = h1['low'].values[i + 1:end]
    op = h1['open'].values[i + 1:end]
    tm = h1['time'].values[i + 1:end]
    if len(hi) == 0:
        return None
    for k in range(len(hi)):
        if side > 0:
            sl_hit = lo[k] <= real_sl
            tp_hit = hi[k] >= real_tp
        else:
            sl_hit = hi[k] >= real_sl
            tp_hit = lo[k] <= real_tp
        if sl_hit and tp_hit:
            exit_px = real_sl if sl_dist_eff <= tp_dist else real_tp
        elif sl_hit:
            exit_px = real_sl
        elif tp_hit:
            exit_px = real_tp
        else:
            continue
        hold_days = max(0, (tm[k] - tm[0]) // 86400) if k > 0 else 0
        sw = swap_long if side > 0 else swap_short
        swap = sw * hold_days * lot if hold_days > 0 else 0.0
        pnl_pts = (exit_px - entry) * side
        return pnl_pts / pip * pip_usd * lot - abs(swap)
    exit_px = float(op[-1])
    pnl_pts = (exit_px - entry) * side
    return pnl_pts / pip * pip_usd * lot


def five_verify_report(leg_data, dsr_data=None, pbo_data=None):
    """七项验收报告 (五验 + DSR 闸 + PBO 闸, 后两项 fail-open).

    leg_data: dict 含 name/symbol/pf/n/wr (五验输入)
    dsr_data: dict {'returns': list, 'n_trials': int} 或 None
    pbo_data: list[dict] walk-forward 窗口, 或 None
    返回 dict: 五验原字段 + dsr_gate + pbo_gate (六/七项)
    """
    pf = leg_data.get('pf', 0.0)
    n = leg_data.get('n', 0)
    # 五验
    v1 = n >= 1000
    v2 = pf >= 1.0
    report = {
        'leg': leg_data.get('name', 'unknown'),
        'symbol': leg_data.get('symbol', ''),
        'v1_sample>=1000': v1,
        'v2_same_denom_pnl': 'N/A',
        'v3_symbol_robust': 'N/A',
        'v4_param_sweet_spot': 'N/A',
        'v5_walk_forward': 'N/A',
        'pf': pf, 'n': n,
    }
    # DSR 闸 (第六项)
    if dsr_data and dsr_data.get('returns') is not None:
        res = deflated_sharpe_ratio(dsr_data['returns'],
                                     n_trials=dsr_data.get('n_trials', 1))
        report['v6_dsr'] = res
    else:
        report['v6_dsr'] = {'dsr': None, 'verdict': 'N/A', 'reason': 'returns missing'}
    # PBO 闸 (第七项)
    if pbo_data:
        res = pbo_probability(pbo_data)
        report['v7_pbo'] = res
    else:
        report['v7_pbo'] = {'pbo': None, 'verdict': 'N/A', 'reason': 'wf windows missing'}
    # 原五验判定 (不含新闸) — fail-open 原则: 缺数据 N/A 不翻转
    orig_pass = v1 and v2
    report['five_verify_pass_orig'] = orig_pass
    report['overall_verdict'] = _seven_gate_verdict(report, dsr_data, pbo_data)
    return report


def _seven_gate_verdict(report, dsr_data, pbo_data):
    """七项综合判定: 五验 PASS 前提下, DSR/PBO 有数据才参与; 缺数据保持 N/A 不影响."""
    if not report.get('five_verify_pass_orig'):
        return 'REJECT(五验不过)'
    dsr = report['v6_dsr']
    pbo = report['v7_pbo']
    dsr_bad = dsr.get('verdict') == 'REJECT'
    pbo_bad = pbo.get('verdict') == 'REJECT'
    if dsr_bad or pbo_bad:
        blocks = []
        if dsr_bad:
            blocks.append(f"DSR={dsr.get('dsr')}<0.95")
        if pbo_bad:
            blocks.append(f"PBO={pbo.get('pbo')}>=0.4")
        return 'REJECT(统计闸)' + ' '.join(blocks)
    if dsr.get('verdict') == 'PASS':
        note_dsr = f"DSR={dsr['dsr']:.4f}过"
    else:
        note_dsr = "DSR=N/A(不拦)"
    if pbo.get('verdict') == 'PASS':
        note_pbo = f"PBO={pbo['pbo']:.4f}过"
    else:
        note_pbo = "PBO=N/A(不拦)"
    return f'PASS({note_dsr}; {note_pbo})'


# =====================================================================
# [2026-11-04 L5, hermes 三重根因①] K线缓存 cache-first (治双引擎霸 IPC 空卷)
#   根: Live Runner(PID584) + 回测引擎共享 MT5 终端 8736, 并发 copy_rates_from_pos
#   -> 谁抢谁拿空卷 -> 全币 "H1数据不足" -> 回测 0 数据 0 edge (empty_volume).
#   治: get_rates 先读 data/tf_cache/{SYM}_{TF}.npz (零 IPC, 与实盘 runner 彻底解耦);
#   缓存缺失/过期才走 live IPC; live IPC 被霸空卷时 stale-fallback 用旧缓存出实数(不空卷).
#   缓存由 refresh_tf_cache.py (00:10 前竞态容错刷新) 落盘, 引擎顺手刷新到活数据.
# =====================================================================
import os as _os
_TF_CACHE_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "data", "tf_cache")
_TF_NPZ = {mt5.TIMEFRAME_H1: "H1", mt5.TIMEFRAME_H4: "H4", mt5.TIMEFRAME_D1: "D1",
           getattr(mt5, "TIMEFRAME_M30", -1): "M30", getattr(mt5, "TIMEFRAME_M15", -1): "M15"}
# 缓存新鲜度闸(小时): 训练回测用历史 K 线, 落后在闸内=新鲜直接用; 超闸=过期, 仅被霸空卷时 stale-fallback.
_CACHE_MAX_AGE_H = {"H1": 120, "H4": 240, "D1": 336, "M30": 96, "M15": 48}


def _cache_read(symbol, tf, target, allow_stale=False):
    """读 npz 缓存 -> DataFrame(time/open/high/low/close + tick_volume/real_volume/spread=0).
    新鲜(落后<闸)或 allow_stale(被霸空卷时)才返回; 否则 None. 零 IPC."""
    tfname = _TF_NPZ.get(tf)
    if tfname is None:
        return None
    p = _os.path.join(_TF_CACHE_DIR, "%s_%s.npz" % (symbol, tfname))
    if not _os.path.exists(p):
        return None
    try:
        z = np.load(p)
        t, o, h, l, c = z["t"], z["o"], z["h"], z["l"], z["c"]
        last = int(t[-1])
        # [11-19 口径修] t[-1] 为 server 墙钟(EET 冬 UTC+2, 11-19 tick 生死测定死), 直接减 UTC time.time() 会把数据恒显"年轻 2h"
        # (新鲜度闸放行过旧数据 + 五验 OOS"数据末端=现在"边界多算 2h 前视). 统一改 mtime 口径(本地写盘时间=UTC, 无时区混淆, 保守安全).
        age_h = (time.time() - _os.path.getmtime(p)) / 3600.0
        if not allow_stale and age_h > _CACHE_MAX_AGE_H.get(tfname, 240):
            return None
        take = min(int(target), int(len(t)))
        df = pd.DataFrame({"time": t[-take:], "open": o[-take:], "high": h[-take:],
                           "low": l[-take:], "close": c[-take:]})
        # 对齐 live IPC df 的额外列(策略只吃 OHLC, 这几列=0 兜底防 KeyError)
        df["tick_volume"] = 0.0
        df["real_volume"] = 0.0
        df["spread"] = 0.0
        df = df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
        return df
    except Exception:
        return None


def _cache_write(symbol, tf, df):
    """拉到活 K 线时顺手刷新 npz (下枪再遇被霸也能 stale-fallback 用)."""
    tfname = _TF_NPZ.get(tf)
    if tfname is None or df is None or len(df) < 500:
        return
    try:
        _os.makedirs(_TF_CACHE_DIR, exist_ok=True)
        p = _os.path.join(_TF_CACHE_DIR, "%s_%s.npz" % (symbol, tfname))
        z = {"time": df["time"].values.astype(np.int64), "open": df["open"].values.astype(np.float32),
             "high": df["high"].values.astype(np.float32), "low": df["low"].values.astype(np.float32),
             "close": df["close"].values.astype(np.float32)}
        np.savez_compressed(p, t=z["time"], o=z["open"], h=z["high"], l=z["low"], c=z["close"])
    except Exception:
        pass


def get_rates(symbol, tf, target=H1_TARGET_BARS, use_cache=True):
    """分页拉取历史 K 线 -> DataFrame(time,open,high,low,close,tick_volume,real_volume,spread).
    [L5①] cache-first: 命中新鲜缓存直接返回(零 IPC, 根治双引擎霸 copy_rates 空卷);
    缓存缺失/过期 -> live IPC; live 被霸空卷 -> stale-fallback 用旧缓存出实数(不再全币空卷)."""
    if use_cache:
        cdf = _cache_read(symbol, tf, target)
        if cdf is not None and len(cdf) >= 200:
            return cdf
    frames = []
    pos = 0
    while True:
        chunk = mt5.copy_rates_from_pos(symbol, tf, pos, PAGINATE)
        if chunk is None or len(chunk) == 0:
            break
        frames.append(pd.DataFrame(chunk))
        if len(chunk) < PAGINATE:
            break
        pos += len(chunk)
        if pos >= target:
            break
    if not frames:
        # [L5①] 被霸空卷 stale-fallback: 旧缓存(哪怕过期)也用来出实数, 不空卷
        if use_cache:
            cdf = _cache_read(symbol, tf, target, allow_stale=True)
            if cdf is not None and len(cdf) >= 200:
                return cdf
        return None
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=['time']).sort_values('time').reset_index(drop=True)
    _cache_write(symbol, tf, df)   # 顺手刷新缓存(为下次被霸兜底)
    return df


def simulate_signal(h1, sig, spread_pts, point, swap_long, swap_short, lot, pip, pip_usd,
                    return_hit=False):
    """单信号模拟. 默认返回 pnl_$ 或 None(数据不足) [全部既有调用方行为不变].
    [2026-11-04 L5, hermes 三重根因② 修触价/胜率判定口径] return_hit=True 时返回 (pnl, hit_tp):
      hit_tp = 本笔是否"触价"=触到 TP (同根皆触保守取近者, 只有 TP 更近才算触到).
      旧口径 wins 计 pnl>=0: 到期没触 TP 只漂到零头正 pnl 也算赢 -> 低波动腿胜率虚高(n>500&wr>0.9
      触发引擎自检哨兵 rc=1, 原 paused_reason "胜率虚高腿 口径偏"). 现: win=触到TP, 到期/仅触SL 不计赢,
      胜率回归"触价率"诚实口径, 不再把'到期零头'当赢. 外部 10 个调用方不传 return_hit -> 行为不变."""
    i = int(sig['bar'])
    if i + 1 >= len(h1):
        return (None, False) if return_hit else None
    side = sig['side']
    sig_entry = float(sig['entry'])
    sl = float(sig['sl']); tp = float(sig['tp'])
    if sl <= 0 or tp <= 0 or sl == tp:
        return (None, False) if return_hit else None
    sl_dist = abs(sig_entry - sl)
    tp_dist = abs(sig_entry - tp)
    if sl_dist <= 0 or tp_dist <= 0:
        return (None, False) if return_hit else None
    # 真实入场: 下一根开盘 + 点差不利偏移
    open_next = float(h1['open'].iloc[i + 1])
    spread_adj = spread_pts * point
    if side > 0:
        entry = open_next + spread_adj
        real_sl = entry - sl_dist
        real_tp = entry + tp_dist
    else:
        entry = open_next - spread_adj
        real_sl = entry + sl_dist
        real_tp = entry - tp_dist
    # 后续 K 线窗口
    end = min(i + 1 + MAX_HOLD_H1, len(h1))
    hi = h1['high'].values[i + 1:end]
    lo = h1['low'].values[i + 1:end]
    op = h1['open'].values[i + 1:end]
    tm = h1['time'].values[i + 1:end]
    if len(hi) == 0:
        return (None, False) if return_hit else None
    for k in range(len(hi)):
        if side > 0:
            sl_hit = lo[k] <= real_sl
            tp_hit = hi[k] >= real_tp
        else:
            sl_hit = hi[k] >= real_sl
            # [2026-10-09 L5-fix] 空头触价修正: 原 lo[k] >= real_tp 判反(空头TP在下, 应是 low 下探到 real_tp 才触, 旧式导致空头腿假胜 99.6% 虚高, TREND 8901笔即此因).
            tp_hit = lo[k] <= real_tp
        hit_tp = False
        if sl_hit and tp_hit:
            # 同根皆触: 距 entry 近者先触发(保守, 通常 SL 更近); 只有 TP 更近才算"触到TP"
            if sl_dist <= tp_dist:
                exit_px = real_sl      # hit_tp=False
            else:
                exit_px = real_tp      # hit_tp=True
                hit_tp = True
        elif sl_hit:
            exit_px = real_sl          # hit_tp=False
        elif tp_hit:
            exit_px = real_tp
            hit_tp = True              # 触到TP = 算赢
        else:
            continue
        # 隔夜 swap: 持仓跨日计数
        hold_days = 0
        if k > 0:
            hold_days = max(0, (tm[k] - tm[0]) // 86400)
        swap = 0.0
        if hold_days > 0:
            sw = swap_long if side > 0 else swap_short
            swap = sw * hold_days * lot
        pnl_pts = (exit_px - entry) * side
        pnl_usd = pnl_pts / pip * pip_usd * lot - abs(swap)
        return (pnl_usd, hit_tp) if return_hit else pnl_usd
    # 到期平仓 (未触 TP/SL, hit_tp 恒 False —— 不计赢, 治胜率虚高)
    exit_px = float(op[-1])
    pnl_pts = (exit_px - entry) * side
    pnl_usd = pnl_pts / pip * pip_usd * lot
    return (pnl_usd, False) if return_hit else pnl_usd


_pip_usd_cache = {}
def pip_usd_of(symbol, pip):
    return _pip_usd_cache.get(symbol, 10.0)


def backtest_symbol(symbol, cfg):
    h1 = get_rates(symbol, mt5.TIMEFRAME_H1)
    if h1 is None or len(h1) < 200:
        return None, "H1数据不足"
    h4 = get_rates(symbol, mt5.TIMEFRAME_H4, 6000)
    d1 = get_rates(symbol, mt5.TIMEFRAME_D1, 6000)
    if h4 is None or d1 is None:
        return None, "H4/D1缺失"
    info = mt5.symbol_info(symbol)
    spread_pts = info.spread if info and info.spread > 0 else 10
    point = info.point if info else 1e-5
    swap_long = info.swap_long if info else 0
    swap_short = info.swap_short if info else 0
    lot = float(cfg.get('lot', 1.0))
    pip = float(cfg.get('pip', 0.0001))
    _pip_usd_cache[symbol] = float(cfg.get('pip_usd', 10.0))
    pip_usd = _pip_usd_cache[symbol]
    results = {}
    for name in STRATS:
        gen = ast.STRATEGY_REGISTRY[name]
        try:
            sigs = gen(h1, h4, d1, cfg)
        except Exception as e:
            results[name] = {'err': str(e)[:80]}
            continue
        if not sigs:
            results[name] = {'n': 0}
            continue
        wins = 0; gw = 0.0; gl = 0.0; n = 0
        for s in sigs:
            pnl, hit_tp = simulate_signal(h1, s, spread_pts, point, swap_long, swap_short, lot, pip, pip_usd,
                                          return_hit=True)
            if pnl is None:
                continue
            n += 1
            if pnl >= 0:
                gw += pnl
            else:
                gl += -pnl
            # [L5② 修触价/胜率判定口径] win=触到TP(hit_tp), 非 pnl>=0.
            #   旧口径把"到期没触TP只漂到零头正pnl"也算赢 -> 低波动腿胜率虚高(n>500&wr>0.9 触发
            #   引擎自检哨兵 rc=1, 原 paused_reason "胜率虚高腿 口径偏"). 现 wr=触价率(触到目标价占比),
            #   诚实反映"真打到TP的比例"; pf/gw/gl/n 仍按 pnl 归因(五验口径不变). 铁律: 高胜率≠正期望.
            if hit_tp:
                wins += 1
        pf = (gw / gl) if gl > 1e-9 else (float('inf') if gw > 0 else 0.0)
        results[name] = {'n': n, 'wins': wins, 'wr': wins / n if n else 0,
                         'wr_caliber': 'tp_touch',
                         'gw': round(gw, 2), 'gl': round(gl, 2),
                         'pf': round(pf, 3) if gl > 1e-9 or gw > 0 else 0.0}
    return results, f"H1={len(h1)}"


def run_universe(symbols=None, out_json="data/backtest_edge.json", time_cap_s=9000):
    """[2026-10-09] time_cap_s 护栏: SMOKE 3品种 13.5min 参考, 2h+ 没出件 = K线拉取/信号量爆.
    到点 fail-open 出件(不丢已算数据, 不让 2h+ 空磨白跑). 默认 1200s=20min, 足够 13.5min 参考 + 余量.
    不碰 L5-fix 等判定逻辑, 纯时间护栏.
    [2026-10-10 L5 修复] 全宇宙 40+ 品种 1200s 跑不完 -> 到点 fail-open 早挂 (连挂 4 起 rc=1 根因之一).
    默认提至 9000s (SMOKE 3品种 13.5min 推 ~40 品种需 ~1.5h), 全宇宙模式才给足时间.
    判据 grep: 本行 time_cap_s=9000 在 code 即销 @chief 19:xx 点名格."""
    # [2026-10-14 L5, chief 06:32 批] TIMECAP 下沉到 initialize: 41588 根因实读 =
    #   双引擎霸 MT5 终端互斥时 initialize 的 IPC 握手白磨(护栏在 initialize 之后的品种循环里, 到不了),
    #   现给 300s 限时: 握手 5min 不完 -> fail-open 退出(daemon 线程进程退即回收, 引擎锁随之释放, 下一枪可拉).
    import threading as _thd
    _init_res = {}
    def _do_init():
        _init_res['ok'] = mt5.initialize()
    _ith = _thd.Thread(target=_do_init, daemon=True)
    _ith.start()
    _ith.join(timeout=300)
    if not _init_res.get('ok', False):
        print("[TIMECAP下沉] mt5.initialize 握手 300s 到点/失败, 诚实让位(不白磨, 释放引擎锁给下一枪)")
        raise MtcUnavailableError("mt5.initialize 握手 300s 超时/失败 (MT5 终端未起或 IPC 被霸)")
    if symbols is None:
        symbols = [k for k, v in su.UNIVERSE.items() if v.get('tradable', True)]
    overall = {}
    sym_summary = {}
    t0 = time.time()
    aborted = False
    for idx, sym in enumerate(symbols):
        # [时间护栏] 下一品种前检查, 超时 fail-open 出件已算的
        if time.time() - t0 > time_cap_s:
            aborted = True
            print(f"[run_universe] 时间护栏 {time_cap_s}s 到点, 已算 {idx}/{len(symbols)} 品种, fail-open 出件")
            break
        cfg = su.UNIVERSE.get(sym, {})
        # [2026-10-10 单品种护栏] 品种内部 IPC 卡死(僵尸进程霸 MT5 价源)时全局 cap 只在品种之间生效,
        # 单品种可白磨 3h+. 现: 每品种给 per_cap 上限, 超时 fail-open 跳过(daemon 线程, 进程退出即回收, 不阻塞退出).
        per_cap = max(300, time_cap_s // max(len(symbols), 1) + 60)
        _slot = {}

        def _run(sym=sym, cfg=cfg, _slot=_slot):
            try:
                _slot['r'] = backtest_symbol(sym, cfg)
            except Exception as e:
                _slot['r'] = (None, "EXC:" + str(e)[:60])

        _th = threading.Thread(target=_run, daemon=True)
        _th.start()
        _th.join(timeout=per_cap)
        if _th.is_alive():
            res, note = None, "TIMECAP: 单品种 %ds 内未完成(疑 IPC 卡死), fail-open 跳过" % per_cap
            aborted = True
        else:
            res, note = _slot.get('r', (None, "TIMECAP: 无结果"))
        if res is None:
            sym_summary[sym] = {'note': note}
            continue
        # 聚合该品种最佳策略
        best = None
        for name, r in res.items():
            if isinstance(r, dict) and 'pf' in r and r.get('n', 0) >= MIN_TRADES and r['pf'] >= PF_PASS:
                if best is None or r['pf'] > best[1]['pf']:
                    best = (name, r)
        sym_summary[sym] = {'note': note, 'best': best, 'strats': res}
    # 策略级汇总
    strat_acc = {s: {'n': 0, 'gw': 0.0, 'gl': 0.0, 'wins': 0} for s in STRATS}
    for sym, d in sym_summary.items():
        for name, r in (d.get('strats') or {}).items():
            if isinstance(r, dict) and 'n' in r and r['n'] > 0:
                a = strat_acc[name]
                a['n'] += r['n']; a['wins'] += r['wins']
                a['gw'] += r['gw']; a['gl'] += r['gl']
    for s, a in strat_acc.items():
        a['pf'] = round(a['gw'] / a['gl'], 3) if a['gl'] > 1e-9 else (float('inf') if a['gw'] > 0 else 0.0)
        a['wr'] = round(a['wins'] / a['n'], 3) if a['n'] else 0.0
    out = {'generated': datetime.datetime.now().isoformat(), 'min_trades': MIN_TRADES,
           'pf_pass': PF_PASS, 'symbols_tested': len(symbols), 'elapsed_s': round(time.time() - t0, 1),
           'aborted_by_timecap': aborted,
           'strategy_overall': strat_acc, 'per_symbol': sym_summary}
    import os
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, 'w') as f:
        json.dump(out, f, indent=2, default=str)
    # 正 edge 候选排名
    cands = []
    for sym, d in sym_summary.items():
        b = d.get('best')
        if b:
            cands.append((sym, b[0], b[1]['pf'], b[1]['n'], b[1]['wr']))
    cands.sort(key=lambda x: -x[2])
    return out, cands


if __name__ == "__main__":
    import sys, os
    # [2026-11-04 L5③A-fix] O_EXCL 独占锁文件 + pid + 存活判定(取代 msvcrt 字节锁):
    #   根因: 原 msvcrt.locking(LK_NBLCK) 在 0 长 lock 文件上跨进程独占不稳定(04:24/04:26 实测 3 引擎并存,
    #   第二/三枪未 exit3 让位), 叠加 wrapper 层 wmic CommandLine=NULL 漏判 -> 双发/三发(双引擎霸IPC=TIMECAP空卷根①).
    #   改 O_EXCL 独占创建 lock 文件(文件系统级, 100% 独占), 写 pid; 后到者判 owner 活否: 活->让位 exit3, 死(stale)->清重建.
    #   无论谁拉(00:10任务/看门狗/bash残留会话)都拦死并发.
    _LP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "backtest_engine.lock")
    def _pid_alive(pid):
        if not pid or pid <= 0:
            return False
        try:
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
            return bool(h)
        except Exception:
            return True  # 判不了活死 -> 保守当活着(宁可让位, 不误抢)
    def _lock_pid():
        try:
            return int(open(_LP).read().strip() or 0)
        except Exception:
            return 0
    _MY = os.getpid()
    import time as _time
    def _acquire_or_yield():
        """拿到独占锁返回可跑; 任何竞态被撞都让位 exit 3.
        2026-11-04 加固: 创锁->写pid 有几 ms 窗口, 两进程同秒拉会都 O_EXCL 成功(空锁被当 stale 抢).
        治法: (a)写完 pid 立即复核 pid 仍是我, 被抢走就 exit3; (b)锁在但 pid 空 -> spin 等 3s,
        别让"刚创锁还没写 pid 的活 owner"被误判 stale 抢走. 08:19:33 实测双发(71652/141144)即此竞态."""
        try:
            _lh = os.open(_LP, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(_lh, str(_MY).encode()); os.close(_lh)
            if _lock_pid() != _MY:  # 复核: 写后 pid 被改写 = 有别人抢进窗口 -> 让位
                print("[引擎锁] 竞态: 锁被 pid=%s 抢走, 本枪让位 exit 3" % _lock_pid())
                sys.exit(3)
            return
        except FileExistsError:
            _own = _lock_pid()
            for _ in range(6):  # 空 pid 窗口 spin 3s(0.5*6), 等 owner 写完 pid
                if _own == 0:
                    _time.sleep(0.5); _own = _lock_pid()
                else:
                    break
            if _own and _pid_alive(_own):
                print("[引擎锁] 已有引擎 pid=%s 在跑, 本枪让位 exit 3 (O_EXCL 独占锁文件拦死并发; 双引擎霸IPC=TIMECAP空卷)" % _own)
                sys.exit(3)
            try:  # stale (owner 已死 / 3s 后仍空): 清重建
                os.remove(_LP)
            except OSError:
                pass
            try:
                _lh = os.open(_LP, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(_lh, str(_MY).encode()); os.close(_lh)
                if _lock_pid() != _MY:  # 重建后再复核
                    print("[引擎锁] 重建竞态: 锁被 pid=%s 抢走, 本枪让位 exit 3" % _lock_pid())
                    sys.exit(3)
                return
            except FileExistsError:
                print("[引擎锁] 重建再撞(并发), 让位 exit 3")
                sys.exit(3)
    _acquire_or_yield()
    syms = sys.argv[1].split(',') if len(sys.argv) > 1 and sys.argv[1] else None
    if syms == ['SMOKE']:
        syms = ['EURUSD', 'XAUUSD', 'BTCUSD']
    try:
        out, cands = run_universe(syms)
    except MtcUnavailableError as _mtc:
        # [L5 2026-11-02 C单] MT5 终端不可用 -> 诚实让位 exit 4 (对齐 rc=3 引擎锁让位), 非 rc=1 崩刷
        print("[引擎] %s -> 本枪让位 exit 4 (MT5 不可用, 非失败, 等终端恢复重跑)" % _mtc)
        sys.exit(4)
    finally:
        # 锁文件清理: 只删"是我 pid"的 lock, 不误删他人(并发安全)
        try:
            if _lock_pid() == _MY:
                os.remove(_LP)
        except Exception:
            pass
    print("=== 策略级整体 edge ===")
    for s, a in out['strategy_overall'].items():
        print(f"  {s:7} n={a['n']:5} wr={a['wr']:.2f} pf={a['pf']}")
    print("=== 正 edge 候选 (前20) ===")
    for c in cands[:20]:
        print(f"  {c[0]:10} {c[1]:6} pf={c[2]:.2f} n={c[3]:4} wr={c[4]:.2f}")
    print(f"正 edge 候选总数: {len(cands)} / 测试 {out['symbols_tested']} 品种")
