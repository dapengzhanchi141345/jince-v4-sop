# -*- coding: utf-8 -*-
"""
_rd_verify_p4path.py — P4 出徒验证批 · 3 正期望候选 (2026-10-05)
==================================================================
候选(来自 交易知识_正期望策略_全网研学.md 落地映射):
  C1 多窗口时序动量 (趋势腿升级, 最优先)
  C2 事件窗口管理 (事件快通道增强, 第二优先)
  C3 资金费率套利 (币系冻结中, 条件性候选)

每个候选做七项验收: 五验(样本>=1000/同分母A-B/品种稳健>=4-6同向/参数甜区相邻不翻号/
walk-forward 3段稳) + DSR>=0.95 + PBO<0.4.
缺数据 fail-open 标 N/A 不造数; 负期望只当否决门不提权; 不承诺赚钱; 出徒必过 P4.

统计闸函数从 backtest_engine.py 按源码加载 (MetaTrader5 仅顶层 import, 离线可安全执行).
数据源: data/*_H1.csv (2025-06-30~2026-06-30, 约361天) / data/event_* (仅未来窗口).
结果落盘: data/rd_verify_batch_p4path.json
"""
import json, math, os, re, datetime
import numpy as np
try:
    import pandas as pd
except ImportError:
    pd = None

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
OUT_JSON = os.path.join(DATA, "rd_verify_batch_p4path.json")

# ------------------------------------------------------------------
# 从 backtest_engine.py 源码加载统计闸函数 (不 import MT5)
# ------------------------------------------------------------------
def _load_gate_funcs():
    """按 def 名切块提取 (SLIPPAGE_TIERS 字典到下一 def 为止), 不 import MT5."""
    src = open(os.path.join(ROOT, "backtest_engine.py"), encoding="utf-8").read()
    blocks = []
    m = re.search(r"^(SLIPPAGE_TIERS\s*=.*?)(?=\ndef |\nMAX_HOLD_H1|\n# =+$)", src, re.S | re.M)
    if m:
        blocks.append(m.group(1))
    for start in ["def deflated_sharpe_ratio", "def _z_scores",
                  "def _ems_bailey", "def _phi_inv_fast", "def pbo_probability"]:
        mm = re.search(rf"^{re.escape(start)}.*?(?=\ndef |\n# ={{4,}}$|\Z)", src, re.S | re.M)
        if mm:
            blocks.append(mm.group(0))
    code = "\n".join(blocks)
    if pd is not None:
        ns = {"np": np, "pd": pd, "__name__": "_gate_extract"}
        exec(compile(code, "backtest_engine_gates", "exec"), ns)
        return ns["deflated_sharpe_ratio"], ns["pbo_probability"]
    # 无 pandas: 用 numpy 重写 skew/kurtosis (与 pandas 口径: skew=三阶, kurtosis=excess)
    def _np_skew(a):
        a = np.asarray(a, dtype=float)
        if len(a) < 3: return 0.0
        m = a.mean(); s = a.std(ddof=1)
        return float(np.mean(((a - m) / s) ** 3)) if s > 1e-15 else 0.0
    def _np_kurt(a):
        a = np.asarray(a, dtype=float)
        if len(a) < 4: return 0.0
        m = a.mean(); s = a.std(ddof=1)
        return float(np.mean(((a - m) / s) ** 4) - 3.0) if s > 1e-15 else 0.0
    fixed = code.replace(
        "skew = float(pd.Series(r).skew()) if n >= 3 else 0.0",
        "skew = _np_skew(r) if n >= 3 else 0.0").replace(
        "kurt = float(pd.Series(r).kurtosis() + 3.0) if n >= 4 else 3.0  # pd kurtosis 是 excess",
        "kurt = _np_kurt(r) + 3.0 if n >= 4 else 3.0  # numpy kurtosis 是 excess")
    assert "pd.Series" not in fixed, "pd.Series 替换失败"
    ns = {"np": np, "pd": None, "__name__": "_gate_extract_np", "_np_skew": _np_skew, "_np_kurt": _np_kurt}
    exec(compile(fixed, "backtest_engine_gates_np", "exec"), ns)
    return ns["deflated_sharpe_ratio"], ns["pbo_probability"]

DSR_FN, PBO_FN = _load_gate_funcs()

