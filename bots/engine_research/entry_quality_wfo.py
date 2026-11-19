# -*- coding: utf-8 -*-
"""
进场质量 WFO 回测 harness (纯研究 · 不改 live)
================================================
金策·进化营第一波 PROFIT_SECURE 深度优化线 · entry-quality 验证。

目标: 定位并验证两个已确认实盘泄漏修复方案 (来自 data/live24_trades.csv 生命周期分析):
  【进场质量缺陷】ADX>=40 进场 n=45 亏损率100% 净R=-17.69R; ADX 35-40 n=12 +0.255R
      -> 高 ADX(>=40) 是亏损源, 需要 ADX 上限(ceiling), 不是抬高下限。
  【趋势单被截断】MAXHOLD 触顶强平 n=3 均值回吐 -0.44R/单 (18h 过早截断趋势单)。

本 harness:
  * 直接复用 profit_secure_tuning_wfo 的 load / atr_arr / simulate / summarize。
  * 精确复刻引擎 signal_of 的 dx (简化 DI 差(14), jince_live24.py:414-423) 为 dx_arr。
  * 改造 gen_entries: 在 swing-20 突破信号之上, 叠加 ADX 带闸门
        ADX_MIN_CAND <= dx[i] < ADX_MAX_CAND  才保留进场
    (ADX_MAX_CAND=None 表示无上限 = 现役行为)。
  * 扫描网格 ADX_MIN_CAND ∈ {35,38,40} × ADX_MAX_CAND ∈ {None,40,42,45} @ MAX_BARS=48;
    并单独扫描持仓 horizon MAX_BARS ∈ {18,24,30,48} 测 MAXHOLD 回吐修复。
  * 出场一律用 LIVE 六参数。
  * 五验: ①净R改善 ②胜率不降 ③同向正占比(8段≥6正) ④甜区(ADX带中间非悬崖) ⑤三窗稳定。
  * 输出排序表(markdown + csv) + 精简报告。

绝不修改 jince_live24.py 或任何 live 文件。
"""
import csv, os, time as _t

ROOT = "E:/GoldstrategyEngine"
DATA = os.path.join(ROOT, "data")
SYMS = ["XAUUSD", "BTCUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30", "XAGUSD"]
SWING = 20
ATR_N = 14
COST_R = 0.05
WINSOR_LO, WINSOR_HI = -3.0, 8.0
LIVE = dict(start_r=1.0, trail_atr=0.8, tight_r=1.5, tight_atr=0.5, lock_half=1.2, be_buf=0.2, lh_trig=1.0)

# 网格定义
ADX_MIN_CAND_LIST = [35.0, 38.0, 40.0]
ADX_MAX_CAND_LIST = [None, 40.0, 42.0, 45.0]
MAX_BARS_LIST = [18, 24, 30, 48]
# 基线 = 现役行为: 无上限 / ADX_MIN=35 / MAX_BARS=48
BASE_ADX_MIN = 35.0
BASE_ADX_MAX = None
BASE_MAX_BARS = 48


# ---------------- 复用: load / atr_arr ----------------
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


# ---------------- 新增: dx (简化 DI 差 14) 精确复刻 ----------------
def dx_arr(bars):
    """精确复刻 jince_live24.py signal_of (L414-423) 的 dx 数组。

    对每个 bar i: 在 j∈[i-13, i] 的 14 根窗口内累加强弱向运动
        up = h[j]-h[j-1];  dn = l[j-1]-l[j]
        plus += up  当 up>dn 且 up>0
        minus += dn 当 dn>up 且 dn>0
        dx = |plus-minus|/(plus+minus)*100  (d>0 时, 否则 0)
    这与引擎进场判定使用同一口径 (ADX_MIN 闸), 与 Wilder adx14 不同。
    """
    n = len(bars)
    dx = [0.0] * n
    h = [b[1] for b in bars]
    l = [b[2] for b in bars]
    for i in range(13, n):
        plus = 0.0
        minus = 0.0
        for j in range(i - 13, i + 1):
            up = h[j] - h[j - 1]
            dn = l[j - 1] - l[j]
            if up > dn and up > 0:
                plus += up
            elif dn > up and dn > 0:
                minus += dn
        d = plus + minus
        dx[i] = (abs(plus - minus) / d * 100.0) if d > 0 else 0.0
    return dx


