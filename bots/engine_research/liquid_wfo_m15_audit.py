#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
liquid_wfo_m15_audit.py —— 对 v2 优化候选做反过拟合硬复核 (审查官口径)
=====================================================================
复核 2 个疑点:
  A) ADX_MIN=20 是网格边界/悬崖 -> 扩域到 [10..50] 找真甜区
  B) 所有品种最优 sl_mult=0.6(下界) -> R 以 SL 距离归一化, SL 越窄 R 越大,
     净R 提升可能只是"归一化假象"。用【固定 1.0ATR 分母】重算绝对收益:
        R_abs = (R_rel + cost) * sl_mult - cost
     只有 R_abs 也改善, 才是真的更赚钱。
另做: sl_mult 扩域 [0.4..1.2] 单参数扫描 + 三窗口稳健 + 成本 0.05/0.10 双档。
纯研究, 不改 live。
"""
import os, json, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import liquid_wfo_m15_v2 as W

OUT = W.OUT
COST = W.COST_R


def eval_abs(P, g, cost=COST):
    """返回相对R与绝对R(固定1ATR分母)两套指标。"""
    k, s = W.gen_signals(P, g)
    R, et, ty = W.simulate(P, g, k, s, cost=cost)
    if len(R) == 0:
        return dict(n=0, net_rel=0., avg_rel=0., net_abs=0., avg_abs=0., win=0., R=R)
    slm = min(g['sl_mult'], W.REAL_SL_CAP)
    # 去掉成本还原成纯价格R, 再按固定1ATR分母缩放, 最后扣固定成本
    R_abs = (R + cost) * slm - cost
    return dict(n=len(R), net_rel=float(R.sum()), avg_rel=float(R.mean()),
                net_abs=float(R_abs.sum()), avg_abs=float(R_abs.mean()),
                win=float((R > 0).mean()), R=R, R_abs=R_abs)


def adx_sweep(P, g, vals):
    out = []
    for v in vals:
        q = dict(g); q['adx_min'] = float(v)
        e = eval_abs(P, q)
        out.append((float(v), e['n'], round(e['avg_rel'], 5), round(e['avg_abs'], 5),
                    round(e['net_abs'], 2)))
    return out


def sl_sweep(P, g, vals):
    out = []
    for v in vals:
        q = dict(g); q['sl_mult'] = float(v)
        e = eval_abs(P, q)
        out.append((float(v), e['n'], round(e['avg_rel'], 5), round(e['avg_abs'], 5),
                    round(e['net_abs'], 2)))
    return out


def main():
    res = json.load(open(os.path.join(OUT, "results.json"), encoding="utf-8"))
    live = W.load_live()
    audit = {}
    print("=== 反过拟合硬复核 (固定1ATR绝对收益口径) ===", flush=True)
    for sym in W.SYMS:
        if sym not in res:
            continue
        r = res[sym]
        if r['bars'] < 10000:
            audit[sym] = dict(verdict="M15样本不足(n<50或bars<10000), 不作候选",
                              bars=r['bars'], base_n=r['base']['n'])
            print("  %-8s M15样本不足(%d根/%d笔) -> 不作候选" %
                  (sym, r['bars'], r['base']['n']), flush=True)
            continue
        P = W.prepare(sym)
        B = r['base']['g']; G = r['opt']['g']
        b = eval_abs(P, B); o = eval_abs(P, G)
        # 基线/最优在绝对口径下的对比
        d_net_abs = o['net_abs'] - b['net_abs']
        d_avg_abs = o['avg_abs'] - b['avg_abs']
        # 甜区: ADX 扩域
        adx_vals = [10, 15, 20, 25, 30, 35, 40, 45, 50]
        sw = adx_sweep(P, G, adx_vals)
        # sl_mult 扩域(在最优g上)
        sl_vals = [0.4, 0.5, 0.6, 0.8, 1.0, 1.2]
        swsl = sl_sweep(P, G, sl_vals)
        # 真甜区判定: 最优在扩域内部且邻域>=80%峰值(用绝对收益)
        absv = [x[3] for x in sw]
        bi = int(np.argmax(absv))
        sweet = (0 < bi < len(absv)-1) and min(absv[max(0,bi-1):bi+2]) >= absv[bi]*0.80
        # 三窗(绝对R)
        wb = np.array_split(b['R_abs'], 3) if b['n'] >= 3 else [b['R_abs']]*3
        wo = np.array_split(o['R_abs'], 3) if o['n'] >= 3 else [o['R_abs']]*3
        win3_improve = all(wo[i].sum() > wb[i].sum() for i in range(3))
        # 成本压力(0.10R)绝对口径
        o_stress = eval_abs(P, G, cost=W.COST_R_STRESS)
        b_stress = eval_abs(P, B, cost=W.COST_R_STRESS)
        stress_ok = (o_stress['avg_abs'] > b_stress['avg_abs']) and o_stress['avg_abs'] > 0

        verdict = ("PASS_ABS" if (d_net_abs > 0 and d_avg_abs > 0 and sweet and
                                  win3_improve and stress_ok and o['n'] >= 100)
                   else ("PARTIAL" if (d_net_abs > 0 and d_avg_abs > 0) else "REJECT_ABS"))
        audit[sym] = dict(
            bars=r['bars'],
            base=dict(g=B, n=b['n'], net_rel=round(b['net_rel'],2), avg_rel=round(b['avg_rel'],5),
                      net_abs=round(b['net_abs'],2), avg_abs=round(b['avg_abs'],5)),
            opt=dict(g=G, n=o['n'], net_rel=round(o['net_rel'],2), avg_rel=round(o['avg_rel'],5),
                     net_abs=round(o['net_abs'],2), avg_abs=round(o['avg_abs'],5),
                     win=round(o['win'],4)),
            d_net_abs=round(d_net_abs,2), d_avg_abs=round(d_avg_abs,5),
            adx_sweep_abs=sw, sl_sweep_abs=swsl,
            sweet_spot=bool(sweet), win3_improve=bool(win3_improve),
            stress_avg_abs=round(o_stress['avg_abs'],5), stress_ok=bool(stress_ok),
            verdict=verdict,
        )
        print("  %-8s Δnet_abs=%+.2f Δavg_abs=%+.4f 甜区=%s 三窗=%s 压力=%s n=%d -> %s" %
              (sym, d_net_abs, d_avg_abs, sweet, win3_improve, stress_ok, o['n'], verdict),
              flush=True)
        print("     ADX扩域(绝对avgR): %s" % [x[3] for x in sw], flush=True)
        print("     SL扩域(绝对avgR):  %s" % [x[3] for x in swsl], flush=True)

    with open(os.path.join(OUT, "audit.json"), "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)
    print("-> %s" % os.path.join(OUT, "audit.json"), flush=True)


if __name__ == "__main__":
    main()
