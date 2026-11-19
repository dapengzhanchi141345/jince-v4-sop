# -*- coding: utf-8 -*-
"""趋势腿(波段)打磨五验: P&L解剖 + 参数面A/B五验. 只读MT5, 无下单. GBK安全: 无emoji."""
import json, os, sys, math, datetime
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "multi_agent", "trading"))
import numpy as np
import MetaTrader5 as mt5

PY = sys.argv[0]
OUT = os.path.join(ROOT, "data", "leg_trend_polish.json")

# ── P&L 解剖 ─────────────────────────────────────────────
def load_state(path):
    try:
        with open(os.path.join(ROOT, path), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

states = {
    "fx":  load_state("data/pending_orders_state.json"),
    "cry": load_state("data/crypto_pending_state.json"),
    "eq":  load_state("data/equity_pending_state.json"),
}

mt5.initialize()
mt5.login(60137964, password=os.environ.get("MT5_PASS_60137964", ""), server="TradeMaxGlobal-Demo")
deals = mt5.history_deals_get(0, int(datetime.datetime.now().timestamp())) or []
outs = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT]
mt5.shutdown()

# 归因桶 (桶: n, 盈亏)
b_stop_sl = dict(n=0, pnl=0.0)     # 止损打掉: 已成交趋势单, 触SL平仓
b_sl_wide = dict(n=0, pnl=0.0)     # SL过宽: SL>2.5*ATR 的止损打掉
b_cancel  = dict(n=0, pnl=0.0)     # 未成交撤单: 挂单未触发被撤
b_d1_mis  = dict(n=0, pnl=0.0)     # D1方向误判: 撤单原因含D1/方向

# 从 state history 提取
for key in ("fx", "cry", "eq"):
    st = states[key]
    for x in st.get("history", []):
        e = x.get("evt", "")
        if e in ("撤单", "重估撤单"):
            b_cancel["n"] += 1
            why = str(x.get("why", ""))
            if "D1" in why or "方向" in why:
                b_d1_mis["n"] += 1
        elif e.startswith("L1"):
            pnl = x.get("pnl", 0.0)
            if "trend" in str(x.get("layer", "")):
                b_stop_sl["n"] += 1
                b_stop_sl["pnl"] += pnl

# 从 MT5 OUT deals 提取 (趋势层: 通过 ticket 关联 state filled / pending)
pending_tickets = {}
for key in ("fx", "cry", "eq"):
    st = states[key]
    for t, v in st.get("pending", {}).items():
        pending_tickets[str(t)] = v
    for t, v in st.get("filled", {}).items():
        m = t.replace("MT5_", "")
        pending_tickets[m] = v

trend_closed_pnl = 0.0
for d in outs:
    key = str(d.ticket)
    # 关联: ticket 在 pending/filled 中且有 layer=trend
    p = pending_tickets.get(key)
    if p and p.get("layer") == "trend":
        trend_closed_pnl += d.profit
        b_stop_sl["n"] += 1
        b_stop_sl["pnl"] += d.profit
        # SL 是否过宽 (SL 距离 > 2.5*ATR 粗略: 用 tp/sl 距离判断)
        entry = p.get("entry", 0)
        sl = p.get("sl", 0)
        if entry and sl and abs(entry - sl) > 0:
            # 保守: 若 |entry-sl| / |sl-tp_entry| 估算过宽
            pass  # 无法从 deal 判 ATR, 归到止损打掉桶

pnl_归因 = [
    {"桶": "止损打掉", "n": b_stop_sl["n"], "盈亏": round(b_stop_sl["pnl"], 2)},
    {"桶": "SL过宽", "n": b_sl_wide["n"], "盈亏": round(b_sl_wide["pnl"], 2)},
    {"桶": "未成交撤单", "n": b_cancel["n"], "盈亏": 0.0},
    {"桶": "D1方向误判", "n": b_d1_mis["n"], "盈亏": 0.0},
]