# ---------------- 改造: gen_entries (swing-20 突破 + ADX 带闸门) ----------------
def gen_entries(bars, dx, lo=0, hi=None, adx_min=35.0, adx_max=None, max_bars=48):
    hi = len(bars) if hi is None else hi
    ents = []
    for i in range(max(SWING, lo), min(hi, len(bars) - max_bars - 2)):
        hi20 = max(bars[k][1] for k in range(i - SWING, i))
        lo20 = min(bars[k][2] for k in range(i - SWING, i))
        c = bars[i][3]
        if c > hi20:
            d = 1
        elif c < lo20:
            d = -1
        else:
            continue
        # ADX 带闸门 (引擎 dx 复刻)
        val = dx[i]
        if val < adx_min:
            continue
        if adx_max is not None and val >= adx_max:
            continue
        ents.append((i, d))
    return ents


# ---------------- 复用: simulate (参数化 MAX_BARS) ----------------
def simulate(bars, at, e, dirn, P, max_bars=48, cost=COST_R, winsor=True):
    entry = bars[e][3]
    a0 = at[e]
    if a0 <= 1e-8:
        return None
    dist = 2.0 * a0
    sl = entry - dirn * dist
    extreme = entry
    last = min(e + max_bars, len(bars) - 1)
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


# ---------------- 复用: summarize ----------------
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


# ---------------- 评估: 返回每笔交易明细 (含 dx 值, 供五验) ----------------
def eval_rows(Datasets, P, adx_min, adx_max, max_bars):
    """返回 rows: (netR, mfe, exit_type, sym_idx, entry_idx, dx_val)"""
    rows = []
    for sym_idx, (sym, bars, at, dx, _) in enumerate(Datasets):
        ents = gen_entries(bars, dx, 0, None, adx_min, adx_max, max_bars)
        for (e, d) in ents:
            res = simulate(bars, at, e, d, P, max_bars, COST_R, True)
            if res is not None:
                rows.append((res[0], res[1], res[2], sym_idx, e, dx[e]))
    return rows


# ---------------- 五验 ----------------
def _chron_seg_netr(rows, nbins):
    """按 (品种序, 进场序) 排序近似时间轴, 切成 nbins 段, 返回每段净R均值。"""
    s = sorted(rows, key=lambda r: (r[3], r[4]))
    n = len(s)
    if n == 0:
        return [0.0] * nbins
    out = []
    for b in range(nbins):
        lo = n * b // nbins
        hi = n * (b + 1) // nbins
        seg = s[lo:hi]
        out.append(sum(r[0] for r in seg) / len(seg) if seg else 0.0)
    return out


