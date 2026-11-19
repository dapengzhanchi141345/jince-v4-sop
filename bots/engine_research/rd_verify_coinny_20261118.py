# -*- coding: utf-8 -*-
"""rd_verify_coinny_20261118.py — 币系NY时段+位移确认五验 (rd_queue coin_ny_session_edge_20261117)
====================================================================
命题(治37亏7赢胜率16%但单笔对称-0.45/+0.43=胜率问题非量问题):
  ①币系(7大币)只在NY午后 17-21 UTC 进场 ②叠加位移确认(信号K实体>=70%区段, 砍23%假信号)
  ③对照=现行全天追突破(base). 同分母五验: 7币, 滑点0.095R(主)/0.15R(T5档), ⑥线1.0, OOS70/30双段.
数据 = tf_cache M30 x30000根 (数据官30min哨刷新, 末端11-18 14:30/15:00 server钟, 7/7 <48h 新鲜度闸PASS)
口径 = 同 11-18 00:58/21:0x 批(同分母): base=现行practice_params(币4.5/7.0, BNB/KSM 2.0/5.0)
      gen_signals 事件集, 变体只在信号K上叠加过滤, 出场参数/成本/切分全同.
时区 = 存储t轴=server墙钟epoch(冬EET UTC+2/夏EEST UTC+3): 17-21 UTC 按 DST 分段映射
      (2026-03-29 03:00 ~ 2026-10-25 04:00 存储轴=UTC+3, 其余 UTC+2), utc_hour=(t//3600-offset)%24.
      liq13 批 13-17 存储轴口径与本批 UTC 映射口径已在 meta 注明(不可直接比数).
五验 T1-T5 + ⑥, 逐品种裁定禁跨品种平均. 裁定: 5验>=4/6且OOS双正=APPROVE候选 | >=3/6=WATCH | 余REJECT;
⑥线均R>=1.0才谈放大. 红线: 纯研究, 引擎/REAL/参数表/挂单零动.
产物 = data/rd_verify_batch_coinny_20261118.json
"""
import os, json, sys, datetime as dt
import numpy as np

ROOT = "E:/GoldstrategyEngine"
sys.path.insert(0, os.path.join(ROOT, "research"))
from rd_verify_batch_20261114 import (prepare30, gen_signals, simulate, five_gates,
                                      verdict_of, COST, COST_T5)

COINS = ["BTCUSD", "ETHUSD", "SOLUSD", "BNBUSD", "XRPUSD", "LTCUSD", "KSMUSD"]
NY_HOURS = (17, 21)   # UTC 17-21 (NY午后13-17ET冬令)
DISP_FRAC = 0.7       # 位移K: 实体>=70%高低区段
OUT = os.path.join(ROOT, "data", "rd_verify_batch_coinny_20261118.json")

# DST 分段 (存储轴): EEST(UTC+3) = 2026-03-29 01:00UTC(=存储03:00) ~ 2026-10-25 01:00UTC(=存储04:00)
import calendar
T_DST_START = calendar.timegm((2026, 3, 29, 3, 0, 0))
T_DST_END = calendar.timegm((2026, 10, 25, 4, 0, 0))