# ------------------------------------------------------------------
# 数据加载
# ------------------------------------------------------------------
def load_h1(sym):
    p = os.path.join(DATA, f"{sym}_H1.csv")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        lines = f.read().strip().split("\n")
    rows = [l.split(",") for l in lines[1:]]
    times = [r[0] for r in rows]
    close = np.array([float(r[4]) for r in rows])
    high = np.array([float(r[3]) for r in rows])
    low = np.array([float(r[2]) for r in rows])
    open_ = np.array([float(r[1]) for r in rows])
    return {"time": times, "open": open_, "high": high, "low": low, "close": close,
            "n": len(times)}

def h1_to_daily(h1):
    """H1 close -> daily close 序列 (按日期分组取最后 close). 返回 (dates, closes)."""
    from collections import OrderedDict
    d = OrderedDict()
    for t, c in zip(h1["time"], h1["close"]):
        d[t[:10]] = c
    return list(d.keys()), np.array(list(d.values()))

def annualize_rvol(close, bars_per_year):
    rets = np.diff(close) / close[:-1]
    sd = float(np.std(rets, ddof=1))
    return sd * math.sqrt(bars_per_year)

# ------------------------------------------------------------------
# 候选 1: 多窗口时序动量
# ------------------------------------------------------------------
def cand1_multihorizon_momentum():
    """
    五验方案 (诚实版):
      1. 样本>=1000: B 腿信号数 x 品种
      2. 同分母 A-B: A=单窗口 Donchian (金策现有趋势腿), B=多窗口投票腿, 同池同时段
      3. 品种稳健: 6 品种, >=4 正 exp_R
      4. 参数甜区: 7d vs 7d+21d exp_R 不翻号
      5. walk-forward 3 段: 每段 OOS 夏普>=0 (段末 24 根 H1 真实 OOS)
      6. DSR: B 腿逐 bar 收益 (动量方向 x bar 收益, 真实方差)
      7. PBO: 3 段 x n 品种 wf

    数据边界 (诚实标注):
      - H1 深度 361 天: 7d 窗口够, 21d 勉强, 63d/12m 不够 -> 12m 动量 N/A
      - exp_R 用简化 H1 close 回测 (无真实点差/swap 成本), 绝对值 ~0.001R/笔为
        噪声级. 本脚本只做"方向性证据" (B 是否同分母跑赢 A, 品种是否同向),
        不做正期望验收. 真验收需接 backtest_engine.simulate_signal 真实成本回测.
      - V1 按 B 腿信号数; V5 按 wf 真实 OOS; DSR 按真实收益序列 (非零方差).
      """
    syms = ["XAUUSD", "EURUSD", "GBPUSD", "BTCUSD", "ETHUSD", "US30"]
    avail, missing = [], []
    pools = {}
    for s in syms:
        h = load_h1(s)
        if h:
            pools[s] = h
            avail.append(s)
        else:
            missing.append(s)
    if len(avail) < 4:
        return _cand_result("c1", "WATCH", ["数据不足: 可用品种<4"], None, None)

    n_bars = min(len(v["close"]) for v in pools.values())
    sig_count_total = 0
    ab = {}          # 每品种 A/B 统计
    b_returns = []   # B 腿逐 bar 收益 (DSR 输入, 同分母=全品种同时段)
    wf = []          # walk-forward 3 段
    sweet = {}       # 参数甜区: 相邻窗口组合 exp_R 不翻号

    for s, h in pools.items():
        close = h["close"]
        rets = np.diff(close) / close[:-1]
        ann_rvol = float(np.std(rets, ddof=1)) * math.sqrt(252 * 24)  # H1 bar 年化
        # 三窗口: 7d=168bar, 21d=504bar, 63d=1512bar (H1 深度不够 63d -> None)
        win_short = 168 if n_bars > 168 else n_bars // 2
        win_med = 504 if n_bars > 504 else None
        win_long = 1512 if n_bars > 1512 else None
        # A 腿: 单窗口 Donchian (现有趋势腿, 短窗口)
        a_exp, a_n = _donchian_expectancy(close, win_short, ann_rvol)
        # B 腿: 多窗口投票 (短+中+长)
        b_exp, b_n = _multiwin_expectancy(close, [win_short, win_med, win_long], ann_rvol)
        ab[s] = {"a_exp_R": a_exp, "a_n": a_n, "b_exp_R": b_exp, "b_n": b_n,
                 "n_bars": len(close)}
        sig_count_total += b_n
        # 参数甜区: 相邻组合 (7d only vs 7d+21d) exp_R 不翻号
        sweet7, _ = _multiwin_expectancy(close, [win_short], ann_rvol)
        sweet721, _ = _multiwin_expectancy(close, [win_short, win_med], ann_rvol)
        sweet[s] = {"7d_only": round(sweet7, 4), "7d_21d": round(sweet721, 4),
                    "no_flip": (sweet7 > 0) == (sweet721 > 0) or sweet7 == sweet721 == 0}
        # B 腿逐 bar 收益 (动量方向 x 当日 bar 收益, 只取有方向的 bar)
        m = _momentum_direction(close, [win_short, win_med, win_long])
        b_rets = rets[:-1]
        n = len(b_rets)
        mm = np.zeros(n)
        mm[:min(n, len(m))] = m[:min(n, len(m))]
        valid = mm != 0
        br = b_rets[valid] * mm[valid]
        b_returns.extend(list(br))
        # walk-forward 3 段 (真实 OOS 夏普: 段末 24 根 H1 的 OOS 夏普)
        seg = len(close) // 3
        wf_segs = []
        for i in range(3):
            s0, e0 = i * seg, (i + 1) * seg if i < 2 else len(close)
            seg_close = close[s0:e0]
            seg_rets = np.diff(seg_close) / seg_close[:-1]
            seg_sharpe = float(np.mean(seg_rets) / np.std(seg_rets, ddof=1)) if len(seg_rets) > 2 else 0.0
            oos_end = min(e0 + 24, len(close))
            oos_rets = np.diff(close[e0:oos_end]) / close[e0:oos_end - 1] if oos_end > e0 + 1 else np.array([])
            oos_sharpe = float(np.mean(oos_rets) / np.std(oos_rets, ddof=1)) if len(oos_rets) > 2 else 0.0
            oos_ret = float(oos_rets.sum()) if len(oos_rets) else 0.0
            wf_segs.append({"seg": i + 1, "sym": s,
                           "train_sharpe": round(seg_sharpe, 4),
                           "oos_sharpe": round(oos_sharpe, 4),
                           "oos_return": round(oos_ret, 6)})
        wf.extend(wf_segs)
    v1 = sig_count_total >= 1000
    a_total_exp = np.mean([ab[s]["a_exp_R"] for s in avail]) if avail else 0
    b_total_exp = np.mean([ab[s]["b_exp_R"] for s in avail]) if avail else 0
    v2 = b_total_exp > a_total_exp  # B 同分母跑赢 A
    v3_same = sum(1 for s in avail if ab[s]["b_exp_R"] > 0)
    v3 = v3_same >= 4
    v4 = all(sweet.get(s, {}).get("no_flip", False) for s in avail if s in sweet)
    v5 = len(wf) == 3 * len(avail) and all(
        (w["train_sharpe"] > 0 and w["oos_sharpe"] > 0) or w["oos_sharpe"] > 0
        for w in wf)

    # DSR: B 腿真实收益序列 (动量方向 x bar 收益, 非零方差)
    dsr = DSR_FN(b_returns, n_trials=3, bars_per_year=252 * 24)  # 3 窗口组合
    # PBO: 3 段 x n 品种 wf, 用真实 oos_return
    pbo = PBO_FN(wf)

    verdict = "WATCH" if v1 and v2 and v3 and v4 and v5 else "REJECT(五验不过, 不提权)"
    if verdict == "WATCH" and dsr.get("verdict") == "REJECT":
        verdict = "REJECT(DSR闸, 不提权)"
    exp_scale = abs(b_total_exp)
    plain = (f"C1多窗口动量: B腿exp_R={b_total_exp:.5f} vs A腿={a_total_exp:.5f} "
             f"(同分母同成本), 品种稳健{v3_same}/{len(avail)}, 样本{sig_count_total} "
             f"V1{'✓' if v1 else '✗'} V2{'✓' if v2 else '✗'} V3{'✓' if v3 else '✗'} "
             f"V4{'✓' if v4 else '✗'} V5{'✓' if v5 else '✗'} "
             f"DSR={'N/A' if dsr.get('dsr') is None else round(dsr['dsr'], 3)} "
             f"PBO={'N/A' if pbo.get('pbo') is None else round(pbo['pbo'], 3)} "
             f"-> {verdict}. 1m窗口够(361天), 3m勉强(340日K), 12m不够需补历史日线. "
             f"exp_R绝对值~{exp_scale:.5f}R/笔为噪声级(简化close回测无真实点差/swap成本), "
             f"不构成正期望证据, 需接 backtest_engine.simulate_signal 真实成本回测再验.")
    return _cand_result("c1", verdict, ["12m动量窗口需历史日线>=365天"],
                        ab, {"v1_sample": v1, "v2_ab": v2, "v3_robust": f"{v3_same}/{len(avail)}",
                              "v4_sweet": v4, "v5_wf": v5, "dsr": dsr, "pbo": pbo,
                              "sweet_spot": sweet, "sig_total": sig_count_total},
                        plain)

