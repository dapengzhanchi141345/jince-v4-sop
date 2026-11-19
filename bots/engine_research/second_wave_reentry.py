# -*- coding: utf-8 -*-
"""
第二波行情捕获 · 深度回测 (金策·进化营)
=================================================
问题(用户 2026-11-11): "吃到第一波利润后, 合适的位置, 看看能不能拿到第二波行情"

当前 PROFIT_SECURE 把整个仓位在"第一波回撤/跟踪止损"处清掉 -> 多波趋势(wave1↑, 回踩, wave2↑)
在第一波回踩处被扫出, 永远吃不到 wave2。

本脚本在已验证的 PROFIT_SECURE 单波规则之上, 叠加"第二波再入场"两种策略, 公平对比:
  B  (基线/单波): 每个 H1 突破 = 1 笔交易, PROFIT_SECURE 单波, 出场即结束, 不连锁。
  R1 (突破再入场): 盈利出场后, 同方向下一根 H1 swing 突破(窗口内)再入场 -> 吃 wave2。
  R2 (回踩续涨再入场): 盈利出场后, 等一波"回踩(回撤>=pb且未破结构)→续涨(创新高)"再入场。

引擎语义忠实复刻 profit_secure_grid.simulate (PROFIT_SECURE 分支):
  入场 H1 swing 突破(20根)@收盘; SL=2×ATR(14); 无初始TP; MAX_BARS=48; dist=2×ATR。
  锁利阶梯: 0.5R 保本缓冲 / 1.0R 锁半利地板 / start_r 起 ATR 跟踪(tight_r 收紧)。

指标(每"波序"= 入场→可能再入场→结束):
  均值R(波序) / 胜率 / 均值R1(第一波) / 均值R2(第二波) / 再入场触发率 / 再入场胜率 /
  净增益 ΔR = 含再入场均值R - 单波基线均值R。

五验纪律沿用: 样本>=1000 / 同向>=4/6 / 参数甜蜜点 / walk-forward 3窗口稳定。
"""
import csv, os, time as _t, itertools

ROOT = "E:/GoldstrategyEngine"
DATA = os.path.join(ROOT, "data")
SYMS = ["XAUUSD", "BTCUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30", "XAGUSD"]
MAX_BARS = 48
SWING = 20
ATR_N = 14

# [2026-11-11 已激活实盘最优] PROFIT_SECURE: lh1.2 / bb0.2
P = {"start_r": 1.0, "trail_atr": 0.8, "tight_atr": 0.5, "lock_half": 1.2, "be_buf": 0.2}

# 再入场寻优维度
GRID_MAX_GAP = [24, 36, 48]          # 出场后最多多少根 H1 内允许再入场 (~1~2天)
GRID_PB_MIN   = [0.30, 0.45, 0.60]   # R2 回踩至少回撤 wave1 幅度比例
GRID_MIN_PEAK = [0.0, 1.5, 2.5]      # 仅当第一波峰值>=该R才考虑再入场(过滤边际赢单)
# 部分止盈+游程(Partial Runner): 第一波到 split_r 平半仓锁利, 余下 1/2 用更宽 RUNNER_ATR 跟踪
# 扛过回踩吃 wave2。这才是"吃到第一波后拿第二波"的教科书机制(而非出场后再追)。
GRID_SPLIT_R    = [1.5, 2.0, 2.5]
GRID_RUNNER_ATR = [1.5, 2.0, 2.5, 3.0]
MODES = ["B", "R1", "R2", "PR"]


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


def gen_entries(bars, lo, hi):
    ents = []
    hi = min(hi, len(bars) - MAX_BARS - 2)
    for i in range(max(SWING, lo), hi):
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