# ── A/B 参数五验 ─────────────────────────────────────────
from intraday_swing import atr as atr_fn, adx as adx_fn, donchian as don_fn

SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "BNBUSD", "XRPUSD", "ADAUSD"]  # T1 6币
N_BARS = 2600
ATR_P = 14

def fetch_ohlc(sym, count=N_BARS):
    mt5.initialize()
    mt5.login(60137964, password=os.environ.get("MT5_PASS_60137964", ""), server="TradeMaxGlobal-Demo")
    mt5.symbol_select(sym, True)
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, count)
    mt5.shutdown()
    if rates is None or len(rates) == 0:
        return None
    h = np.array([r["high"] for r in rates], dtype=np.float64)
    l = np.array([r["low"]  for r in rates], dtype=np.float64)
    c = np.array([r["close"] for r in rates], dtype=np.float64)
    return h, l, c

def donchian_break_events(h, l, c, n_dc=20):
    """返回 Donchian 突破事件列表: (i, side, entry, atr_val)
    side=+1 突破20期高点, side=-1 跌破20期低点
    现参数: BREAK_BUFFER=1.005, 2*ATR SL
    入场 = 突破价 * buffer (多) 或 低点 / buffer (空)
    """
    hi, lo = don_fn(h, l, n_dc)
    a = atr_fn(h, l, c, ATR_P)
    events = []
    for i in range(n_dc + 1, len(h)):
        if hi[i] <= 0 or lo[i] <= 0 or a[i] <= 0:
            continue
        # 多头: c[i] > hi[i-1] (突破20期高点)
        if c[i] > hi[i - 1]:
            events.append((i, +1, hi[i - 1], a[i]))
        # 空头: c[i] < lo[i-1]
        if c[i] < lo[i - 1]:
            events.append((i, -1, lo[i - 1], a[i]))
    return events

def simulate_event(i, side, ref, atr_val, c, h, l, horizon=48,
                  buffer=1.005, sl_atr=2.0, min_rr=2.0):
    """
    现参数回放:
    多头: entry = ref * buffer, SL = entry - sl_atr*atr, TP = entry + min_rr*(entry-SL)
    空头: entry = ref / buffer, SL = entry + sl_atr*atr, TP = entry - min_rr*(SL-entry)
    后续 K 根内触 SL → -1R; 触 TP → +min_rr R; 超时 → 0 (保守)
    返回 R (以 SL 距离为 1R)
    """
    if side > 0:
        entry = ref * buffer
        sl = entry - sl_atr * atr_val
        risk = sl_atr * atr_val
        tp = entry + min_rr * risk
        # 向前找 SL/TP
        out = 0.0
        for j in range(i + 1, min(i + 1 + horizon, len(c))):
            if l[j] <= sl:
                out = -1.0
                break
            if h[j] >= tp:
                out = min_rr
                break
        return out
    else:
        entry = ref / buffer
        sl = entry + sl_atr * atr_val
        risk = sl_atr * atr_val
        tp = entry - min_rr * risk
        out = 0.0
        for j in range(i + 1, min(i + 1 + horizon, len(c))):
            if h[j] >= sl:
                out = -1.0
                break
            if l[j] <= tp:
                out = min_rr
                break
        return out

# 拉取各品种 OHLC
data = {}
for sym in SYMS:
    try:
        data[sym] = fetch_ohlc(sym)
        print(f"[OK] {sym} bars={len(data[sym][0]) if data[sym] else 0}")
    except Exception as e:
        print(f"[!] {sym} fetch fail: {e}")
        data[sym] = None

# 五验参数网格
CURRENT = (1.005, 2.0)  # (buffer, sl_atr)
CANDIDATES = [
    (1.003, 2.0), (1.005, 2.0), (1.008, 2.0),
    (1.003, 2.5), (1.005, 2.5), (1.008, 2.5),
    (1.003, 3.0), (1.005, 3.0), (1.008, 3.0),
]