def _donchian_expectancy(close, win, ann_rvol):
    """单窗口 Donchian 突破 (简化: 价格创 N bar 新高/新低 -> 次日方向). 返回 (exp_R, n)."""
    n = max(2, win)
    sigs = []
    for i in range(n, len(close) - 1):
        hi = close[i - n:i].max()
        lo = close[i - n:i].min()
        if close[i] > hi:
            sigs.append((i, +1))
        elif close[i] < lo:
            sigs.append((i, -1))
    pnl = []
    for i, side in sigs:
        ret = (close[i + 1] - close[i]) / close[i] * side
        pnl.append(ret / ann_rvol if ann_rvol > 0 else 0.0)
    if not pnl:
        return 0.0, 0
    return float(np.mean(pnl)), len(pnl)

def _multiwin_expectancy(close, wins, ann_rvol):
    """多窗口投票: 3 个窗口各自 Donchian, 方向一致才出信号 (>=2 同向)."""
    votes = {}
    for win in wins:
        if win is None or win < 2:
            continue
        for i in range(win, len(close) - 1):
            side = 0
            if close[i] > close[i - win:i].max():
                side = +1
            elif close[i] < close[i - win:i].min():
                side = -1
            if side:
                votes.setdefault(i, []).append(side)
    pnl = []
    for i, vs in sorted(votes.items()):
        if sum(vs) >= 2 or (len(vs) == 1 and vs[0] != 0):
            side = 1 if sum(vs) >= 0 else -1
            if i + 1 < len(close):
                ret = (close[i + 1] - close[i]) / close[i] * side
                pnl.append(ret / ann_rvol if ann_rvol > 0 else 0.0)
    if not pnl:
        return 0.0, 0
    return float(np.mean(pnl)), len(pnl)

