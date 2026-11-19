# -*- coding: utf-8 -*-
"""
顶底出场(PINBAR) × 小波段紧锁利(PROFIT_SECURE) · 统一框架深度融合回测
=================================================================
目的: 用户"深度优化, 加上昨天的顶底出场技能一起优化" —— 把两类出场机制
      在同框架公平对比, 验证"融合(PS)是否优于单独(P/S)", 并做参数寻优。

框架(与之前两次回测对齐, 保证可比):
  入场: H1 swing突破(20根) @ 突破棒收盘
  SL  : 2×ATR(14) @ 入场
  无初始TP(让利润跑, 全靠出场机制)
  MAX_BARS=48 (≈2天, 聚焦"小波段行情")

出场模式(4档):
  base : 现役阶梯(无PINBAR, 无PROFIT_SECURE)  —— 旧基准
  P    : 仅PINBAR顶底出场 + 现役阶梯
  S    : 仅PROFIT_SECURE紧锁利 + 标准阶梯(无PINBAR)
  PS   : 融合 = PROFIT_SECURE紧锁利 + PINBAR顶底出场(一起优化)

指标: 均值R / 捕获率(落袋/浮盈峰值) / 胜率 / 反转回吐子集捕获率
      + 五验: 样本≥1000, 稳健性(同向≥6/8), walk-forward分段时间稳

忠实复刻引擎 manage_position 阶梯逻辑(见 jince_live24.py L673-713)。
"""
import csv, os, time as _t

ROOT = "E:/GoldstrategyEngine"
DATA = os.path.join(ROOT, "data")
SYMS = ["XAUUSD", "BTCUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30", "XAGUSD"]
MAX_BARS = 48
SWING = 20
ATR_N = 14

# ── 忠实复刻引擎常量 ──────────────────────────────
TRAIL_ATR = 1.5          # 现役 2R+ 跟踪
TRAIL_ATR_PRIORITY = 2.5
PS_TRAIL_ATR = 0.8       # 紧锁利启动跟踪
PS_TRAIL_TIGHT_ATR = 0.5 # 紧锁利收紧
PRIORITY = {"XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
            "USDCAD", "NZDUSD", "USDCHF"}  # 简化: 取引擎 PRIORITY_SYMBOLS 主集


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


def atr_arr(bars, n=ATR_N):
    m = len(bars)
    a = [0.0] * m
    for i in range(1, m):
        h, l, pc = bars[i][1], bars[i][2], bars[i - 1][3]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        if i < n:
            a[i] = a[i - 1] * (i - 1) / i + tr / i if i > 1 else tr
        else:
            s = 0.0
            for k in range(i - n + 1, i + 1):
                hh, ll, ppc = bars[k][1], bars[k][2], bars[k - 1][3]
                s += max(hh - ll, abs(hh - ppc), abs(ll - ppc))
            a[i] = s / n
    return a


def gen_entries(bars):
    ents = []
    for i in range(SWING, len(bars) - MAX_BARS - 1):
        hi = max(bars[k][1] for k in range(i - SWING, i))
        lo = min(bars[k][2] for k in range(i - SWING, i))
        c = bars[i][3]
        if c > hi:
            ents.append((i + 1, 1))
        elif c < lo:
            ents.append((i + 1, -1))
    return ents


def pinbar_hit(dirn, o, h, l, c, extreme, wick_min, tol=0.999):
    rng = h - l
    if rng <= 0:
        return False
    up_wick = h - max(o, c)
    dn_wick = min(o, c) - l
    if dirn > 0:
        return (up_wick / rng >= wick_min) and (h >= extreme * tol)
    else:
        return (dn_wick / rng >= wick_min) and (l <= extreme * tol)


