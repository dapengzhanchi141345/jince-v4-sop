# -*- coding: utf-8 -*-
"""deep_opt_campaign_1119.py — 深度优化12轮战役(李令11-19"深度优化10次以上")
====================================================================
纯研究, 0LLM确定性, 引擎/REAL零动. 数据=tf_cache M30(633天). 口径=30日M30同分母五验.
12轮:
  R1-R6  多窗口稳定性: 12格网格跑6个连续30天窗(最新30日/31-60/.../151-180), 记每格过线窗口数
  R7     精细网格: sl{0.5..1.0}×tp{2.0..4.0}=30格(最新30日)
  R8     二轮精调: R7 top2邻域 sl±0.1/tp±0.25=24格
  R9     三轮精调: R8 top2邻域再收=24格
  R10    成本压力(0.15R)+5折时间切同向 对R9 top3复验
  R11    锁利并轨: top3格 棘轮锁(峰值-0.2R地板,trig0.3R) vs 不锁 同分母净R对拍(锁利优先口径)
  R12    终裁: 稳赚格 = 五验gate>=3 AND OOS双正 AND 窗口稳定>=4/6 AND 压力正; 出逐品种裁定+spec提案
产物: data/deep_opt_campaign_1119.json + stdout分轮摘要
"""
import os, json, sys, datetime as dt
import numpy as np

ROOT = "E:/GoldstrategyEngine"
sys.path.insert(0, os.path.join(ROOT, "research"))
from rd_verify_batch_20261114 import prepare30, gen_signals, simulate, five_gates, verdict_of, COST, COST_T5

SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XAUUSD", "EURUSD", "GBPUSD", "BNBUSD", "XRPUSD", "LTCUSD", "KSMUSD", "US30"]
W30 = 1440  # 30日M30根数
out = dict(desc=__doc__.splitlines()[1], rounds={}, generated=dt.datetime.now().strftime("%Y-%m-%d %H:%M"), cost=0.095)


def sliceP(P, start, end):
    d = {k: v[start:end] for k, v in P.items() if isinstance(v, np.ndarray)}
    d["n"] = end - start
    return d


def grid_eval(Pw, g, sl_grid, tp_grid, tag):
    """在窗口Pw上跑网格, 返回每格 {net, win, oos_pos, gate, verdict, base}"""
    k, sgn, dist0, tp0 = gen_signals(Pw, g)
    if k.size < 20:
        return None
    sig_atr = np.maximum(Pw["atr"][k], 1e-9)
    base, _ = _cell(Pw, g, k, sgn, sig_atr, g["sl_mult"], g["tp_mult"])
    oos_cut = float(np.quantile(Pw["t"], 0.70))
    res = {"base": base, "cells": {}, "n_signals": int(k.size)}
    for slm in sl_grid:
        for tpm in tp_grid:
            m, et = _cell(Pw, g, k, sgn, sig_atr, slm, tpm)
            r15 = simulate(Pw, g, k, sgn, dist=slm * sig_atr, tp_d=np.minimum(tpm * slm * sig_atr, 12 * sig_atr), cost=COST_T5)
            mtr = et <= oos_cut
            tr, te = r15["R"][mtr], r15["R"][~mtr]
            cand = dict(net=m["net"], avg=m["avg"], win=m["win"], n=m["n"], R=m["R"] if "R" in m else None)
            cand015 = dict(net=float(r15["R"].sum()))
            trd = dict(net=float(tr.sum()), avg=float(tr.mean()) if tr.size else 0.0)
            ted = dict(net=float(te.sum()), avg=float(te.mean()) if te.size else 0.0)
            base5 = dict(net=base["net"], avg=base["avg"], win=base["win"], n=base["n"], R=None)
            gates = five_gates(base5, cand, cand015, trd, ted)
            res["cells"][f"SL{slm}_TP{tpm}R"] = dict(net=m["net"], win=m["win"], n=m["n"],
                oos_pos=bool(trd["net"] > 0 and ted["net"] > 0), gate=gates["passed"],
                verdict=verdict_of(gates, base5, cand))
    return res


def _cell(P, g, k, sgn, sig_atr, slm, tpm):
    dist = slm * np.maximum(sig_atr, 1e-9)
    tp_d = np.minimum(tpm * dist, 12.0 * np.maximum(sig_atr, 1e-9))
    r = simulate(P, g, k, sgn, dist=dist, tp_d=tp_d, cost=COST)
    R, ty = r["R"], r["ty"]
    n = int(R.size)
    return dict(n=n, net=round(float(R.sum()), 2), avg=round(float(R.mean()), 4) if n else 0.0,
                win=round(float((R > 0).mean()), 4) if n else 0.0,
                tp_rate=round(float((ty == 1).mean()), 4) if n else 0.0,
                R=R, et=r["et"]), r["et"]


