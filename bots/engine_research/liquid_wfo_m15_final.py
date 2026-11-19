#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
liquid_wfo_m15_final.py —— 最终审查: 甜区修正 + 样本外(OOS)验证
================================================================
1) T4甜区修正: v3 的 adx_curve 取自坐标下降中间轮, 与最终 g 不匹配 -> 在【最终g上】
   重扫 ADX 曲线, apples-to-apples 判定甜区。
2) 过拟合屏(OOS): 全量 M15 按时间切 train70% / test30%,
   仅在 train 上坐标下降求参 -> 在 test 上评估, 对比"基线参数在test"的表现。
   OOS 仍改善 = 真 edge; OOS 崩 = 过拟合, 驳回。
3) 黄金额外做 ADX 精细扫描 [12..26 步长2] 找真甜区。
输出 final_verdict.json + 供 Hermes 的候选清单。纯研究, 不改 live。
"""
import os, json, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import liquid_wfo_m15_v2 as W
import liquid_wfo_m15_v3 as V3

OUT = W.OUT
LONG_SYMS = ["XAUUSD", "EURUSD", "GBPUSD", "BTCUSD", "ETHUSD"]


def slice_P(P, a, b):
    """按 bar 区间切片(预计算指标已对齐, 直接切)。"""
    q = {}
    for k, v in P.items():
        if isinstance(v, np.ndarray) and len(v) == P['n']:
            q[k] = v[a:b]
        else:
            q[k] = v
    q['n'] = b - a
    return q


def sweep_adx(P, g, vals):
    out = []
    for v in vals:
        q = dict(g); q['adx_min'] = float(v)
        e = V3.ev(P, q)
        out.append([float(v), e['n'], round(e['avg'], 5), round(e['net'], 2)])
    return out


def five_final(b, o, curve):
    if b['n'] == 0 or o['n'] == 0:
        return dict(T1=0,T2=0,T3=0,T4=0,T5=0,passed=0)
    T1 = int((o['avg'] > b['avg']) and (o['net'] > b['net']))
    T2 = int(o['win'] >= b['win'] - 0.02)
    T3 = int(o['seg8'] >= 6)
    T4 = 0
    if curve and len(curve) >= 3:
        v = [x[2] for x in curve]; mx = max(v); bi = v.index(mx)
        T4 = int((0 < bi < len(v)-1) and min(v[max(0,bi-1):bi+2]) >= mx*0.80)
    wb = np.array_split(b['R'], 3) if b['n'] >= 3 else [b['R']]*3
    wo = np.array_split(o['R'], 3) if o['n'] >= 3 else [o['R']]*3
    T5 = int(all(wo[i].sum() > wb[i].sum() for i in range(3)))
    return dict(T1=T1,T2=T2,T3=T3,T4=T4,T5=T5,passed=T1+T2+T3+T4+T5)


def main():
    v3 = json.load(open(os.path.join(OUT, "results_v3.json"), encoding="utf-8"))
    live = W.load_live()
    final = {}
    t0 = time.time()
    print("=== 最终审查: 甜区修正 + 70/30 OOS 过拟合屏 ===", flush=True)
    for sym in LONG_SYMS:
        r = v3.get(sym, {})
        if not r or r.get('verdict') == 'INSUFFICIENT_M15':
            continue
        P = W.prepare(sym)
        B = r['base']['g']; G = r['opt']['g']
        b = V3.ev(P, B); o = V3.ev(P, G)
        # 1) 在最终g上重扫ADX甜区
        curve = sweep_adx(P, G, [10,15,20,25,30,35,40,45,50])
        ft = five_final(b, o, curve)
        # 2) OOS: 70/30 时间切分, train上优化, test上验证
        cut = int(P['n'] * 0.70)
        Ptr, Pte = slice_P(P, 0, cut), slice_P(P, cut, P['n'])
        g_oos, e_tr, _ = V3.coord(Ptr, B, rounds=2, n_req=80)
        base_te = V3.ev(Pte, B)
        opt_tr_te = V3.ev(Pte, g_oos)          # train求参 -> test评估
        opt_v3_te = V3.ev(Pte, G)              # 全量求参 -> test(仅参考)
        oos_pass = int(opt_tr_te['n'] >= 30 and
                       opt_tr_te['avg'] > base_te['avg'] and
                       opt_tr_te['net'] > base_te['net'])
        print("  %-8s 五验(修正)=%d/5 %s | OOS: test基线avg=%+.4f vs train求参=%+.4f -> %s" %
              (sym, ft['passed'], "".join(str(ft[k]) for k in ("T1","T2","T3","T4","T5")),
               base_te['avg'], opt_tr_te['avg'], "PASS" if oos_pass else "FAIL"), flush=True)
        print("     ADX甜区(最终g,绝对avgR)=%s" % [x[2] for x in curve], flush=True)

        verdict = ("VALIDATED" if (ft['passed'] == 5 and oos_pass and r['stress_pass'])
                   else "PARTIAL" if (o['net'] > b['net'] and oos_pass)
                   else "HOLD_OVERFIT")
        final[sym] = dict(
            bars=P['n'], base=r['base'], opt=r['opt'],
            d_net=r['d_net'], d_avg=r['d_avg'], d_trades=r['d_trades'],
            five_corrected=ft, adx_curve_final=curve,
            stress_avg=r['stress_avg'], stress_pass=r['stress_pass'],
            oos=dict(train_bars=cut, test_bars=P['n']-cut,
                     g_from_train=g_oos,
                     test_base=dict(n=base_te['n'], avg=round(base_te['avg'],5),
                                    net=round(base_te['net'],2)),
                     test_opt=dict(n=opt_tr_te['n'], avg=round(opt_tr_te['avg'],5),
                                   net=round(opt_tr_te['net'],2)),
                     test_v3=dict(n=opt_v3_te['n'], avg=round(opt_v3_te['avg'],5),
                                  net=round(opt_v3_te['net'],2)),
                     pass_=oos_pass),
            verdict=verdict,
        )
        # 3) 黄金 ADX 精扫
        if sym == "XAUUSD":
            fine = sweep_adx(P, G, list(range(12, 27, 2)))
            final[sym]['gold_adx_fine'] = fine
            print("     黄金ADX精扫(绝对avgR)=%s" % [x[2] for x in fine], flush=True)
        final[sym]['verdict'] = verdict
        print("     -> %s" % verdict, flush=True)

    # 短样本品种如实标注
    for sym in W.SYMS:
        if sym not in final:
            final[sym] = dict(verdict="INSUFFICIENT_M15",
                              note="M15仅4000根(约42天)/成交33~40笔, 样本不足以五验, 不作候选; "
                                   "建议补M15历史或走H1降级验证")
    with open(os.path.join(OUT, "final_verdict.json"), "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print("用时 %.1fs -> final_verdict.json" % (time.time()-t0), flush=True)


if __name__ == "__main__":
    main()