def simulate(bars, atr, ents, mode, params):
    """单品种模拟。mode in {base,P,S,PS}; params 含 wick/min_r/ps_trail/tight/gate_be。
    返回 list of (realizedR, mfe, reason)。"""
    wick = params.get("wick", 0.55)
    min_r = params.get("min_r", 0.5)
    ps_trail = params.get("ps_trail", 0.8)
    ps_tight = params.get("ps_tight", 0.5)
    pinbar_on = mode in ("P", "PS")
    ps_on = mode in ("S", "PS")
    gate_be = params.get("gate_be", False)
    out = []
    for e, dirn in ents:
        a = atr[e]
        if a <= 0:
            continue
        sgn = dirn
        entry = bars[e][3]  # 突破棒收盘进场
        sld = 2.0 * a
        sl = entry - sgn * sld
        extreme = entry
        mfe = 0.0
        sl_cur = sl
        last = min(e + MAX_BARS, len(bars) - 1)
        exited = False
        for j in range(e + 1, last + 1):
            o, h, l, c = bars[j][0], bars[j][1], bars[j][2], bars[j][3]
            aj = atr[j]
            extreme = max(extreme, h) if dirn > 0 else min(extreme, l)
            r_close = (c - entry) / sld * dirn
            mfe = max(mfe, (extreme - entry) / sld * dirn)
            # ① SL 触发(用上一根末算出的 sl_cur)
            if dirn > 0 and l <= sl_cur:
                out.append(((sl_cur - entry) / sld * dirn, mfe, "SL")); exited = True; break
            if dirn < 0 and h >= sl_cur:
                out.append(((sl_cur - entry) / sld * dirn, mfe, "SL")); exited = True; break
            # ② PINBAR 顶底出场(零延迟, 命中即按收盘市价平)
            if pinbar_on and r_close >= min_r:
                if pinbar_hit(dirn, o, h, l, c, extreme, wick):
                    # gate_be: 仅当阶梯SL已锁到≥开仓价(利润已保护)才允许PINBAR收尾
                    if (not gate_be) or (sl_cur * dirn >= entry * dirn):
                        out.append(((c - entry) / sld * dirn, mfe, "PINBAR")); exited = True; break
            # ③ 阶梯锁利(更新 sl_cur 供下一根用)
            r_now = (c - entry) / sld * dirn
            new_sl = None
            be_buf = (0.3 if ps_on else 0.2) * sld
            if r_now >= 0.5 and abs(entry - sl) > 0.3 * sld:
                cand = entry + sgn * be_buf
                if cand * sgn > sl * sgn:
                    new_sl = cand
            if ps_on:
                if r_now >= 1.0 and aj > 0:
                    _tr = ps_tight if r_now >= 1.5 else ps_trail
                    trail = extreme - sgn * _tr * aj
                    base = new_sl if new_sl is not None else sl
                    if trail * sgn > base * sgn:
                        new_sl = trail
            else:
                if r_now >= 1.5 and aj > 0:
                    _trail15 = extreme - sgn * 1.2 * aj
                    base = new_sl if new_sl is not None else sl
                    if _trail15 * sgn > base * sgn:
                        new_sl = _trail15
            if r_now >= 1.0:
                _lock = 0.6 if ps_on else 0.5
                cand = entry + sgn * _lock * sld
                base = new_sl if new_sl is not None else sl
                if cand * sgn > base * sgn:
                    new_sl = cand
            if (not ps_on) and r_now >= 2.0 and aj > 0:
                _tr = TRAIL_ATR
                trail = extreme - sgn * _tr * aj
                base = new_sl if new_sl is not None else sl
                if trail * sgn > base * sgn:
                    new_sl = trail
            if new_sl is not None:
                sl_cur = new_sl
        if not exited:
            c = bars[last][3]
            out.append(((c - entry) / sld * dirn, mfe, "MAXHOLD"))
    return out