def simulate_leg(bars, at, e, dirn, P):
    """模拟单条腿(第一波或第二波), 忠实复刻 PROFIT_SECURE 出场。返回完整状态。"""
    entry = bars[e][3]
    a0 = at[e]
    if a0 <= 1e-8:
        return None
    dist = 2.0 * a0
    sl0 = entry - dirn * dist
    extreme = entry
    mfe = 0.0
    sl_level = sl0
    last = min(e + MAX_BARS, len(bars) - 1)
    start_r = P["start_r"]; trail_atr = P["trail_atr"]; tight_atr = P["tight_atr"]
    lock_half = P["lock_half"]; be_buf = P["be_buf"]
    peak_r = 0.0
    for j in range(e + 1, last + 1):
        o, h, l, c = bars[j]
        a = at[j]
        if a <= 0:
            a = a0
        extreme = max(extreme, h) if dirn > 0 else min(extreme, l)
        r = (extreme - entry) / dist * dirn
        mfe = max(mfe, r)
        peak_r = max(peak_r, r)
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
            # 忠实复刻引擎: r>=1.5R 收紧到 tight_atr(0.5), 否则 trail_atr(0.8)
            mult = tight_atr if r >= 1.5 else trail_atr
            trail = extreme - dirn * mult * a
            if trail * dirn > sl_level * dirn:
                sl_level = trail
        # 出场(当棒高低触发SL)
        if l <= sl_level:
            realized = (sl_level - entry) / dist * dirn
            return dict(R=realized, mfe=mfe, peak_r=peak_r, exit_idx=j, exit_px=sl_level,
                        entry_px=entry, dist=dist, peak_px=entry + dirn * peak_r * dist, dirn=dirn)
    exit_px = bars[last][3]
    realized = (exit_px - entry) / dist * dirn
    return dict(R=realized, mfe=mfe, peak_r=peak_r, exit_idx=last, exit_px=exit_px,
                entry_px=entry, dist=dist, peak_px=entry + dirn * peak_r * dist, dirn=dirn)


def simulate_runner(bars, at, e, dirn, P, split_r, runner_atr):
    """部分止盈+游程(PR): 第一波到 split_r 平半仓锁利, 余下半仓用更宽 RUNNER_ATR 跟踪扛过回踩吃 wave2。
    返回 total_R(波序总R, 同风险口径) / split_r / runner_r / split_done。"""
    entry = bars[e][3]
    a0 = at[e]
    if a0 <= 1e-8:
        return None
    dist = 2.0 * a0
    sl0 = entry - dirn * dist
    extreme = entry
    sl_level = sl0
    last = min(e + MAX_BARS, len(bars) - 1)
    start_r = P["start_r"]; trail_atr = P["trail_atr"]; tight_atr = P["tight_atr"]
    lock_half = P["lock_half"]; be_buf = P["be_buf"]
    split_done = False
    split_R = 0.0
    runner_sl = entry          # 游程止损: 初始保本(入口价)
    runner_sl_active = False
    for j in range(e + 1, last + 1):
        o, h, l, c = bars[j]
        a = at[j]
        if a <= 0:
            a = a0
        extreme = max(extreme, h) if dirn > 0 else min(extreme, l)
        r = (extreme - entry) / dist * dirn
        # 分仓点: 首次达到 split_r -> 平半仓(记 split_R), 余下半仓转游程(宽跟踪)
        if (not split_done) and r >= split_r:
            split_done = True
            split_R = r
            runner_sl = entry                      # 半仓保本出场线(回踩到入场即平, 不伤已锁利润)
            runner_sl_active = True
            # 分仓后该棒不立即按原SL出场(我们刚在 split_r 平了半仓)
        if not split_done:
            # 分仓前: 沿用 PROFIT_SECURE 单波逻辑
            if r >= 0.5:
                cand = entry + dirn * be_buf * dist
                if cand * dirn > sl_level * dirn:
                    sl_level = cand
            if r >= 1.0:
                cand = entry + dirn * lock_half * dist
                if cand * dirn > sl_level * dirn:
                    sl_level = cand
            if r >= start_r and a > 0:
                mult = tight_atr if r >= 1.5 else trail_atr
                trail = extreme - dirn * mult * a
                if trail * dirn > sl_level * dirn:
                    sl_level = trail
            if l <= sl_level:
                realized = (sl_level - entry) / dist * dirn
                return dict(R=realized, split_r=split_R, runner_r=0.0, split_done=False)
        else:
            # 分仓后: 半仓锁利, 余下半仓宽跟踪(扛过回踩)
            if a > 0:
                trail = extreme - dirn * runner_atr * a
                # 游程止损只上移(或保持在保本), 用更宽倍数 -> 容回踩
                if trail * dirn > runner_sl * dirn:
                    runner_sl = trail
                # 不低于保本(入口价), 保本优先
                if entry * dirn > runner_sl * dirn:
                    runner_sl = entry
            if l <= runner_sl:
                runner_R = (runner_sl - entry) / dist * dirn
                # 总R(同风险口径): 半仓 split_R + 半仓 runner_R
                total = 0.5 * split_R + 0.5 * runner_R
                return dict(R=total, split_r=split_R, runner_r=runner_R, split_done=True)
    # 到 MAX_BARS: 若已分仓, 半仓锁利+余下半仓按收盘了结; 否则整仓按收盘
    exit_px = bars[last][3]
    if split_done:
        runner_R = (exit_px - entry) / dist * dirn
        total = 0.5 * split_R + 0.5 * runner_R
        return dict(R=total, split_r=split_R, runner_r=runner_R, split_done=True)
    realized = (exit_px - entry) / dist * dirn
    return dict(R=realized, split_r=split_R, runner_r=0.0, split_done=False)