def run_grid(sym_data):
    """对单一品种跑全网格, 返回 {params: {win_rate, exp_R, max_dd, n, wins}}"""
    h, l, c = sym_data
    events = donchian_break_events(h, l, c)
    results = {}
    for buf, slatr in CANDIDATES:
        rs = [simulate_event(i, s, ref, av, c, h, l, buffer=buf, sl_atr=slatr)
              for (i, s, ref, av) in events if i + 48 < len(c)]
        if not rs:
            results[(buf, slatr)] = dict(win_rate=0, exp_R=0.0, max_dd=0.0, n=0)
            continue
        arr = np.array(rs)
        n = len(arr)
        wins = int((arr > 0).sum())
        # 最大回撤 (按 R 序列的净值曲线, 每笔 R 等权累加)
        eq = np.cumsum(arr)
        peak = np.maximum.accumulate(eq)
        dd = (peak - eq).max() if len(eq) > 0 else 0.0
        results[(buf, slatr)] = dict(
            win_rate = round(wins / n, 4),
            exp_R    = round(float(arr.mean()), 4),
            max_dd   = round(float(dd), 4),
            n        = n,
            wins     = wins,
        )
    return results, events

# 品种稳健性: 对每币单独评估
ab_grid = []
per_sym_results = {}
for sym, d in data.items():
    if d is None:
        continue
    res, evs = run_grid(d)
    per_sym_results[sym] = res

# 汇总 (同分母: 取所有品种并集事件, 每参数取平均 exp_R)
all_params = set(CANDIDATES)
all_results = {}
for p in all_params:
    exps, wins_tot, n_tot, dd_max = [], 0, 0, 0.0
    for sym, res in per_sym_results.items():
        r = res[p]
        exps.append(r["exp_R"])
        wins_tot += r["wins"]
        n_tot += r["n"]
        dd_max = max(dd_max, r["max_dd"])
    if exps:
        all_results[p] = dict(
            win_rate = round(wins_tot / n_tot, 4) if n_tot else 0,
            exp_R    = round(np.mean(exps), 4),
            max_dd   = round(dd_max, 4),
            n        = n_tot,
        )

ab_grid = [
    dict(params=f"buf={p[0]}/SL={p[1]}xATR" if p != CURRENT else f"buf={p[0]}/SL={p[1]}xATR[现]",
         win_rate=all_results[p]["win_rate"], exp_R=all_results[p]["exp_R"],
         max_dd=all_results[p]["max_dd"], n=all_results[p]["n"])
    for p in CANDIDATES
]

# 正态 p: 现参数 vs 最优候选
cur = all_results.get(CURRENT, dict(exp_R=0.0))
best_p = max(all_results, key=lambda p: all_results[p]["exp_R"])
best = all_results[best_p]
delta = round(best["exp_R"] - cur["exp_R"], 4)

# 显著性: 用全事件数做正态近似
total_n = sum(r["n"] for r in all_results.values()) // len(CANDIDATES)
import statistics
all_exp = [all_results[p]["exp_R"] for p in all_params]
mean_exp = statistics.mean(all_exp)
sd_exp = statistics.stdev(all_exp) if len(all_exp) > 1 else 1e-9
p_val = 0.5 if delta == 0 else min(1.0, abs(delta / (sd_exp + 1e-12)) / 1.0)
# 保守: p = 1 - 2*norm_cdf(|z|)
from math import erf
z = abs(delta) / (sd_exp / math.sqrt(max(total_n, 1))) if sd_exp > 0 else float("inf")
p_val = round(max(0.0, 1.0 - (2.0 * 0.5 * (1.0 + erf(z / math.sqrt(2.0))))), 6) if z != float("inf") else 0.0

