# -*- coding: utf-8 -*-
"""
PROFIT_SECURE 第一波 · 深度优化 v2  (2026-11-11)
================================================
目标(用户): "深度优化第一波" —— 第二波冻结, 只把单波紧锁利做到无 bug + 真最优。

v1 (research/profit_secure_grid.py) 存在 4 处会误导参数定稿的缺陷, 本版全部修正:
  B1 空单 SL 触发: v1 仅判 `l <= sl` (多单语义), 空单几乎永不触发 -> 空单样本全错。
     v2: 多 `l <= sl`, 空 `h >= sl`; 成交价统一 (exit-entry)/dist*dirn。
  B2 tight_r 阈值错位: v1 `mult = trail_atr if r < tight_atr(0.5) else tight_atr`,
     因进入条件 r>=start_r(>=0.8) 恒假 -> 永远用 tight_atr, trail_atr 参数完全失效,
     被误读为"ATR 松紧对 R 不敏感"。v2: tight_r 独立旋钮, `r < tight_r` 用 trail_atr。
  B3 SL 同 bar 自指: v1 先按当 bar 极值推 SL 再用同 bar 影线判触发 -> 捕获率虚高。
     v2: 先用**上一根 bar 结束时已确定的 SL** 判触发, 再更新 SL 供下一 bar 用。
  B4 基线标签过时: v1 标"当前引擎默认 lh1.0/bb0.3", 引擎实际定稿 lh1.2/bb0.2。

新增能力:
  * 交易成本 COST_R (默认 0.05R/笔, 做 0/0.05/0.10 敏感性)
  * 厚尾 winsorize (realized R 截到 [-3, +8], 防 BTC 单边 40R 扭曲均值)
  * 多目标: 净 mean R 优先, 反转捕获率 / >50%回吐占比 次之
  * tight_r 独立旋钮 + 坐标下降网格(约 100 组, 而非 1536 全笛卡尔)
  * 分品种独立最优诊断(只出建议表, 不擅自改实盘全品种参数 -> 守第62节 chief 裁决)
  * WFO 三窗口 Δ 稳定性 + 五验裁定

引擎语义(jince_live24.py L727-764)忠实复刻:
  入场 H1 swing(20) 突破 @ 收盘; SL=2*ATR(14); 无 TP; MAX_BARS=48;
  r = (extreme-entry)/dist (dist=2*ATR@entry, 用当 bar 影线更新 extreme);
  0.5R -> 保本缓冲 be_buf*dist; 1.0R -> 锁半利地板 lock_half*dist;
  r>=start_r -> ATR 跟踪 extreme - sgn*mult*a (mult=trail_atr, r>=tight_r 时 tight_atr);
  SL 只往有利方向移动; 触发按 SL 价成交, 跳空按开盘更差价成交(保守)。

红线: 本脚本纯研究, 不改引擎、不连 MT5、不开实单。
"""
import csv, os, itertools, time as _t
from collections import defaultdict

ROOT = "E:/GoldstrategyEngine"
DATA = os.path.join(ROOT, "data")
SYMS = ["XAUUSD", "BTCUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30", "XAGUSD"]
MAX_BARS = 48
SWING = 20
ATR_N = 14
COST_R = 0.05
WINSOR_LO, WINSOR_HI = -3.0, 8.0

# 现役引擎定稿参数 (jince_live24.py L216-230)
LIVE = dict(start_r=1.0, trail_atr=0.8, tight_r=1.5, tight_atr=0.5,
            lock_half=1.2, be_buf=0.2)

# 坐标下降网格
G_START_R   = [0.8, 1.0, 1.2, 1.5]
G_LOCK_HALF = [0.8, 1.0, 1.2, 1.5]
G_BE_BUF    = [0.1, 0.2, 0.3, 0.5]
G_TRAIL_ATR = [0.6, 0.8, 1.0, 1.2]
G_TIGHT_R   = [1.5, 2.0, 2.5]
G_TIGHT_ATR = [0.35, 0.5, 0.65]


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


def simulate(bars, at, e, dirn, P, cost=COST_R, winsor=True):
    """返回 (realized_R, mfe_R, reason)。SL 更新滞后一根 bar, 消除同 bar 自指。"""
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

    for j in range(e + 1, last + 1):
        o, h, l, c = bars[j]
        a = at[j] if at[j] > 0 else a0

        # ── 1) 先用「上一根 bar 结束时已确定的 SL」判触发 (B3 修复) ──
        if dirn > 0 and l <= sl:
            px = min(sl, o)            # 跳空低开按更差价成交
            realized = (px - entry) / dist * dirn
            return (_clip(realized, winsor) - cost, (extreme - entry) / dist * dirn, "SL")
        if dirn < 0 and h >= sl:       # B1 修复: 空单看 high
            px = max(sl, o)
            realized = (px - entry) / dist * dirn
            return (_clip(realized, winsor) - cost, (extreme - entry) / dist * dirn, "SL")

        # ── 2) 再用当 bar 影线更新 extreme / SL (供下一 bar 生效) ──
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
            mult = ta if r < tr_ else tta        # B2 修复: 用 R 阈值 tr_, 不是 tta
            t = extreme - dirn * mult * a
            if cand is None or t * dirn > cand * dirn:
                cand = t
        if cand is not None and cand * dirn > sl * dirn:   # 单调: 只往有利方向
            sl = cand

    exit_px = bars[last][3]
    realized = (exit_px - entry) / dist * dirn
    return (_clip(realized, winsor) - cost, (extreme - entry) / dist * dirn, "MAXBARS")