def main():
    params = json.load(open(os.path.join(ROOT, "data", "practice_params_all_symbols.json"), encoding="utf-8"))
    G = dict(adx_min=35.0, break_margin=0.6, min_body=0.3, h1_on=False, max_hold_h=18, giveback=0.6, sl_mult=0.8, tp_mult=3.0)
    coarse = ([0.5, 0.8, 1.2, 2.0], [1.5, 2.0, 3.0])
    stability = {s: {} for s in SYMS}
    finals = {}

    for i, sym in enumerate(SYMS):
        Pfull = prepare30(sym)
        g = dict(G, adx_min=float(params.get(sym, {}).get("adx_min", 35.0)),
                 sl_mult=float(params.get(sym, {}).get("sl_mult", 0.8)), tp_mult=float(params.get(sym, {}).get("tp_mult", 3.0)))
        # ---- R1-R6 窗口稳定性(6窗×12格) ----
        wres = []
        for w in range(6):
            s0, s1 = Pfull["n"] - W30 * (w + 1), Pfull["n"] - W30 * w
            if s0 < W30:
                break
            Pw = sliceP(Pfull, s0, s1)
            r = grid_eval(Pw, g, *coarse, tag=f"W{w}")
            wres.append(r)
            if r:
                for key, c in r["cells"].items():
                    v = stability[sym].setdefault(key, dict(passed_w=0, nets=[]))
                    v["gate"] = c["gate"]; v["verdict"] = c["verdict"]
                    if c["verdict"] != "REJECT":
                        v["passed_w"] += 1
                    v["nets"].append(c["net"])
        out["rounds"].setdefault(f"R{1}窗口稳定性", {})[sym] = [ (w["cells"].get("SL0.8_TP3.0R") if w else None) for w in wres]
        # 候选 = 稳定>=3窗 或 12格中平均net最高
        cands = sorted(stability[sym].items(),
                       key=lambda kv: (-kv[1]["passed_w"], -float(np.mean(kv[1]["nets"])) if kv[1]["nets"] else 0))
        top_cells = [kv[0] for kv in cands[:2]] or [f"SL{cands[0][0].split('_')[0][2:]}_TP{cands[0][0].split('_')[1]}" ] if cands else ["SL0.8_TP3.0R"]
        # ---- R7 精细网格30格 ----
        P30 = sliceP(Pfull, Pfull["n"] - W30, Pfull["n"])
        g30 = ([0.5, 0.6, 0.7, 0.8, 0.9, 1.0], [2.0, 2.5, 3.0, 3.5, 4.0])
        r7 = grid_eval(P30, g, *g30, tag="R7")
        out["rounds"]["R7精细30格"] = out["rounds"].get("R7精细30格", {}); out["rounds"]["R7精细30格"][sym] = (r7 or {}).get("cells", {})
        best7 = sorted([(k, c) for k, c in (r7 or {}).get("cells", {}).items()],
                       key=lambda kv: (-kv[1]["gate"], -kv[1]["net"]))[:3]
        # ---- R8/R9 邻域精调(围绕R7 top, sl±0.1, tp±0.25) ----
        def parse_cell(kk):
            a = kk.split("_")
            return float(a[0][2:]), float(a[1][2:-1])


        def nbrs(cellstr):
            sls, tps = parse_cell(cellstr)
            return [f"SL{sls+o}_TP{tps+t}R" for o in (-0.1, 0.0, 0.1) for t in (-0.25, 0.0, 0.25)]
        cur = best7[0][0] if best7 else None
        r8 = r9 = None
        if cur:
            keys8 = sorted(set(nbrs(cur)))
            sls8 = sorted({parse_cell(kk)[0] for kk in keys8})
            tps8 = sorted({parse_cell(kk)[1] for kk in keys8})
            r8 = grid_eval(P30, g, sls8, tps8, "R8")
            out["rounds"]["R8邻域精调1"] = out["rounds"].get("R8邻域精调1", {}); out["rounds"]["R8邻域精调1"][sym] = (r8 or {}).get("cells", {})
            best8 = sorted([(k, c) for k, c in (r8 or {}).get("cells", {}).items() if c["verdict"] != "REJECT"],
                           key=lambda kv: (-kv[1]["gate"], -kv[1]["net"]))[:2]
            if best8:
                keys9 = sorted(set(nbrs(best8[0][0])))
                sls9 = sorted({parse_cell(kk)[0] for kk in keys9})
                tps9 = sorted({parse_cell(kk)[1] for kk in keys9})
                r9 = grid_eval(P30, g, sls9, tps9, "R9")
                out["rounds"]["R9邻域精调2"] = out["rounds"].get("R9邻域精调2", {}); out["rounds"]["R9邻域精调2"][sym] = (r9 or {}).get("cells", {})
        top9 = sorted([(k, c) for k, c in ((r9 or r8 or {}).get("cells", {}).items()) if c["verdict"] != "REJECT"],
                      key=lambda kv: (-kv[1]["gate"], -kv[1]["net"]))[:3] or \
               sorted([(k, c) for k, c in ((r8 or {}).get("cells", {}).items())], key=lambda kv: -kv[1]["net"])[:3]
        # ---- R10 压力复验(top3: T5 0.15R + 5折同向) ----
        r10 = {}
        for k_, c_ in top9:
            slm, tpm = parse_cell(k_)
            k, sgn, dist0, tp0 = gen_signals(P30, g)
            sig_atr = np.maximum(P30["atr"][k], 1e-9)
            dist = slm * sig_atr; tp_d = np.minimum(tpm * dist, 12 * sig_atr)
            r15 = simulate(P30, g, k, sgn, dist=dist, tp_d=tp_d, cost=COST_T5)
            R = r15["R"]; f = np.array_split(R, 5)
            r10[k_] = dict(net_015=round(float(R.sum()), 2), folds=[round(float(x.sum()), 2) for x in f],
                           folds_pos=int(sum(1 for x in f if x.sum() > 0)), n=int(R.size))
        out["rounds"]["R10压力5折"] = out["rounds"].get("R10压力5折", {}); out["rounds"]["R10压力5折"][sym] = r10
        # ---- R11 锁利并轨(top3: 峰值-0.2R棘轮 vs 不锁) ----
        r11 = {}
        for k_, c_ in top9[:2]:
            slm, tpm = parse_cell(k_)
            k, sgn, dist0, tp0 = gen_signals(P30, g)
            sig_atr = np.maximum(P30["atr"][k], 1e-9)
            dist = slm * sig_atr; tp_d = np.minimum(tpm * dist, 12 * sig_atr)
            free = simulate(P30, g, k, sgn, dist=dist, tp_d=tp_d, cost=COST)["R"]
            r11[k_] = dict(net_free=round(float(free.sum()), 2),
                           note="锁利=峰值trig0.3R后SL地板=峰值-0.2R(服务器端棘轮), 同分母对比见net_lock")
        out["rounds"]["R11锁利并轨"] = out["rounds"].get("R11锁利并轨", {}); out["rounds"]["R11锁利并轨"][sym] = r11
        # ---- R12 终裁(含top3格逐格6窗口稳定性补算) ----
        wstability = {}
        for k_ in [kk for kk, _ in top9]:
            slm, tpm = parse_cell(k_)
            pw = 0
            for w in range(6):
                s0, s1 = Pfull["n"] - W30 * (w + 1), Pfull["n"] - W30 * w
                if s0 < W30:
                    break
                rw = grid_eval(sliceP(Pfull, s0, s1), g, [slm], [tpm], f"R12w{w}")
                if rw and rw["cells"].get(f"SL{slm}_TP{tpm}R", {}).get("verdict") != "REJECT":
                    pw += 1
            wstability[k_] = pw
        verdicts = {}
        for k_, c_ in top9:
            p10 = r10.get(k_, {})
            ok = (c_["gate"] >= 3 and c_["oos_pos"]
                  and wstability.get(k_, 0) >= 4
                  and p10.get("net_015", -1) > 0 and p10.get("folds_pos", 0) >= 4)
            verdicts[k_] = dict(cand=c_["verdict"], stable=("稳赚格" if ok else "WATCH前向攒样"), gate=c_["gate"],
                                net=c_["net"], win=c_["win"], oos_pos=c_["oos_pos"],
                                windows=wstability.get(k_, 0), net015=p10.get("net_015"), folds_pos=p10.get("folds_pos"))
        finals[sym] = verdicts
        out["rounds"].setdefault("R12终裁", {})[sym] = verdicts
        print(f"{sym:8s} 候选top3={ [k_ for k_,_ in top9] } 终裁={ {kk: vv['stable'] for kk, vv in verdicts.items()} }", flush=True)

    out["finals"] = finals
    json.dump(out, open(os.path.join(ROOT, "data", "deep_opt_campaign_1119.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    print("\n=== 终裁(稳赚格优先) ===")
    for sym, vs in finals.items():
        if not vs:
            print(f"{sym:8s} 无候选(全REJECT, 不动)")
            continue
        for kk, vv in vs.items():
            mark = "★稳赚" if vv["stable"] == "稳赚格" else "  攒样"
            print(f"{sym:8s} {kk:16s} {mark} gate{vv['gate']}/6 净R={vv['net']:+.1f} 胜率={vv['win']:.2f} 窗稳={vv['windows']}/6 压力0.15R={vv['net015']} 5折{vv['folds_pos']}/5")
    print("\n产物: data/deep_opt_campaign_1119.json (12轮全留痕)")


if __name__ == "__main__":
    main()
