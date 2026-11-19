# -*- coding: utf-8 -*-
"""liq_universe_deep_opt_20261118.py — 高流动性宇宙全面深度优化 (李彦明11-18令'全面深度优化高流动性品种的策略')
====================================================================
宇宙(13) = 11-13 R12 高流动性12 (AUD/BTC/ETH/EUR/GBPJPY/GBP/JPN225/US30/USDJPY/XAG/XAU/XTI) + SOL(spec v4 赚钱格币)
数据 = tf_cache M30 30000根(数据官刷新 + 11-18 主bot补拉6只新npz, 末端11-18 14:30 server钟, 全 <48h)
协议 = 同 11-18 00:58 all_sym_deep 批(同分母): gen_signals base(现行参数) 事件集, 只换距离/离场/时段
  维度A(主): SL∈{0.5,0.8,1.2,2.0}×ATR30 × TP∈{1.5,2.0,3.0}R(封顶12ATR) = 12格/品种
  维度B(离场层, 仅顶格): giveback∈{0.4,0.8}(0.6=base) 顶1格
  维度C(时段窗, 仅顶格): 全市场重叠窗 13-17(存储t轴小时∈[13,17)) 顶1格
五验 T1-T5 + ⑥净期望线1.0, 扣0.095R主/T5档0.15R, OOS70/30双段, winsor[-3,8], 逐品种裁定禁跨品种平均
裁定: APPROVE=5验≥4/6且OOS双正净>0 | WATCH=未达APPROVE但≥3/6 | REJECT=其余; ⑥<1.0 一律不放大
红线: 纯研究, 引擎/REAL/参数表/挂单零动. 产物= data/rd_verify_batch_liq13_deep_20261118.json
"""
import os, json, sys, datetime as dt
import numpy as np

ROOT = "E:/GoldstrategyEngine"
sys.path.insert(0, os.path.join(ROOT, "research"))
from rd_verify_batch_20261114 import (prepare30, gen_signals, simulate, five_gates,
                                      verdict_of, COST, COST_T5, load_npz)

LIQ13 = ["AUDUSD", "BTCUSD", "ETHUSD", "EURUSD", "GBPJPY", "GBPUSD", "JPN225",
         "US30", "USDJPY", "XAGUSD", "XAUUSD", "XTIUSD", "SOLUSD"]
SL_GRID = [0.5, 0.8, 1.2, 2.0]
TP_GRID = [1.5, 2.0, 3.0]
GB_GRID = [0.4, 0.8]
SESSION_HOURS = (13, 17)  # 存储t轴小时区间 [13,17) = 全市场重叠窗(11-14窗口表13-16UTC口径, 末端含16时整点bar归入13-17)
OUT = os.path.join(ROOT, "data", "rd_verify_batch_liq13_deep_20261118.json")


def base_cell(P, g, k, sgn, sig_atr, slm, tpm):
    dist = slm * np.maximum(sig_atr, 1e-9)
    tp_d = np.minimum(tpm * dist, 12.0 * np.maximum(sig_atr, 1e-9))
    res = simulate(P, g, k, sgn, dist=dist, tp_d=tp_d, cost=COST)
    R, ty = res["R"], res["ty"]
    n = int(R.size)
    return dict(n=n, net=round(float(R.sum()), 2),
                avg=round(float(R.mean()), 4) if n else 0.0,
                win=round(float((R > 0).mean()), 4) if n else 0.0,
                tp_rate=round(float((ty == 1).mean()), 4) if n else 0.0), res["et"], res


def gates_block(m, r15, oos_cut, et, base, g, P, k, sgn, sig_dist_fn, label_extra=""):
    """同分母五验块 (复制 1117 批口径)"""
    mtr = et <= oos_cut
    tr = r15["R"][mtr]; te = r15["R"][~mtr]
    cand = dict(net=m["net"], avg=m["avg"], win=m["win"], n=m["n"], R=r15["R"])
    cand015 = dict(net=float(r15["R"].sum()))
    trd = dict(net=float(tr.sum()), avg=float(tr.mean()) if tr.size else 0.0)
    ted = dict(net=float(te.sum()), avg=float(te.mean()) if te.size else 0.0)
    gates = five_gates({kk: vv for kk, vv in base.items()}, cand, cand015, trd, ted)
    verd = verdict_of(gates, base, cand)
    return dict(net=m["net"], win=m["win"], tp_rate=m["tp_rate"], n=m["n"],
                delta=round(m["net"] - base["net"], 1),
                oos_pos=bool(trd["net"] > 0 and ted["net"] > 0),
                five_gate=gates["passed"], verdict=verd, **{**label_extra})


