# -*- coding: utf-8 -*-
"""
现役六参数调优 · WFO (2026-11-12 续·Round 5)
=============================================
用户口谕: "小单子有利润不再亏" + "拿到大的趋势利润"。前两轮(HARD_BE/EPF)证明"新增早期锁利组件"必损净R。
本轮回测: 仅调现役已有旋钮(不引入新组件), 看能否在净R不崩前提下更早保护小利润:
  A) start_r   : ATR 轨道起始 R(现役1.0) -> 越低=越早开始轨道=越早保护
  B) trail_atr : 轨道松紧(现役0.8) -> 越松=越少被扫=更多趋势
  C) be_buf    : +0.5R 保本缓冲(现役0.2) -> 越小=保本越严=更早锁零亏
  D) lock_half : 锁半利地板 R(现役1.2, 触发于 r>=1.0) -> 越低=越早锁利润
五验: 净R不崩(>=基线-0.01) / 亏损率不升 / 捕获率不崩 / WFO三窗口稳定。纯研究。
"""
import csv, os, time as _t

ROOT = "E:/GoldstrategyEngine"
DATA = os.path.join(ROOT, "data")
SYMS = ["XAUUSD", "BTCUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30", "XAGUSD"]
MAX_BARS = 48
SWING = 20
ATR_N = 14
COST_R = 0.05
WINSOR_LO, WINSOR_HI = -3.0, 8.0
LIVE = dict(start_r=1.0, trail_atr=0.8, tight_r=1.5, tight_atr=0.5, lock_half=1.2, be_buf=0.2, lh_trig=1.0)


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
    entry = bars[e][3]
    a0 = at[e]
    if a0 <= 1e-8:
        return None
    dist = 2.0 * a0
    sl = entry - dirn * dist
    extreme = entry
    last = min(e + MAX_BARS, len(bars) - 1)
    sr, ta = P["start_r"], P["trail_atr"]
    tr_, tta = P["tight_r"], P["tight_atr"]
    lh, bb, lh_trig = P["lock_half"], P["be_buf"], P["lh_trig"]

    for j in range(e + 1, last + 1):
        o, h, l, c = bars[j]
        a = at[j] if at[j] > 0 else a0
        if dirn > 0 and l <= sl:
            px = min(sl, o)
            return (_clip((px - entry) / dist * dirn, winsor) - cost, (extreme - entry) / dist * dirn, "SL")
        if dirn < 0 and h >= sl:
            px = max(sl, o)
            return (_clip((px - entry) / dist * dirn, winsor) - cost, (extreme - entry) / dist * dirn, "SL")
        extreme = max(extreme, h) if dirn > 0 else min(extreme, l)
        r = (extreme - entry) / dist * dirn
        cand = None
        if r >= 0.5:
            cand = entry + dirn * bb * dist
        if r >= lh_trig:
            c2 = entry + dirn * lh * dist
            if cand is None or c2 * dirn > cand * dirn:
                cand = c2
        if r >= sr and a > 0:
            mult = ta if r < tr_ else tta
            t = extreme - dirn * mult * a
            if cand is None or t * dirn > cand * dirn:
                cand = t
        if cand is not None and cand * dirn > sl * dirn:
            sl = cand

    exit_px = bars[last][3]
    return (_clip((exit_px - entry) / dist * dirn, winsor) - cost, (extreme - entry) / dist * dirn, "MAXBARS")


def _clip(x, winsor):
    return x if not winsor else max(WINSOR_LO, min(WINSOR_HI, x))


def summarize(rows):
    n = len(rows)
    if n == 0:
        return dict(n=0, mean=0.0, win=0.0, cap=0.0, loss=1.0)
    mean = sum(r[0] for r in rows) / n
    win = sum(1 for r in rows if r[0] > 0) / n
    loss = sum(1 for r in rows if r[0] < -1e-6) / n
    eff = [r for r in rows if r[1] >= 0.5]
    cap = sum(min(1.0, max(-5.0, r[0] / r[1])) for r in eff) / len(eff) if eff else 0.0
    return dict(n=n, mean=mean, win=win, cap=cap, loss=loss)


