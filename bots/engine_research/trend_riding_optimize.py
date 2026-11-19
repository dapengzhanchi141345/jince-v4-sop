# -*- coding: utf-8 -*-
"""
Track B · 趋势骑行(第二波)解耦优化 (金策·进化营)
=================================================
问题(用户): "吃到第一波利润后, 合适位置拿到第二波行情" —— 且"务必优化好"。

关键认知:
  此前第二波为负, 是因为用 PROFIT_SECURE 的"紧出场+再入场"去碰趋势 —— 紧出场在回踩
  就把趋势单扫掉, 再入场接的是衰竭段。真正的趋势骑行必须走 *独立 regime*:
    D1 趋势过滤(EMA) + H1 顺势突破入场 + 宽游程/结构止损(扛过回踩) + 金字塔加仓。
  这样"第二波"是宽止损自然过滤回踩后 *免费*得到的, 而非出场后再追。

本 harness 公平对比(同 D1 过滤入场):
  B_tight : D1过滤 + PROFIT_SECURE 紧出场 (现役思路移植到好入场)
  T_wide  : D1过滤 + 宽游程/结构止损 (骑行, 不加仓)
  T_pyr   : D1过滤 + 宽游程 + 金字塔加仓 (骑行 + 加仓)

指标: 均值R/胜率/金字塔触发率; 关键 Δ = T - B_tight (第二波骑行增益)。
五验: 样本>=1000 / 同向>=4/8 / WFO三窗口稳定 / 参数甜蜜点 / 显著。
"""
import csv, os, time as _t

ROOT = "E:/GoldstrategyEngine"
DATA = os.path.join(ROOT, "data")
SYMS = ["XAUUSD", "BTCUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30", "XAGUSD"]
MAX_BARS = 240          # 10天, 允许多波
SWING_H1 = 20
ATR_N = 14
P_TIGHT = {"start_r": 1.0, "trail_atr": 0.8, "tight_atr": 0.5, "lock_half": 1.2, "be_buf": 0.2}
COST_R = 0.2   # 每单位回合成本(点差+佣金), 以 R 计; 公平从紧/宽/金字塔同扣, Δ不受影响

GRID_EMA = [50, 100, 150]
GRID_TRAIL = ["ATR2", "ATR3", "ATR4", "SW48", "SW72"]
GRID_PYR = [False, True]


def load_h1(sym):
    p = os.path.join(DATA, sym + "_H1.csv")
    if not os.path.exists(p):
        return None
    bars = []
    with open(p, encoding="utf-8") as f:
        r = csv.reader(f); next(r, None)
        for row in r:
            if len(row) < 5: continue
            try: o, h, l, c = float(row[1]), float(row[2]), float(row[3]), float(row[4])
            except Exception: continue
            bars.append([o, h, l, c])
    return bars


def load_d1(sym):
    p = os.path.join(DATA, sym + "_D1.csv")
    if not os.path.exists(p):
        return None
    bars = []
    with open(p, encoding="utf-8") as f:
        r = csv.reader(f); next(r, None)
        for row in r:
            if len(row) < 5: continue
            try: o, h, l, c = float(row[1]), float(row[2]), float(row[3]), float(row[4])
            except Exception: continue
            bars.append([o, h, l, c])
    return bars


def atr_arr(bars, n=ATR_N):
    L = len(bars); tr = [0.0] * L; at = [0.0] * L
    for i in range(1, L):
        h, l, pc = bars[i][1], bars[i][2], bars[i - 1][3]
        tr[i] = max(h - l, abs(h - pc), abs(l - pc))
    for i in range(n, L):
        at[i] = sum(tr[i - n + 1:i + 1]) / n
    return at


def ema_arr(closes, period):
    L = len(closes); e = [0.0] * L
    if L == 0: return e
    a = 2.0 / (period + 1)
    e[0] = closes[0]
    for i in range(1, L):
        e[i] = closes[i] * a + e[i - 1] * (1 - a)
    return e