def find_reentry_R1(bars, at, leg1, max_gap):
    """R1: 盈利出场后, 同方向下一根 H1 swing 突破再入场。"""
    x1 = leg1["exit_idx"]; d = leg1["dirn"]
    lo = x1 + 1; hi = min(x1 + 1 + max_gap, len(bars) - MAX_BARS - 2)
    for j in range(max(SWING, lo), hi):
        if j < SWING:
            continue
        hi20 = max(bars[k][1] for k in range(j - SWING, j))
        lo20 = min(bars[k][2] for k in range(j - SWING, j))
        c = bars[j][3]
        if (d > 0 and c > hi20) or (d < 0 and c < lo20):
            return simulate_leg(bars, at, j, d, P)
    return None


def find_reentry_R2(bars, at, leg1, max_gap, pb_min, min_peak):
    """R2: 盈利出场后, 等回踩(回撤>=pb*波幅 且未破结构 entry)→续涨(创新高)再入场。
    min_peak: 仅当第一波峰值R>=该阈值才考虑(过滤边际赢单, 只跟真趋势的 wave2)。"""
    x1 = leg1["exit_idx"]; d = leg1["dirn"]
    entry = leg1["entry_px"]; peak_px = leg1["peak_px"]
    peak_ext = abs(peak_px - entry)
    if peak_ext <= 1e-9 or leg1["peak_r"] < max(0.5, min_peak):
        return None
    lo = x1 + 1; hi = min(x1 + 1 + max_gap, len(bars) - 1)
    pb_start = -1
    # 回踩极值: 多=运行最低 low; 空=运行最高 high (初始化为对应无穷, 避免被 entry 污染)
    run_ext = float("inf") if d > 0 else float("-inf")
    for j in range(lo, hi):
        o, h, l, c = bars[j]
        if d > 0:
            run_ext = min(run_ext, l)
            retrace = (peak_px - run_ext) / peak_ext
            struct_ok = (run_ext > entry)  # 结构未破(entry 上方回踩)
        else:
            run_ext = max(run_ext, h)
            retrace = (run_ext - peak_px) / peak_ext
            struct_ok = (run_ext < entry)
        if pb_start < 0 and retrace >= pb_min and struct_ok:
            pb_start = j  # 回踩条件满足, 开始等续涨
        if pb_start >= 0:
            # 续涨: 收盘创 [pb_start, j] 新高(多)/新低(空)
            if d > 0:
                hh = max(bars[k][1] for k in range(pb_start, j + 1))
                if c >= hh:
                    return simulate_leg(bars, at, j, d, P)
            else:
                ll = min(bars[k][2] for k in range(pb_start, j + 1))
                if c <= ll:
                    return simulate_leg(bars, at, j, d, P)
    return None


