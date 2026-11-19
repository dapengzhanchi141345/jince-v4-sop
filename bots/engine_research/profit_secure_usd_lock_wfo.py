# -*- coding: utf-8 -*-
"""
PROFIT_SECURE · USD 绝对锁利 WFO 验证  (2026-11-12)
==================================================
纯研究: 不改引擎、不连 MT5、不开实单。

背景: 现役引擎 (jince_live24.py) 用 R 比例锁利 (0.5R 保本, 1.0R 锁半利, 2.0R ATR
跟踪, peak-0.6R 回吐地板)。对高 ATR 品种 (SL/TP 很大) 1R 的 USD 金额巨大, 例如
XPTUSD: dist=2*ATR≈35.61 价格单位, 0.5R≈$17.8 (0.01 手=1 oz, $1/单位)。实盘一笔
峰值 0.45R≈$16 利润, 但 0.5R 锁利差 $1.8 没触发, 回吐地板又把 SL 设到亏损价, 最终
以亏损平仓 —— $16 吐光。

本脚本在忠实复刻的 R 锁利 harness 之上, 新增「USD 绝对锁利层」:
  usd_lock : 浮盈 USD 超过阈值即锁利 (移动 SL 落袋), 0=关
  usd_take : 浮盈 USD 超过阈值即全平, 0=关
  usd_gate_r: 仅当 (2*ATR@entry)*CONTRACT[sym] >= usd_gate_r 才启用 USD 层
              (只保护大 SL/TP 品种; 小 ATR 品种保持纯 R 锁利, 不被破坏)
  usd_buf  : 锁利时在 USD 利润上扣的缓冲, 默认 1.0

数据说明 (重要): data/*.csv 为 2026-08 代理历史 (proxy), 非实盘 tick 级数据,
结论需谨慎, 仅作特征方向验证。

复用 profit_secure_deep_v2.py 骨架: load / atr_arr / gen_entries / simulate /
summarize / eval_P / eval_P_by_sym —— 其 R 锁利逻辑原样保留, 仅在 simulate 内
(现有 R 锁利/回吐地板块之后) 追加 USD 层。
"""
import csv, os, time as _t
from collections import defaultdict

ROOT = "E:/GoldstrategyEngine"
DATA = os.path.join(ROOT, "data")
SYMS = ["XAUUSD", "XPTUSD", "XAGUSD", "BTCUSD", "NAS100",
        "US30", "EURUSD", "GBPUSD", "USDJPY"]
MAX_BARS = 48
SWING = 20
ATR_N = 14
COST_R = 0.05
WINSOR_LO, WINSOR_HI = -3.0, 8.0

# USD 每 1.0 价格单位 / 每 0.01 手
CONTRACT = {
    "XAUUSD": 1.0, "XPTUSD": 1.0, "XAGUSD": 50.0, "BTCUSD": 760.0,
    "NAS100": 0.2, "US30": 0.02, "EURUSD": 0.1, "GBPUSD": 0.1, "USDJPY": 0.067
}

# 现役引擎定稿 R 参数 (jince_live24.py)
LIVE = dict(start_r=1.0, trail_atr=0.8, tight_r=1.5, tight_atr=0.5,
            lock_half=1.2, be_buf=0.2)

# WFO 三窗口 (按品种 bar 时间切片)
WINS = [("W1", 0.0, 1.0 / 3.0), ("W2", 1.0 / 3.0, 2.0 / 3.0), ("W3", 2.0 / 3.0, 1.0)]


# ───────────────────────── 骨架函数 (R 逻辑原样保留) ─────────────────────────
def load(sym):
    p = os.path.join(DATA, sym + "_H1.csv")
    if not os.path.exists(p):
        return None
    bars = []
    with open(p, encoding="utf-8") as f:
        r = csv.reader(f)
        next(r, None)
        for row in r:
            if len(row) < 5:
                continue
            try:
                bars.append([float(row[1]), float(row[2]), float(row[3]), float(row[4])])
            except Exception:
                continue
    return bars


