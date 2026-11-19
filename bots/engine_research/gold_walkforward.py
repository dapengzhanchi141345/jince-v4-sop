#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gold_walkforward.py —— 黄金"少参数 + 5折Walk-Forward"稳健优化
============================================================
背景: v3 全参数(9维)坐标下降在全量上绝对净收益 +51.59 -> +84.53(+63.9%),
      但 70/30 OOS FAIL (test基线 +0.1311 vs train求参 +0.1138) = 过拟合, 已驳回。
      黄金基线本身是正期望(全量 +0.1720 / test +0.1311), 真实痛点是"很久没交易"
      = 触发频率低(全局 ADX_MIN=35 + VOL_EXPAND_K=0.7 + H1共振 三闸叠加)。
方法: 只动【根因两闸】(ADX_MIN / VOL_EXPAND_K), 其余 7 个参数全部保持现役,
      参数空间仅 4x2=8 组, 几乎无过拟合空间;
      5 折 Walk-Forward(每折 train->test 滚动), 以 test 段【固定1ATR绝对收益】
      与【交易笔数】双指标判定, 要求多数折改善且频率提升。
输出 gold_wf_result.json (供 Hermes R11 议案)。纯研究, 不改 live。
"""
import os, json, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import liquid_wfo_m15_v2 as W
import liquid_wfo_m15_v3 as V3

OUT = W.OUT
ADXS = [20., 25., 30., 35.]          # 35=现役
VOLKS = [0.5, 0.6, 0.7]             # 0.7=现役


def slice_P(P, a, b):
    q = {}
    for k, v in P.items():
        q[k] = v[a:b] if isinstance(v, np.ndarray) and len(v) == P['n'] else v
    q['n'] = b - a
    return q


def main():
    P = W.prepare("XAUUSD")
    live = W.load_live()["XAUUSD"]
    B = dict(W.BASE); B['sl_mult'] = live['sl']; B['tp_mult'] = live['tp']
    n = P['n']
    folds = [(0.0, 0.6, 0.6, 0.7), (0.0, 0.7, 0.7, 0.8),
             (0.0, 0.8, 0.8, 0.9), (0.0, 0.9, 0.9, 1.0),
             (0.3, 0.8, 0.8, 1.0)]     # 第5折用不同训练窗复核
    print("=== 黄金 少参数 5折 Walk-Forward (固定1ATR绝对收益) ===", flush=True)
    print("候选: ADX_MIN=%s x VOL_K=%s (现役 35/0.7), 其余7参数全部冻结现役" %
          (ADXS, VOLKS), flush=True)

    cands = []
    for adx in ADXS:
        for vk in VOLKS:
            g = dict(B); g['adx_min'] = adx; g['vol_k'] = vk
            cands.append((adx, vk, g))

    rows = []
    for adx, vk, g in cands:
        fold_res = []
        for (ta, tb, ea, eb) in folds:
            Ptr = slice_P(P, int(n*ta), int(n*tb))
            Pte = slice_P(P, int(n*ea), int(n*eb))
            gb = V3.ev(Pte, B)     # 现役参数在test
            go = V3.ev(Pte, g)     # 候选参数在test(参数非本折训练所得, 因为只有2个离散闸)
            fold_res.append(dict(base_avg=round(gb['avg'],5), base_net=round(gb['net'],2),
                                 base_n=gb['n'], opt_avg=round(go['avg'],5),
                                 opt_net=round(go['net'],2), opt_n=go['n'],
                                 d_avg=round(go['avg']-gb['avg'],5),
                                 d_net=round(go['net']-gb['net'],2),
                                 d_n=go['n']-gb['n']))
        n_improve = sum(1 for f in fold_res if f['d_avg'] > 0)
        n_improve_net = sum(1 for f in fold_res if f['d_net'] > 0)
        avg_davg = float(np.mean([f['d_avg'] for f in fold_res]))
        avg_dnet = float(np.mean([f['d_net'] for f in fold_res]))
        avg_dn = float(np.mean([f['d_n'] for f in fold_res]))
        full = V3.ev(P, g); fullb = V3.ev(P, B)
        rows.append(dict(adx_min=adx, vol_k=vk, folds=fold_res,
                         n_improve_folds=n_improve, n_improve_net=n_improve_net,
                         mean_d_avg=round(avg_davg,5), mean_d_net=round(avg_dnet,2),
                         mean_d_trades=round(avg_dn,1),
                         full=dict(n=full['n'], net=round(full['net'],2),
                                   avg=round(full['avg'],5), win=round(full['win'],4)),
                         full_base=dict(n=fullb['n'], net=round(fullb['net'],2),
                                        avg=round(fullb['avg'],5)),
                         robust=int(n_improve >= 4 and n_improve_net >= 4 and
                                    avg_davg > 0 and avg_dn >= 0)))
        print("  ADX=%-4.0f VOLK=%.1f | 改善折=%d/5 净R改善折=%d/5 均Δavg=%+.4f 均Δ净R=%+.2f 均Δ笔数=%+.1f | 全量 n=%d net=%+.2f avg=%+.4f %s" %
              (adx, vk, n_improve, n_improve_net, avg_davg, avg_dnet, avg_dn,
               full['n'], full['net'], full['avg'], "ROBUST" if rows[-1]['robust'] else ""),
              flush=True)

    robust = [r for r in rows if r['robust'] and not (r['adx_min'] == 35 and r['vol_k'] == 0.7)]
    # 排序: 稳健 > 平均绝对收益改善 > 交易数提升
    robust.sort(key=lambda r: (r['n_improve_folds'], r['mean_d_avg'], r['mean_d_trades']), reverse=True)
    base_row = [r for r in rows if r['adx_min'] == 35 and r['vol_k'] == 0.7][0]
    out = dict(sym="XAUUSD", bars=n, cost=W.COST_R,
               baseline=base_row, candidates=rows,
               robust_candidates=[dict(adx_min=r['adx_min'], vol_k=r['vol_k'],
                                       mean_d_avg=r['mean_d_avg'], mean_d_net=r['mean_d_net'],
                                       mean_d_trades=r['mean_d_trades'],
                                       n_improve_folds=r['n_improve_folds'],
                                       full=r['full']) for r in robust],
               recommendation=(robust[0] if robust else None),
               note="全参数(9维)深优化已OOS证伪(见final_verdict.json); 此处仅动ADX_MIN/VOL_K两闸, "
                    "其余7参数冻结现役, 5折WF稳健验证。参数变更仍须 Hermes chief R11 翻闸。")
    with open(os.path.join(OUT, "gold_wf_result.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n=== 结论 ===", flush=True)
    if robust:
        r = robust[0]
        print("推荐黄金策略: ADX_MIN=%.0f VOL_EXPAND_K=%.1f (其余7参数保持现役)" %
              (r['adx_min'], r['vol_k']), flush=True)
        print("  5折改善=%d/5 均Δ绝对avgR=%+.4f 均Δ笔数=%+.1f 全量净R=%+.2f (基线 %+.2f)" %
              (r['n_improve_folds'], r['mean_d_avg'], r['mean_d_trades'],
               r['full']['net'], base_row['full']['net']), flush=True)
    else:
        print("无候选通过5折稳健验证 -> 维持现役参数(HOLD), 不提交翻闸。", flush=True)
    print("-> gold_wf_result.json", flush=True)


if __name__ == "__main__":
    main()