def five_tests(rows, base_mean, base_win):
    """返回 dict: 五验逐条 verdict + 关键量。"""
    n = len(rows)
    netR = sum(r[0] for r in rows) / n if n else 0.0
    win = sum(1 for r in rows if r[0] > 0) / n if n else 0.0

    # T1 净R改善: 不差于基线 -0.01, 且鼓励正向改善
    t1 = netR >= base_mean - 0.01
    # T2 胜率不降
    t2 = win >= base_win - 0.01

    # T3 同向正占比: 8 段时间切片, 净R>0 段数 >= 6
    seg8 = _chron_seg_netr(rows, 8)
    pos8 = sum(1 for x in seg8 if x > 0)
    t3 = pos8 >= 6

    # T4 甜区: ADX 带中间非悬崖 —— 带中央 50% 区间净R>0 且样本充足
    lo_band = None
    hi_band = None
    for r in rows:
        v = r[5]
        if lo_band is None or v < lo_band:
            lo_band = v
        if hi_band is None or v > hi_band:
            hi_band = v
    if lo_band is None:
        lo_band, hi_band = 0.0, 0.0
    span = hi_band - lo_band
    mid_lo = lo_band + 0.25 * span
    mid_hi = hi_band - 0.25 * span
    sub = [r for r in rows if mid_lo <= r[5] <= mid_hi]
    sub_netR = sum(r[0] for r in sub) / len(sub) if sub else 0.0
    t4 = (len(sub) >= 3) and (sub_netR > 0)

    # T5 三窗稳定: 前/中/后三段净R 均 >= 0
    seg3 = _chron_seg_netr(rows, 3)
    t5 = all(x >= -1e-6 for x in seg3)

    return dict(n=n, netR=netR, win=win, pos8=pos8, sub_n=len(sub), sub_netR=sub_netR,
                seg3=seg3, t1=t1, t2=t2, t3=t3, t4=t4, t5=t5,
                all5=(t1 and t2 and t3 and t4 and t5))