def run_mode(bars, at, mode, max_gap, pb_min, min_peak=0.0, split_r=2.0, runner_atr=2.0):
    rows = []
    for (e, d) in gen_entries(bars, 0, len(bars)):
        if mode == "PR":
            leg = simulate_runner(bars, at, e, d, P, split_r, runner_atr)
            if leg is None:
                continue
            rows.append((leg["R"], leg["R"], 0.0, leg["split_done"]))
            continue
        leg1 = simulate_leg(bars, at, e, d, P)
        if leg1 is None:
            continue
        R1 = leg1["R"]
        R2 = 0.0
        triggered = False
        if R1 > 0 and mode in ("R1", "R2"):
            leg2 = find_reentry_R1(bars, at, leg1, max_gap) if mode == "R1" \
                   else find_reentry_R2(bars, at, leg1, max_gap, pb_min, min_peak)
            if leg2 is not None:
                R2 = leg2["R"]
                triggered = True
        rows.append((R1 + R2, R1, R2, triggered))
    return rows


def summarize(rows):
    n = len(rows)
    if n == 0:
        return dict(n=0)
    mean = sum(r[0] for r in rows) / n
    win = sum(1 for r in rows if r[0] > 0) / n
    mean_r1 = sum(r[1] for r in rows) / n
    trig = sum(1 for r in rows if r[3])
    mean_r2 = sum(r[2] for r in rows if r[3]) / trig if trig else 0.0
    rewin = sum(1 for r in rows if r[3] and r[2] > 0) / trig if trig else 0.0
    return dict(n=n, mean=mean, win=win, mean_r1=mean_r1, mean_r2=mean_r2,
                trig=trig, trig_rate=trig / n, rewin=rewin)


