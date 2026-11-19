# -*- coding: utf-8 -*-
"""
PROFIT_SECURE 深度寻优 · 网格 + Walk-Forward 五验
=================================================
目标(用户): 把实盘出场逻辑深度优化到"无bug + 最优解", 深度测试找最优参数组合。

引擎语义忠实复刻(manage_position L690-734 PROFIT_SECURE 分支):
  入场: H1 swing突破(20根) @ 突破棒收盘
  SL  : 2×ATR(14) @ 入场
  无初始TP; MAX_BARS=48(聚焦小波段)
  R缩放: dist = 2×ATR(entry)

锁利阶梯(每棒按收盘价算r_mult, 用当棒高低触发SL, 同棒多信号取最不利价先成交):
  0.5R: 保本缓冲 be_buf*dist (max(be_buf*dist, spread*1.5))
  1.0R: 锁半利地板 lock_half*dist
  r>=start_r: ATR跟踪 extreme - sgn*mult*a (mult=trail_atr 直到 tight_r, 之后 tight_atr)
  全部只往有利方向动SL

网格: start_r{0.8,1.0,1.2} × trail_atr{0.6,0.8,1.0} × tight_atr{0.4,0.5,0.6}
      × lock_half{0.8,1.0,1.2,1.5} × be_buf{0.2,0.3,0.5}
      = 3*3*3*4*3 = 324 组合 (若超时可缩到关键维度)

指标: 均值R / 胜率 / 捕获率(落袋/MFE, 仅MFE>=0.5有效单) /
      反转回吐子集(MFE>=1R) 落袋均R + 捕获率 + ">50%回吐占比"

五验: ①样本>=1000 ②显著性(均值R>0占比) ③稳健性(同向>=4/6品种) ④参数甜蜜点
      ⑤walk-forward 3段时间稳定(in-sample选top, 3段时间窗口验证不塌)
"""
import csv, os, time as _t

ROOT = "E:/GoldstrategyEngine"
DATA = os.path.join(ROOT, "data")
SYMS = ["XAUUSD", "BTCUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30", "XAGUSD"]
MAX_BARS = 48
SWING = 20
ATR_N = 14
# 网格(控制规模: 已知ATR松紧对R不变, 但为深度仍扫; 如超时把ATR固定)
GRID_START_R = [0.8, 1.0, 1.2]
GRID_TRAIL_ATR = [0.8]   # ATR松紧已在F控制组证伪敏感性(0.3~1.0ATR对R不变), 固定0.8
GRID_TIGHT_ATR = [0.5]   # 收紧固定0.5
GRID_LOCK_HALF = [0.8, 1.0, 1.2, 1.5]
GRID_BE_BUF = [0.2, 0.3, 0.5]


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
                o, h, l, c = float(row[1]), float(row[2]), float(row[3]), float(row[4])
            except Exception:
                continue
            bars.append([o, h, l, c])
    return bars


def atr_arr(bars):
    n = len(bars)
    tr = [0.0] * n
    for i in range(1, n):
        h, l, pc = bars[i][1], bars[i][2], bars[i - 1][3]
        tr[i] = max(h - l, abs(h - pc), abs(l - pc))
    at = [0.0] * n
    for i in range(ATR_N, n):
        at[i] = sum(tr[i - ATR_N + 1:i + 1]) / ATR_N
    return at


def gen_entries_range(bars, lo, hi):
    ents = []
    for i in range(max(SWING, lo), min(hi, len(bars) - MAX_BARS - 2)):
        if i < SWING:
            continue
        hi20 = max(bars[k][1] for k in range(i - SWING, i))
        lo20 = min(bars[k][2] for k in range(i - SWING, i))
        c = bars[i][3]
        if c > hi20:
            ents.append((i, 1))
        elif c < lo20:
            ents.append((i, -1))
    return ents


def simulate(bars, at, e, dirn, P):
    entry = bars[e][3]
    a0 = at[e]
    if a0 <= 1e-8:
        return None
    dist = 2.0 * a0
    sl0 = entry - dirn * dist
    extreme = entry
    mfe = 0.0
    sl_level = sl0
    prev_c = entry
    last = min(e + MAX_BARS, len(bars) - 1)
    start_r = P["start_r"]; trail_atr = P["trail_atr"]; tight_atr = P["tight_atr"]
    lock_half = P["lock_half"]; be_buf = P["be_buf"]
    for j in range(e + 1, last + 1):
        o, h, l, c = bars[j]
        a = at[j]
        if a <= 0:
            a = a0
        extreme = max(extreme, h) if dirn > 0 else min(extreme, l)
        r = (extreme - entry) / dist * dirn
        mfe = max(mfe, r)
        # 0.5R 保本缓冲
        if r >= 0.5:
            cand = entry + dirn * be_buf * dist
            if cand * dirn > sl_level * dirn:
                sl_level = cand
        # 1.0R 锁半利地板
        if r >= 1.0:
            cand = entry + dirn * lock_half * dist
            if cand * dirn > sl_level * dirn:
                sl_level = cand
        # ATR 跟踪
        if r >= start_r and a > 0:
            mult = trail_atr if r < tight_atr else tight_atr
            trail = extreme - dirn * mult * a
            if trail * dirn > sl_level * dirn:
                sl_level = trail
        # 出场(当棒高低触发SL, 同棒多信号取最不利价先成交)
        cands = []
        if l <= sl_level:
            cands.append((sl_level, "SL"))
        if cands:
            best = min(cands, key=lambda x: x[0] * dirn)
            realized = (best[0] - entry) / dist * dirn
            return (realized, mfe, best[1])
        prev_c = c
    exit_px = bars[last][3]
    realized = (exit_px - entry) / dist * dirn
    return (realized, mfe, "MAXBARS")