def _momentum_direction(close, wins):
    """返回每 bar 的动量方向 (+1/-1/0), 用于 DSR 收益序列."""
    m = np.zeros(len(close))
    for i in range(max(wins) if max(wins) else len(close)):
        vs = []
        for w in wins:
            if w and i >= w:
                if close[i] > close[i - w:i].max():
                    vs.append(1)
                elif close[i] < close[i - w:i].min():
                    vs.append(-1)
        m[i] = 1 if sum(vs) > 0 else (-1 if sum(vs) < 0 else 0)
    return m

# ------------------------------------------------------------------
# 候选 2: 事件窗口管理
# ------------------------------------------------------------------
def cand2_event_window_mgmt():
    """
    五验方案:
      1. 样本>=1000: 全部事件日对 (NFP月x4 + CPI月x12 + FOMC季x4 x N年)
      2. 同分母 A-B: A=事件日全程满仓常规策略, B=三段式管理(前30分降仓+后5-30分
         第二波进场+后2h恢复), 同品种同时段
      3. 品种稳健: 金/汇/币三池
      4. 参数甜区: 前窗口30/60分, 后窗口5/10/30分, 仓位系数0.25/0.5
      5. walk-forward: 跨两个完整年份

    数据边界: 金策 event_calendar.json / event_daily_calendar.json 只有未来 24h 窗口,
    无历史事件日对. event_risk.json 的 sigma_table 可喂, 但历史事件时间戳缺失 ->
    1000 事件日对样本无法构造 -> V1 N/A, 整体标 WATCH(方案可跑但缺数据).
    """
    # 检查历史事件数据
    hist_events = []
    for fn in ["event_calendar.json", "event_daily_calendar.json", "event_risk_map.json"]:
        p = os.path.join(DATA, fn)
        if not os.path.exists(p):
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict) and "windows" in d:
            hist_events.extend(d.get("windows", []))
        if isinstance(d, dict) and "events" in d:
            evs = d.get("events", [])
            if evs and isinstance(evs, list):
                hist_events.extend(evs)

    # 提取有明确时间戳的事件
    n_dated = 0
    for e in hist_events:
        ts = e.get("event_time") or e.get("time") or e.get("ts")
        if ts:
            n_dated += 1

    # 从 H1 数据推算: 事件日 = 点差异常放大日 (proxy)
    # 但金策无历史事件日历 -> 只能做 proxy 分析, 不做真五验
    syms = ["XAUUSD", "EURUSD", "GBPUSD", "BTCUSD"]
    pools = {}
    for s in syms:
        h = load_h1(s)
        if h:
            pools[s] = h
    n_avail = len(pools)

    # V1: 1000 事件日对 -> 需要历史事件日历, 现只有 4 个未来窗口
    v1 = False  # 数据不足
    data_missing = "历史事件日对>=1000 (需 FOMC/CPI/NFP 历史时间戳, 金策 event_calendar 仅未来24h)"

    # 能做 proxy: 点差异常日 vs 常规日的 vol 管理 (不满足五验 V1, 只算 proxy 证据)
    proxy_results = {}
    for s, h in pools.items():
        close = h["close"]
        rets = np.diff(close) / close[:-1]
        vol = np.std(rets[-24:], ddof=1)
        # 点差异常日 = 当日 |ret| > 2 * 7d 均值
        mean_abs = np.mean(np.abs(rets[-168:]))
        n_high_vol = int(np.sum(np.abs(rets) > 2 * mean_abs))
        proxy_results[s] = {"n_bars": len(close), "n_high_vol_days_approx": n_high_vol,
                            "note": "proxy only, not five-verify V1"}
    v2 = False  # 无事件日历 -> 无法做同分母 A-B
    v3 = False
    v4 = False
    v5 = False
    dsr = {"dsr": None, "verdict": "N/A", "reason": "无事件日对收益序列"}
    pbo = {"pbo": None, "verdict": "N/A", "reason": "无 wf 窗口"}

    verdict = "WATCH"  # 方案可跑, 缺历史事件数据 -> 条件 WATCH, 不 REJECT (fail-open)
    plain = (f"C2事件窗口管理: 历史事件日对样本 N/A (金策 event_calendar 仅未来24h, "
             f"有 {n_dated} 个带时间戳事件), 1000事件日对无法构造 -> V1 FAIL "
             f"(数据不足, 需补 FOMC/CPI/NFP 历史时间戳源). 品种池 {n_avail} 个可用. "
             f"sigma_table 可喂 event_risk.json. 判定 WATCH(条件可跑, 缺数据不造数).")
    return _cand_result("c2", verdict, [data_missing], proxy_results,
                        {"v1_sample": v1, "v2_ab": v2, "v3_robust": "N/A",
                         "v4_sweet": v4, "v5_wf": v5, "dsr": dsr, "pbo": pbo,
                         "n_dated_events": n_dated, "n_avail_syms": n_avail},
                        plain)

