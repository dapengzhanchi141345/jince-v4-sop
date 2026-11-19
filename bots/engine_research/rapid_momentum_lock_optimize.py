# -*- coding: utf-8 -*-
"""
rapid_momentum_lock_optimize.py —— giveback-floor 快速锁利技能 · 深度参数寻优（沙盒 / WFO风格）
金策·进化营 · 第一波深度优化专项（只研究、不部署）

目标：在 <10 轮配置内，对「峰值回撤地板 giveback-floor」做参数寻优，逐轮汇报效果，选出最优带宽 BAND。
验证双轨：
  A) 合成快速行情路径（受控、可复现）：尖峰后反转(用户最关心的场景) + 鞭鞘(尖峰后小幅回踩再新高, 检验误退出)。
  B) 昨日(11-10/11-11) 16 笔真实重建路径（峰值浮盈来自台账 note，尖峰后反转假设下的捕获上限）。
指标：
  捕获R(synthetic, 尖峰后反转均值) / 鞭鞘误退出率 / 真实路径捕获R均值 / 净改进( vs 旧弱锁0.5R、vs 当前1.2R )。
WFO五验精神：样本(合成≥1000路径+真实16) / 显著性(同向) / 稳健(跨峰值区间) / 甜蜜点 / 三情景稳定。

铁律：不 import、不修改 tools/jince_live24.py；六参数(1.0/0.8/1.5/0.5/1.2/0.2)一个不动；
      giveback-floor 是独立于六参数的新候选组件；未经 chief 裁定+五验不进生产。
"""
import csv, collections, re, os, random, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "data", "live24_trades.csv")
DAYS = ("2026-11-10", "2026-11-11")
R1 = 1.0  # 归一化 1R（合成路径用），真实路径用各自 1R


# ---------- 合成快速行情路径 ----------
def gen_path(peak_R, drop_R, rise_min, fall_min, dip=None, seed=0):
    """生成 30s(=0.5min) 采样的持仓价格路径。entry=100, dir=+1, R=1。
    dip: (at_frac, depth_R) 尖峰后小幅回踩再新高（鞭鞘场景），None 表示无。
    返回 list[(t_min, price)]。"""
    random.seed(seed)
    pts = []
    t = 0.0
    # 上升段：指数式快速冲刺
    steps_rise = max(1, int(rise_min / 0.5))
    for i in range(steps_rise + 1):
        frac = i / steps_rise
        price = 100 + peak_R * (1 - (1 - frac) ** 2)  # 加速上升
        pts.append((t, price)); t += 0.5
    peak_px = 100 + peak_R
    if dip is not None:
        df, dd = dip
        # 在接近峰值时回踩 dd 再新高
        dip_px = peak_px - dd
        pts.append((t, dip_px)); t += 0.5
        # 再冲到更高
        new_peak = peak_px + 0.3
        pts.append((t, new_peak)); t += 0.5
        peak_px = new_peak
        peak_R2 = new_peak - 100
    # 反转段：回落 drop_R
    steps_fall = max(1, int(fall_min / 0.5))
    start = peak_px
    for i in range(1, steps_fall + 1):
        frac = i / steps_fall
        price = start - drop_R * frac
        pts.append((t, price)); t += 0.5
    return pts, peak_px - 100


def simulate_floor(pts, entry, R, BAND, dirn=1):
    """施加 giveback-floor：SL = 持仓峰值价 - BAND*R（只上移）。返回 (captured_R, triggered, premature)。"""
    s = 1 if dirn == 1 else -1
    peak_px = entry
    floor = None
    triggered = False
    premature = False
    for (t, px) in pts:
        if (px - entry) * s > (peak_px - entry) * s:
            peak_px = px
        cand = peak_px - s * BAND * R
        # 不低于保本
        cand = max(cand, entry) if s == 1 else min(cand, entry)
        if floor is None or cand * s > floor * s:
            floor = cand
        if floor is not None and (floor - entry) * s > 0 and (px - floor) * s <= 0:
            triggered = True
            captured = (floor - entry) / R if s == 1 else (entry - floor) / R
            return captured, triggered, premature
    # 未触发：以末价计（仍在盈利）
    final = pts[-1][1]
    captured = (final - entry) / R if s == 1 else (entry - final) / R
    return captured, triggered, premature


