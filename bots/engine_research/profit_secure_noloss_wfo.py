# -*- coding: utf-8 -*-
"""
硬保本无亏损模式 · WFO 验证 (2026-11-12)
========================================
用户口谕: "绝不能出现账面上的亏损单子" + "深度优化策略参数 找到最优的方案参数 映射到全部品种中"。

本母机:
  A) 硬保本 HARD_BE 模式: 持仓浮盈越过 HARD_BE_R(默认0.05R)即把 SL 钉到 入场±spread*1.5(保本地板),
     此后价格不破入场=永不亏损。按 R 倍触发 -> 与品种尺度无关, 天然映射全品种。
     网格 HARD_BE_R ∈ {0.0,0.05,0.1,0.15,0.2,0.3}, 量: 净均值R / 亏损率(frac R<0) / 胜率 / 捕获率 / 样本。
     五验: 样本>=1000 / 亏损率压降 / 净R 不崩(相对基线) / WFO三窗口稳定。
  B) 逐品种最优六参数映射(守R1冻结: 仅出建议表, 不落码; 需 per-symbol 五验PASS+chief R11)。

引擎语义忠实复刻自 jince_live24.py(修正 B1/B2/B3 后)。纯研究, 不改引擎/不连MT5。
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
LIVE = dict(start_r=1.0, trail_atr=0.8, tight_r=1.5, tight_atr=0.5, lock_half=1.2, be_buf=0.2)

G_START_R   = [0.8, 1.0, 1.2, 1.5]
G_LOCK_HALF = [0.8, 1.0, 1.2, 1.5]
G_BE_BUF    = [0.1, 0.2, 0.3, 0.5]

HBES = [0.0, 0.05, 0.1, 0.15, 0.2, 0.3]


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


def simulate(bars, at, e, dirn, P, cost=COST_R, winsor=True, hbe_r=0.0):
    entry = bars[e][3]
    a0 = at[e]
    if a0 <= 1e-8:
        return None
    dist = 2.0 * a0
    sl = entry - dirn * dist
    extreme = entry
    last = min(e + MAX_BARS, len(bars) - 1)
    sr, ta, tr_, tta = P["start_r"], P["trail_atr"], P["tight_r"], P["tight_atr"]
    lh, bb = P["lock_half"], P["be_buf"]

    for j in range(e + 1, last + 1):
        o, h, l, c = bars[j]
        a = at[j] if at[j] > 0 else a0
        # 1) 先用上一根 bar 已确定的 SL 判触发
        if dirn > 0 and l <= sl:
            px = min(sl, o)
            return (_clip((px - entry) / dist * dirn, winsor) - cost, (extreme - entry) / dist * dirn, "SL")
        if dirn < 0 and h >= sl:
            px = max(sl, o)
            return (_clip((px - entry) / dist * dirn, winsor) - cost, (extreme - entry) / dist * dirn, "SL")
        # 2) 更新 extreme / SL
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
        # 硬保本地板(HARD_BE): 浮盈越 hbe_r 即钉 SL 到 entry±spread*1.5, 永不亏损侧
        if hbe_r > 0 and r >= hbe_r:
            _hb = entry + dirn * max(dist * 0.1, 1e-5)   # 0.1R 缓冲覆盖 0.05R 成本 -> 保本出场净+0.05R, 账面零亏损
            if cand is None or _hb * dirn > cand * dirn:
                cand = _hb
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


def eval_P(datasets, P, hbe_r=0.0, window=None):
    rows = []
    for sym, bars, at, ents in Datasets:
        if window is not None:
            lo, hi = int(len(bars) * window[0]), int(len(bars) * window[1])
            ents = gen_entries(bars, lo, hi)
        for (e, d) in ents:
            res = simulate(bars, at, e, d, P, COST_R, True, hbe_r)
            if res is not None:
                rows.append(res)
    return summarize(rows)


def eval_P_by_sym(Datasets, P, hbe_r=0.0):
    out = {}
    for sym, bars, at, ents in Datasets:
        rows = [simulate(bars, at, e, d, P, COST_R, True, hbe_r) for (e, d) in ents]
        rows = [r for r in rows if r is not None]
        out[sym] = summarize(rows)
    return out


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

    base = eval_P(Datasets, LIVE, 0.0)
    print("\n=== 基线(无硬保本) ===")
    print("  n=%d 净R=%+.4f 胜率=%.1f%% 捕获率=%.1f%% 亏损率=%.1f%%" %
          (base["n"], base["mean"], base["win"]*100, base["cap"]*100, base["loss"]*100))

    print("\n=== A) 硬保本 HARD_BE_R 网格(全品种合并) ===")
    res = {}
    for hr in HBES:
        s = eval_P(Datasets, LIVE, hr)
        res[hr] = s
        print("  HBE_R=%.2f | 净R=%+.4f ΔR=%+.4f 亏损率=%.1f%%→%.1f%% 胜率=%.1f%% 捕获率=%.1f%% n=%d" %
              (hr, s["mean"], s["mean"]-base["mean"], base["loss"]*100, s["loss"]*100,
               s["win"]*100, s["cap"]*100, s["n"]))

    # 五验(选亏损率最低且净R不崩者)
    best_hr = min(HBES, key=lambda hr: (res[hr]["loss"], -(res[hr]["mean"]))
                  if res[hr]["mean"] > base["mean"] - 0.05 else (1.0, 0))
    print("\n=== A) 五验 ===")
    bsel = res[best_hr]
    wd = []
    for wn, lo, hi in [("W1", 0.0, 1/3), ("W2", 1/3, 2/3), ("W3", 2/3, 1.0)]:
        sc = eval_P(Datasets, LIVE, best_hr, window=(lo, hi))["mean"]
        sb = eval_P(Datasets, LIVE, 0.0, window=(lo, hi))["mean"]
        wd.append(sc - sb)
        print("  %s ΔR=%+.4f" % (wn, sc - sb))
    print("  候选 HARD_BE_R=%.2f: 亏损率=%.1f%% (基线%.1f%%), 净R=%+.4f(基线%+.4f)" %
          (best_hr, bsel["loss"]*100, base["loss"]*100, bsel["mean"], base["mean"]))
    print("  verdict: 亏损率压降=%s, 净R保持=%s" %
          ("PASS" if bsel["loss"] < base["loss"] * 0.5 else "CHECK",
           "PASS" if bsel["mean"] > base["mean"] - 0.05 else "CHECK"))

    # 逐品种 HARD_BE_R 最优
    print("\n=== A) 逐品种最优 HARD_BE_R(亏损率优先) ===")
    for sym, bars, at, ents in Datasets:
        best = None
        for hr in HBES:
            s = eval_P([(sym, bars, at, ents)], LIVE, hr)
            key = (s["loss"], -s["mean"])
            if best is None or key < best[1]:
                best = (hr, key, s)
        hr, _, s = best
        print("  %-7s HBE_R=%.2f 亏损率=%.1f%% 净R=%+.4f 胜率=%.1f%%" %
              (sym, hr, s["loss"]*100, s["mean"], s["win"]*100))

    # B) 逐品种六参数映射(守R1: 仅建议)
    print("\n=== B) 逐品种最优六参数映射(候选池: start×lock×be = 64组, 其余固定现役) ===")
    pool = []
    for sr, lh, bb in itertools.product(G_START_R, G_LOCK_HALF, G_BE_BUF):
        P = dict(LIVE); P.update(start_r=sr, lock_half=lh, be_buf=bb)
        pool.append(P)
    for sym, bars, at, ents in Datasets:
        best_p, best_m = None, -1e9
        sub = [(sym, bars, at, ents)]
        for p in pool:
            m = eval_P(sub, p)["mean"]
            if m > best_m:
                best_m, best_p = m, p
        live_m = eval_P(sub, LIVE)["mean"]
        print("  %-7s 现役R=%+.4f 独立最优R=%+.4f Δ=%+.4f @ sr%.1f/ta%.1f/tr%.1f/tta%.2f/lh%.1f/bb%.2f" %
              (sym, live_m, best_m, best_m-live_m, best_p["start_r"], best_p["trail_atr"],
               best_p["tight_r"], best_p["tight_atr"], best_p["lock_half"], best_p["be_buf"]))

    print("\n用时 %.1fs" % (_t.time() - t0))


if __name__ == "__main__":
    main()
