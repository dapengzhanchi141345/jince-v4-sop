# -*- coding: utf-8 -*-
"""
行情反转早出场 · 深度优化回测
================================
用户命门: "关键在行情反转的时候 及时出场" —— 当前 PROFIT_SECURE 靠 ATR 跟踪,
反转时要先回吐 0.8ATR(或0.5ATR)才触发。本脚本验证: 能否比 ATR 跟踪更早识别反转、
在更接近极值的位置出场, 且不增加噪音误杀。

统一框架(与 exit_combined_optimize.py 一致, 保证可比):
  入场: H1 swing突破(20根) @ 突破棒收盘
  SL  : 2×ATR(14) @ 入场
  无初始TP; MAX_BARS=48(≈2天, 聚焦"小波段行情")
  R 缩放: dist = 2×ATR(entry)

出场模式:
  S  : 当前 DEMO 紧锁利(忠实复刻引擎 L676-715: BE0.3R/锁半利0.6R/1R起0.8ATR/1.5R收紧0.5ATR)
  B  : 结构破位早出场 + ATR回补  (K=近K根swing低点, 收线跌破即出)
  C  : 动量反扑早出场 + ATR回补  (反向收盘≥β·ATR的"反扑棒", 收线即出)
  D  : 自适应收紧跟踪(无收线信号, 仅倍数随R收缩)
  E  : 混合 = B∪C∪D 任一先触发即出(最早者)

指标: 均值R / 胜率 / 捕获率(落袋/MFE) / 反转回吐子集(MFE≥1R)的 落袋均R 与 捕获率 与 ">50%回吐占比"

忠实度: 复刻引擎 _be_buf=0.3*dist, 锁半利0.6R, ATR trail 0.8→0.5。
"""
import csv, os, time as _t

ROOT = "E:/GoldstrategyEngine"
DATA = os.path.join(ROOT, "data")
SYMS = ["XAUUSD", "BTCUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30", "XAGUSD"]
MAX_BARS = 48
SWING = 20
ATR_N = 14

# ── 忠实复刻引擎 PROFIT_SECURE 常量 ──
PS_TRAIL_START_R = 1.0
PS_TRAIL_ATR = 0.8
PS_TRAIL_TIGHT_R = 1.5
PS_TRAIL_TIGHT_ATR = 0.5
PS_LOCK_HALF_R = 0.6
PS_BE_BUF_R = 0.3


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


def gen_entries(bars):
    ents = []
    n = len(bars)
    for i in range(SWING, n - MAX_BARS - 2):
        hi = max(bars[k][1] for k in range(i - SWING, i))
        lo = min(bars[k][2] for k in range(i - SWING, i))
        c = bars[i][3]
        if c > hi:
            ents.append((i, 1))
        elif c < lo:
            ents.append((i, -1))
    return ents


def simulate(bars, at, e, dirn, mode, params):
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
    K = params.get("K", 5)
    beta = params.get("beta", 0.8)
    for j in range(e + 1, last + 1):
        o, h, l, c = bars[j]
        a = at[j]
        if a <= 0:
            a = a0
        extreme = max(extreme, h) if dirn > 0 else min(extreme, l)
        r = (extreme - entry) / dist * dirn
        mfe = max(mfe, r)
        # ── 忠实复刻引擎锁利阶梯 (S 基线也含这些固定档) ──
        be_buf = params.get("be_buf", PS_BE_BUF_R)
        lock_half = params.get("lock_half", PS_LOCK_HALF_R)
        if r >= 0.5:
            cand = entry + dirn * be_buf * dist
            if cand * dirn > sl_level * dirn:
                sl_level = cand
        if r >= 1.0:
            cand = entry + dirn * lock_half * dist
            if cand * dirn > sl_level * dirn:
                sl_level = cand
        # ATR 跟踪 (S 基线)
        trailed = False
        if r >= PS_TRAIL_START_R and a > 0:
            mult = PS_TRAIL_ATR if r < PS_TRAIL_TIGHT_R else PS_TRAIL_TIGHT_ATR
            trail = extreme - dirn * mult * a
            if trail * dirn > sl_level * dirn:
                sl_level = trail
                trailed = True
        # ── 早反转出场候选 ──
        cands = []  # (price, tag)
        # 固定SL/跟踪触发
        if l <= sl_level:
            cands.append((sl_level, "SL/TRAIL"))
        if mode in ("B", "E"):
            if r >= 0.5 and j - max(e + 1, j - K) >= 1:
                lo0 = max(e + 1, j - K)
                swl = min(bars[t][2] for t in range(lo0, j))
                if dirn > 0 and c < swl:
                    cands.append((c, "STRUCT"))
                if dirn < 0 and c > swl:
                    cands.append((c, "STRUCT"))
        if mode in ("C", "E"):
            if r >= 0.5 and a > 0:
                move = (prev_c - c) * dirn  # 对多: 前收-今收(下跌量); 对空: 今收-前收(上涨量)
                if move >= beta * a:
                    cands.append((c, "IMPULSE"))
        if mode in ("D", "E"):
            if r >= PS_TRAIL_START_R and a > 0:
                mult2 = min(0.8, max(0.2, 0.8 - 0.15 * max(0.0, r - 1.0)))
                trail2 = extreme - dirn * mult2 * a
                if trail2 * dirn > sl_level * dirn:
                    cands.append((trail2, "ADAPT"))
        if mode == "F":
            # 控制组: 固定跟踪倍数(自1.0R起), 隔离"跟踪该多紧"
            if r >= PS_TRAIL_START_R and a > 0:
                multf = params.get("mult", 0.8)
                trailf = extreme - dirn * multf * a
                if trailf * dirn > sl_level * dirn:
                    cands.append((trailf, "FIXTRAIL"))
        if mode == "G":
            # 波动回撤跟踪: 锁定整段行情的50%回撤(经典波浪半仓), 自1.0R起, 下限BE+0.3R
            if r >= PS_TRAIL_START_R:
                half = entry + dirn * 0.5 * (extreme - entry)
                if half * dirn > sl_level * dirn:
                    cands.append((half, "WAVE50"))
        if cands:
            # 保守成交价: 同棒若多信号触发, 价格先打到更不利方向(多单=最低触发价)的止损先成交
            best = min(cands, key=lambda x: x[0] * dirn)
            exit_px = best[0]
            reason = best[1]
            realized = (exit_px - entry) / dist * dirn
            return (realized, mfe, reason)
        prev_c = c
    exit_px = bars[last][3]
    realized = (exit_px - entry) / dist * dirn
    return (realized, mfe, "MAXBARS")