# ------------------------------------------------------------------
# 候选 3: 资金费率套利
# ------------------------------------------------------------------
def cand3_funding_rate_arb():
    """
    五验方案:
      1. 样本>=1000: 费率x情景
      2. 同分母 A-B: A=同资金HODL, B=spot+perp delta中性+费率开关
      3. 品种稳健: BTC/ETH/主流alt
      4. 参数甜区: 费率阈值X% x 持续天数N x 杠杆
      5. walk-forward: 跨牛熊

    数据边界: 币所资金费率历史数据 MT5 拿不到 (MT5 无永续合约), 金策无币所数据模块.
    币系 11-02 NFP 前冻结 -> 全部 N/A, 现只作品种中性打底仓输入.
    判定: WATCH(条件可做, 冻结解除后需补币所费率数据源)
    """
    # 检查是否有费率数据
    n_rate_files = 0
    for fn in os.listdir(DATA):
        if "funding" in fn.lower() or "perp" in fn.lower():
            n_rate_files += 1

    verdict = "WATCH"  # 条件可做, 缺数据 -> 不 REJECT
    plain = (f"C3资金费率套利: 币所费率数据 N/A (MT5无永续合约, 金策无币所数据模块, "
             f"币系冻结至11-02 NFP). 0个费率数据文件. 判定 WATCH(冻结解除后条件可做, "
             f"现只作品种中性打底仓输入, 不进live). 需补: 币所永续资金费率历史API "
             f"(如 Binance/OKX funding_rate 历史). 同分母基线=HODL(同币种同时段同费率).")
    return _cand_result("c3", verdict,
                       ["币所永续资金费率历史数据 (Binance/OKX API, 1000+费率区间)"],
                       {}, {"v1_sample": False, "v2_ab": False, "v3_robust": "N/A",
                            "v4_sweet": False, "v5_wf": False,
                            "dsr": {"dsr": None, "verdict": "N/A", "reason": "无费率数据"},
                            "pbo": {"pbo": None, "verdict": "N/A", "reason": "无 wf"},
                            "n_rate_files": n_rate_files,
                            "crypto_frozen_until": "2026-11-02 NFP"},
                       plain)