def utc_hour_axis(t):
    off = np.where((t >= T_DST_START) & (t < T_DST_END), 3, 2)
    return ((t // 3600) - off) % 24


def cell(P, g, k, sgn, sig_atr, oos_cut):
    """同 liq13 批 base_cell: 主成本统计 + 0.15档 + OOS分段, 返回 (m, r15, et)"""
    dist = g["sl_mult"] * np.maximum(sig_atr, 1e-9)
    tp_d = np.minimum(g["tp_mult"] * dist, 12.0 * np.maximum(sig_atr, 1e-9))
    res = simulate(P, g, k, sgn, dist=dist, tp_d=tp_d, cost=COST)
    R, ty = res["R"], res["ty"]
    n = int(R.size)
    m = dict(n=n, net=round(float(R.sum()), 2),
             avg=round(float(R.mean()), 4) if n else 0.0,
             win=round(float((R > 0).mean()), 4) if n else 0.0,
             tp_rate=round(float((ty == 1).mean()), 4) if n else 0.0)
    r15 = simulate(P, g, k, sgn, dist=dist, tp_d=tp_d, cost=COST_T5)
    return m, r15, res


def variant_block(m, r15, oos_cut, et, base, label):
    """同 liq13 批 gates_block 口径"""
    mtr = et <= oos_cut
    tr = r15["R"][mtr]; te = r15["R"][~mtr]
    cand = dict(net=m["net"], avg=m["avg"], win=m["win"], n=m["n"], R=r15["R"])
    cand015 = dict(net=float(r15["R"].sum()))
    trd = dict(net=float(tr.sum()), avg=float(tr.mean()) if tr.size else 0.0, n=int(tr.size))
    ted = dict(net=float(te.sum()), avg=float(te.mean()) if te.size else 0.0, n=int(te.size))
    gates = five_gates({kk: vv for kk, vv in base.items()}, cand, cand015, trd, ted)
    verd = verdict_of(gates, base, cand)
    return dict(net=m["net"], win=m["win"], n=m["n"],
                delta=round(m["net"] - base["net"], 1),
                oos_pos=bool(trd["net"] > 0 and ted["net"] > 0),
                oos_train=trd, oos_test=ted,
                five_gate=gates["passed"], gates_detail=gates,
                verdict=verd, label=label)


def main():
    params = json.load(open(os.path.join(ROOT, "data/practice_params_all_symbols.json"), encoding="utf-8"))
    out = dict(desc="币系7大币 NY时段17-21UTC(DST映射) + 位移确认(实体>=70%区段) 五验 vs 现行全天追突破, 同分母",
               ny_hours_utc=NY_HOURS, disp_frac=DISP_FRAC, cost=0.095, cost_t5=0.15,
               generated=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
               data_src="tf_cache M30x30000 数据官刷新, 末端11-18 14:30/15:00 server钟(冬=UTC+2), 7/7 <48h PASS",
               tz_note="存储t轴=server墙钟epoch(冬UTC+2/夏UTC+3), 17-21UTC按DST分段映射; liq13批13-17为存储轴口径, 两批时段窗不可直接比数",
               cells={})
    summary = {}
    for s in COINS:
        P = prepare30(s)
        p = params.get(s, {})
        g = dict(adx_min=float(p.get("adx_min", 35.0)), break_margin=0.6, min_body=0.3,
                 h1_on=False, max_hold_h=18, giveback=0.6,
                 sl_mult=float(p.get("sl_mult", 4.5)), tp_mult=float(p.get("tp_mult", 7.0)))
        oos_cut = float(np.quantile(P["t"], 0.70))
        k, sgn, d0, t0 = gen_signals(P, g)
        sig_atr = np.maximum(P["atr"][k], 1e-9)
        base, _, _ = cell(P, g, k, sgn, sig_atr, oos_cut)
        hour = utc_hour_axis(P["t"][k])
        rng = P["h"][k] - P["l"][k]
        disp = P["body"][k] >= DISP_FRAC * np.maximum(rng, 1e-12)
        ny = (hour >= NY_HOURS[0]) & (hour < NY_HOURS[1])
        n_ny = int(ny.sum()); n_disp = int(disp.sum()); n_both = int((ny & disp).sum())
        out["cells"][s] = dict(sym=s, base_params=dict(sl=g["sl_mult"], tp=g["tp_mult"], adx_min=g["adx_min"]),
                               n_sig=int(k.size), base=dict(net=base["net"], n=base["n"], win=base["win"], avg=base["avg"]),
                               n_ny=n_ny, n_disp=n_disp, n_both=n_both,
                               variants={})
        print(f"{s:8s} base(SL{g['sl_mult']}/TP{g['tp_mult']}): n{base['n']:4d} {base['net']:+9.1f} win{base['win']:.2f} avg{base['avg']:.3f} | 信号{k.size} NY窗{n_ny:4d} 位移{n_disp:4d} 双{n_both:4d}", flush=True)
        for vname, mask in (("base", np.ones_like(k, dtype=bool)),
                            ("ny17_21", ny),
                            ("disp70", disp),
                            ("ny17_21_disp70", ny & disp)):
            if mask.sum() < 1 and vname != "base":
                out["cells"][s]["variants"][vname] = dict(n=0, verdict="N/A", note="无信号")
                continue
            kv, sv, av = k[mask], sgn[mask], sig_atr[mask]
            m, r15, res = cell(P, g, kv, sv, av, oos_cut)
            blk = variant_block(m, r15, oos_cut, res["et"], base, vname)
            out["cells"][s]["variants"][vname] = blk
            print(f"   {vname:14s} n{blk['n']:4d} net{blk['net']:+9.1f} d{blk['delta']:+7.1f} "
                  f"win{blk['win']:.2f} oos_pos{blk['oos_pos']} gates{blk['five_gate']}/6 {blk['verdict']}", flush=True)
        # 汇总: 最优变体(排除base), 按 gates>verdict>net
        rankmap = {"APPROVE": 2, "WATCH": 1, "REJECT": 0, "N/A": -1}
        best = ("base", -1, "REJECT")
        for vname, blk in out["cells"][s]["variants"].items():
            if vname == "base" or blk.get("verdict") == "N/A":
                continue
            cur = (rankmap[best[2]], best[1])
            if (rankmap[blk["verdict"]], blk["five_gate"]) > cur:
                best = (vname, blk["five_gate"], blk["verdict"])
        out["cells"][s]["best_variant"] = [best[0], best[1], best[2]]
        summary[s] = best[0]
    out["summary"] = summary
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    print("\n产物:", OUT)
    print("逐品种最优变体:", json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