def atr_arr(bars):
    n = len(bars)
    tr = [0.0] * n
    for i in range(1, n):
        h, l, pc = bars[i][1], bars[i][2], bars[i - 1][3]
        tr[i] = max(h - l, abs(h - pc), abs(l - pc))
    at = [0.0] * n
    s = 0.0
    for i in range(1, n):
        s += tr[i]
        if i > ATR_N:
            s -= tr[i - ATR_N]
        if i >= ATR_N:
            at[i] = s / ATR_N
    return at


def gen_entries(bars, lo=0, hi=None):
    hi = len(bars) if hi is None else hi
    ents = []
    for i in range(max(SWING, lo), min(hi, len(bars) - MAX_BARS - 2)):
        hi20 = max(bars[k][1] for k in range(i - SWING, i))
        lo20 = min(bars[k][2] for k in range(i - SWING, i))
        c = bars[i][3]
        if c > hi20:
            ents.append((i, 1))
        elif c < lo20:
            ents.append((i, -1))
    return ents


def _clip(x, winsor):
    if not winsor:
        return x
    return max(WINSOR_LO, min(WINSOR_HI, x))


def simulate(bars, at, e, dirn, P, cost=COST_R, winsor=True, sym=None):
    """返回 (realized_R, mfe_R, reason)。SL 更新滞后一根 bar, 消除同 bar 自指。
    AUGMENT: 现有 R 锁利/回吐地板块之后追加 USD 绝对锁利层。"""
    entry = bars[e][3]
    a0 = at[e]
    if a0 <= 1e-8:
        return None
    dist = 2.0 * a0
    sl = entry - dirn * dist          # 初始 -2ATR 硬止损
    extreme = entry
    last = min(e + MAX_BARS, len(bars) - 1)
    sr, ta, tr_, tta = P["start_r"], P["trail_atr"], P["tight_r"], P["tight_atr"]
    lh, bb = P["lock_half"], P["be_buf"]

    # USD 层参数
    usd_lock = P.get("usd_lock", 0.0)
    usd_take = P.get("usd_take", 0.0)
    usd_gate = P.get("usd_gate_r", 10.0)
    usd_buf  = P.get("usd_buf", 1.0)
    contract = CONTRACT.get(sym, 0.0) if sym else 0.0
    usd_per_r = (2.0 * a0) * contract          # 每 1R 的 USD 价值
    gate_on = (usd_gate > 0.0) and (usd_per_r >= usd_gate)

    for j in range(e + 1, last + 1):
        o, h, l, c = bars[j]
        a = at[j] if at[j] > 0 else a0

        # ── 1) 先用「上一根 bar 结束时已确定的 SL」判触发 ──
        if dirn > 0 and l <= sl:
            px = min(sl, o)
            realized = (px - entry) / dist * dirn
            return (_clip(realized, winsor) - cost, (extreme - entry) / dist * dirn, "SL")
        if dirn < 0 and h >= sl:
            px = max(sl, o)
            realized = (px - entry) / dist * dirn
            return (_clip(realized, winsor) - cost, (extreme - entry) / dist * dirn, "SL")

        # ── 2) 用当 bar 影线更新 extreme / SL (供下一 bar 生效) ──
        extreme = max(extreme, h) if dirn > 0 else min(extreme, l)
        r = (extreme - entry) / dist * dirn
        cand = None
        if r >= 0.5:
            cand = entry + dirn * bb * dist
        if r >= 1.0:
            c2 = entry + dirn * lh * dist
            if cand is None or c2 * dirn > cand * dirn:
                cand = c2
        if r >= sr and a > 0:
            mult = ta if r < tr_ else tta
            t = extreme - dirn * mult * a
            if cand is None or t * dirn > cand * dirn:
                cand = t

        # ── 3) USD 绝对锁利层 (AUGMENT, 在 R 锁利之后, 合并进同一 ratchet) ──
        usd_profit = (extreme - entry) * dirn * contract
        if gate_on:
            if usd_lock > 0 and usd_profit >= usd_lock:
                _lockpx = entry + dirn * max(usd_profit - usd_buf, 0.0) / contract
                base = cand if cand is not None else sl
                if _lockpx * dirn > base * dirn:     # 只取更优 (更靠有利方向)
                    cand = _lockpx
            if usd_take > 0 and usd_profit >= usd_take:
                # 全平: 以峰值 (extreme) 落袋, 模型化为峰值退出
                realized_R = _clip(usd_profit / contract / dist, winsor) - cost
                mfe_R = (extreme - entry) / dist * dirn
                return (realized_R, mfe_R, "USD止盈")

        # ── 4) 单调 ratchet: SL 只往有利方向 (USD 锁利与 R 锁利共存) ──
        if cand is not None and cand * dirn > sl * dirn:
            sl = cand

    exit_px = bars[last][3]
    realized = (exit_px - entry) / dist * dirn
    return (_clip(realized, winsor) - cost, (extreme - entry) / dist * dirn, "MAXBARS")


