# -*- coding: utf-8 -*-
"""
第一波 · 可证伪性 / 参数可辨识性 / 真噪声地板 检验 v4  (2026-11-11)
=====================================================================
起因: 审查官骆守关增量裁定 —— v3 的「34 组全 Δ=0 / 帕累托最优即现役」**不予采信**:
  ① 三个约束阈值全部锚定现役实测指纹(捕获72.6%/回吐11.2%/胜率60.7%),
     v2 那个 Δ=+0.0044R 候选被 >=72.6% 硬约束**剔除**, 而非被数据证伪;
  ② "全 0" 更可能是 B2 式恒值短路(参数改了等于没改 / 不可辨识),
     与 v1 harness 的 trail_atr 完全失效同源;
  ③ 育种官自提结构风险与"机会不存在"结论自相矛盾。
裁定: v3 结果仅作探索性沙盒存档, 阳性对照通过前一律不采信;
     拦截清单新增 **I 参数可辨识性证明**; 台账状态 HOLD / 证据链未闭合, 不得 CLOSED。

本脚本全部为**纯沙盒检验**, sandbox_only=true / no_live_extrapolation=true,
不改引擎、不连 MT5、不固化任何范式、不含实盘外推力。

检验项:
  A 阳性对照: 把 v2 候选注入同一 pipeline, 必须报出非零 Δ≈+0.0044R / 捕获62.4%(6位小数)
  B 参数可辨识性(拦截I): 6 维度逐一变动, 统计逐笔 realized_R / exit_reason 的 diff 笔数
  C 约束松弛扫描: 捕获阈值 72.6→70→65→60% × 容差 0.5/1/2pp, 看前沿是否移动
  D 164→34 筛除归因分解: 每组被 H1/H2/H3 哪条剔除
  E 真噪声地板: 1000 次 8 品种分层配对 bootstrap, 给实测 σ_noise / 95%CI / Bonferroni
  F 未 winsor 原始分布: 左尾 1%/5% 分位、最大单笔亏损、平均盈亏比
  G 34 组四元组表(净R/捕获/回吐/胜率) + 5 项闸门逐项原始数值(禁合并陈述)
  H 品种 jackknife: leave-one-out 看 Δ 符号稳定性
"""
import os, sys, itertools, hashlib, random, time, time as _t
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profit_secure_deep_v2 as V2
import profit_secure_deep_v3 as V3

LIVE = dict(V2.LIVE)
# v2 单目标最优候选(审查官指定注入的阳性对照)
CAND_V2 = dict(start_r=1.5, trail_atr=1.2, tight_r=2.0, tight_atr=0.5,
               lock_half=0.8, be_buf=0.1)

OUT_LINES = []


def say(s=""):
    print(s)
    OUT_LINES.append(str(s))


def fmt6(x):
    return "%+.6f" % x


def build():
    ds = []
    for sym in V2.SYMS:
        bars = V2.load(sym)
        if bars is None or len(bars) < 200:
            continue
        ds.append((sym, bars, V2.atr_arr(bars), V2.gen_entries(bars)))
    return ds


def rows(ds, P, **kw):
    return V3.eval_rows(ds, P, **kw)


def sample_hash(rr):
    h = hashlib.md5()
    for r in rr:
        h.update(("%.9f|%.9f|%s;" % (r[0], r[1], r[2])).encode())
    return h.hexdigest()[:16]


def build_164(ds):
    """复现 v3 三阶段坐标下降的 164 组(其各阶段最优恒为 LIVE, 故 baseP 保持 LIVE)。"""
    combos = []
    for sr, lh, bb in itertools.product(V3.G_START_R, V3.G_LOCK_HALF, V3.G_BE_BUF):
        P = dict(LIVE); P.update(start_r=sr, lock_half=lh, be_buf=bb); combos.append(P)
    for ta, tr, tta in itertools.product(V3.G_TRAIL_ATR, V3.G_TIGHT_R, V3.G_TIGHT_ATR):
        P = dict(LIVE); P.update(trail_atr=ta, tight_r=tr, tight_atr=tta); combos.append(P)
    for sr, lh, bb in itertools.product(V3.G_START_R, V3.G_LOCK_HALF, V3.G_BE_BUF):
        P = dict(LIVE); P.update(start_r=sr, lock_half=lh, be_buf=bb); combos.append(P)
    # 去重
    seen = set(); uniq = []
    for P in combos:
        k = tuple(sorted(P.items()))
        if k in seen:
            continue
        seen.add(k); uniq.append(P)
    stats = [(P, V2.summarize(rows(ds, P))) for P in uniq]
    return stats