def main():
    t0 = _t.time()
    all_data = []
    for sym in SYMS:
        bars = load(sym)
        if bars is None or len(bars) < 200:
            print("  [skip] %s" % sym); continue
        all_data.append((sym, bars, atr_arr(bars)))
    print("载入 %d 品种, 全样本入场点 %d" % (len(all_data),
          sum(len(gen_entries(b, 0, len(b))) for _, b, _ in all_data)))

    # 1) 单波基线 B
    print("\n=== 基线 B (单波 PROFIT_SECURE, 不连锁) ===")
    base_rows = []
    for sym, bars, at in all_data:
        base_rows += run_mode(bars, at, "B", 0, 0.0, 0.0)
    base = summarize(base_rows)
    print("n=%d 均值R=%+.3f 胜率=%.1f%%" % (base["n"], base["mean"], base["win"]*100))

    # 2) R1 / R2 网格
    print("\n=== 再入场网格 (指标: 净ΔR=含再入场均值R - 基线均值R, 再入场胜率) ===")
    print("%-5s %4s %5s %5s | %8s %8s %8s %9s %9s %9s %9s" %
          ("mode", "gap", "pb", "mpk", "n", "均值R", "胜率", "ΔR", "触发率", "R2均值", "R2胜率"))
    print("-" * 100)
    results = []
    for mode in ("R1", "R2"):
        for mg in GRID_MAX_GAP:
            for pb in (GRID_PB_MIN if mode == "R2" else [0.0]):
                for mpk in GRID_MIN_PEAK:
                    rows = []
                    for sym, bars, at in all_data:
                        rows += run_mode(bars, at, mode, mg, pb, mpk)
                    s = summarize(rows)
                    delta = s["mean"] - base["mean"]
                    results.append((mode, mg, pb, mpk, 0.0, 0.0, s, delta))
                    print("%-5s %4d %5.2f %5.1f | %8d %+8.3f %7.1f%% %+8.3f %8.1f%% %+8.3f %8.1f%%" %
                          (mode, mg, pb, mpk, s["n"], s["mean"], s["win"]*100, delta,
                           s["trig_rate"]*100, s["mean_r2"], s["rewin"]*100))
    # PR 部分止盈+游程
    for sr in GRID_SPLIT_R:
        for ratr in GRID_RUNNER_ATR:
            rows = []
            for sym, bars, at in all_data:
                rows += run_mode(bars, at, "PR", 0, 0.0, 0.0, sr, ratr)
            s = summarize(rows)
            delta = s["mean"] - base["mean"]
            results.append(("PR", 0, 0.0, 0.0, sr, ratr, s, delta))
            print("%-5s %4s %5s %5s sr%4.1f ra%4.1f | %8d %+8.3f %7.1f%% %+8.3f %8.1f%% %+8.3f %8.1f%%" %
                  ("PR", "-", "-", "-", sr, ratr, s["n"], s["mean"], s["win"]*100, delta,
                   s["trig_rate"]*100, s["mean_r2"], s["rewin"]*100))

    # 3) 取 ΔR 最优, 报告 per-symbol 稳健性(同向>=4/6)
    best = max(results, key=lambda x: x[7])
    print("\n=== 最优方案 %s (gap=%s, pb=%.2f, mpk=%.1f, split_r=%.1f, runner_atr=%.1f) 分品种稳健性 ===" %
          (best[0], best[1], best[2], best[3], best[4], best[5]))
    mode, mg, pb, mpk, sr, ratr = best[0], best[1], best[2], best[3], best[4], best[5]
    good = 0
    for sym, bars, at in all_data:
        r_mode = summarize(run_mode(bars, at, mode, mg, pb, mpk, sr, ratr))
        r_base = summarize(run_mode(bars, at, "B", 0, 0.0, 0.0))
        d = r_mode["mean"] - r_base["mean"]
        if d > 0:
            good += 1
        print("  %-7s 基线均值R=%+.3f  方案均值R=%+.3f  Δ=%+3.3f  触发率=%5.1f%%" %
              (sym, r_base["mean"], r_mode["mean"], d, r_mode["trig_rate"]*100))
    print("正向品种数 = %d / %d (>=4/6 即稳健)" % (good, len(all_data)))

    # 4) WFO: 最优在 3 段时间窗口的 ΔR 稳定性
    print("\n=== Walk-Forward: 最优在 3 段时间窗口的 ΔR 稳定性 ===")
    windows = [("W1前1/3",0.0,1/3),("W2中1/3",1/3,2/3),("W3后1/3",2/3,1.0)]
    for wname, lo_f, hi_f in windows:
        mode_rows = []; base_rows_w = []
        for sym, bars, at in all_data:
            n = len(bars)
            lo = int(n*lo_f); hi = int(n*hi_f)
            ents = gen_entries(bars, lo, hi)
            m_rows = []; b_rows = []
            for (e, d) in ents:
                if mode == "PR":
                    leg = simulate_runner(bars, at, e, d, P, sr, ratr)
                    m_rows.append(leg["R"] if leg else 0.0); b_rows.append(0.0)
                    continue
                leg1 = simulate_leg(bars, at, e, d, P)
                if leg1 is None: continue
                r1 = leg1["R"]; r2 = 0.0
                if r1 > 0:
                    leg2 = find_reentry_R1(bars,at,leg1,mg) if mode=="R1" else find_reentry_R2(bars,at,leg1,mg,pb,mpk)
                    if leg2: r2 = leg2["R"]
                m_rows.append(r1+r2); b_rows.append(r1)
            mode_rows.append(sum(m_rows)/len(m_rows) if m_rows else 0)
            base_rows_w.append(sum(b_rows)/len(b_rows) if b_rows else 0)
        dm = sum(mode_rows)/len(mode_rows); db = sum(base_rows_w)/len(base_rows_w)
        print("  %-10s 方案均值R=%+.3f 基线=%+.3f Δ=%+.3f" % (wname, dm, db, dm-db))

    print("\n用时 %.1fs" % (_t.time() - t0))


if __name__ == "__main__":
    main()
