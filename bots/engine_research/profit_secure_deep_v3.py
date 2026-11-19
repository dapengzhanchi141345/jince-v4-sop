# -*- coding: utf-8 -*-
"""
第一波 PROFIT_SECURE · 深度优化 v3 · 约束帕累托 + 噪声地板
============================================================
v2 教训: 按「净均值R 最大」单目标寻优, 选出 sr1.5/lh0.8/bb0.10 把反转捕获率
从 72.6% 砍到 62.4%(-10.2pp) 换 +0.0044R -> 与用户「反转前吃到利润」诉求相反。
本版改为**约束帕累托**:
  硬约束 H1: 反转捕获率 >= 现役 rev_cap - TOL_CAP   (不让最痛指标退化)
  硬约束 H2: 回吐>50%占比 <= 现役 gave50 + TOL_GIVE (不让回撤恶化)
  硬约束 H3: 胜率 >= 现役 win - TOL_WIN
  目标    : 在可行域内最大化净均值R
  噪声地板: 对逐笔配对 ΔR 做 block bootstrap, 要求 95%CI 下界 > 0 才算真改进
            (防 +0.0044R 这类量级被误判为信号)

复用 v2 (research/profit_secure_deep_v2.py) 的修正版 simulate, 不重复实现。

红线: 纯研究, 不改引擎、不连 MT5、不开实单。落码与否由主理人依审查官裁定执行。
"""
import os, sys, itertools, random, time as _t
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profit_secure_deep_v2 as V2

# ── 约束阈值(审查官/架构师结论回传后由主理人定稿) ──
TOL_CAP = 0.000     # 反转捕获率不得退化(严格)
TOL_GIVE = 0.005    # 回吐>50% 允许 +0.5pp 容差
TOL_WIN = 0.005     # 胜率允许 -0.5pp 容差
MIN_DELTA = 0.010   # ΔR 至少 +0.010R 才值得考虑改实盘(噪声地板之上)
MIN_SAME = 6        # 同向正向品种 >=6/8
N_BOOT = 400
SEED = 20261111

G_START_R   = [0.8, 1.0, 1.2, 1.5]
G_TRAIL_ATR = [0.6, 0.8, 1.0, 1.2]
G_TIGHT_R   = [1.5, 2.0, 2.5]
G_TIGHT_ATR = [0.35, 0.5, 0.65]
G_LOCK_HALF = [0.8, 1.0, 1.2, 1.5]
G_BE_BUF    = [0.1, 0.2, 0.3, 0.5]


def eval_rows(datasets, P, cost=V2.COST_R, winsor=True, window=None):
    """逐笔结果, 顺序与 datasets/ents 严格一致 -> 可与 LIVE 配对做 bootstrap。"""
    rows = []
    for sym, bars, at, ents in datasets:
        if window is not None:
            lo, hi = int(len(bars) * window[0]), int(len(bars) * window[1])
            ents = V2.gen_entries(bars, lo, hi)
        for (e, d) in ents:
            res = V2.simulate(bars, at, e, d, P, cost, winsor)
            if res is not None:
                rows.append(res)
    return rows


