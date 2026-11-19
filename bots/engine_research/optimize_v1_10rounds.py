#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
optimize_v1_10rounds.py —— 全面深度优化 R0~R10（11 轮迭代），用户 20:17 令「全面深度优化10次以上后立即执行」
================================================================================
数据源: E:/GoldstrategyEngine/data/fresh（11品种四层补齐至2026-11-12、统一UTC口径）
口径  : 固定 1ATR 绝对收益 R_abs=(R_rel+cost)*min(sl_mult,1.2)-cost, 成本0.05R/压力0.10R
裁决  : 净期望最大化(chief 14:25口径); OPTIMIZED_PASS 须同时过:
        五验>=4 + 5折WF(净R>0且avg改善)>=3折 + 70/30 OOS PASS + 成本0.10R压力avg>0且>=现役
红线  : 研究与候选产出, 不改 jince_live24.py / practice_params / 任何 live 参数;
        六参数 PROFIT_SECURE 冻结; 全落 E 盘。

轮次:
  R0  现役基线重估(fresh数据)
  R1  进场闸坐标下降 adx_min/vol_k/break_margin/min_body
  R2  出场坐标下降 sl_mult/tp_mult/max_hold_h/giveback
  R3  h1_on 开关 + 第二轮全坐标下降
  R4  随机变异 120 组(最优邻域 70% + 全空间 30%)
  R5  随机变异 120 组(全空间)
  R6  Top10 -> 5折 Walk-Forward 稳健筛选
  R7  Top5 -> 70/30 OOS
  R8  Top3 -> 成本 0.10R 压力
  R9  联合微调(最优 g 每参数±1档再确认局部最优)
  R10 终选五验 + vs 现役 Δ 对比 + 裁决