def main():
    params = json.load(open(os.path.join(ROOT, "data", "practice_params_all_symbols.json"), encoding="utf-8"))
    out = dict(desc="高流动性宇宙13只全面深优: SL{0.5,0.8,1.2,2.0}×TP{1.5,2,3} 12格 + 顶格giveback{0.4,0.8} + 顶格重叠窗13-17, 同分母五验",
               sl_grid=SL_GRID, tp_grid=TP_GRID, gb_grid=GB_GRID, session=SESSION_HOURS, cost=0.095,
               generated=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
               data_src="tf_cache M30x30000 (数据官刷+主bot补拉6只, 末端11-18 14:30 server钟)",
               note="裁定: 5/6=APPROVE候选 | 3-4/6=WATCH前向攒样 | <3=REJECT; ⑥线均R>=1.0才谈放大(本批大概率0过线=纪律正常); 逐品种禁跨品种平均",
               cells={})
    summary = {}
    for s in LIQ13:
        P = prepare30(s)
        p = params.get(s, {})
        g = dict(adx_min=float(p.get("adx_min", 35.0)), break_margin=0.6, min_body=0.3,
                 h1_on=False, max_hold_h=18, giveback=0.6,
                 sl_mult=float(p.get("sl_mult", 1.0)), tp_mult=float(p.get("tp_mult", 3.0)))
        k, sgn, dist0, tp0 = gen_signals(P, g)
        oos_cut = float(np.quantile(P["t"], 0.70))
        sig_atr = np.maximum(P["atr"][k], 1e-9)
        base, etb, _ = base_cell(P, g, k, sgn, sig_atr, g["sl_mult"], g["tp_mult"])
        out["cells"][s] = dict(base=base, base_sl=g["sl_mult"], base_tp=g["tp_mult"],
                               adx_min=g["adx_min"], n_sig=int(k.size), grid={}, extras={})
        print(f"{s:8s} base(SL{g['sl_mult']}/TP{g['tp_mult']}): n{base['n']} {base['net']:+8.1f} win{base['win']:.2f} | 信号{k.size}")
        best = (None, -1, None)  # (key, gates, verdict)
        cell_res = {}
        rankmap = {"APPROVE": 2, "WATCH": 1, "REJECT": 0}

        def better(b):  # b = (key, gates, verdict, net)
            if best[0] is None:
                cur = (-1, -1, -1e9)
            else:
                cur = (rankmap[best[2]], best[1], cell_res[best[0]]["net"])
            nb = (rankmap[b[2]], b[1], b[3])
            return nb > cur

        for slm in SL_GRID:
            for tpm in TP_GRID:
                key = f"SL{slm}_TP{tpm}R"
                m, et, _ = base_cell(P, g, k, sgn, sig_atr, slm, tpm)
                sig_dist = slm * sig_atr
                r15 = simulate(P, g, k, sgn, dist=sig_dist,
                               tp_d=np.minimum(tpm * sig_dist, 12 * sig_atr), cost=COST_T5)
                blk = gates_block(m, r15, oos_cut, et, base, g, P, k, sgn, None,
                                  label_extra=dict(sl=slm, tp=tpm))
                out["cells"][s]["grid"][key] = blk
                cell_res[key] = blk
                if better((key, blk["five_gate"], blk["verdict"], m["net"])):
                    best = (key, blk["five_gate"], blk["verdict"])
        def parse_top(key):
            a, b = key.split("_")
            return float(a[2:]), float(b[2:-1])

        top = best[0]
        # 维度B: 顶格 giveback 变体
        if top and top in cell_res:
            slm, tpm = parse_top(top)
            for gvb in GB_GRID:
                gg = dict(g); gg["giveback"] = gvb
                m, et, _ = base_cell(P, gg, k, sgn, sig_atr, slm, tpm)
                sig_dist = slm * sig_atr
                r15 = simulate(P, gg, k, sgn, dist=sig_dist,
                               tp_d=np.minimum(tpm * sig_dist, 12 * sig_atr), cost=COST_T5)
                blk = gates_block(m, r15, oos_cut, et, base, gg, P, k, sgn, None,
                                  label_extra=dict(sl=slm, tp=tpm, giveback=gvb, note="exit层变体"))
                out["cells"][s]["extras"][f"{top}_gb{gvb}"] = blk
        # 维度C: 顶格 重叠窗 13-17(存储t轴) 变体
        if top and top in cell_res:
            slm, tpm = parse_top(top)
            hour = (P["t"][k] // 3600) % 24
            sm = (hour >= SESSION_HOURS[0]) & (hour < SESSION_HOURS[1])
            if sm.sum() >= 30:
                k2, sgn2, a2 = k[sm], sgn[sm], sig_atr[sm]
                m, et, _ = base_cell(P, g, k2, sgn2, a2, slm, tpm)
                sig_dist = slm * a2
                r15 = simulate(P, g, k2, sgn2, dist=sig_dist,
                               tp_d=np.minimum(tpm * sig_dist, 12 * a2), cost=COST_T5)
                mtr = et <= oos_cut
                tr = r15["R"][mtr]; te = r15["R"][~mtr]
                cand = dict(net=m["net"], avg=m["avg"], win=m["win"], n=m["n"], R=r15["R"])
                trd = dict(net=float(tr.sum()), avg=float(tr.mean()) if tr.size else 0.0)
                ted = dict(net=float(te.sum()), avg=float(te.mean()) if te.size else 0.0)
                gates = five_gates({kk: vv for kk, vv in base.items()}, cand, dict(net=float(r15["R"].sum())), trd, ted)
                verd = verdict_of(gates, base, cand)
                out["cells"][s]["extras"][f"{top}_overlap13_17"] = dict(
                    net=m["net"], win=m["win"], n=m["n"], delta=round(m["net"] - base["net"], 1),
                    oos_pos=bool(trd["net"] > 0 and ted["net"] > 0), five_gate=gates["passed"],
                    verdict=verd, sl=slm, tp=tpm, note="仅13-17存储时重叠窗信号")
        out["cells"][s]["best"] = [best[0], best[1], best[2]]
        summary[s] = best[0] if best[0] else "NONE"
        print(f"   -> 最优格: {best[0]} ({best[1]}/6 {best[2]})")
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n产物:", OUT)
    print("全宇宙最优格:", json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