# 品种稳健: ≥4/6 品种最优参数方向一致 (exp_R > 0)
n_pos = sum(1 for sym, res in per_sym_results.items()
            if res[best_p]["exp_R"] > 0)
robust = n_pos >= 4

# 参数甜蜜点: 相邻格无符号翻转
# 检查 3x3 网格内, 最优参数的 8 邻居 exp_R 是否均与最优同号
idx = CANDIDATES.index(best_p)
bi = idx // 3
bj = idx % 3
sign_best = 1 if all_results[best_p]["exp_R"] >= 0 else -1
sugar_point = True
for di in [-1, 0, 1]:
    for dj in [-1, 0, 1]:
        if di == 0 and dj == 0:
            continue
        ni = bi + di
        nj = bj + dj
        if 0 <= ni < 3 and 0 <= nj < 3:
            np_ = CANDIDATES[ni * 3 + nj]
            if all_results[np_]["exp_R"] * sign_best < 0:
                sugar_point = False

# walk-forward 三段 (全史 2600 根, 三段各 ~867 根)
def wf_seg(data_dict, n_bars=2600, segs=3):
    seg_len = n_bars // segs
    results = []
    for k in range(segs):
        sl0, sl1 = k * seg_len, min((k + 1) * seg_len, n_bars)
        seg_res = {}
        for p in all_params:
            exps = []
            for sym, d in data_dict.items():
                if d is None:
                    continue
                h, l, c = d
                h2, l2, c2 = h[sl0:sl1], l[sl0:sl1], c[sl0:sl1]
                evs = donchian_break_events(h2, l2, c2)
                rs = [simulate_event(i, s, ref, av, c2, h2, l2, buffer=p[0], sl_atr=p[1])
                      for (i, s, ref, av) in evs if i + 48 < len(c2)]
                if rs:
                    exps.append(float(np.mean(rs)))
            seg_res[p] = round(np.mean(exps), 4) if exps else 0.0
        results.append(seg_res)
    # 方向稳定性: 最优参数在每段均 exp_R > 0 且方向不变
    signs = [ (1 if r[best_p] >= 0 else -1) for r in results ]
    stable = len(set(signs)) == 1
    return results, stable

wf_segs, wf_stable = wf_seg(data)

# 五验汇总
five = {
    "样本":   f"全史H4x{N_BARS}根, 6币T1, 事件n={sum(r['n'] for r in ab_grid)}",
    "显著":   f"p={p_val}, delta_exp_R={delta}, z={z:.3f}",
    "稳健":   f"最优参数{best_p} 在 {n_pos}/6 品种 exp_R>0, 要求>=4/6",
    "甜蜜点": f"相邻格无符号翻转={sugar_point}",
    "时间稳定": f"walk-forward 3段方向不反转={wf_stable}",
}
five_pass_count = sum(1 for v in [p_val < 0.05, robust, sugar_point, wf_stable] if v)

# 最优参数字符串
best_str = f"buf={best_p[0]},SL={best_p[1]}xATR" if best_p != CURRENT else f"现参数(buf=1.005,SL=2.0xATR)已最优"

out = {
    "pnl归因": pnl_归因,
    "ab_grid": ab_grid,
    "同分母结论": {
        "最优参数": best_str,
        "delta": delta,
        "p": p_val,
        "最优exp_R": best["exp_R"],
        "现exp_R": cur["exp_R"],
        "现n": cur["n"],
    },
    "五验": five,
    "五验全过": f"{five_pass_count}/5 (显著+稳健+甜蜜点+时间稳定, 样本为描述)",
    "裁决": "接" if five_pass_count == 5 else "维持现参数",
    "walk_forward_三段": [
        {"段": k+1, "最优exp_R": segs[best_p], "现exp_R": segs[CURRENT]}
        for k, segs in enumerate(wf_segs)
    ],
}

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("[OK] 写出:", OUT)
print(json.dumps(out, ensure_ascii=False, indent=2)[:2000])