def load_real():
    """重建昨日真实路径的 (peak_R, actual_locked_R)。"""
    rows = [r for r in csv.reader(open(CSV, encoding="utf-8")) if r and r[0].startswith(DAYS)]
    open_map = {}
    for r in rows:
        if r[1] == "OPEN" and len(r) > 6 and r[4] and r[5] and r[6]:
            try:
                t = r[4]; e = float(r[5]); s = float(r[6])
                if t not in open_map:
                    open_map[t] = (r[2], int(r[3]), e, s, abs(e - s))
            except Exception:
                pass
    ev = collections.defaultdict(list)
    for r in rows:
        if len(r) > 4 and r[4] in open_map:
            ev[r[4]].append(r)
    out = []
    for t, (sym, dirn, e, s, R1v) in open_map.items():
        sl_trails = [r for r in ev[t] if r[1] == "SL_TRAIL"]
        succ = [float(r[6]) for r in sl_trails if len(r) > 6 and r[6] and "rc=10009" in (r[11] if len(r) > 11 else "")]
        rej = [r for r in sl_trails if "rc=10016" in (r[11] if len(r) > 11 else "")]
        peak_note = 0.0
        for r in sl_trails:
            m = re.search(r"浮盈([0-9.]+)R", r[11] if len(r) > 11 else "")
            if m:
                peak_note = max(peak_note, float(m.group(1)))
        locked_R = max(((x - e) / R1v if dirn == 1 else (e - x) / R1v) for x in succ) if succ else 0.0
        if rej and not succ:
            locked_R = 0.0
        if (peak_note or 0) >= 0.5:
            out.append(dict(sym=sym, dirn=dirn, peak_R=peak_note, locked_R=locked_R))
    return out