输出: research/optimize_v1_results.json + 控制台逐轮日志
"""
import os, sys, json, time, random
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import liquid_wfo_m15_v2 as W

W.DATA = "E:/GoldstrategyEngine/data/fresh"     # fresh 数据源(统一UTC、补齐至11-12)
OUT = os.path.join(W.ROOT, "research", "optimize_v1_results.json")
COST, STRESS = W.COST_R, W.COST_R_STRESS
NFOLD, OOS_SPLIT = 5, 0.70
random.seed(20261112)

GRID = dict(
    adx_min=[20., 25., 30., 35., 40., 45.],
    break_margin=[0.3, 0.6, 1.0],
    vol_k=[0.5, 0.6, 0.7, 0.9],
    min_body=[0.1, 0.3, 0.5],
    h1_on=[True, False],
    max_hold_h=[12, 18, 24, 30],
    giveback=[0.4, 0.6, 0.8],
    sl_mult=[0.6, 0.8, 1.0, 1.2],
    tp_mult=[2.0, 3.0, 4.0, 5.0],
)
CD_ORDER = ["adx_min", "vol_k", "break_margin", "min_body",
            "sl_mult", "tp_mult", "max_hold_h", "giveback"]
ENTER_KEYS = ["adx_min", "vol_k", "break_margin", "min_body"]
EXIT_KEYS = ["sl_mult", "tp_mult", "max_hold_h", "giveback"]


def ev(P, g, cost=COST, lo=None, hi=None):
    k, s = W.gen_signals(P, g)
    if lo is not None:
        m = (k >= lo) & (k < hi)
        k, s = k[m], s[m]
    R, _, _ = W.simulate(P, g, k, s, cost=cost)
    n = len(R)
    Ra = (R + cost) * min(g['sl_mult'], W.REAL_SL_CAP) - cost if n else np.array([])
    if n == 0:
        return dict(n=0, net=0., avg=0., win=0., R=Ra)
    return dict(n=n, net=float(Ra.sum()), avg=float(Ra.mean()),
                win=float((R > 0).mean()), R=Ra)


def slim(e):
    return dict(n=e['n'], net=round(e['net'], 3), avg=round(e['avg'], 5),
                win=round(e['win'], 4))


def coord_descent(P, g, keys, cur):
    g = dict(g)
    for key in keys:
        bv, be = g[key], cur
        for v in GRID[key]:
            if v == g[key]:
                continue
            q = dict(g); q[key] = v
            e = ev(P, q)
            if e['n'] >= 40 and e['avg'] > be['avg'] + 1e-6:
                be, bv = e, v
        if bv != g[key]:
            g[key] = bv; cur = be
    return g, cur


def mutate(g, p_full=0.3):
    q = dict(g)
    if random.random() < p_full:                     # 全空间重采样
        for key in GRID:
            q[key] = random.choice(GRID[key])
    else:                                            # 邻域: 随机动 1~3 个参数
        keys = random.sample(list(GRID.keys()), random.randint(1, 3))
        for key in keys:
            q[key] = random.choice([v for v in GRID[key] if v != q[key]] +
                                   [q[key]])
    return q


def five(b, o):
    if b['n'] == 0 or o['n'] == 0:
        return dict(passed=0)
    bb = dict(n=b['n'], avg=b['avg'], net=b['net'], win=b['win'], R=b['R'])
    oo = dict(n=o['n'], avg=o['avg'], net=o['net'], win=o['win'], R=o['R'])
    return W.five_tests(bb, oo, curve=None)


def optimize_symbol(sym, log):
    P = W.prepare(sym)
    live = W.load_live_fresh() if hasattr(W, 'load_live_fresh') else W.load_live()
    g0 = dict(W.BASE); g0['sl_mult'] = live[sym]['sl']; g0['tp_mult'] = live[sym]['tp']
    rounds = {}

    # R0 基线
    base = ev(P, g0)
    rounds['R0_基线'] = dict(g=dict(g0), **slim(base))
    log("    R0 基线 n=%d net=%+.2f avg=%+.4f" % (base['n'], base['net'], base['avg']))

    # R1 进场坐标下降
    g1, c1 = coord_descent(P, g0, ENTER_KEYS, base)
    rounds['R1_进场坐标'] = dict(g=dict(g1), **slim(c1))
    log("    R1 进场 avg=%+.4f (%s)" % (c1['avg'], {k: g1[k] for k in ENTER_KEYS if g1[k] != g0[k]}))

    # R2 出场坐标下降
    g2, c2 = coord_descent(P, g1, EXIT_KEYS, c1)
    rounds['R2_出场坐标'] = dict(g=dict(g2), **slim(c2))
    log("    R2 出场 avg=%+.4f (%s)" % (c2['avg'], {k: g2[k] for k in EXIT_KEYS if g2[k] != g1[k]}))

    # R3 h1_on + 第二轮全坐标
    g3 = dict(g2)
    cur = c2
    for v in GRID['h1_on']:
        if v != g3['h1_on']:
            q = dict(g3); q['h1_on'] = v
            e = ev(P, q)
            if e['n'] >= 40 and e['avg'] > cur['avg'] + 1e-6:
                g3['h1_on'] = v; cur = e
    g3, c3 = coord_descent(P, g3, CD_ORDER, cur)
    rounds['R3_h1开关+全坐标二轮'] = dict(g=dict(g3), **slim(c3))
    log("    R3 二轮 avg=%+.4f" % c3['avg'])

    # R4/R5 随机变异
    pool = [(c3['avg'], dict(g3))]
    best_g = dict(g3)
    for tag, n_mut, p_full in (("R4_变异邻域", 120, 0.0), ("R5_变异全空间", 120, 1.0)):
        best_a, best_g = pool[0]
        tried = 0
        for _ in range(n_mut):
            q = mutate(g3, p_full=p_full)
            if q == g3:
                continue
            tried += 1
            e = ev(P, q)
            if e['n'] >= 40 and e['avg'] > best_a + 1e-6:
                best_a, best_g = e['avg'], dict(q)
        pool.append((best_a, best_g))
        eb = ev(P, best_g)
        rounds[tag] = dict(g=dict(best_g), **slim(eb))
        log("    %s tried=%d best avg=%+.4f" % (tag, tried, best_a))

    # 汇总候选(去重) 取 avg Top10
    seen, cands = set(), []
    for a, g in pool + [(ev(P, g1)['avg'], g1), (ev(P, g2)['avg'], g2)]:
        key = json.dumps(g, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key); cands.append((a, g))
    cands = sorted(cands, key=lambda x: -x[0])[:10]

    # R6 5折 WF 筛选
    N = P['n']
    edges = np.linspace(0, N, NFOLD + 1).astype(int)
    wf_score = {}
    for a, g in cands:
        pos = 0
        for f in range(NFOLD):
            lo, hi = int(edges[f]), int(edges[f + 1])
            ef = ev(P, g, lo=lo, hi=hi)
            e0 = ev(P, g0, lo=lo, hi=hi)
            if ef['n'] >= 5 and ef['net'] > 0 and ef['avg'] > e0['avg']:
                pos += 1
        wf_score[json.dumps(g, sort_keys=True, default=str)] = pos
    cands_wf = [(a, g, wf_score[json.dumps(g, sort_keys=True, default=str)]) for a, g in cands]
    cands_wf.sort(key=lambda x: (-x[2], -x[0]))
    rounds['R6_WF筛选'] = [dict(g=dict(g), avg=round(a, 5), wf_pos=pos) for a, g, pos in cands_wf[:5]]
    log("    R6 WF top: " + ", ".join("%d/5(%.4f)" % (p, a) for a, g, p in cands_wf[:3]))

    # R7 70/30 OOS
    cut = int(N * OOS_SPLIT)
    oos_list = []
    for a, g, pos in cands_wf[:5]:
        e0t = ev(P, g0, lo=cut, hi=N)
        et = ev(P, g, lo=cut, hi=N)
        ok = et['n'] >= 10 and et['net'] > 0 and et['avg'] >= e0t['avg']
        oos_list.append((a, g, pos, ok, slim(et)))
    oos_list.sort(key=lambda x: (not x[3], -x[0]))
    rounds['R7_OOS'] = [dict(g=dict(g), oos_pass=ok, test=et_s) for a, g, pos, ok, et_s in oos_list[:5]]
    log("    R7 OOS: " + ", ".join("%s" % ("PASS" if ok else "FAIL") for _, _, _, ok, _ in oos_list[:3]))

    # R8 成本压力(Top3)
    stress_list = []
    for a, g, pos, ok, et_s in oos_list[:3]:
        es = ev(P, g, cost=STRESS)
        stress_list.append((a, g, pos, ok, es['avg'] > 0 and es['avg'] >= ev(P, g0, cost=STRESS)['avg']))
    rounds['R8_成本压力'] = [dict(g=dict(g), stress_pass=ok2) for a, g, pos, ok, ok2 in stress_list]

    # R9 联合微调(对综合最优者±1档确认局部最优)
    best = None
    for a, g, pos, ok, ok2 in stress_list:
        score = (ok2, ok, pos, a)
        if best is None or score > best[0]:
            best = (score, g)
    gb = dict(best[1])
    cb = ev(P, gb)
    g9, c9 = coord_descent(P, gb, CD_ORDER, cb)
    rounds['R9_联合微调'] = dict(g=dict(g9), **slim(c9))
    log("    R9 微调 avg %+.4f -> %+.4f" % (cb['avg'], c9['avg']))

    # R10 终选五验 + 裁决
    ft = five(base, c9)
    wf_pos_final = 0
    for f in range(NFOLD):
        lo, hi = int(edges[f]), int(edges[f + 1])
        ef = ev(P, g9, lo=lo, hi=hi); e0 = ev(P, g0, lo=lo, hi=hi)
        if ef['n'] >= 5 and ef['net'] > 0 and ef['avg'] > e0['avg']:
            wf_pos_final += 1
    e0t = ev(P, g0, lo=cut, hi=N); et = ev(P, g9, lo=cut, hi=N)
    oos_ok = et['n'] >= 10 and et['net'] > 0 and et['avg'] >= e0t['avg']
    es = ev(P, g9, cost=STRESS); es0 = ev(P, g0, cost=STRESS)
    stress_ok = es['avg'] > 0 and es['avg'] >= es0['avg']
    verdict = ('OPTIMIZED_PASS' if (ft['passed'] >= 4 and wf_pos_final >= 3
                                    and oos_ok and stress_ok and c9['net'] > base['net'])
               else 'HOLD_LIVE')
    rounds['R10_终选'] = dict(
        g=dict(g9), **slim(c9), five_passed=ft['passed'],
        wf_pos=wf_pos_final, oos_pass=bool(oos_ok), stress_pass=bool(stress_ok),
        verdict=verdict, dNetR=round(c9['net'] - base['net'], 3),
        dAvgR=round(c9['avg'] - base['avg'], 5))
    log("    R10 终选 five=%d/5 WF=%d/5 OOS=%s stress=%s | Δnet=%+.2f -> %s" %
        (ft['passed'], wf_pos_final, oos_ok, stress_ok,
         c9['net'] - base['net'], verdict))
    return dict(sym=sym, rounds=rounds, final=dict(
        g=dict(g9), verdict=verdict, five_passed=ft['passed'],
        wf_pos=wf_pos_final, oos_pass=bool(oos_ok), stress_pass=bool(stress_ok),
        base=slim(base), opt=slim(c9),
        dNetR=round(c9['net'] - base['net'], 3)))


def main():
    t0 = time.time()
    live = W.load_live()
    results, passed = {}, []
    print("=== 全面深度优化 R0~R10 (fresh 数据, 11品种) ===", flush=True)
    for sym in W.SYMS:
        p = os.path.join(W.DATA, "%s_M15.csv" % sym)
        if not os.path.exists(p):
            print("  %-8s 无M15, 跳过" % sym, flush=True); continue

        def log(m):
            print("  %-8s %s" % (sym, m), flush=True)
        try:
            r = optimize_symbol(sym, log)
        except Exception as ex:
            print("  %-8s FAILED %r" % (sym, ex), flush=True)
            results[sym] = dict(sym=sym, error=repr(ex)); continue
        results[sym] = r
        if r['final']['verdict'] == 'OPTIMIZED_PASS':
            passed.append(sym)
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(dict(ts=time.strftime("%F %T"), data_source=W.DATA,
                           verdicts={s: results[s].get('final', {}).get('verdict', 'ERROR')
                                     for s in results},
                           passed=passed, symbols=results),
                      f, ensure_ascii=False, indent=2, default=str)
    print("=== 完成 %.0fs | PASS=%s | -> %s ===" %
          (time.time() - t0, passed or "无", OUT), flush=True)


if __name__ == "__main__":
    main()