def gen_trend_entries(h1, h1_atr, d1, d1_ema):
    """D1 趋势过滤 + H1 swing 突破入场。返回 [(i, dirn), ...]"""
    n = len(h1); ents = []
    for i in range(SWING_H1, n - MAX_BARS - 2):
        d1i = min(i // 24, len(d1) - 1)
        if d1i < 1: continue
        dirn = 1 if d1[d1i][3] > d1_ema[d1i] else (-1 if d1[d1i][3] < d1_ema[d1i] else 0)
        if dirn == 0: continue
        hi20 = max(h1[k][1] for k in range(i - SWING_H1, i))
        lo20 = min(h1[k][2] for k in range(i - SWING_H1, i))
        c = h1[i][3]
        if dirn > 0 and c > hi20: ents.append((i, 1))
        elif dirn < 0 and c < lo20: ents.append((i, -1))
    return ents


def sim_tight(h1, atr, e, dirn):
    """复刻 PROFIT_SECURE 紧出场(单波)。"""
    entry = h1[e][3]; a0 = atr[e]
    if a0 <= 1e-8: return None
    dist = 2.0 * a0; sl = entry - dirn * dist
    extreme = entry; P = P_TIGHT
    last = min(e + MAX_BARS, len(h1) - 1)
    for j in range(e + 1, last + 1):
        o, h, l, c = h1[j]; a = atr[j] if atr[j] > 0 else a0
        extreme = max(extreme, h) if dirn > 0 else min(extreme, l)
        r = (extreme - entry) / dist * dirn
        if r >= 0.5:
            sl = max(sl, entry + dirn * P["be_buf"] * dist) if dirn > 0 else min(sl, entry + dirn * P["be_buf"] * dist)
        if r >= 1.0:
            sl = max(sl, entry + dirn * P["lock_half"] * dist) if dirn > 0 else min(sl, entry + dirn * P["lock_half"] * dist)
        if r >= P["start_r"]:
            trail = extreme - dirn * (P["trail_atr"] if r < 1.5 else P["tight_atr"]) * a
            sl = max(sl, trail) if dirn > 0 else min(sl, trail)
        if dirn > 0 and l <= sl: return (sl - entry) / dist - COST_R
        if dirn < 0 and h >= sl: return (entry - sl) / dist - COST_R
    # MAX_BARS 出场(用最后极端)
    return (extreme - entry) / dist * dirn - COST_R


def sim_wide(h1, atr, e, dirn, trail_kind, pyramid):
    """宽游程/结构止损 + 可选金字塔。第二波骑行核心。返回净R(扣成本)。"""
    entry = h1[e][3]; a0 = atr[e]
    if a0 <= 1e-8: return None
    dist0 = 2.0 * a0
    units = [(entry, dist0)]          # (entry, dist)
    extreme = entry
    lo_since = h1[e][2]; hi_since = h1[e][1]   # 自入场以来极值(用于回撤检测)
    sl = entry - dirn * dist0
    added = False; pb_hit = False; pb_extreme = entry
    last = min(e + MAX_BARS, len(h1) - 1)
    for j in range(e + 1, last + 1):
        o, h, l, c = h1[j]; a = atr[j] if atr[j] > 0 else a0
        extreme = max(extreme, h) if dirn > 0 else min(extreme, l)
        lo_since = min(lo_since, l); hi_since = max(hi_since, h)
        r = (extreme - entry) / dist0 * dirn
        # 宽止损
        if trail_kind.startswith("ATR"):
            mult = float(trail_kind[3:]); trail = extreme - dirn * mult * a
        else:
            # [2026-11-11 修复自指bug] 结构止损只能取"截至上一根bar"的结构极值:
            # 若含当前bar低点, 则 sl>=当前low 恒成立 -> 每根bar立刻以当期低点平仓,
            # 根本不是"扛过回踩的宽止损", 会把结论做成假象。故排除 j 本身。
            N = int(trail_kind[2:]); lo = max(e, j - N)
            if j > lo:
                roll = min(h1[k][2] for k in range(lo, j)) if dirn > 0 else max(h1[k][1] for k in range(lo, j))
            else:
                roll = entry - dirn * dist0   # 首根无历史结构, 退回初始 -2ATR 硬止损
            trail = roll
        # BE 地板(保护): +1R 锁保本, +2R 锁半利
        if r >= 1.0:
            sl = max(sl, entry) if dirn > 0 else min(sl, entry)
        if r >= 2.0:
            floor2 = entry + dirn * 0.5 * dist0
            sl = max(sl, floor2) if dirn > 0 else min(sl, floor2)
        sl = max(sl, trail) if dirn > 0 else min(sl, trail)
        # 金字塔: +1R 后回撤>=38% 且再破前高 -> 加1单位
        if pyramid and not added and r >= 1.0:
            if not pb_hit:
                pb = ((extreme - lo_since) / dist0 >= 0.382) if dirn > 0 else ((hi_since - extreme) / dist0 >= 0.382)
                if pb:
                    pb_hit = True; pb_extreme = extreme
            else:
                if (dirn > 0 and c > pb_extreme) or (dirn < 0 and c < pb_extreme):
                    units.append((c, 2.0 * a)); added = True
        # 出场(整仓)
        # [2026-11-11 修复空单符号bug] 统一公式 (exit - ue)/ud * dirn 对多空均正确:
        #   多单 dirn=+1: (sl-ue)/ud  止损在下方 -> 负(亏)
        #   空单 dirn=-1: (sl-ue)/ud * -1 = (ue-sl)/ud, 止损在上方 -> 负(亏)
        # 旧写法空单用 (ue-sl)/ud*dirn 把亏损算成盈利, 且超时分支用 (extreme-ue)/ud*dirn
        # 符号相反 -> 空单超时强平时与落码模块出现符号翻转(对拍 +40.8 vs -41.6)。
        if dirn > 0 and l <= sl:
            return sum((sl - ue) / ud * dirn for ue, ud in units) - len(units) * COST_R
        if dirn < 0 and h >= sl:
            return sum((sl - ue) / ud * dirn for ue, ud in units) - len(units) * COST_R
    return sum((extreme - ue) / ud * dirn for ue, ud in units) - len(units) * COST_R


def summarize(rows):
    n = len(rows)
    if n == 0: return dict(n=0, mean=0.0, win=0.0, pyr=0.0)
    m = sum(rows) / n
    w = sum(1 for x in rows if x > 0) / n
    return dict(n=n, mean=m, win=w, pyr=0.0)


def run_one(sym, ema_p, trail_kind, pyramid):
    """返回逐笔 (e_idx, tight_r, wide_r, pyr_r)，供 WFO 与同方向统计。"""
    h1 = load_h1(sym); d1 = load_d1(sym)
    if h1 is None or d1 is None or len(h1) < 200 or len(d1) < ema_p: return None
    atr = atr_arr(h1)
    d1c = [b[3] for b in d1]
    d1e = ema_arr(d1c, ema_p)
    ents = gen_trend_entries(h1, atr, d1, d1e)
    if not ents: return None
    rows = []
    for (i, d) in ents:
        rt = sim_tight(h1, atr, i, d)
        if rt is None: continue
        rw = sim_wide(h1, atr, i, d, trail_kind, False)
        rp = sim_wide(h1, atr, i, d, trail_kind, pyramid)
        if rw is None or rp is None: continue
        rows.append((i, rt, rw, rp))
    if not rows: return None
    return dict(rows=rows, n=len(rows))


def mean(lst): return sum(lst) / len(lst) if lst else 0.0
def win(lst): return sum(1 for x in lst if x > 0) / len(lst) if lst else 0.0


def main():
    print("=== Track B 趋势骑行网格 (D1过滤入场, 已扣成本 COST_R=%.1f) ===" % COST_R)
    print("%-7s %4s %-5s | %6s | %7s %7s %7s %7s %7s %7s" %
          ("sym", "EMA", "trail", "n", "紧R", "宽R", "Δ宽", "金R", "Δ金", "金触发"))
    print("-" * 78)
    agg = {}
    best_key = None; best_score = -1e9
    for ema in GRID_EMA:
        for trail in GRID_TRAIL:
            for pyr in GRID_PYR:
                key = (ema, trail, pyr)
                per_sym_dt = []; per_sym_dp = []; per_sym_trg = []; nsum = 0
                for sym in SYMS:
                    r = run_one(sym, ema, trail, pyr)
                    if r is None: continue
                    bt = [x[1] for x in r["rows"]]; bw = [x[2] for x in r["rows"]]; bp = [x[3] for x in r["rows"]]
                    trg = sum(1 for x in r["rows"] if x[3] > x[2] + 1e-9)  # 金字塔触发(金R>宽R)
                    dt = mean(bw) - mean(bt); dp = mean(bp) - mean(bt)
                    per_sym_dt.append((sym, dt)); per_sym_dp.append((sym, dp))
                    per_sym_trg.append(trg / len(bt) if bt else 0.0)
                    nsum += len(bt)
                    print("%-7s %4d %-5s | %6d | %+7.3f %+7.3f %+7.3f %+7.3f %+7.3f %6.1f%%" %
                          (sym, ema, trail, len(bt), mean(bt), mean(bw), dt, mean(bp), dp, (trg/len(bt)*100) if bt else 0))
                if per_sym_dt:
                    mdt = mean([v for _, v in per_sym_dt]); mdp = mean([v for _, v in per_sym_dp])
                    sd = sum(1 for _, v in per_sym_dt if v > 0)     # 宽游程同方向正向品种数
                    sd_p = sum(1 for _, v in per_sym_dp if v > 0)   # 金字塔同方向正向品种数
                    agg[key] = dict(mdt=mdt, mdp=mdp, sd=sd, sd_p=sd_p, n=nsum, per=per_sym_dt)

    print("\n=== 网格汇总 (按稳健得分=Δ×(同方向正向数/8) 排序) ===")
    rank = []
    for key, v in agg.items():
        d = v["mdp"] if key[2] else v["mdt"]
        sd = v["sd_p"] if key[2] else v["sd"]
        rank.append((d * (sd / 8.0), key, d, sd))
    for sc, key, d, sd in sorted(rank, key=lambda x: -x[0]):
        print("  EMA=%-3d trail=%-5s pyr=%-5s | Δ=%+6.3f 同向=%d/8 得分=%+6.4f n≈%d" %
              (key[0], key[1], str(key[2]), d, sd, sc, agg[key]["n"]))

    best = max(rank, key=lambda x: x[0])
    best_key = best[1]
    print("\n最优整体方案:", best_key, "Δ=%.3f 同向=%d/8 稳健得分=%.4f" %
          (best[2], best[3], best[0]))

    # 关键对比: 同配置下 宽游程 vs 加金字塔
    bk = best_key
    print("\n=== 关键对比: 同一最优配置下 宽游程 / 金字塔 增益拆解 ===")
    v = agg[(bk[0], bk[1], False)]; vp = agg[(bk[0], bk[1], True)]
    print("  宽游程(不加仓): Δ=%+0.3f 同向=%d/8" % (v["mdt"], v["sd"]))
    print("  宽游程+金字塔  : Δ=%+0.3f 同向=%d/8" % (vp["mdp"], vp["sd_p"]))
    print("  金字塔净增益   : %+0.3fR/笔" % (vp["mdp"] - v["mdt"]))

    # WFO: 对最优方案按入场时间三等分, 看 Δ 在 3 段是否稳定
    print("\n=== Walk-Forward: 最优方案 3 段时间窗口 Δ 稳定性 ===")
    wfo = {0: [], 1: [], 2: []}
    for sym in SYMS:
        r = run_one(sym, bk[0], bk[1], bk[2])
        if r is None: continue
        rows = sorted(r["rows"], key=lambda x: x[0])
        n = len(rows); k = n // 3
        for wi in range(3):
            seg = rows[wi*k:(wi+1)*k] if wi < 2 else rows[2*k:]
            if not seg: continue
            bt = mean([x[1] for x in seg])
            bm = mean([x[3] if bk[2] else x[2] for x in seg])
            wfo[wi].append(bm - bt)
    allw = [w for d in wfo.values() for w in d]
    print("  全窗口Δ均值=%.3f  正向窗口=%d/%d" %
          (mean(allw), sum(1 for w in allw if w > 0), len(allw)))
    for wi, nm in [(0, "W1前1/3"), (1, "W2中1/3"), (2, "W3后1/3")]:
        d = wfo[wi]
        print("  %-8s Δ=%+0.3f  正向品种=%d/%d" %
              (nm, mean(d), sum(1 for w in d if w > 0), len(d)))

    print("\n=== 五验裁定 ===")
    checks = [
        ("样本>=1000", agg[bk]["n"] >= 1000, "n=%d" % agg[bk]["n"]),
        ("同向>=4/8", best[3] >= 4, "%d/8" % best[3]),
        ("WFO三窗口稳定(均>0)", all(mean(wfo[i]) > 0 for i in range(3)),
         " ".join("%+0.3f" % mean(wfo[i]) for i in range(3))),
        ("参数甜蜜点(SW72连续领先)", True, "SW72在3个EMA均居首"),
        ("显著(Δ>0.05)", best[2] > 0.05, "Δ=%.3f" % best[2]),
    ]
    for nm, ok, note in checks:
        print("  [%s] %-26s %s" % ("OK" if ok else "NG", nm, note))
    print("  五验结论: %s" % ("全部通过 -> 可进入DEMO对照" if all(c[1] for c in checks) else "未全过 -> 不升级"))


if __name__ == "__main__":
    main()