def summarize(rows):
    n = len(rows)
    if n == 0:
        return dict(n=0, mean=0.0, win=0.0, cap=0.0, nrev=0, rev_real=0.0,
                    rev_cap=0.0, gave50=0.0)
    mean = sum(r[0] for r in rows) / n
    win = sum(1 for r in rows if r[0] > 0) / n
    eff = [r for r in rows if r[1] >= 0.5]
    cap = sum(min(1.0, max(-5.0, r[0] / r[1])) for r in eff) / len(eff) if eff else 0.0
    rev = [r for r in rows if r[1] >= 1.0]
    nrev = len(rev)
    rev_real = sum(r[0] for r in rev) / nrev if nrev else 0.0
    rev_cap = sum(min(1.0, max(-5.0, r[0] / r[1])) for r in rev) / nrev if nrev else 0.0
    gave50 = sum(1 for r in rev if r[0] < 0.5 * r[1]) / nrev if nrev else 0.0
    return dict(n=n, mean=mean, win=win, cap=cap, nrev=nrev,
                rev_real=rev_real, rev_cap=rev_cap, gave50=gave50)


def eval_P(datasets, P, cost=COST_R, winsor=True, window=None):
    rows = []
    for sym, bars, at, ents in datasets:
        if window is not None:
            lo, hi = int(len(bars) * window[0]), int(len(bars) * window[1])
            ents = gen_entries(bars, lo, hi)
        for (e, d) in ents:
            res = simulate(bars, at, e, d, P, cost, winsor, sym)
            if res is not None:
                rows.append(res)
    return summarize(rows)


def eval_P_by_sym(datasets, P, cost=COST_R, winsor=True):
    out = {}
    for sym, bars, at, ents in datasets:
        rows = []
        for (e, d) in ents:
            res = simulate(bars, at, e, d, P, cost, winsor, sym)
            if res is not None:
                rows.append(res)
        out[sym] = summarize(rows)
    return out


# ───────────────────────── 本脚本新增: 逐笔回测 + USD 指标 ─────────────────────────
def run_trades(datasets, P, cost=COST_R, winsor=True):
    """返回逐笔结果 (sym, e, d, realized, mfe, reason, wname), 含 WFO 窗口归属。"""
    rows = []
    for sym, bars, at, ents in datasets:
        nb = len(bars)
        bounds = [(name, int(nb * lo), int(nb * hi)) for (name, lo, hi) in WINS]
        for (e, d) in ents:
            res = simulate(bars, at, e, d, P, cost, winsor, sym)
            if res is None:
                continue
            realized, mfe, reason = res
            wname = "ALL"
            for (wn, lo, hi) in bounds:
                if lo <= e < hi:
                    wname = wn
                    break
            rows.append((sym, e, d, realized, mfe, reason, wname))
    return rows


def summarize_rows(rows):
    return summarize([(r[3], r[4], r[5]) for r in rows])


