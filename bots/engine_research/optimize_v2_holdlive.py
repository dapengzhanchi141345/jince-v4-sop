#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
optimize_v2_holdlive.py —— HOLD_LIVE 品种第二轮深度优化（GBPJPY / ETHUSD），用户 20:44 令
「把剩余的也全部优化好后 发给Hermes进一步讨论 择优执行」
================================================================================
v1 失败原因诊断:
  GBPJPY  R10 five=5/5 但 WF 仅 2/5 -> 参数不稳; 根因之一: v1 候选只取 avg Top10 进 WF,
          把 WF 稳健但 avg 稍低的参数挤掉了。
  ETHUSD  R10 five=3/5 -> 五验未达 4; 同样受 Top10 截断影响。

v2 改法:
  1) 变异量加倍: 邻域 200 + 全空间 300, 变异过程中 n>=40 且 avg>基线 的独特参数全收池;
  2) 全池去重 -> avg Top30 全部进 5折WF -> wf_pos>=3 者再进 7折WF(更严格时间切分);
  3) 双折皆稳者 -> 70/30 OOS -> 成本压力 -> 五验(逐项明细落盘);
  4) 终选从全部过验证候选中按 (验证全过, 净R最高) 择优, 而非单一路径最优。
红线: 研究与候选产出, 不改引擎/实盘参数; 六参数冻结; 全落 E 盘。
输出: research/optimize_v2_holdlive_results.json
"""
import os, sys, json, time, random
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import liquid_wfo_m15_v2 as W

W.DATA = "E:/GoldstrategyEngine/data/fresh"
OUT = os.path.join(W.ROOT, "research", "optimize_v2_holdlive_results.json")
COST, STRESS = W.COST_R, W.COST_R_STRESS
NFOLD5, NFOLD7, OOS_SPLIT = 5, 7, 0.70
TARGET = ["GBPJPY", "ETHUSD"]
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


def gkey(g):
    return json.dumps(g, sort_keys=True, default=str)


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
    if random.random() < p_full:
        for key in GRID:
            q[key] = random.choice(GRID[key])
    else:
        keys = random.sample(list(GRID.keys()), random.randint(1, 3))
        for key in keys:
            q[key] = random.choice([v for v in GRID[key] if v != q[key]] + [q[key]])
    return q


def wf_pos(P, g, g0, nfold):
    N = P['n']
    edges = np.linspace(0, N, nfold + 1).astype(int)
    pos = 0
    for f in range(nfold):
        lo, hi = int(edges[f]), int(edges[f + 1])
        ef = ev(P, g, lo=lo, hi=hi); e0 = ev(P, g0, lo=lo, hi=hi)
        if ef['n'] >= 5 and ef['net'] > 0 and ef['avg'] > e0['avg']:
            pos += 1
    return pos


def five_detail(P, g0, g):
    b = ev(P, g0); o = ev(P, g)
    if b['n'] == 0 or o['n'] == 0:
        return dict(passed=0, detail={}, base_n=b['n'], opt_n=o['n'])
    ft = W.five_tests(dict(n=b['n'], avg=b['avg'], net=b['net'], win=b['win'], R=b['R']),
                      dict(n=o['n'], avg=o['avg'], net=o['net'], win=o['win'], R=o['R']),
                      curve=None)
    det = {k: (round(v, 4) if isinstance(v, float) else v)
           for k, v in ft.items() if k != 'passed'}
    return dict(passed=ft.get('passed', 0), detail=det, base_n=b['n'], opt_n=o['n'])


def optimize_symbol_v2(sym, log):
    P = W.prepare(sym)
    live = W.load_live_fresh() if hasattr(W, 'load_live_fresh') else W.load_live()
    g0 = dict(W.BASE); g0['sl_mult'] = live[sym]['sl']; g0['tp_mult'] = live[sym]['tp']
    base = ev(P, g0)
    log("R0 基线 n=%d net=%+.2f avg=%+.4f" % (base['n'], base['net'], base['avg']))
    rounds = {'R0_基线': dict(g=dict(g0), **slim(base))}

    # S1 坐标下降(进场->出场->h1+全坐标二轮)
    g1, c1 = coord_descent(P, g0, ENTER_KEYS, base)
    g2, c2 = coord_descent(P, g1, EXIT_KEYS, c1)
    g3 = dict(g2); cur = c2
    for v in GRID['h1_on']:
        if v != g3['h1_on']:
            q = dict(g3); q['h1_on'] = v
            e = ev(P, q)
            if e['n'] >= 40 and e['avg'] > cur['avg'] + 1e-6:
                g3['h1_on'] = v; cur = e
    g3, c3 = coord_descent(P, g3, CD_ORDER, cur)
    log("S1 坐标下降 avg=%+.4f" % c3['avg'])
    rounds['S1_坐标下降'] = dict(g=dict(g3), **slim(c3))

    # S2 大变异全收池(邻域200+全空间300, 保留所有 avg>基线 的独特参数)
    pool = {gkey(g3): (c3['avg'], dict(g3))}
    for tag, n_mut, p_full in (("S2a_邻域200", 200, 0.0), ("S2b_全空间300", 300, 1.0)):
        kept = 0; tried = 0
        for _ in range(n_mut):
            q = mutate(g3, p_full=p_full)
            if q == g3:
                continue
            tried += 1
            e = ev(P, q)
            if e['n'] >= 40 and e['avg'] > base['avg'] + 1e-6:
                kq = gkey(q)
                if kq not in pool:
                    pool[kq] = (e['avg'], dict(q)); kept += 1
        log("%s tried=%d 新入池=%d 池=%d" % (tag, tried, kept, len(pool)))
    cands = sorted(pool.values(), key=lambda x: -x[0])[:30]
    log("S2 全池=%d -> avg Top30 进 WF" % len(pool))

    # S3 5折WF 全候选筛选 -> wf_pos>=3 进 7折WF
    stage5 = [(a, g, wf_pos(P, g, g0, NFOLD5)) for a, g in cands]
    stable = [(a, g, p5) for a, g, p5 in stage5 if p5 >= 3]
    stable.sort(key=lambda x: (-x[2], -x[0]))
    log("S3 5折WF: %d/%d 稳(>=3/5); top: %s" % (
        len(stable), len(cands),
        ", ".join("%d/5(%.4f)" % (p5, a) for a, g, p5 in stable[:3]) or "无"))
    rounds['S3_WF5'] = [dict(g=dict(g), avg=round(a, 5), wf5=p5)
                        for a, g, p5 in stage5 if p5 >= 3][:8]
    if not stable:
        rounds['S3_WF5'] = [dict(g=dict(g), avg=round(a, 5), wf5=p5)
                            for a, g, p5 in sorted(stage5, key=lambda x: (-x[2], -x[0]))[:5]]

    stage7 = [(a, g, p5, wf_pos(P, g, g0, NFOLD7)) for a, g, p5 in stable[:12]]
    stage7.sort(key=lambda x: (-(x[2] + x[3]), -x[0]))
    dual = [(a, g, p5, p7) for a, g, p5, p7 in stage7 if p7 >= max(3, (NFOLD7 + 1) // 2)]
    log("S3 7折WF: %d 双折皆稳 -> OOS" % len(dual))
    rounds['S3_WF7'] = [dict(g=dict(g), wf5=p5, wf7=p7) for a, g, p5, p7 in stage7[:6]]
    finals = dual[:6] if dual else stage7[:3]

    # S4 OOS + 压力 + 五验, 择优
    N = P['n']; cut = int(N * OOS_SPLIT)
    e0t = ev(P, g0, lo=cut, hi=N); es0 = ev(P, g0, cost=STRESS)
    verdicts = []
    for a, g, p5, p7 in finals:
        et = ev(P, g, lo=cut, hi=N)
        oos_ok = et['n'] >= 10 and et['net'] > 0 and et['avg'] >= e0t['avg']
        es = ev(P, g, cost=STRESS)
        stress_ok = es['avg'] > 0 and es['avg'] >= es0['avg']
        ft = five_detail(P, g0, g)
        net_gain = ev(P, g)['net'] > base['net']
        ok_all = (ft['passed'] >= 4 and oos_ok and stress_ok and net_gain)
        verdicts.append(dict(g=dict(g), wf5=p5, wf7=p7, oos_pass=bool(oos_ok),
                             stress_pass=bool(stress_ok), five_passed=ft['passed'],
                             five_detail=ft['detail'], all_pass=bool(ok_all),
                             opt=slim(ev(P, g))))
        log("候选 wf5=%d wf7=%d oos=%s stress=%s five=%d/5 all=%s opt_net=%+.2f" %
            (p5, p7, oos_ok, stress_ok, ft['passed'], ok_all, verdicts[-1]['opt']['net']))
    rounds['S4_终验'] = verdicts

    winners = [v for v in verdicts if v['all_pass']]
    if winners:
        w = max(winners, key=lambda v: v['opt']['net'])
        verdict = 'OPTIMIZED_PASS'
        chosen = w
    else:
        # 无全过者: 取最接近者作 OBSERVE 候选, 参数仍不动
        w = max(verdicts, key=lambda v: (v['five_passed'], v['wf5'] + v['wf7'], v['opt']['net']))
        verdict = 'STILL_HOLD'
        chosen = w
    log("终选 %s | wf5=%d wf7=%d five=%d/5 net=%+.2f (基线 %+.2f)" %
        (verdict, chosen['wf5'], chosen['wf7'], chosen['five_passed'],
         chosen['opt']['net'], base['net']))
    return dict(sym=sym, verdict=verdict, base=slim(base),
                chosen=dict(chosen), rounds=rounds)


def main():
    t0 = time.time()
    print("=== HOLD_LIVE 二轮深度优化 v2 (%s) ===" % ",".join(TARGET), flush=True)
    results = {}
    for sym in TARGET:
        p = os.path.join(W.DATA, "%s_M15.csv" % sym)
        if not os.path.exists(p):
            print("  %-8s 无M15, 跳过" % sym, flush=True); continue

        def log(m):
            print("  %-8s %s" % (sym, m), flush=True)
        try:
            r = optimize_symbol_v2(sym, log)
        except Exception as ex:
            import traceback; traceback.print_exc()
            print("  %-8s FAILED %r" % (sym, ex), flush=True)
            results[sym] = dict(sym=sym, verdict='ERROR', error=repr(ex)); continue
        results[sym] = r
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(dict(ts=time.strftime("%F %T"), data_source=W.DATA,
                           verdicts={s: results[s].get('verdict', 'ERROR') for s in results},
                           symbols=results),
                      f, ensure_ascii=False, indent=2, default=str)
    print("=== 完成 %.0fs | verdicts=%s | -> %s ===" %
          (time.time() - t0, {s: r.get('verdict') for s, r in results.items()}, OUT), flush=True)


if __name__ == "__main__":
    main()