def _clip(x, winsor):
    if not winsor:
        return x
    return max(WINSOR_LO, min(WINSOR_HI, x))


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
    """同一批入场点, 只换出场参数 -> 公平相对对比。window=(lo_f,hi_f) 时按品种时间切片。"""
    rows = []
    for sym, bars, at, ents in datasets:
        if window is not None:
            lo, hi = int(len(bars) * window[0]), int(len(bars) * window[1])
            ents = gen_entries(bars, lo, hi)
        for (e, d) in ents:
            res = simulate(bars, at, e, d, P, cost, winsor)
            if res is not None:
                rows.append(res)
    return summarize(rows)


def eval_P_by_sym(datasets, P, cost=COST_R, winsor=True):
    out = {}
    for sym, bars, at, ents in datasets:
        rows = []
        for (e, d) in ents:
            res = simulate(bars, at, e, d, P, cost, winsor)
            if res is not None:
                rows.append(res)
        out[sym] = summarize(rows)
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

    # ── 0) 现役基线(修正 harness 下重新测量) ──
    base = eval_P(datasets, LIVE)
    print("\n=== 现役基线 lh1.2/bb0.2 (修正后 harness 重测) ===")
    print("  n=%d 净均值R=%+.4f 胜率=%.1f%% 捕获率=%.1f%% 反转n=%d 反转捕获=%.1f%% 回吐>50%%=%.1f%%" %
          (base["n"], base["mean"], base["win"]*100, base["cap"]*100,
           base["nrev"], base["rev_cap"]*100, base["gave50"]*100))

    # ── 1) Stage1: start_r × lock_half × be_buf (其余固定为现役) ──
    print("\n=== Stage1 坐标下降: start_r × lock_half × be_buf ===")
    best1 = None
    results1 = []
    for sr, lh, bb in itertools.product(G_START_R, G_LOCK_HALF, G_BE_BUF):
        P = dict(LIVE); P.update(start_r=sr, lock_half=lh, be_buf=bb)
        s = eval_P(datasets, P)
        results1.append((P, s))
        if best1 is None or s["mean"] > best1[1]["mean"]:
            best1 = (P, s)
    for P, s in sorted(results1, key=lambda x: -x[1]["mean"])[:8]:
        print("  sr%.1f lh%.1f bb%.2f | 净R=%+.4f 反转捕获=%.1f%% ΔR=%+.4f" %
              (P["start_r"], P["lock_half"], P["be_buf"], s["mean"],
               s["rev_cap"]*100, s["mean"]-base["mean"]))
    print("  Stage1 最优: sr%.1f lh%.1f bb%.2f ΔR=%+.4f" %
          (best1[0]["start_r"], best1[0]["lock_half"], best1[0]["be_buf"],
           best1[1]["mean"]-base["mean"]))

    # ── 2) Stage2: 在 Stage1 最优上扫 trail_atr × tight_r × tight_atr ──
    print("\n=== Stage2 坐标下降: trail_atr × tight_r × tight_atr (B2 修复后首次真实生效) ===")
    best2 = None
    results2 = []
    for ta, tr_, tta in itertools.product(G_TRAIL_ATR, G_TIGHT_R, G_TIGHT_ATR):
        P = dict(best1[0]); P.update(trail_atr=ta, tight_r=tr_, tight_atr=tta)
        s = eval_P(datasets, P)
        results2.append((P, s))
        if best2 is None or s["mean"] > best2[1]["mean"]:
            best2 = (P, s)
    for P, s in sorted(results2, key=lambda x: -x[1]["mean"])[:8]:
        print("  ta%.1f tr%.1f tta%.2f | 净R=%+.4f 反转捕获=%.1f%% ΔR=%+.4f" %
              (P["trail_atr"], P["tight_r"], P["tight_atr"], s["mean"],
               s["rev_cap"]*100, s["mean"]-base["mean"]))
    print("  Stage2 最优: ta%.1f tr%.1f tta%.2f ΔR=%+.4f" %
          (best2[0]["trail_atr"], best2[0]["tight_r"], best2[0]["tight_atr"],
           best2[1]["mean"]-base["mean"]))

    # ── 3) Stage3: 回到 start/lock/be 再细化一轮(坐标下降第二圈) ──
    print("\n=== Stage3 第二圈细化: start_r × lock_half × be_buf ===")
    best3 = None
    for sr, lh, bb in itertools.product(G_START_R, G_LOCK_HALF, G_BE_BUF):
        P = dict(best2[0]); P.update(start_r=sr, lock_half=lh, be_buf=bb)
        s = eval_P(datasets, P)
        if best3 is None or s["mean"] > best3[1]["mean"]:
            best3 = (P, s)
    BP, BS = best3
    print("  全局最优参数: %s" % BP)
    print("  净均值R=%+.4f (现役 %+.4f, Δ=%+.4f) 胜率=%.1f%% 反转捕获=%.1f%% 回吐>50%%=%.1f%%" %
          (BS["mean"], base["mean"], BS["mean"]-base["mean"], BS["win"]*100,
           BS["rev_cap"]*100, BS["gave50"]*100))

    # ── 4) 五验 ──
    print("\n=== 五验 (候选 = 全局最优 vs 现役) ===")
    by_c = eval_P_by_sym(datasets, BP)
    by_b = eval_P_by_sym(datasets, LIVE)
    same = sum(1 for s in by_c if by_c[s]["mean"] > by_b[s]["mean"])
    print("  ① 样本 n=%d (>=1000 %s)" % (BS["n"], "PASS" if BS["n"] >= 1000 else "FAIL"))
    print("  ② 净均值R 提升 Δ=%+.4f (%s)" %
          (BS["mean"]-base["mean"], "PASS" if BS["mean"] > base["mean"] else "FAIL"))
    print("  ③ 同向正向品种 = %d/%d (>=6/8 严格, >=4/6 宽松)" % (same, len(by_c)))
    print("  ④ 参数甜蜜点: Stage2 top8 净R 区间 [%.4f, %.4f]" %
          (min(s["mean"] for _, s in sorted(results2, key=lambda x: -x[1]["mean"])[:8]),
           max(s["mean"] for _, s in sorted(results2, key=lambda x: -x[1]["mean"])[:8])))
    wins = [("W1前1/3", 0.0, 1/3), ("W2中1/3", 1/3, 2/3), ("W3后1/3", 2/3, 1.0)]
    wd = []
    print("  ⑤ Walk-Forward 三窗口 ΔR:")
    for wn, lo, hi in wins:
        sc = eval_P(datasets, BP, window=(lo, hi))
        sb = eval_P(datasets, LIVE, window=(lo, hi))
        d = sc["mean"] - sb["mean"]
        wd.append(d)
        print("     %-10s 候选=%+.4f 现役=%+.4f Δ=%+.4f n=%d" % (wn, sc["mean"], sb["mean"], d, sc["n"]))
    wfo_ok = all(d > 0 for d in wd)
    verdict = (BS["n"] >= 1000 and BS["mean"] > base["mean"] and
               same >= 6 and wfo_ok)
    print("\n  五验裁定: %s" % ("PASS -> 可考虑落码" if verdict else "NOT PASS -> 维持现役参数"))

    # ── 5) 稳健性: 成本 / 厚尾 敏感性 ──
    print("\n=== 敏感性 (候选 ΔR vs 现役) ===")
    for c in (0.0, 0.05, 0.10):
        sc = eval_P(datasets, BP, cost=c)["mean"]
        sb = eval_P(datasets, LIVE, cost=c)["mean"]
        print("  成本 %.2fR : Δ=%+.4f" % (c, sc - sb))
    for w in (True, False):
        sc = eval_P(datasets, BP, winsor=w)["mean"]
        sb = eval_P(datasets, LIVE, winsor=w)["mean"]
        print("  winsor=%-5s: Δ=%+.4f (候选R=%+.4f 现役R=%+.4f)" % (str(w), sc - sb, sc, sb))

    # ── 6) 分品种独立最优(只出建议表, 不擅自改实盘) ──
    print("\n=== 分品种诊断 (守第62节 chief「暂缓全品种提速」: 仅建议, 不落码) ===")
    pool = [dict(LIVE)] + [p for p, _ in results1[:12]] + [p for p, _ in results2[:12]] + [BP]
    seen = set(); uniq = []
    for p in pool:
        k = tuple(sorted(p.items()))
        if k not in seen:
            seen.add(k); uniq.append(p)
    print("  候选池 %d 组; 逐品种取净均值R最高者" % len(uniq))
    for sym, bars, at, ents in datasets:
        best_p, best_m = None, -1e9
        sub = [(sym, bars, at, ents)]
        for p in uniq:
            m = eval_P(sub, p)["mean"]
            if m > best_m:
                best_m, best_p = m, p
        live_m = eval_P(sub, LIVE)["mean"]
        print("  %-7s 现役R=%+.4f  独立最优R=%+.4f  Δ=%+.4f  @ sr%.1f/ta%.1f/tr%.1f/tta%.2f/lh%.1f/bb%.2f" %
              (sym, live_m, best_m, best_m-live_m, best_p["start_r"], best_p["trail_atr"],
               best_p["tight_r"], best_p["tight_atr"], best_p["lock_half"], best_p["be_buf"]))

    print("\n用时 %.1fs" % (_t.time() - t0))


if __name__ == "__main__":
    main()