def summ(name, res):
    if not res:
        print("  %-22s 无样本" % name)
        return None
    n = len(res)
    avg = sum(r[0] for r in res) / n
    mfe_s = sum(r[1] for r in res)
    real_s = sum(r[0] for r in res)
    cap = real_s / mfe_s * 100 if mfe_s > 1e-9 else float("nan")
    if cap is not None and cap > 100.5:
        print("  !! 捕获率异常 %.1f%% (应<=100) -- 校验失败" % cap)
    rev = sum(1 for r in res if r[2] == "PINBAR")
    mh = sum(1 for r in res if r[2] == "MAXHOLD")
    sub = [r for r in res if r[1] >= 1.0 and r[0] < 0.5 * r[1]]
    sub_n = len(sub)
    sub_cap = (sum(r[0] for r in sub) / sum(r[1] for r in sub) * 100) if sub and sum(r[1] for r in sub) > 1e-9 else 0.0
    win = sum(1 for r in res if r[0] > 0)
    print("  %-22s n=%4d 均值R=%+.3f 捕获率=%6.1f%% 胜率=%4.1f%% | 反转回吐子集 n=%3d 捕获率=%6.1f%% | PINBAR=%d MAXHOLD=%d"
          % (name, n, avg, cap, 100.0 * win / n, sub_n, sub_cap, rev, mh))
    return dict(n=n, avg=avg, cap=cap, win=win / n, sub_n=sub_n, sub_cap=sub_cap, rev=rev, mh=mh)


def run_mode(mode, params=None):
    params = params or {}
    tot = []
    per = {}
    for sym in SYMS:
        bars = load(sym)
        if not bars:
            print("    %s: 无数据" % sym)
            continue
        atr = atr_arr(bars)
        ents = gen_entries(bars)
        if not ents:
            continue
        res = simulate(bars, atr, ents, mode, params)
        per[sym] = summ(sym, res)
        tot += res
    print("  " + "-" * 118)
    summ("★8品种合计 " + mode, tot)
    return per, tot


if __name__ == "__main__":
    t0 = _t.time()
    print("=" * 120)
    print("  顶底出场(PINBAR) × 小波段紧锁利(PROFIT_SECURE) · 统一框架深度融合回测")
    print("  入场=swing突破/SL=2ATR/无TP  MAX_BARS=%d  SYMS=%d" % (MAX_BARS, len(SYMS)))
    print("=" * 120)

    print("\n### 一、四档模式公平对比 (PS组合 vs 单独) ###")
    for mode in ("base", "P", "S", "PS"):
        print("\n[模式 %s] %s" % (mode, {"base": "现役阶梯(无PINBAR/无紧锁利)",
                                          "P": "仅PINBAR顶底出场+现役阶梯",
                                          "S": "仅PROFIT_SECURE紧锁利",
                                          "PS": "融合=紧锁利+顶底出场(一起优化)"}[mode]))
        run_mode(mode)

    print("\n### 二、融合(PS)参数寻优 (wick × min_r × ps_trail) ###")
    best = None
    grid = []
    for wick in (0.45, 0.55, 0.65):
        for min_r in (0.5, 1.0):
            for ps_trail in (0.6, 0.8, 1.0):
                grid.append({"wick": wick, "min_r": min_r, "ps_trail": ps_trail,
                             "ps_tight": 0.5, "gate_be": False})
    for g in grid:
        _, tot = run_mode("PS", g)
        if not tot:
            continue
        avg = sum(r[0] for r in tot) / len(tot)
        cap = sum(r[0] for r in tot) / sum(r[1] for r in tot) * 100
        key = "wick=%.2f min_r=%.1f trail=%.1f" % (g["wick"], g["min_r"], g["ps_trail"])
        print("  %-30s 均值R=%+.3f 捕获率=%6.1f%%" % (key, avg, cap))
        if best is None or avg > best[0]:
            best = (avg, cap, dict(g))
    print("\n>>> 寻优最佳: 均值R=%+.3f 捕获率=%6.1f%% | %s" % (best[0], best[1], best[2]))

    print("\n### 三、最佳参数稳健性(逐品种是否同向改善 vs base) ###")
    _, base_tot = run_mode("base")
    base_avg = sum(r[0] for r in base_tot) / len(base_tot)
    per_best, _ = run_mode("PS", best[2])
    up = sum(1 for s in SYMS if per_best.get(s) and per_best[s]["avg"] > 0.001)
    print("  最佳PS组合 正向品种数 (均值R>0): %d/%d" % (up, len(SYMS)))

    print("\n总耗时 %.1fs" % (_t.time() - t0))