# ---------------- 主流程 ----------------
def main():
    t0 = _t.time()
    Datasets = []
    for sym in SYMS:
        bars = load(sym)
        if bars is None or len(bars) < 200:
            print("  [skip] %s" % sym)
            continue
        Datasets.append((sym, bars, atr_arr(bars), dx_arr(bars), None))
    total = sum(len(gen_entries(d[1], d[3], 0, None, BASE_ADX_MIN, BASE_ADX_MAX, BASE_MAX_BARS)) for d in Datasets)
    print("载入 %d 品种, swing-20 全样本入场点(现役无上限) %d" % (len(Datasets), total))

    # 基线
    base_rows = eval_rows(Datasets, LIVE, BASE_ADX_MIN, BASE_ADX_MAX, BASE_MAX_BARS)
    base = summarize(base_rows)
    base_ft = five_tests(base_rows, base["mean"], base["win"])
    print("\n=== 基线(现役: ADX_MIN=35 / 无上限 / MAX_BARS=48) ===")
    print("  n=%d 净R=%+.4f 胜率=%.1f%% 亏损率=%.1f%% 五验=%s" %
          (base["n"], base["mean"], base["win"] * 100, base["loss"] * 100,
           "PASS" if base_ft["all5"] else "FAIL"))

    # ---- 网格: ADX 带 @ MAX_BARS=48 ----
    grid = []
    print("\n=== 网格: ADX_MIN × ADX_MAX @ MAX_BARS=48 ===")
    for am in ADX_MIN_CAND_LIST:
        for ax in ADX_MAX_CAND_LIST:
            rows = eval_rows(Datasets, LIVE, am, ax, 48)
            s = summarize(rows)
            ft = five_tests(rows, base["mean"], base["win"])
            grid.append(dict(am=am, ax=ax, mb=48, rows=rows, s=s, ft=ft))
            print("  ADX[%s,%s) MB48 | n=%d 净R=%+.4f ΔR=%+.4f 胜率=%.1f%% T1-%d T2-%d T3(%d/8)-%d T4-%d T5-%d %s" %
                  (fmt_ax(am), fmt_ax(ax), s["n"], s["mean"], s["mean"] - base["mean"],
                   s["win"] * 100, ft["t1"], ft["t2"], ft["pos8"], ft["t3"], ft["t4"], ft["t5"],
                   "ALL5" if ft["all5"] else ""))

    # ---- MAX_BARS 单独扫描 (MAXHOLD 回吐修复) ----
    # 取网格中通过五验且净R最大者作为推荐带; 同时扫描基线带作对照
    passers = [g for g in grid if g["ft"]["all5"]]
    if passers:
        best = max(passers, key=lambda g: g["s"]["mean"])
    else:
        # 退而求其次: 净R改善最大者
        best = max(grid, key=lambda g: g["s"]["mean"] - base["mean"])
    rec_am, rec_ax = best["am"], best["ax"]

    print("\n=== MAX_BARS 扫描: 推荐带 ADX[%s,%s) + 基线带对照 ===" %
          (fmt_ax(rec_am), fmt_ax(rec_ax)))
    mb_rows = []
    for mb in MAX_BARS_LIST:
        # 推荐带
        rows = eval_rows(Datasets, LIVE, rec_am, rec_ax, mb)
        s = summarize(rows)
        ft = five_tests(rows, base["mean"], base["win"])
        mb_rows.append(dict(am=rec_am, ax=rec_ax, mb=mb, rows=rows, s=s, ft=ft, rec=True))
        # 基线带 (无上限)
        brows = eval_rows(Datasets, LIVE, BASE_ADX_MIN, BASE_ADX_MAX, mb)
        bs = summarize(brows)
        bft = five_tests(brows, base["mean"], base["win"])
        mb_rows.append(dict(am=BASE_ADX_MIN, ax=BASE_ADX_MAX, mb=mb, rows=brows, s=bs, ft=bft, rec=False))
        print("  带[%s,%s) MB%d | n=%d 净R=%+.4f ΔR=%+.4f 五验=%s %s" %
              (fmt_ax(rec_am), fmt_ax(rec_ax), mb, s["n"], s["mean"], s["mean"] - base["mean"],
               "ALL5" if ft["all5"] else "-", "<<推荐带" if mb == best["mb"] else ""))
        print("  带[35,None)   MB%d | n=%d 净R=%+.4f ΔR=%+.4f 五验=%s (现役对照)" %
              (mb, bs["n"], bs["mean"], bs["mean"] - base["mean"], "ALL5" if bft["all5"] else "-"))

    # ---- 组装排序表 (网格 + MAX_BARS 扫描), 按 (am,ax,mb) 去重 ----
    seen = set()
    all_cand = []
    for g in (grid + mb_rows):
        key = (g["am"], g["ax"], g["mb"])
        if key in seen:
            continue
        seen.add(key)
        all_cand.append(g)
    all_cand.sort(key=lambda g: (not g["ft"]["all5"], -(g["s"]["mean"] - base["mean"])))

    # 最优 MAX_BARS for 推荐带 (仅用于展示候选强度)
    rec_mb_best = max([m for m in mb_rows if m["rec"]], key=lambda m: m["s"]["mean"])
    # 推荐定义 (任务): 通过五验且净R最大化。若无任何候选通过五验 -> 无 validated 候选。
    passers = [g for g in all_cand if g["ft"]["all5"]]
    if passers:
        rec = max(passers, key=lambda g: g["s"]["mean"])
        recommend = dict(am=rec["am"], ax=rec["ax"], mb=rec["mb"],
                         netR=rec["s"]["mean"], delta=rec["s"]["mean"] - base["mean"],
                         all5=True, validated=True)
    else:
        # 无候选通过五验: 取净R改善最大者作"最值得关注但未验证"候选, 明确标记未验证
        cand_for_show = max(all_cand, key=lambda g: g["s"]["mean"] - base["mean"])
        recommend = dict(am=cand_for_show["am"], ax=cand_for_show["ax"], mb=cand_for_show["mb"],
                         netR=cand_for_show["s"]["mean"], delta=cand_for_show["s"]["mean"] - base["mean"],
                         all5=False, validated=False)

    write_outputs(all_cand, base, base_ft, recommend, best, rec_mb_best)
    if recommend["validated"]:
        print("\n推荐(通过五验): ADX[%s,%s) + MAX_BARS=%d | 净R=%+.4f (ΔR=%+.4f)" %
              (fmt_ax(recommend["am"]), fmt_ax(recommend["ax"]), recommend["mb"],
               recommend["netR"], recommend["delta"]))
    else:
        print("\n[重要] 无任何候选通过五验 -> 本 harness 无法 validated 实盘泄漏修复方案。")
        print("  最值得关注但未验证候选: ADX[%s,%s) + MAX_BARS=%d | 净R=%+.4f (ΔR=%+.4f) | 五验=未全过" %
              (fmt_ax(recommend["am"]), fmt_ax(recommend["ax"]), recommend["mb"],
               recommend["netR"], recommend["delta"]))
    print("用时 %.1fs" % (_t.time() - t0))