def eval_P(Datasets, P, window=None):
    rows = []
    for sym, bars, at, ents in Datasets:
        if window is not None:
            lo, hi = int(len(bars) * window[0]), int(len(bars) * window[1])
            ents = gen_entries(bars, lo, hi)
        for (e, d) in ents:
            res = simulate(bars, at, e, d, P, COST_R, True)
            if res is not None:
                rows.append(res)
    return summarize(rows)


Datasets = None


def main():
    global Datasets
    t0 = _t.time()
    Datasets = []
    for sym in SYMS:
        bars = load(sym)
        if bars is None or len(bars) < 200:
            print("  [skip] %s" % sym)
            continue
        Datasets.append((sym, bars, atr_arr(bars), gen_entries(bars)))
    total = sum(len(d[3]) for d in Datasets)
    print("载入 %d 品种, 全样本入场点 %d" % (len(Datasets), total))

    base = eval_P(Datasets, LIVE)
    print("\n=== 基线(现役) ===")
    print("  n=%d 净R=%+.4f 胜率=%.1f%% 捕获率=%.1f%% 亏损率=%.1f%%" %
          (base["n"], base["mean"], base["win"]*100, base["cap"]*100, base["loss"]*100))

    def show(name, P):
        s = eval_P(Datasets, P)
        wd = []
        for wn, lo, hi in [("W1", 0.0, 1/3), ("W2", 1/3, 2/3), ("W3", 2/3, 1.0)]:
            sc = eval_P(Datasets, P, window=(lo, hi))["mean"]
            sb = eval_P(Datasets, LIVE, window=(lo, hi))["mean"]
            wd.append(sc - sb)
        flag = "OK" if (s["mean"] >= base["mean"] - 0.01 and s["loss"] <= base["loss"] + 0.01
                        and s["cap"] >= base["cap"] - 0.03 and min(wd) > -0.02) else "x"
        print("  %s | 净R=%+.4f ΔR=%+.4f 亏损率=%.1f%%→%.2f%% 胜率=%.1f%% 捕获率=%.1f%% W=[%+.3f,%+.3f,%+.3f] %s" %
              (name, s["mean"], s["mean"]-base["mean"], base["loss"]*100, s["loss"]*100,
               s["win"]*100, s["cap"]*100, wd[0], wd[1], wd[2], flag))
        return s

    print("\n=== A) start_r (ATR轨道起始R) ===")
    for v in [0.5, 0.8, 1.0, 1.5, 2.0]:
        P = dict(LIVE); P["start_r"] = v
        show("start_r=%.1f" % v, P)

    print("\n=== B) trail_atr (轨道松紧) ===")
    for v in [0.5, 0.8, 1.0, 1.2]:
        P = dict(LIVE); P["trail_atr"] = v
        show("trail_atr=%.1f" % v, P)

    print("\n=== C) be_buf (+0.5R保本缓冲) ===")
    for v in [0.1, 0.2, 0.3, 0.5]:
        P = dict(LIVE); P["be_buf"] = v
        show("be_buf=%.2f" % v, P)

    print("\n=== D) lock_half 触发阈值 lh_trig (现役1.0) ===")
    for v in [0.5, 0.8, 1.0, 1.5]:
        P = dict(LIVE); P["lh_trig"] = v
        show("lh_trig=%.1f" % v, P)

    print("\n=== D2) lock_half 地板值 (触发于 lh_trig) ===")
    for v in [0.8, 1.0, 1.2, 1.5]:
        P = dict(LIVE); P["lock_half"] = v
        show("lock_half=%.1f" % v, P)

    print("\n用时 %.1fs" % (_t.time() - t0))


if __name__ == "__main__":
    main()