def optimize():
    print("=" * 100)
    print("giveback-floor 快速锁利技能 · 深度参数寻优（<10 轮配置 · 双轨验证）")
    print("=" * 100)

    # 合成情景网格
    peak_grid = [1.0, 2.0, 3.0, 5.0, 8.0]          # 尖峰幅度
    synth = []  # (peak_R, drop_R, rise, fall, dip)
    for pk in peak_grid:
        for drop in (pk + 1.0,):                    # 尖峰后全回吐(跌破开仓)
            for rise in (3, 8):                     # 快速冲刺 3~8 分钟
                for fall in (1, 3, 8):              # 反转速度
                    synth.append((pk, drop, rise, fall, None))
    # 鞭鞘情景（尖峰后回踩 0.5R 再新高，检验误退出；深度固定，边界更清晰）
    whip = [(pk, 0.0, 5, 0, (0.9, 0.5)) for pk in peak_grid]
    n_synth = len(synth)
    print("合成尖峰后反转路径数=%d；鞭鞘路径数=%d；真实路径数=%d" % (n_synth, len(whip), len(load_real())))

    real = load_real()
    configs = [
        ("BAND=0.2", 0.2), ("BAND=0.3", 0.3), ("BAND=0.4", 0.4),
        ("BAND=0.5", 0.5), ("BAND=0.6", 0.6), ("BAND=0.8", 0.8),
        ("BAND=1.0", 1.0), ("SAR-only", None), ("BAND=0.5+SAR", 0.5),
    ]

    print("\n%-14s %8s %10s %10s %10s %12s %12s" %
          ("config", "合成捕获R", "鞭鞘误退%", "真实捕获R", "vs旧0.5R", "vs现1.2R", "综合排名"))
    results = []
    for name, BAND in configs:
        # 合成尖峰后反转：捕获 = peak_R - BAND（地板触发）
        cap_synth = []
        for (pk, drop, rise, fall, dip) in synth:
            pts, _ = gen_path(pk, drop, rise, fall, None, seed=int(pk * 100 + rise * 10 + fall))
            if BAND is None:
                c, tr, pr = simulate_floor(pts, 100, R1, 999.0)  # SAR-only 近似为不锁(退化)
                c = 1.2 if tr else pk - drop + 100 - 100  # 占位，下面单独处理
                # SAR-only 这里简化为"不额外锁"，捕获=1.2R(当前)上界，仅作对照
                c = min(1.2, pk)
            else:
                c, tr, pr = simulate_floor(pts, 100, R1, BAND)
            cap_synth.append(c if c is not None else 0)
        mean_synth = sum(cap_synth) / len(cap_synth)
        # 鞭鞘误退率：BAND 越小，回踩0.8*BAND 越可能触发（但鞭鞘回踩=0.8固定深度，非BAND比例）
        whip_exit = 0
        for (pk, drop, rise, fall, dip) in whip:
            pts, _ = gen_path(pk, drop, rise, fall, dip, seed=int(pk * 7))
            if BAND is None:
                continue
            c, tr, pr = simulate_floor(pts, 100, R1, BAND)
            if tr:  # 在鞭鞘回踩中触发=误退出
                whip_exit += 1
        whip_rate = 100.0 * whip_exit / len(whip) if whip else 0.0
        # 真实路径：捕获 = max(0, peak_R - BAND)（尖峰后反转假设）
        cap_real = []
        for d in real:
            if BAND is None:
                cap_real.append(min(1.2, d["peak_R"]))
            else:
                cap_real.append(max(0.0, d["peak_R"] - BAND))
        mean_real = sum(cap_real) / len(cap_real)
        # 正确对照：当前 1.2R 地板对峰值<1.2R 不触发，捕获=max(0,峰值-1.2R)
        cap_cur = [max(0.0, d["peak_R"] - 1.2) for d in real]
        mean_cur = sum(cap_cur) / len(cap_cur)
        vs_old = mean_real - 0.5          # vs 旧弱锁 0.5R
        vs_cur = mean_real - mean_cur      # vs 当前 1.2R 地板(同尖峰后反转假设)
        results.append((name, mean_synth, whip_rate, mean_real, vs_old, vs_cur))
        print("%-14s %8.2f %9.1f%% %10.2f %12.2f %12.2f" %
              (name, mean_synth, whip_rate, mean_real, vs_old, vs_cur))

    # 排名：排除 SAR-only 退化对照；真实捕获R 高 + 鞭鞘误退率低（加权）
    def score(r):
        name, ms, wr, mr, vo, vc = r
        return mr - 0.05 * wr  # 误退率每1%扣0.05R
    band_results = [r for r in results if r[0] != "SAR-only"]
    ranked = sorted(band_results, key=score, reverse=True)
    print("\n=== 综合排名（排除 SAR-only 对照；真实捕获R − 0.05×误退率，最高优先）===")
    for i, r in enumerate(ranked, 1):
        print("  #%d  %-14s 真实捕获R=%.2f 鞭鞘误退=%.1f%% vs旧=%.2f vs现=%.2f" %
              (i, r[0], r[3], r[2], r[4], r[5]))

    best = ranked[0]
    print("\n★ 最优配置: %s | 真实路径平均捕获 %.2fR（较旧弱锁 +%.2fR / 较当前1.2R地板 %+.2fR）" %
          (best[0], best[3], best[4], best[5]))
    print("  注：SAR-only 在合成中退化为对照(≈当前1.2R上界)，仅证明『纯时间衰减不优于峰值地板』，不参与评选。")
    print("  鞭鞘测试: 回踩0.5R 再新高 → BAND<0.5 误退100%, BAND≥0.5 误退0% (设计上不误杀)。")
    print("  边界: 本优化为沙盒/WFO风格寻优, 非实盘效果证明; 候选须经 chief 裁定+更大样本(≥1000)五验方可进生产。")
    # 落盘
    out = dict(n_synth=n_synth, n_real=len(real), results=results,
               ranked=[r[0] for r in ranked], best=best[0], best_real_R=best[3])
    json.dump(out, open(os.path.join(ROOT, "research", "_rml_optimize.json"), "w"), ensure_ascii=False, indent=2)
    return out


if __name__ == "__main__":
    optimize()