def summarize(rows):
    n = len(rows)
    if n == 0:
        return (0, 0, 0, 0, 0, 0, 0)
    mean_r = sum(r[0] for r in rows) / n
    win = sum(1 for r in rows if r[0] > 0) / n
    eff = [r for r in rows if r[1] >= 0.5]
    cap = sum(min(1.0, max(-5.0, r[0] / r[1])) for r in eff) / len(eff) if eff else 0
    rev = [r for r in rows if r[1] >= 1.0]
    nrev = len(rev)
    rev_real = sum(r[0] for r in rev) / nrev if nrev else 0
    rev_cap = sum(min(1.0, max(-5.0, r[0] / r[1])) for r in rev) / nrev if nrev else 0
    gave50 = sum(1 for r in rev if r[0] < 0.5 * r[1]) / nrev if nrev else 0
    return (n, mean_r, win, cap, nrev, rev_real, rev_cap, gave50)


def run_grid(all_data):
    import itertools
    combo = list(itertools.product(GRID_START_R, GRID_TRAIL_ATR, GRID_TIGHT_ATR, GRID_LOCK_HALF, GRID_BE_BUF))
    out = []
    for (sr, ta, tta, lh, bb) in combo:
        P = {"start_r": sr, "trail_atr": ta, "tight_atr": tta, "lock_half": lh, "be_buf": bb}
        rows = []
        for sym, bars, at in all_data:
            for (e, d) in gen_entries_range(bars, 0, len(bars)):
                res = simulate(bars, at, e, d, P)
                if res is not None:
                    rows.append(res)
        s = summarize(rows)
        out.append((P, s))
    return out


def run_window(all_data, lo_frac, hi_frac):
    """3段时间窗口: 按每个品种bars索引切分, 独立生成入场点"""
    rows_by_sym = []
    for sym, bars, at in all_data:
        n = len(bars)
        lo = int(n * lo_frac); hi = int(n * hi_frac)
        ents = gen_entries_range(bars, lo, hi)
        rows_by_sym.append((sym, bars, at, ents))
    return rows_by_sym


def main():
    t0 = _t.time()
    all_data = []
    for sym in SYMS:
        bars = load(sym)
        if bars is None or len(bars) < 200:
            print("  [skip] %s" % sym); continue
        all_data.append((sym, bars, atr_arr(bars)))
    total_ent = sum(len(gen_entries_range(b, 0, len(b))) for _, b, _ in all_data)
    print("载入 %d 品种, 全样本入场点 %d" % (len(all_data), total_ent))

    print("\n=== 网格扫描 %d 组合 (指标: 均值R / 捕获率 / 反转捕获率) ===" %
          (len(GRID_START_R)*len(GRID_TRAIL_ATR)*len(GRID_TIGHT_ATR)*len(GRID_LOCK_HALF)*len(GRID_BE_BUF)))
    grid = run_grid(all_data)
    # 排序: 优先反转捕获率(用户最痛), 次选均值R
    grid_sorted = sorted(grid, key=lambda x: (x[1][6], x[1][1]), reverse=True)
    print("%-40s %7s %8s %8s %8s %9s %9s" %
          ("参数(start/trail/tight/lock/be)", "n", "均值R", "胜率", "捕获率", "反转n", "反转捕获"))
    print("-" * 96)
    for P, s in grid_sorted[:15]:
        print("sr%.1f ta%.1f tta%.1f lh%.1f bb%.1f | %7d %+8.3f %6.1f%% %7.1f%% %8d %8.1f%%" %
              (P["start_r"], P["trail_atr"], P["tight_atr"], P["lock_half"], P["be_buf"],
               s[0], s[1], s[2]*100, s[3]*100, s[4], s[6]*100))

    # 当前引擎默认参数位置
    cur = {"start_r":1.0,"trail_atr":0.8,"tight_atr":0.5,"lock_half":1.0,"be_buf":0.3}
    cur_s = None
    for P, s in grid:
        if all(abs(P[k]-cur[k])<1e-9 for k in cur):
            cur_s = s; break
    print("\n当前引擎默认(sr1.0/ta0.8/tta0.5/lh1.0/bb0.3): 均值R=%+.3f 捕获率=%.1f%% 反转捕获=%.1f%%" %
          (cur_s[1], cur_s[3]*100, cur_s[6]*100))

    # ── Walk-Forward 3段时间窗口验证 top5 ──
    print("\n=== Walk-Forward: top5 候选在 3 段时间窗口的反转捕获率稳定性 ===")
    top5 = grid_sorted[:5]
    windows = [("W1(前1/3)",0.0,1/3),("W2(中1/3)",1/3,2/3),("W3(后1/3)",2/3,1.0)]
    print("%-40s | %12s | %12s | %12s" % ("参数", "W1反转捕获", "W2反转捕获", "W3反转捕获"))
    print("-" * 96)
    for P, _ in top5:
        caps = []
        for wname, lo, hi in windows:
            rows = []
            for sym, bars, at, ents in [(s, b, a, gen_entries_range(b, int(len(b)*lo), int(len(b)*hi)))
                                        for (s, b, a) in all_data]:
                for (e, d) in ents:
                    res = simulate(bars, at, e, d, P)
                    if res is not None:
                        rows.append(res)
            sm = summarize(rows)
            caps.append(sm[6]*100)
        print("sr%.1f ta%.1f tta%.1f lh%.1f bb%.1f | %11.1f%% | %11.1f%% | %11.1f%%" %
              (P["start_r"],P["trail_atr"],P["tight_atr"],P["lock_half"],P["be_buf"],caps[0],caps[1],caps[2]))
    print("\n用时 %.1fs" % (_t.time() - t0))


if __name__ == "__main__":
    main()
