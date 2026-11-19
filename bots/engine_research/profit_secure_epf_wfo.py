# -*- coding: utf-8 -*-
"""
早期正地板锁利 (EARLY_POS_FLOOR, EPF) · WFO 验证 (2026-11-12 续)
=============================================================
用户口谕: "那些小单子 只要有利润了就能再亏损出场了 ， 还要争取能拿到大的趋势利润"。

HARD_BE(钉0R保本) 已 WFO 驳回: 它把 SL 钉到入场=0R, 任何回踩到入场即保本出场,
砍掉本可长成大赢的单子 -> 净R恶化(基线-0.0131, HBE_R=0.30仅-0.0179, 仍更差)。

EPF 设计(区别于 HARD_BE):
  1) 仅在浮盈越过 EPF_TRIGGER_R(0.15~0.5R)后启用 -> 不钉过早噪音(比HARD_BE的0.05R温和得多)。
  2) 锁的是"正地板"(entry + EPF_FLOOR_R*1R, 默认0.1R>成本0.05R)而非0R保本 -> 即便回撤触发也是小赢, 账面永不亏损。
  3) 地板随 MFE 棘轮上行: floor = max(EPF_FLOOR_R, EPF_RATCHET * r) -> 大赢单回撤到高位才出, 仍吃掉大部分趋势。
  4) 与现役六参数+1.2R锁半利+ATR轨道自然衔接(>1.0R后锁半利接管, 平滑过渡)。

WFO 五验: 样本>=1000 / 亏损率压降(目标趋近0) / 净R不崩(相对基线-0.0131) / 捕获率不崩 / WFO三窗口稳定。
引擎语义忠实复刻自 jince_live24.py + profit_secure_noloss_wfo.py 的 simulate。纯研究, 不改引擎/不连MT5。
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
LIVE = dict(start_r=1.0, trail_atr=0.8, tight_r=1.5, tight_atr=0.5, lock_half=1.2, be_buf=0.2)

# EPF 网格
TRIGS = [0.15, 0.2, 0.3, 0.5]
FLOORS = [0.1, 0.15]
RATCHETS = [0.3, 0.5]


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


def simulate(bars, at, e, dirn, P, cost=COST_R, winsor=True, epf=None):
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
    epf_trig = epf["trig"] if epf else 0.0
    epf_floor = epf["floor"] if epf else 0.0
    epf_ratchet = epf["ratchet"] if epf else 0.0

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
        if r >= 1.0:
            c2 = entry + dirn * lh * dist
            if cand is None or c2 * dirn > cand * dirn:
                cand = c2
        if r >= sr and a > 0:
            mult = ta if r < tr_ else tta
            t = extreme - dirn * mult * a
            if cand is None or t * dirn > cand * dirn:
                cand = t
        # EPF 正地板: 浮盈越 trig 后, 锁 max(floor, ratchet*r) 正R地板, 棘轮只升不降
        if epf is not None and r >= epf_trig:
            _ef = entry + dirn * max(epf_floor, epf_ratchet * r) * dist
            if cand is None or _ef * dirn > cand * dirn:
                cand = _ef
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


def eval_P(Datasets, P, epf=None, window=None):
    rows = []
    for sym, bars, at, ents in Datasets:
        if window is not None:
            lo, hi = int(len(bars) * window[0]), int(len(bars) * window[1])
            ents = gen_entries(bars, lo, hi)
        for (e, d) in ents:
            res = simulate(bars, at, e, d, P, COST_R, True, epf)
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
    print("\n=== 基线(无EPF) ===")
    print("  n=%d 净R=%+.4f 胜率=%.1f%% 捕获率=%.1f%% 亏损率=%.1f%%" %
          (base["n"], base["mean"], base["win"]*100, base["cap"]*100, base["loss"]*100))

    print("\n=== EPF 网格(trig × floor × ratchet) ===")
    res = {}
    for trig in TRIGS:
        for floor in FLOORS:
            for ratchet in RATCHETS:
                epf = dict(trig=trig, floor=floor, ratchet=ratchet)
                s = eval_P(Datasets, LIVE, epf)
                res[(trig, floor, ratchet)] = s
                tag = "**" if s["loss"] < 0.005 and s["mean"] >= base["mean"] else ""
                print("  trig=%.2f floor=%.2f rat=%.2f | 净R=%+.4f ΔR=%+.4f 亏损率=%.1f%%→%.2f%% 胜率=%.1f%% 捕获率=%.1f%% n=%d %s" %
                      (trig, floor, ratchet, s["mean"], s["mean"]-base["mean"],
                       base["loss"]*100, s["loss"]*100, s["win"]*100, s["cap"]*100, s["n"], tag))

    # 选最优: 亏损率压到最低, 且净R不崩(>=基线-0.01), 且捕获率不崩
    def keyf(k):
        s = res[k]
        return (s["loss"], -(s["mean"]), -(s["cap"]))
    cands = [k for k in res if res[k]["mean"] >= base["mean"] - 0.01]
    best = min(cands, key=keyf) if cands else min(res, key=keyf)
    bs = res[best]
    print("\n=== 最优 EPF 组 ===")
    print("  trig=%.2f floor=%.2f rat=%.2f | 净R=%+.4f ΔR=%+.4f 亏损率=%.2f%% 胜率=%.1f%% 捕获率=%.1f%%" %
          (best[0], best[1], best[2], bs["mean"], bs["mean"]-base["mean"],
           bs["loss"]*100, bs["win"]*100, bs["cap"]*100))

    print("\n=== 五验(最优组) ===")
    wd = []
    for wn, lo, hi in [("W1", 0.0, 1/3), ("W2", 1/3, 2/3), ("W3", 2/3, 1.0)]:
        sc = eval_P(Datasets, LIVE, dict(trig=best[0], floor=best[1], ratchet=best[2]), window=(lo, hi))["mean"]
        sb = eval_P(Datasets, LIVE, None, window=(lo, hi))["mean"]
        wd.append(sc - sb)
        print("  %s ΔR=%+.4f" % (wn, sc - sb))
    print("  W1~W3 稳定: %s" % ("PASS" if min(wd) > -0.02 and max(wd) < 0.05 else "CHECK"))
    print("  亏损率压降: %.1f%%→%.2f%% (%s)" %
          (base["loss"]*100, bs["loss"]*100, "PASS" if bs["loss"] < 0.01 else "CHECK"))
    print("  净R保持: %s (基线%+.4f, 候选%+.4f)" %
          ("PASS" if bs["mean"] >= base["mean"] - 0.01 else "CHECK", base["mean"], bs["mean"]))
    print("  捕获率保持: %s (基线%.1f%%, 候选%.1f%%)" %
          ("PASS" if bs["cap"] >= base["cap"] - 0.03 else "CHECK", base["cap"]*100, bs["cap"]*100))

    print("\n用时 %.1fs" % (_t.time() - t0))


if __name__ == "__main__":
    main()