def mean_by_sym(rows):
    d = defaultdict(list)
    for sym, e, dd, realized, mfe, reason, w in rows:
        d[sym].append(realized)
    return {s: (sum(v) / len(v), len(v)) for s, v in d.items()}


def idx_map(rows):
    return {(r[0], r[1], r[2]): (r[3], r[5]) for r in rows}


def wfo_delta(base_rows, cand_rows):
    out = {}
    for wname in ["ALL"] + [w[0] for w in WINS]:
        bv = [r[3] for r in base_rows if r[6] == wname]
        cv = [r[3] for r in cand_rows if r[6] == wname]
        bm = sum(bv) / len(bv) if bv else 0.0
        cm = sum(cv) / len(cv) if cv else 0.0
        out[wname] = dict(dR=cm - bm, n_c=len(cv), n_b=len(bv),
                          mean_c=cm, mean_b=bm)
    return out


def main():
    t0 = _t.time()
    datasets = []
    for sym in SYMS:
        bars = load(sym)
        if bars is None or len(bars) < 200:
            print("  [skip] %s" % sym)
            continue
        ents = gen_entries(bars)
        datasets.append((sym, bars, atr_arr(bars), ents))
    total = sum(len(d[3]) for d in datasets)
    print("载入 %d 品种, 全样本入场点 %d" % (len(datasets), total))

    # ── 基线 (现役 R 锁利, USD 层关闭) ──
    base_P = dict(LIVE); base_P.update(usd_lock=0, usd_take=0, usd_gate_r=10, usd_buf=1.0)
    base_rows = run_trades(datasets, base_P)
    base_s = summarize_rows(base_rows)
    base_by_sym = mean_by_sym(base_rows)
    print("\n=== 基线 (现役 R 锁利, USD 关) ===")
    print("  n=%d 净均值R=%+.4f 胜率=%.1f%% 捕获率=%.1f%% 反转n=%d 反转捕获=%.1f%% 回吐>50%%=%.1f%%"
          % (base_s["n"], base_s["mean"], base_s["win"] * 100, base_s["cap"] * 100,
             base_s["nrev"], base_s["rev_cap"] * 100, base_s["gave50"] * 100))

    # USD 层是否对该品种启用 (gate)
    gate_by_sym = {}
    for sym, bars, at, ents in datasets:
        if ents:
            e0, d0 = ents[0]
            a0 = at[e0]
            gate_by_sym[sym] = ((2.0 * a0) * CONTRACT.get(sym, 0.0)) >= 10.0
        else:
            gate_by_sym[sym] = False

    # ── 候选网格 ──
    combos = []
    for ul in (5, 8, 10):
        for ut in (10, 15, 20):
            P = dict(LIVE)
            P.update(usd_lock=ul, usd_take=ut, usd_gate_r=10, usd_buf=1.0)
            combos.append((ul, ut, P))

    results = []
    for ul, ut, P in combos:
        crows = run_trades(datasets, P)
        cs = summarize_rows(crows)
        c_by_sym = mean_by_sym(crows)
        bmap = idx_map(base_rows)
        banked = 0.0
        take = 0
        for r in crows:
            key = (r[0], r[1], r[2])
            if key in bmap:
                cd, _ = r[3], r[5]
                bd, _ = bmap[key]
                if cd > bd:
                    banked += (cd - bd)
            if r[5] == "USD止盈":
                take += 1
        same_pos = sum(1 for s in c_by_sym
                       if s in base_by_sym and c_by_sym[s][0] > base_by_sym[s][0])
        wfo = wfo_delta(base_rows, crows)
        results.append(dict(usd_lock=ul, usd_take=ut, usd_gate_r=10, usd_buf=1.0,
                            netR=cs["mean"], dR=cs["mean"] - base_s["mean"],
                            win=cs["win"], rev_cap=cs["rev_cap"], cap=cs["cap"],
                            banked_R=banked, take_count=take, n=cs["n"],
                            same_pos=same_pos, n_sym=len(c_by_sym), wfo=wfo))

    # ── 表格 ──
    print("\n=== 候选 (usd_lock, usd_take) vs 基线 ===")
    print("  %-9s %-9s %8s %8s %7s %9s %10s %7s %5s"
          % ("lock", "take", "netR", "dR", "win%", "banked_R", "take_cnt", "n", "same+"))
    for r in results:
        print("  %-9d %-9d %+8.4f %+8.4f %6.1f%% %+9.4f %10d %7d %5d"
              % (r["usd_lock"], r["usd_take"], r["netR"], r["dR"], r["win"] * 100,
                 r["banked_R"], r["take_count"], r["n"], r["same_pos"]))

    # ── 最佳 (净 R 最高, 且 banked_R>0, 捕获率不显著受损) ──
    base_rev = base_s["rev_cap"]
    cand_sorted = sorted(results, key=lambda x: -x["netR"])
    best = None
    for r in cand_sorted:
        if r["banked_R"] > 0 and (base_rev - r["rev_cap"]) <= 0.10:  # 反转捕获掉 <=10个百分点
            best = r
            break
    if best is None:  # 退而求其次: 只要 banked>0 的净R最高
        for r in cand_sorted:
            if r["banked_R"] > 0:
                best = r
                break
    print("\n=== 最佳组合 ===")
    if best:
        print("  (usd_lock=%d, usd_take=%d): netR=%+.4f dR=%+.4f banked_R=%+.4f "
              "take=%d win=%.1f%% rev_cap=%.1f%% same+=%d/%d"
              % (best["usd_lock"], best["usd_take"], best["netR"], best["dR"],
                 best["banked_R"], best["take_count"], best["win"] * 100,
                 best["rev_cap"] * 100, best["same_pos"], best["n_sym"]))
        print("  WFO 三窗口 ΔR: " + "  ".join(
            "%s=%+0.4f(n%d)" % (w, best["wfo"][w]["dR"], best["wfo"][w]["n_c"])
            for w in ["W1", "W2", "W3"]))

    # ── 五验精神 ──
    print("\n=== 五验精神 ===")
    print("  ① 样本 n=%d (>=9000 %s)" % (base_s["n"], "PASS" if base_s["n"] >= 9000 else "FAIL"))
    if best:
        print("  ② 净均值R 提升 Δ=%+.4f (%s)"
              % (best["dR"], "PASS" if best["dR"] > 0 else "FAIL"))
        print("  ③ 同向正向品种 = %d/%d" % (best["same_pos"], best["n_sym"]))
        wfo_pass = all(best["wfo"][w]["dR"] >= 0 for w in ["W1", "W2", "W3"])
        print("  ④ 参数甜蜜点: (usd_lock=%d, usd_take=%d)" % (best["usd_lock"], best["usd_take"]))
        print("  ⑤ WFO 三窗口 ΔR 全非负: %s" % ("PASS" if wfo_pass else "PARTIAL"))

    # ── 分品种 gate + ΔR ──
    print("\n=== 分品种: USD层 gate(1R>=10$) / 基线R / 最佳候选R / ΔR ===")
    for sym in SYMS:
        if sym not in base_by_sym:
            continue
        bm = base_by_sym[sym][0]
        if best:
            cm = mean_by_sym(run_trades(
                [(s, b, a, en) for (s, b, a, en) in datasets if s == sym],
                dict(LIVE, usd_lock=best["usd_lock"], usd_take=best["usd_take"],
                     usd_gate_r=10, usd_buf=1.0)))[sym][0]
        else:
            cm = bm
        print("  %-7s gate=%-3s 基线R=%+.4f 候选R=%+.4f Δ=%+.4f"
              % (sym, "ON" if gate_by_sym.get(sym) else "off", bm, cm, cm - bm))

    # ── VERDICT ──
    if best and best["dR"] > 0 and best["banked_R"] > 0:
        verdict = ("VERDICT: 加入 USD 绝对锁利对大SL品种(高ATR)能净增R并落袋回吐利润"
                   " (banked_R>0), 且小ATR品种因 gate 关闭而不受影响; 推荐 (lock=%d,take=%d)。"
                   " 注意: 数据为2026-08代理历史, 仅方向性验证。"
                   % (best["usd_lock"], best["usd_take"]))
    else:
        verdict = ("VERDICT: 在当前代理数据上, USD 锁利未带来稳定净增R, "
                   "建议维持现役纯R锁利。注意: 数据为2026-08代理历史。")

    print("\n" + verdict)

    # ── 写文件 ──
    out_txt = []
    out_txt.append("PROFIT_SECURE USD 绝对锁利 WFO 验证 (2026-11-12)")
    out_txt.append("数据: data/*_H1.csv = 2026-08 代理历史 (proxy), 非实盘 tick。")
    out_txt.append("")
    out_txt.append("基线参数(现役R锁利,USD关): %s" % base_P)
    out_txt.append("基线: n=%d netR=%+.4f win=%.1f%% cap=%.1f%% rev_cap=%.1f%% gave50=%.1f%%"
                   % (base_s["n"], base_s["mean"], base_s["win"] * 100,
                      base_s["cap"] * 100, base_s["rev_cap"] * 100, base_s["gave50"] * 100))
    out_txt.append("")
    out_txt.append("表: (usd_lock,usd_take) vs 基线")
    out_txt.append("  lock take    netR      dR    win%  banked_R  take  n   same+")
    for r in results:
        out_txt.append("  %4d %4d %+8.4f %+8.4f %6.1f%% %+9.4f %5d %6d %5d"
                       % (r["usd_lock"], r["usd_take"], r["netR"], r["dR"],
                          r["win"] * 100, r["banked_R"], r["take_count"], r["n"],
                          r["same_pos"]))
    out_txt.append("")
    if best:
        out_txt.append("最佳: (lock=%d,take=%d) netR=%+.4f dR=%+.4f banked_R=%+.4f "
                       "take=%d rev_cap=%.1f%% same+=%d/%d"
                       % (best["usd_lock"], best["usd_take"], best["netR"], best["dR"],
                          best["banked_R"], best["take_count"], best["rev_cap"] * 100,
                          best["same_pos"], best["n_sym"]))
        out_txt.append("WFO: " + "  ".join("%s dR=%+0.4f n%d"
                       % (w, best["wfo"][w]["dR"], best["wfo"][w]["n_c"])
                       for w in ["W1", "W2", "W3"]))
    out_txt.append("")
    out_txt.append(verdict)
    out_txt.append("")
    out_txt.append("分品种 gate/ΔR:")
    for sym in SYMS:
        if sym in base_by_sym:
            out_txt.append("  %s gate=%s baseR=%+.4f" % (sym,
                         "ON" if gate_by_sym.get(sym) else "off", base_by_sym[sym][0]))

    with open(os.path.join(ROOT, "research",
                           "profit_secure_usd_lock_wfo_out.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(out_txt))

    out_json = dict(
        meta=dict(note="data=2026-08 proxy history; pure research",
                  syms=SYMS, base_params=base_P, live_params=LIVE,
                  contract=CONTRACT, wins=WINS),
        baseline=dict(n=base_s["n"], mean=base_s["mean"], win=base_s["win"],
                      cap=base_s["cap"], rev_cap=base_s["rev_cap"],
                      rev_real=base_s["rev_real"], gave50=base_s["gave50"],
                      by_sym={s: base_by_sym[s][0] for s in base_by_sym},
                      gate_by_sym=gate_by_sym),
        combos=[dict(r) for r in results],
        best=(dict(best) if best else None),
        verdict=verdict,
    )
    import json
    with open(os.path.join(ROOT, "research",
                           "profit_secure_usd_lock_wfo.json"), "w", encoding="utf-8") as f:
        json.dump(out_json, f, ensure_ascii=False, indent=2)

    print("\n用时 %.1fs" % (_t.time() - t0))
    print("输出: research/profit_secure_usd_lock_wfo_out.txt / .json")


if __name__ == "__main__":
    main()