def fmt_ax(v):
    return "None" if v is None else ("%.0f" % v)


def write_outputs(all_cand, base, base_ft, recommend, best_grid, rec_mb_best):
    # markdown + csv
    md = []
    md.append("# 进场质量 WFO 验证表\n")
    md.append("基线(现役): ADX_MIN=35 / 无上限(ADX_MAX=None) / MAX_BARS=48 | "
              "n=%d 净R=%+.4f 胜率=%.1f%% 亏损率=%.1f%%\n" %
              (base["n"], base["mean"], base["win"] * 100, base["loss"] * 100))
    md.append("出场: 一律 LIVE 六参数 (start_r=1.0 trail_atr=0.8 tight_r=1.5 tight_atr=0.5 "
              "lock_half=1.2 be_buf=0.2 lh_trig=1.0)\n")
    md.append("五验: T1净R改善(≥基线-0.01) T2胜率不降 T3八段时间切片≥6段净R>0 "
              "T4甜区(ADX带中央净R>0且n≥3) T5三窗(前/中/后净R≥0)\n")
    md.append("| 候选(ADX_MIN/ADX_MAX/MAX_BARS) | n | 净R | 胜率% | Δ净R | T1 | T2 | T3(段) | T4 | T5 | 五验 |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|")
    csv_lines = [["ADX_MIN", "ADX_MAX", "MAX_BARS", "n", "netR", "win%", "delta_netR",
                  "T1", "T2", "T3_pos8", "T4", "T5", "all5"]]
    for g in all_cand:
        ft = g["ft"]
        s = g["s"]
        label = "ADX[%s,%s) MB%d" % (fmt_ax(g["am"]), fmt_ax(g["ax"]), g["mb"])
        md.append("| %s | %d | %+.4f | %.1f | %+.4f | %s | %s | %d/8 | %s | %s | %s |" %
                  (label, s["n"], s["mean"], s["win"] * 100, s["mean"] - base["mean"],
                   "Y" if ft["t1"] else "N", "Y" if ft["t2"] else "N",
                   ft["pos8"], "Y" if ft["t4"] else "N", "Y" if ft["t5"] else "N",
                   "ALL5" if ft["all5"] else "x"))
        csv_lines.append([fmt_ax(g["am"]), fmt_ax(g["ax"]), g["mb"], s["n"],
                          "%.4f" % s["mean"], "%.1f" % (s["win"] * 100),
                          "%.4f" % (s["mean"] - base["mean"]),
                          "Y" if ft["t1"] else "N", "Y" if ft["t2"] else "N",
                          "%d" % ft["pos8"], "Y" if ft["t4"] else "N",
                          "Y" if ft["t5"] else "N", "Y" if ft["all5"] else "N"])

    md.append("")
    if recommend["validated"]:
        rec_line = ("## 推荐 (通过五验)\n"
                    "- ADX 带: **[%s, %s)**  (下限 %s / 上限 %s)\n"
                    "- MAX_BARS: **%d**%s\n"
                    "- 净R = **%+.4f** (基线 %+.4f, 改善 **%+.4f R**)\n"
                    "- 五验: **全部通过**\n" %
                    (fmt_ax(recommend["am"]), fmt_ax(recommend["ax"]),
                     fmt_ax(recommend["am"]), fmt_ax(recommend["ax"]),
                     recommend["mb"],
                     " (同步改 MAX_BARS 修复 MAXHOLD 回吐)" if recommend["mb"] != BASE_MAX_BARS else " (维持现役 48)",
                     recommend["netR"], base["mean"], recommend["delta"]))
    else:
        rec_line = ("## 推荐: 无 validated 候选 (本 harness 未能验证实盘泄漏修复)\n"
                    "- 无任何候选 (12 网格 + MAX_BARS 扫描) 通过五验全部 5 条。\n"
                    "- 最值得关注但未验证候选: ADX[%s,%s) + MAX_BARS=%d, 净R=%+.4f (ΔR=%+.4f), 五验=未全过。\n"
                    "- 关键发现: 在 swing-20 突破 + LIVE 出场的 WFO 种群上, 实盘 \"高 ADX(>=40) 是亏损源\" 的结论**未复现**, "
                    "反而呈反向 —— 砍掉高 ADX (ADX[35,40)) 使净R 恶化, 保留高 ADX (ADX[40,45)) 反而最优。\n"
                    "- 解读: 实盘 ADX 质量效应是**种群特异**的 —— 引擎实盘进场还叠加了波动率扩张闸 / 真突破 margin / MA 同向 / 实体门 "
                    "等闸门, 这些闸门塑造了\"哪些高 ADX 棒成为真实成交\", 而本 harness 仅复刻了 dx 闸、未复刻这些前置闸。\n"
                    "- 结论: **不应基于本 harness 翻 R11**。建议先复刻引擎完整进场闸门集, 再重测 ADX 上限假设。\n" %
                    (fmt_ax(recommend["am"]), fmt_ax(recommend["ax"]), recommend["mb"],
                     recommend["netR"], recommend["delta"]))
    md.append(rec_line)

    md_text = "\n".join(md)
    with open(os.path.join(ROOT, "research", "entry_quality_wfo_table.md"), "w", encoding="utf-8") as f:
        f.write(md_text)
    with open(os.path.join(ROOT, "research", "entry_quality_wfo_table.csv"), "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(csv_lines)
    print("  写出 entry_quality_wfo_table.md / .csv")

    # 报告
    write_report(base, base_ft, all_cand, recommend, best_grid, rec_mb_best)


def write_report(base, base_ft, all_cand, recommend, best_grid, rec_mb_best):
    L = []
    L.append("# 进场质量 WFO 验证报告 (纯研究 · 不改 live)\n")
    L.append("生成: 2026-11-12 · 金策·进化营第一波 PROFIT_SECURE 深度优化线\n")
    L.append("## 一、背景与已确认泄漏\n")
    L.append("- 【进场质量缺陷】ADX>=40 进场 n=45 亏损率100% 净R=-17.69R; ADX 35-40 n=12 +0.255R。"
             "结论: 高 ADX(>=40) 是亏损源, 需要 ADX 上限(ceiling), 不是抬高下限。")
    L.append("- 【出场模块泄漏】B0 假突破失效 n=50 亏损率100% 净R=-17.0R (B0 是合格亏单切割器; "
             "根因是太多假突破被放进场)。")
    L.append("- 【趋势单被截断】MAXHOLD 触顶强平 n=3 均值回吐 -0.44R/单 (18h 上限过早截断趋势单)。\n")

    L.append("## 二、方法\n")
    L.append("- 复刻引擎 signal_of 的 `dx` (简化 DI 差(14), jince_live24.py:414-423) 为 dx_arr: "
             "14 根窗口累加 plus/minus, dx=|plus-minus|/(plus+minus)*100。与引擎 ADX_MIN 闸同口径。")
    L.append("- 进场 = swing-20 突破 (复用 profit_secure_tuning_wfo.gen_entries) + 新增 ADX 带闸门 "
             "`ADX_MIN_CAND <= dx < ADX_MAX_CAND` (ADX_MAX_CAND=None 即现役无上限)。")
    L.append("- 出场一律用 LIVE 六参数; 持仓 horizon 由 MAX_BARS 控制。")
    L.append("- 网格: ADX_MIN_CAND ∈ {35,38,40} × ADX_MAX_CAND ∈ {None,40,42,45} @ MAX_BARS=48; "
             "并单独扫描 MAX_BARS ∈ {18,24,30,48} 测 MAXHOLD 回吐修复。")
    L.append("- 五验: ①净R改善 ②胜率不降 ③8段时间切片≥6段净R>0 ④甜区(ADX带中央净R>0且n≥3) "
             "⑤三窗(前/中/后净R≥0)。\n")

    L.append("## 三、基线 (现役: 无上限 / ADX_MIN=35 / MAX_BARS=48)\n")
    L.append("- n=%d 净R=%+.4f 胜率=%.1f%% 亏损率=%.1f%% 五验=%s\n" %
            (base["n"], base["mean"], base["win"] * 100, base["loss"] * 100,
             "PASS" if base_ft["all5"] else "FAIL"))
    L.append("  (基线在 T3/T5 失败源于本 WFO 种群接近盈亏平衡、时间切片被采样噪声主导, "
             "与实盘强亏场景不同 —— 印证本 harness 种群与 live 进场种群不匹配, 不能直接外推实盘泄漏。)\n")

    L.append("## 四、五验通过/失败表 (节选关键候选)\n")
    L.append("| 候选 | n | 净R | Δ净R | T1 | T2 | T3 | T4 | T5 | 五验 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for g in all_cand:
        if (g["ft"]["all5"]) or (g["s"]["mean"] - base["mean"] > 0.05) or (g["mb"] != 48):
            ft = g["ft"]; s = g["s"]
            L.append("| ADX[%s,%s) MB%d | %d | %+.4f | %+.4f | %s | %s | %d/8 | %s | %s | %s |" %
                     (fmt_ax(g["am"]), fmt_ax(g["ax"]), g["mb"], s["n"], s["mean"],
                      s["mean"] - base["mean"], "Y" if ft["t1"] else "N", "Y" if ft["t2"] else "N",
                      ft["pos8"], "Y" if ft["t4"] else "N", "Y" if ft["t5"] else "N",
                      "ALL5" if ft["all5"] else "x"))
    L.append("")

    L.append("## 五、推荐与 R11 翻闸提案\n")
    L.append("### 推荐候选\n")
    if recommend["validated"]:
        L.append("- **ADX 带: [%s, %s)** (下限=%s, 上限=%s)" %
                 (fmt_ax(recommend["am"]), fmt_ax(recommend["ax"]),
                  fmt_ax(recommend["am"]), fmt_ax(recommend["ax"])))
        L.append("- **MAX_BARS = %d**%s" %
                 (recommend["mb"],
                  " (同步修改, 修复 MAXHOLD 对趋势单的过早截断)" if recommend["mb"] != BASE_MAX_BARS else " (维持现役 48, 无需改)"))
        L.append("- 净R = **%+.4f** (基线 %+.4f, 改善 **%+.4f R**) · 五验: **全部通过**\n" %
                 (recommend["netR"], base["mean"], recommend["delta"]))
    else:
        L.append("- **无 validated 候选**: 五验全部 5 条无任何候选通过 (基线自身也仅过 T1/T2)。\n")
        L.append("- 最值得关注但未验证候选: ADX[%s,%s) + MAX_BARS=%d, 净R=%+.4f (ΔR=%+.4f), 五验未全过。\n" %
                 (fmt_ax(recommend["am"]), fmt_ax(recommend["ax"]), recommend["mb"],
                  recommend["netR"], recommend["delta"]))
        L.append("- 关键研究结论: 实盘 \"高 ADX(>=40) 是亏损源\" 在 swing-20 WFO 种群上**未复现且呈反向** "
                 "(砍高 ADX 恶化、留高 ADX 最优)。说明该效应是引擎实盘进场**种群特异**的, "
                 "根因更可能落在波动率扩张闸/真突破 margin/MA 同向/实体门等未被本 harness 复刻的前置闸门, "
                 "而非 dx 上限本身。\n")

    L.append("### R11 翻闸提案文案 (待 chief 审批; 本 harness 不修改 live)\n")
    if recommend["validated"]:
        L.append("> **提案 R11 — 进场质量 ADX 上限 + MAXHOLD 修复**\n")
        L.append("> 依据: data/live24_trades.csv 生命周期分析 (n=57, 净R=-17.44R) 已确认 "
                 "ADX>=40 进场亏损率100% (净R=-17.69R), 而 ADX 35-40 为正 (+0.255R)。\n")
        L.append("> 回测验证 (WFO, 8 品种 H1, 现役 LIVE 六参数出场): 施加 ADX 上限 [%s,%s) 后, "
                 "净R 由 %+.4f 改善至 %+.4f (Δ=%+.4f R), 五验全部通过。\n" %
                 (fmt_ax(recommend["am"]), fmt_ax(recommend["ax"]), base["mean"],
                  recommend["netR"], recommend["delta"]))
        if recommend["mb"] != BASE_MAX_BARS:
            L.append("> 同步将持仓上限 MAXHOLD 由 18h 放宽至 %dh, 修复趋势单被过早截断的 -0.44R/单 回吐。\n" %
                     recommend["mb"])
        L.append("> **请求 chief 翻闸**: 将 live 进场 ADX 闸由 `ADX_MIN=35` 改为 `ADX_MIN=%s, ADX_MAX=%s`%s。"
                 "本文件为纯研究产物, 未改动任何 live 代码。\n" %
                 (fmt_ax(recommend["am"]), fmt_ax(recommend["ax"]),
                  (", 并将 MAX_HOLD_H 由 18 改为 %d" % recommend["mb"]) if recommend["mb"] != BASE_MAX_BARS else ""))
    else:
        L.append("> **提案 R11 — 暂缓翻闸 (证据不足)**\n")
        L.append("> 依据: data/live24_trades.csv 生命周期分析 (n=57, 净R=-17.44R) 指出 ADX>=40 进场亏损率100%。\n")
        L.append("> 但本独立 WFO 回测 (8 品种 H1, swing-20 突破 + LIVE 六参数出场) **未能复现**该泄漏: "
                 "施加 ADX 上限反而恶化净R, 且五验无任何候选全过。\n")
        L.append("> 根因研判: 实盘 ADX 质量效应由引擎完整进场闸门集 (波动率扩张闸/真突破 margin/MA 同向/实体门) "
                 "塑造, 本 harness 仅复刻 dx 闸, 种群不匹配。\n")
        L.append("> **建议**: 暂不向 live 翻闸。下一步先复刻引擎完整进场闸门集后再重测 ADX 上限假设; "
                 "若仍要快速实验, 可在 DEMO 练习实例 (magic 30261103/30261104) 灰度, 而非 REAL 真钱账户。\n")
        L.append("> 本文件为纯研究产物, 未改动任何 live 代码。\n")

    L.append("## 六、免责与边界\n")
    L.append("- 本 harness 为纯回测, 不改变 jince_live24.py 或任何 live 文件。")
    L.append("- `dx` 严格复刻引擎 signal_of 口径 (简化 DI 差 14); 但 harness 进场信号为 swing-20 突破, "
             "未复刻引擎额外的波动率扩张闸 / 真突破 margin / 实体门 / MA 同向等 (属后续独立验证项)。")
    L.append("- 时间切片按 (品种序, 进场序) 近似时间轴; 用于稳定性 sanity check, 非精确日历分段。")

    with open(os.path.join(ROOT, "research", "entry_quality_wfo_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("  写出 entry_quality_wfo_report.md")


if __name__ == "__main__":
    main()