def bootstrap_ci(delta, n_boot=N_BOOT, seed=SEED):
    """逐笔 ΔR 的 bootstrap 均值 95%CI。delta = list of (R_cand - R_live)。"""
    rng = random.Random(seed)
    n = len(delta)
    means = []
    for _ in range(n_boot):
        s = 0.0
        for _ in range(n):
            s += delta[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    return means[int(0.025 * n_boot)], means[int(0.975 * n_boot)], sum(means) / n_boot


def main():
    t0 = _t.time()
    datasets = []
    for sym in V2.SYMS:
        bars = V2.load(sym)
        if bars is None or len(bars) < 200:
            continue
        datasets.append((sym, bars, V2.atr_arr(bars), V2.gen_entries(bars)))
    total = sum(len(d[3]) for d in datasets)
    LIVE = dict(V2.LIVE)
    base_rows = eval_rows(datasets, LIVE)
    base = V2.summarize(base_rows)
    print("载入 %d 品种, 入场点 %d" % (len(datasets), total))
    print("现役基线: 净R=%+.4f 胜率=%.1f%% 反转捕获=%.1f%% 回吐>50%%=%.1f%% 反转n=%d" %
          (base["mean"], base["win"]*100, base["rev_cap"]*100,
           base["gave50"]*100, base["nrev"]))

    cap_min = base["rev_cap"] - TOL_CAP
    give_max = base["gave50"] + TOL_GIVE
    win_min = base["win"] - TOL_WIN
    print("可行域: 反转捕获>=%.1f%%  回吐>50%%<=%.1f%%  胜率>=%.1f%%" %
          (cap_min*100, give_max*100, win_min*100))

    def feasible(s):
        return (s["rev_cap"] >= cap_min and s["gave50"] <= give_max
                and s["win"] >= win_min)

    # ── 约束帕累托: 三阶段坐标下降, 每阶段只在可行域内推进 ──
    feasible_pool = []
    tested = 0

    def scan(baseP, dims, tag):
        nonlocal tested
        best = None
        for vals in itertools.product(*dims[1]):
            P = dict(baseP)
            P.update(dict(zip(dims[0], vals)))
            s = V2.summarize(eval_rows(datasets, P))
            tested += 1
            feasible_pool.append((P, s))
            if not feasible(s):
                continue
            if best is None or s["mean"] > best[1]["mean"]:
                best = (P, s)
        print("  %-8s 本阶段可行解 %d 组, 阶段最优净R=%s" %
              (tag, sum(1 for _, s in feasible_pool[-len(list(itertools.product(*dims[1]))):] if feasible(s)),
               ("%+.4f" % best[1]["mean"]) if best else "无(全部违反约束)"))
        return best[0] if best else baseP

    print("\n=== 约束帕累托 三阶段坐标下降 ===")
    cur = dict(LIVE)
    cur = scan(cur, (("start_r", "lock_half", "be_buf"),
                     (G_START_R, G_LOCK_HALF, G_BE_BUF)), "Stage1")
    cur = scan(cur, (("trail_atr", "tight_r", "tight_atr"),
                     (G_TRAIL_ATR, G_TIGHT_R, G_TIGHT_ATR)), "Stage2")
    cur = scan(cur, (("start_r", "lock_half", "be_buf"),
                     (G_START_R, G_LOCK_HALF, G_BE_BUF)), "Stage3")
    print("  累计测试 %d 组" % tested)

    # 从全部可行解里取净R 最高者(全局可行帕累托最优), 而非只看最后一轮
    fp = [(p, s) for p, s in feasible_pool if feasible(s)]
    # 去重
    seen = set(); uniq = []
    for p, s in sorted(fp, key=lambda x: -x[1]["mean"]):
        k = tuple(sorted(p.items()))
        if k in seen:
            continue
        seen.add(k); uniq.append((p, s))
    print("\n=== 可行域内 top8 (按净均值R) ===")
    for p, s in uniq[:8]:
        print("  sr%.1f ta%.1f tr%.1f tta%.2f lh%.1f bb%.2f | 净R=%+.4f Δ=%+.4f 捕获=%.1f%% 回吐=%.1f%% 胜率=%.1f%%" %
              (p["start_r"], p["trail_atr"], p["tight_r"], p["tight_atr"],
               p["lock_half"], p["be_buf"], s["mean"], s["mean"]-base["mean"],
               s["rev_cap"]*100, s["gave50"]*100, s["win"]*100))

    if not uniq:
        print("\n  可行域为空: 在「反转捕获不退化」硬约束下, 没有任何参数组合可行。")
        print("  裁定: 维持现役参数 lh1.2/bb0.2 (v2 的 +0.0044R 确认为牺牲捕获率的伪改进)。")
        return

    BP, BS = uniq[0]
    print("\n=== 帕累托最优候选深度验证 ===")
    print("  参数: %s" % BP)
    print("  净R=%+.4f (现役 %+.4f, Δ=%+.4f) 捕获=%.1f%% 回吐=%.1f%% 胜率=%.1f%%" %
          (BS["mean"], base["mean"], BS["mean"]-base["mean"],
           BS["rev_cap"]*100, BS["gave50"]*100, BS["win"]*100))

    # 1) bootstrap 噪声地板
    cand_rows = eval_rows(datasets, BP)
    assert len(cand_rows) == len(base_rows), (len(cand_rows), len(base_rows))
    delta = [a[0] - b[0] for a, b in zip(cand_rows, base_rows)]
    lo, hi, mb = bootstrap_ci(delta)
    print("  ① Bootstrap 逐笔ΔR: 均值=%+.4f 95%%CI=[%+.4f, %+.4f] n_boot=%d" %
          (mb, lo, hi, N_BOOT))
    print("     CI下界>0 ? %s" % ("PASS" if lo > 0 else "FAIL -> Δ 不显著, 判为噪声"))

    # 2) 同向品种数
    by_c = V2.eval_P_by_sym(datasets, BP)
    by_b = V2.eval_P_by_sym(datasets, LIVE)
    same = sum(1 for s in by_c if by_c[s]["mean"] > by_b[s]["mean"])
    print("  ② 同向正向品种 %d/%d (需>=%d) %s" %
          (same, len(by_c), MIN_SAME, "PASS" if same >= MIN_SAME else "FAIL"))

    # 3) WFO
    wins = [("W1前1/3", 0.0, 1/3), ("W2中1/3", 1/3, 2/3), ("W3后1/3", 2/3, 1.0)]
    wd = []
    print("  ③ Walk-Forward:")
    for wn, a, b in wins:
        sc = V2.summarize(eval_rows(datasets, BP, window=(a, b)))
        sb = V2.summarize(eval_rows(datasets, LIVE, window=(a, b)))
        d = sc["mean"] - sb["mean"]
        wd.append(d)
        print("     %-10s Δ=%+.4f 捕获 候选=%.1f%% 现役=%.1f%% n=%d" %
              (wn, d, sc["rev_cap"]*100, sb["rev_cap"]*100, sc["n"]))
    wfo_ok = all(d > 0 for d in wd)

    # 4) 敏感性与甜蜜点
    print("  ④ 敏感性:")
    sens = []
    for c in (0.0, 0.05, 0.10):
        d = V2.summarize(eval_rows(datasets, BP, cost=c))["mean"] - \
            V2.summarize(eval_rows(datasets, LIVE, cost=c))["mean"]
        sens.append(d)
        print("     成本 %.2fR Δ=%+.4f" % (c, d))
    for w in (True, False):
        d = V2.summarize(eval_rows(datasets, BP, winsor=w))["mean"] - \
            V2.summarize(eval_rows(datasets, LIVE, winsor=w))["mean"]
        print("     winsor=%-5s Δ=%+.4f" % (str(w), d))
    top8 = [s["mean"] for _, s in uniq[:8]]
    print("  ⑤ 参数甜蜜点 top8 净R 区间 [%+.4f, %+.4f] 跨度=%.4f" %
          (min(top8), max(top8), max(top8)-min(top8)))

    # ── 最终闸门 ──
    checks = {
        "bootstrap CI下界>0": lo > 0,
        "ΔR >= %.3f" % MIN_DELTA: (BS["mean"] - base["mean"]) >= MIN_DELTA,
        "同向 >= %d/8" % MIN_SAME: same >= MIN_SAME,
        "WFO 三窗口全正": wfo_ok,
        "成本敏感性同号": all(d > 0 for d in sens),
        "约束未破": feasible(BS),
    }
    print("\n=== 落码闸门 ===")
    for k, v in checks.items():
        print("  [%s] %s" % ("PASS" if v else "FAIL", k))
    verdict = all(checks.values())
    print("\n  裁定: %s" % ("PASS -> 可提交 chief 联合复核后落码" if verdict
                            else "NOT PASS -> 维持现役参数 lh1.2/bb0.2, 不改实盘"))
    print("\n用时 %.1fs" % (_t.time() - t0))


if __name__ == "__main__":
    main()