def run_mode(mode, params, all_data):
    rows = []
    for sym, bars, at in all_data:
        ents = gen_entries(bars)
        for (e, d) in ents:
            res = simulate(bars, at, e, d, mode, params)
            if res is None:
                continue
            rows.append(res)
    return rows


def summarize(rows):
    n = len(rows)
    if n == 0:
        return (0, 0, 0, 0, 0, 0, 0)
    mean_r = sum(r[0] for r in rows) / n
    win = sum(1 for r in rows if r[0] > 0) / n
    # 捕获率(仅对有过≥0.5R浮盈的有效单)——避免 MFE≈0 小分母爆炸
    eff = [r for r in rows if r[1] >= 0.5]
    cap = sum(min(1.0, max(-5.0, r[0] / r[1])) for r in eff) / len(eff) if eff else 0
    # 反转回吐子集: MFE>=1R (有真实盈利波段)
    rev = [r for r in rows if r[1] >= 1.0]
    nrev = len(rev)
    rev_real = sum(r[0] for r in rev) / nrev if nrev else 0
    rev_cap = sum(min(1.0, max(-5.0, r[0] / r[1])) for r in rev) / nrev if nrev else 0
    gave50 = sum(1 for r in rev if r[0] < 0.5 * r[1]) / nrev if nrev else 0
    return (n, mean_r, win, cap, nrev, rev_real, rev_cap, gave50)


def main():
    t0 = _t.time()
    all_data = []
    for sym in SYMS:
        bars = load(sym)
        if bars is None or len(bars) < 200:
            print("  [skip] %s 数据不足" % sym)
            continue
        all_data.append((sym, bars, atr_arr(bars)))
    print("载入 %d 品种, 共 %d 入场点" % (len(all_data),
          sum(len(gen_entries(b)) for _, b, _ in all_data)))

    variants = [
        ("S·当前紧锁利基线(0.8→0.5)", "S", {}),
        ("F·固定0.3ATR", "F", {"mult": 0.3}),
        ("F·固定0.5ATR", "F", {"mult": 0.5}),
        ("F·固定0.8ATR", "F", {"mult": 0.8}),
        ("F·固定1.0ATR", "F", {"mult": 1.0}),
        ("B·结构破位 K=5", "B", {"K": 5}),
        ("C·反扑棒 β=0.8", "C", {"beta": 0.8}),
        ("D·自适应收紧", "D", {}),
        ("E·混合B5+C0.8+D", "E", {"K": 5, "beta": 0.8}),
        ("G·波动50%回撤跟踪", "G", {}),
        ("H·锁半利0.8R", "S", {"lock_half": 0.8}),
        ("H·锁半利1.0R", "S", {"lock_half": 1.0}),
        ("H·锁半利1.2R", "S", {"lock_half": 1.2}),
        ("H·锁半利1.5R", "S", {"lock_half": 1.5}),
    ]
    print("\n%-26s %7s %8s %7s %9s %9s %9s %9s" %
          ("模式", "n", "均值R", "胜率", "捕获率", "反转n", "反转均R", "反转捕获"))
    print("-" * 100)
    results = {}
    for name, mode, params in variants:
        rows = run_mode(mode, params, all_data)
        s = summarize(rows)
        results[name] = s
        print("%-26s %7d %+8.3f %6.1f%% %8.1f%% %9d %8.3f %8.1f%%" %
              (name, s[0], s[1], s[2] * 100, s[3] * 100, s[4], s[5], s[6] * 100))
    # 逐品种 S vs 最佳早出场 (E)
    print("\n=== 逐品种: S基线 vs E混合(反转均R / 反转捕获率) ===")
    print("%-10s | %12s | %12s | %12s" % ("品种", "S反转均R", "E反转均R", "E反转捕获"))
    print("-" * 52)
    for sym, bars, at in all_data:
        rows_s = run_mode("S", {}, [(sym, bars, at)])
        rows_e = run_mode("E", {"K": 5, "beta": 0.8}, [(sym, bars, at)])
        rs = summarize(rows_s); re = summarize(rows_e)
        print("%-10s | %+11.3f | %+11.3f | %11.1f%%" % (sym, rs[4], re[4], re[5] * 100))
    print("\n用时 %.1fs" % (_t.time() - t0))


if __name__ == "__main__":
    main()