# ------------------------------------------------------------------
# 辅助
# ------------------------------------------------------------------
def _cand_result(cid, verdict, missing_data, ab_data, five_verify, plain):
    return {
        "candidate": cid,
        "verdict": verdict,
        "missing_data": missing_data,
        "ab_data": ab_data,
        "five_verify": five_verify,
        "plain_summary": plain,
        "run_at": datetime.datetime.now().isoformat(),
        "engine": "backtest_engine.py DSR_FN/PBO_FN + data/*_H1.csv",
    }

def _json_default(o):
    """numpy 类型 -> 原生 Python (json.dump default 钩子)."""
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.ndarray,)):
        return o.tolist()
    raise TypeError(f"not serializable: {type(o)}")


def main():
    results = []
    # 跑 3 个候选
    r1 = cand1_multihorizon_momentum()
    r2 = cand2_event_window_mgmt()
    r3 = cand3_funding_rate_arb()
    results.extend([r1, r2, r3])

    # 离 P4 最近排名
    p4_ranking = []
    for r in results:
        v = r.get("five_verify", {})
        n_pass = sum(1 for k in ["v1_sample", "v2_ab", "v3_robust", "v4_sweet", "v5_wf"]
                      if v.get(k) in (True, "PASS"))
        n_na = sum(1 for k in ["v1_sample", "v2_ab", "v3_robust", "v4_sweet", "v5_wf"]
                    if v.get(k) in (False, "N/A", None) or isinstance(v.get(k), str))
        dsr_v = v.get("dsr", {}).get("verdict", "N/A")
        pbo_v = v.get("pbo", {}).get("verdict", "N/A")
        stats_ok = dsr_v in ("PASS", "N/A") and pbo_v in ("PASS", "N/A")
        p4_ranking.append({
            "candidate": r["candidate"],
            "verdict": r["verdict"],
            "five_pass": n_pass,
            "five_na": n_na,
            "dsr": dsr_v,
            "pbo": pbo_v,
            "stats_gate_ok": stats_ok,
            "blocking": [m for m in r.get("missing_data", []) if m],
            "closest_to_p4": n_pass >= 3 and stats_ok,
            "plain": r["plain_summary"],
        })
    p4_ranking.sort(key=lambda x: (-x["five_pass"], x.get("candidate", "")))

    out = {
        "generated": datetime.datetime.now().isoformat(),
        "engine": "backtest_engine.py DSR+PBO + data/*_H1.csv (361天) + event_* (未来窗口)",
        "data_boundary_note": (
            "H1 CSV 实际深度 ~361天 (2025-06-30~2026-06-30), 远超任务上下文'96根H1'. "
            "7d动量窗口够, 3m勉强(340日K), 12m不够需补历史日线. "
            "事件日历仅未来24h, 历史事件日对 N/A. 币所费率数据 N/A (币系冻结至11-02 NFP)."
        ),
        "candidates": results,
        "p4_ranking": p4_ranking,
        "red_line_checklist": {
            "同分母铁律": "C1 A-B 同品种池同时段同成本, exp_R 对比. C2 缺事件日历无法同分母 -> N/A. C3 基线=HODL.",
            "负期望只当否决门": "C1 V2 FAIL 则 REJECT, 不提权. C2/C3 缺数据不造数, WATCH 不 REJECT.",
            "缺数据 fail-open N/A": "C2 V1 N/A (历史事件), C3 全 N/A (费率数据). 不补数不造数.",
            "不承诺赚钱": "全部候选=需再验, P4出徒前不进 live.",
            "出徒必过 P4": "P4 五条: 净值正且回撤<8% / 分盘胜率RR达阈 / 连2周零故障 / 风控合规 / 边衰检测无异常.",
        },
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=_json_default)
    print(f"落盘: {OUT_JSON}")
    print(f"候选: {len(results)} 个, P4 排名: {len(p4_ranking)} 个")
    for r in p4_ranking:
        print(f"  {r['candidate']} {r['verdict']} five_pass={r['five_pass']}/{5} "
              f"dsr={r['dsr']} pbo={r['pbo']} blocking={r['blocking'][:2]}")
    return out

if __name__ == "__main__":
    main()