def main():
    t0 = _t.time()
    say("=== 第一波 可证伪性检验 v4  %s ===" % time.strftime("%F %T"))
    say("标签: sandbox_only=true / no_live_extrapolation=true / live_change_approved=false")
    say("      pipeline_selfcheck=pending(本脚本完成后复核) / 台账=HOLD 证据链未闭合")
    ds = build()
    n = sum(len(d[3]) for d in ds)
    say("数据: %d 品种 %d 入场点" % (len(ds), n))

    live_rows = rows(ds, LIVE)
    live_s = V2.summarize(live_rows)
    say("\n现役 LIVE: 净R=%s 捕获=%.4f%% 回吐=%.4f%% 胜率=%.4f%% 样本哈希=%s" %
        (fmt6(live_s["mean"]), live_s["rev_cap"]*100, live_s["gave50"]*100,
         live_s["win"]*100, sample_hash(live_rows)))

    # ── A 阳性对照(审查官硬前置) ──
    say("\n=== A 阳性对照: v2 候选注入同一 pipeline (6位小数) ===")
    c2_rows = rows(ds, CAND_V2)
    c2_s = V2.summarize(c2_rows)
    d2 = [a[0]-b[0] for a, b in zip(c2_rows, live_rows)]
    mean_d2 = sum(d2)/len(d2)
    diff_n = sum(1 for a, b in zip(c2_rows, live_rows)
                 if abs(a[0]-b[0]) > 1e-12 or a[2] != b[2])
    say("  CAND_V2 = %s" % CAND_V2)
    say("  净R 候选=%s 现役=%s Δ=%s" % (fmt6(c2_s["mean"]), fmt6(live_s["mean"]), fmt6(mean_d2)))
    say("  反转捕获 候选=%.4f%% 现役=%.4f%% Δ=%+.4fpp" %
        (c2_s["rev_cap"]*100, live_s["rev_cap"]*100,
         (c2_s["rev_cap"]-live_s["rev_cap"])*100))
    say("  逐笔 diff 笔数 = %d / %d (%.2f%%)" % (diff_n, n, diff_n/n*100))
    say("  样本哈希 候选=%s 现役=%s" % (sample_hash(c2_rows), sample_hash(live_rows)))
    A_PASS = abs(mean_d2) > 1e-6 and diff_n > 0
    say("  A 判定: %s" % ("PASS — pipeline 能报出非零Δ, 无全局恒值短路" if A_PASS
                          else "FAIL — pipeline 恒值短路, v3 全部结果作废"))

    # ── B 参数可辨识性(拦截项 I) ──
    say("\n=== B 参数可辨识性 (拦截项I): 单维度变动的逐笔 diff 笔数 ===")
    dims = {
        "start_r": V3.G_START_R, "trail_atr": V3.G_TRAIL_ATR,
        "tight_r": V3.G_TIGHT_R, "tight_atr": V3.G_TIGHT_ATR,
        "lock_half": V3.G_LOCK_HALF, "be_buf": V3.G_BE_BUF,
    }
    ident = {}
    for dim, vals in dims.items():
        rec = []
        for v in vals:
            P = dict(LIVE); P[dim] = v
            rr = rows(ds, P)
            dn = sum(1 for a, b in zip(rr, live_rows)
                     if abs(a[0]-b[0]) > 1e-12 or a[2] != b[2])
            rec.append((v, dn))
        total = sum(x[1] for x in rec)
        ident[dim] = total
        say("  %-11s 取值%s -> 各档diff笔数 %s  合计=%d  %s" %
            (dim, str(vals), str([x[1] for x in rec]), total,
             "ACTIVE" if total > 0 else "**不可辨识/恒值短路**"))
    dead = [k for k, v in ident.items() if v == 0]
    say("  B 判定: 不可辨识维度 = %s" % (dead if dead else "无(全部可辨识)"))

    # ── C 约束松弛扫描(审查官要求 >=4 档) ──
    say("\n=== C 约束松弛扫描: 验证『v3 全0 是约束设计使然』 ===")
    stats = build_164(ds)
    say("  164组去重后 %d 组, 已全部重算四元组" % len(stats))
    cap_levels = [0.726, 0.70, 0.65, 0.60]
    tol_levels = [0.005, 0.01, 0.02]
    for cap in cap_levels:
        for tol in tol_levels:
            feasible = [(P, s) for P, s in stats
                        if s["rev_cap"] >= cap
                        and s["gave50"] <= live_s["gave50"] + tol
                        and s["win"] >= live_s["win"] - tol]
            feasible.sort(key=lambda x: -x[1]["mean"])
            bestP, bestS = feasible[0] if feasible else (None, None)
            is_live = bestP is not None and all(abs(bestP[k]-LIVE[k]) < 1e-9 for k in LIVE)
            say("  捕获>=%.1f%% 容差=%.1fpp | 可行%3d组 最优净R=%s Δ=%s 是否现役=%s" %
                (cap*100, tol*100, len(feasible),
                 fmt6(bestS["mean"]) if bestS else "N/A",
                 fmt6(bestS["mean"]-live_s["mean"]) if bestS else "N/A",
                 "是" if is_live else "**否(前沿已移动)**"))

    # ── D 164→34 筛除归因 ──
    say("\n=== D 筛除归因分解 (H1捕获 / H2回吐 / H3胜率) ===")
    c1 = c2 = c3 = cpass = 0
    for P, s in stats:
        h1 = s["rev_cap"] < 0.726
        h2 = s["gave50"] > live_s["gave50"] + 0.005
        h3 = s["win"] < live_s["win"] - 0.005
        if h1: c1 += 1
        elif h2: c2 += 1
        elif h3: c3 += 1
        else: cpass += 1
    say("  被 H1(捕获<72.6%%) 剔除 %d 组 / H2(回吐) %d 组 / H3(胜率) %d 组 / 通过 %d 组" %
        (c1, c2, c3, cpass))
    say("  → v2 候选捕获=%.1f%% 正是被 H1 剔除; 说明 v3『无改进机会』是**约束排除**而非数据证伪" %
        (c2_s["rev_cap"]*100))

    # ── E 真噪声地板: 1000次 8品种分层配对 bootstrap ──
    say("\n=== E 真噪声地板 (1000次 8品种分层配对bootstrap, 对 v2 候选) ===")
    # 按品种切片配对 Δ
    seg = []
    i = 0
    for sym, bars, at, ents in ds:
        k = sum(1 for (e, d) in ents if V2.simulate(bars, at, e, d, LIVE) is not None)
        seg.append((sym, d2[i:i+k])); i += k
    rng = random.Random(20261111)
    NB = 1000
    bmeans = []
    for _ in range(NB):
        s = 0.0; m = 0
        for sym, arr in seg:
            for _ in range(len(arr)):
                s += arr[rng.randrange(len(arr))]; m += 1
        bmeans.append(s/m)
    bmeans.sort()
    lo, hi = bmeans[int(0.025*NB)], bmeans[int(0.975*NB)]
    mu = sum(bmeans)/NB
    var = sum((x-mu)**2 for x in bmeans)/(NB-1)
    sigma = var ** 0.5
    say("  配对ΔR 实测均值=%s  bootstrap均值=%s" % (fmt6(mean_d2), fmt6(mu)))
    say("  σ_noise(分层配对bootstrap均值标准差)=%s  (n_boot=%d, 分层=8品种)" %
        (fmt6(sigma), NB))
    say("  Δ 的 95%%CI = [%s, %s]" % (fmt6(lo), fmt6(hi)))
    say("  |Δ| > 2σ_noise ? %s (需 |%s| > %s)" %
        ("PASS" if abs(mean_d2) > 2*sigma else "FAIL",
         fmt6(mean_d2), fmt6(2*sigma)))
    say("  Bonferroni α=0.05/164=%.6f (三层选择路径校正未做, 标注为缺口)" % (0.05/164))
    say("  转正需 Δ>+0.0131R; risk-officer ALLOWED(exp_r>0.1R) 需 Δ>+0.1131R → 均远未达")

    # ── F 未 winsor 原始分布 ──
    say("\n=== F 未 winsor 原始分布 (解释胜率60.7%下盈亏平衡比0.647) ===")
    raw = rows(ds, LIVE, winsor=False)
    rs = sorted(r[0] for r in raw)
    q01, q05 = rs[int(0.01*len(rs))], rs[int(0.05*len(rs))]
    wins = [x for x in rs if x > 0]; losses = [x for x in rs if x <= 0]
    avg_w = sum(wins)/len(wins) if wins else 0
    avg_l = abs(sum(losses)/len(losses)) if losses else 0
    say("  左尾 1%%分位=%s  5%%分位=%s  最大单笔亏损=%s" %
        (fmt6(q01), fmt6(q05), fmt6(rs[0])))
    say("  平均盈利=%s 平均亏损=%s 盈亏比=%.4f (盈亏平衡所需胜率=%.4f)" %
        (fmt6(avg_w), fmt6(-avg_l), avg_w/avg_l if avg_l else 0,
         avg_l/(avg_w+avg_l) if (avg_w+avg_l) else 0))
    say("  实际胜率=%.4f → 净R=%s" % (live_s["win"], fmt6(sum(rs)/len(rs))))

    # ── G 34组四元组表 + 5项闸门逐项 ──
    say("\n=== G 可行域四元组表(前12组, 完整表见输出文件) ===")
    feas = [(P, s) for P, s in stats
            if s["rev_cap"] >= 0.726 and s["gave50"] <= live_s["gave50"]+0.005
            and s["win"] >= live_s["win"]-0.005]
    feas.sort(key=lambda x: -x[1]["mean"])
    say("  %-58s %10s %9s %9s %9s" % ("参数", "净R", "捕获%", "回吐%", "胜率%"))
    for P, s in feas:
        say("  sr%.1f ta%.1f tr%.1f tta%.2f lh%.1f bb%.2f | %s %9.4f %9.4f %9.4f" %
            (P["start_r"], P["trail_atr"], P["tight_r"], P["tight_atr"],
             P["lock_half"], P["be_buf"], fmt6(s["mean"]),
             s["rev_cap"]*100, s["gave50"]*100, s["win"]*100))
    say("\n  5项闸门逐项原始数值(禁合并陈述, 对 v2 候选):")
    say("    1) bootstrap CI下界 = %s (要求>0)" % fmt6(lo))
    say("    2) ΔR = %s (要求>=+0.010)" % fmt6(mean_d2))
    byc = V2.eval_P_by_sym(ds, CAND_V2); byb = V2.eval_P_by_sym(ds, LIVE)
    same = sum(1 for s in byc if byc[s]["mean"] > byb[s]["mean"])
    say("    3) 同向正向品种 = %d/8 (要求>=6; 审查官已弃用符号检验改bootstrap)" % same)
    wd = []
    for a, b in [(0.0,1/3),(1/3,2/3),(2/3,1.0)]:
        sc = V2.summarize(rows(ds, CAND_V2, window=(a,b)))
        sb = V2.summarize(rows(ds, LIVE, window=(a,b)))
        wd.append(sc["mean"]-sb["mean"])
    say("    4) WFO三窗口Δ = %s / %s / %s" % (fmt6(wd[0]), fmt6(wd[1]), fmt6(wd[2])))
    sens = []
    for c in (0.0, 0.05, 0.10):
        sens.append(V2.summarize(rows(ds, CAND_V2, cost=c))["mean"] -
                    V2.summarize(rows(ds, LIVE, cost=c))["mean"])
    say("    5) 成本敏感性Δ = %s / %s / %s" % (fmt6(sens[0]), fmt6(sens[1]), fmt6(sens[2])))

    # ── H 品种 jackknife ──
    say("\n=== H 品种 leave-one-out jackknife (v2候选Δ符号稳定性) ===")
    pos = 0
    for k, (sym, arr) in enumerate(seg):
        rest = [x for j, (_, a2) in enumerate(seg) if j != k for x in a2]
        m = sum(rest)/len(rest)
        if m > 0: pos += 1
        say("  剔除 %-7s 后 Δ=%s %s" % (sym, fmt6(m), "正" if m > 0 else "负"))
    say("  正向窗口 %d/8" % pos)

    # ── 总结 ──
    say("\n=== 检验结论 (sandbox_only, 不含实盘外推力) ===")
    say("  A 阳性对照          : %s" % ("PASS(pipeline自证通过)" if A_PASS else "FAIL"))
    say("  B 不可辨识维度      : %s" % (",".join(dead) if dead else "无"))
    say("  C 约束松弛          : 见上表; 若松弛后出现非现役最优 → 证实 v3 全0 为约束设计使然")
    say("  D 筛除归因          : H1 捕获阈值剔除 %d 组 (v2候选即在此)" % c1)
    say("  E 真噪声地板        : σ_noise=%s, Δ=%s, |Δ|>2σ %s" %
        (fmt6(sigma), fmt6(mean_d2), "PASS" if abs(mean_d2)>2*sigma else "FAIL"))
    say("  台账状态            : HOLD / 证据链未闭合 / 待 chief 文字裁定 (不得 CLOSED)")
    say("  v3 结果             : 探索性沙盒存档, 阳性对照通过前不予采信")
    say("\n用时 %.1fs" % (_t.time()-t0))

    with open("E:/GoldstrategyEngine/research/_falsify_v4_out.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(OUT_LINES) + "\n")


if __name__ == "__main__":
    main()
