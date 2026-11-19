#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
liquid_wfo_liq12.py —— 12 高流动性品种 M15 同分母五门走查优化 (WFO), 研究专用
============================================================================
协议 (全品种同一分母):
  * 数据: 每品种自身 M15 CSV (40000 根); JPN225/US30 无管线 CSV -> MT5 只读抓取
    存 research/liquid_wfo_liq12_data/ (data/ 未动)。
  * 成本: 0.095R/笔 (官方五门口径) 为主; 另记 0.10R 参考档。
  * 基线 BASE = 引擎现役参数: ADX_MIN=35 (简化DI差) / BREAK_MARGIN=0.6 /
    VOL_EXPAND_K=0.7 / MIN_BODY_ATR=0.3 / h1_on=True / MAX_HOLD_H=18 /
    giveback=0.6 + 该品种 practice_params_all_symbols.json 的 sl_mult/tp_mult
    (REAL 口径 SL 封顶 1.2ATR, TP>=2R 地板, 12ATR 顶 — 与 jince_live24 一致)。
  * OPT: 70/30 时间切分, 仅 train 上 V3 坐标下降(3 轮, n_req=60, 裁剪网格)。
  * OOS: OPT 在 test 上评估 vs BASE 在 test 上评估。
  * 五门 five_final 在【全量】上以 train-OPT g 跑: T1 avg&net 优 / T2 胜率不劣 /
    T3 seg8>=6 / T4 甜区(最终 g 上 ADX 扫 [12..30 步长2]) / T5 三窗全优。
  * 成本压力: 0.095 下 OPT avg>0 且 OPT avg>BASE avg (另附 0.10 参考)。
  裁定: APPROVE = 五门>=4/5 且 OOS_opt_net>OOS_base_net 且 OOS_opt_net>0;
        WATCH  = 五门 3/5, 或 OOS 偏弱但样本内为正;
        REJECT = OOS 崩(<=0) 或 OOS 劣于基线且样本内不优;
        DATA_THIN = M15 < 5000 根 (不出结论); STALE_DATA = 数据 >48h 排除。
红线: 纯研究。不改 tools/、l24_feature_flags.json、cron/watchdog、live 参数。
"""
import os, sys, json, time, datetime as dt
import numpy as np

ROOT = "E:/GoldstrategyEngine"
sys.path.insert(0, os.path.join(ROOT, "research"))
import liquid_wfo_m15_v2 as W
import liquid_wfo_m15_v3 as V3
import liquid_wfo_m15_final as FIN

OUT = os.path.join(ROOT, "research", "liquid_wfo_liq12_result.json")
LOCAL_DATA = os.path.join(ROOT, "research", "liquid_wfo_liq12_data")

COST = 0.095          # 官方五门成本口径 (主)
COST_REF = 0.10       # 参考压力档

LIQ12 = ["AUDUSD", "BTCUSD", "ETHUSD", "EURUSD", "GBPJPY", "GBPUSD",
         "JPN225", "US30", "USDJPY", "XAGUSD", "XAUUSD", "XTIUSD"]
MIN_BARS = 5000
N_REQ = 60
ADX_SWEET = list(range(12, 31, 2))   # [12,14,...,30] 10 点

# 裁剪网格 (同 V3 域, 按任务裁剪控运行时)
GRID12 = dict(
    adx_min=[10., 15., 20., 25., 30., 35., 40.],
    break_margin=[0.3, 0.6, 1.0],
    vol_k=[0.5, 0.6, 0.7, 0.9],
    min_body=[0.1, 0.3, 0.5],
    h1_on=[True, False],
    max_hold_h=[12, 18, 24, 30],
    giveback=[0.4, 0.6, 0.8],
    sl_mult=[0.4, 0.6, 0.8, 1.0, 1.2],
    tp_mult=[2.0, 3.0, 4.0, 5.0, 7.0],
)
ORDER12 = ["adx_min", "sl_mult", "vol_k", "h1_on", "break_margin",
           "min_body", "tp_mult", "giveback", "max_hold_h"]


def ev(P, g, cost=COST):
    return V3.ev(P, g, cost=cost)


def coord12(P, g0, rounds=3, n_req=N_REQ, label=""):
    """V3 坐标下降, 用裁剪网格 GRID12 / 目标=固定 1ATR 绝对收益+三窗惩罚。"""
    g = dict(g0); cur = ev(P, g); sc = V3.score(cur, n_req); curve = []
    for rd in range(rounds):
        improved = False
        for key in ORDER12:
            bv, bs, be, cv = g[key], sc, cur, []
            for v in GRID12[key]:
                q = dict(g); q[key] = v
                e = ev(P, q); s_ = V3.score(e, n_req)
                cv.append((float(v) if isinstance(v, float) else (1 if v else 0),
                           round(float(e["avg"]), 5)))
                if s_ > bs + 1e-7:
                    bs, bv, be = s_, v, e
            if key == "adx_min":
                curve = cv
            if bv != g[key]:
                g[key] = bv; sc, cur = bs, be; improved = True
        if label:
            print("    [%s] r%d absAvgR=%+.4f n=%d ADX=%s SL=%s TP=%s" %
                  (label, rd + 1, cur["avg"], cur["n"], g["adx_min"], g["sl_mult"], g["tp_mult"]),
                  flush=True)
        if not improved:
            break
    return g, cur, curve


def sweep_adx(P, g, vals):
    out = []
    for v in vals:
        q = dict(g); q["adx_min"] = float(v)
        e = ev(P, q)
        out.append([float(v), e["n"], round(e["avg"], 5), round(e["net"], 2)])
    return out


def load_prepared(sym):
    """M15/H1: 优先管线 data/; JPN225/US30 用 MT5 抓取件 research/liquid_wfo_liq12_data/。
    复用 W.prepare 的原样复刻逻辑(切数据目录, 零重复实现)。
    返回 (P, kline_source, data_end_ts, data_age_h, fresh)。"""
    if sym in ("JPN225", "US30"):
        m15p = os.path.join(LOCAL_DATA, f"{sym}_M15.csv")
        h1p = os.path.join(LOCAL_DATA, f"{sym}_H1.csv")
        if not (os.path.exists(m15p) and os.path.exists(h1p)):
            return None, "MISSING", None, 0.0, False
        src = "mt5_readonly_fetch_utc_label"
        saved = W.DATA
        W.DATA = LOCAL_DATA
        try:
            P = W.prepare(sym)
        finally:
            W.DATA = saved
    else:
        if not os.path.exists(os.path.join(W.DATA, f"{sym}_M15.csv")):
            return None, "MISSING", None, 0.0, False
        src = "pipeline_csv"
        P = W.prepare(sym)
    data_end_ts = dt.datetime.fromtimestamp(P["t"][-1]).strftime("%Y-%m-%d %H:%M:%S")
    age_h = (time.time() - P["t"][-1]) / 3600.0
    return P, src, data_end_ts, age_h, age_h <= 48.0


_PARAMS_CACHE = None


def build_base(sym):
    """引擎同口径 BASE: 全局 gate (ADX_MIN 35 简化DI差等, 同 W.BASE) +
    该品种 practice_params_all_symbols.json 的 sl_mult/tp_mult (缺失=引擎全局 3.5/8.0)。"""
    global _PARAMS_CACHE
    if _PARAMS_CACHE is None:
        _PARAMS_CACHE = json.load(open(
            os.path.join(W.DATA, "practice_params_all_symbols.json"), encoding="utf-8"))
    p = _PARAMS_CACHE.get(sym, {})
    B = dict(W.BASE)
    B["sl_mult"] = float(p.get("sl_mult", 3.5))   # 引擎缺失 fallback SL_MULT=3.5
    B["tp_mult"] = float(p.get("tp_mult", 8.0))   # TP_MULT=8.0
    return B, p


def run_symbol(sym):
    P, src, end_ts, age_h, fresh = load_prepared(sym)
    rec = dict(sym=sym, kline_source=src, data_end_ts=end_ts, data_age_h=round(age_h, 1),
               cost=COST)
    if P is None:
        rec.update(verdict="DATA_UNAVAILABLE", reason="M15/H1 CSV 缺失且 MT5 抓取失败",
                   bars=0)
        return rec
    rec["bars"] = P["n"]
    if P["n"] < MIN_BARS:
        rec.update(verdict="DATA_THIN", bars=P["n"],
                   reason=f"M15 仅 {P['n']} 根 < {MIN_BARS}, 不出结论")
        return rec
    if not fresh:
        rec.update(verdict="STALE_DATA", reason=f"数据末端 {age_h:.1f}h > 48h, 排除裁定")
        return rec
    B, live = build_base(sym)
    rec["base_g"] = B
    rec["base_params_from"] = ("practice_params_all_symbols.json"
                               f"(sl={B['sl_mult']}, tp={B['tp_mult']}, cat={live.get('category', 'engine_default')})")
    # 70/30 时间切分 (全品种同比例)
    cut = int(P["n"] * 0.70)
    Ptr, Pte = FIN.slice_P(P, 0, cut), FIN.slice_P(P, cut, P["n"])
    # OOS: 仅 train 上坐标下降
    g_oos, e_tr, _ = coord12(Ptr, B, rounds=2, label=sym)
    rec["opt_g"] = g_oos
    rec["opt_train"] = dict(n=e_tr["n"], net=round(e_tr["net"], 2),
                            avg=round(e_tr["avg"], 5), win=round(e_tr["win"], 4))
    # 全量评估 (BASE vs train-OPT)
    b = ev(P, B); o = ev(P, g_oos)
    o_ref = ev(P, g_oos, cost=COST_REF); b_ref = ev(P, B, cost=COST_REF)
    rec["opt_sample"] = dict(n=o["n"], net=round(o["net"], 2), avg=round(o["avg"], 5),
                             win=round(o["win"], 4))
    rec["base_sample"] = dict(n=b["n"], net=round(b["net"], 2), avg=round(b["avg"], 5),
                              win=round(b["win"], 4))
    # OOS test
    base_te = ev(Pte, B); opt_te = ev(Pte, g_oos)
    rec["oos_test"] = dict(base_n=base_te["n"], base_net=round(base_te["net"], 2),
                           base_avg=round(base_te["avg"], 5),
                           opt_n=opt_te["n"], opt_net=round(opt_te["net"], 2),
                           opt_avg=round(opt_te["avg"], 5))
    # 五门 (全量, 最终 g = train-OPT; T4 甜区扫 [12..30 步2])
    curve = sweep_adx(P, g_oos, ADX_SWEET)
    ft = FIN.five_final(b, o, curve)
    rec["five"] = ft
    rec["sweet_adx_curve"] = curve
    sv = [x[2] for x in curve]
    rec["sweet_adx"] = [curve[int(np.argmax(sv))][0]] if curve else []
    # 成本压力: 主 0.095 (即上面 b/o), 参考 0.10
    stress_ok = int(o["avg"] > b["avg"] and o["avg"] > 0)
    rec["stress"] = dict(cost=COST, pass_=stress_ok,
                         opt_avg095=round(o["avg"], 5), base_avg095=round(b["avg"], 5),
                         opt_avg_10ref=round(o_ref["avg"], 5), base_avg_10ref=round(b_ref["avg"], 5),
                         note="0.095 下 OPT avg>BASE avg 且 >0; 0.10 档仅供参考")
    # 裁定 (同分母规则; OOS 非正 = 崩溃 -> 一票 REJECT)
    d_net, d_avg = o["net"] - b["net"], o["avg"] - b["avg"]
    oos_opt_net, oos_base_net = opt_te["net"], base_te["net"]
    oos_thin = opt_te["n"] < 30
    if oos_opt_net <= 0:
        verdict = "REJECT"
        rec["oos_note"] = "OOS opt_net=%+.2f 非正 -> 样本外崩溃/为负, 一票 REJECT" % oos_opt_net
    elif ft["passed"] >= 4 and oos_opt_net > oos_base_net:
        verdict = "APPROVE" if not oos_thin else "WATCH"
        if oos_thin:
            rec["oos_note"] = "OOS 判据满足但 test 仅 %d 笔(<30), 证据薄 -> 降 WATCH" % opt_te["n"]
    elif ft["passed"] >= 3 or (oos_opt_net > 0 and d_net > 0):
        verdict = "WATCH"
    else:
        verdict = "REJECT"
        rec["oos_note"] = "OOS 劣于基线且样本内不优 -> REJECT"
    rec["d_net"] = round(d_net, 2)
    rec["d_avg"] = round(d_avg, 5)
    rec["verdict"] = verdict
    rec["verdict_rule"] = ("APPROVE: five>=4/5 & OOS opt_net>base_net>0 | "
                           "WATCH: five 3/5 或 OOS 弱但样本内正 | REJECT: OOS<=0 或 崩溃")
    return rec


def main():
    t0 = time.time()
    results = {}
    print("=== 12 高流动性品种 M15 同分母五门 WFO (cost=0.095, 70/30 OOS) ===", flush=True)
    print(f"{'SYM':8s} {'bars':>7s} {'BASE n/net':>14s} {'OPT  n/net':>14s} "
          f"{'OOS b/opt':>12s} {'5g':>3s} {'verdict':>9s}", flush=True)
    for sym in LIQ12:
        r = run_symbol(sym)
        results[sym] = r
        v = r["verdict"]
        if v in ("APPROVE", "WATCH", "REJECT"):
            bs, os_ = r["base_sample"], r["opt_sample"]
            ot = r["oos_test"]
            print(f"{sym:8s} {r['bars']:>7d} {bs['n']:>6d}/{bs['net']:>+9.2f} "
                  f"{os_['n']:>6d}/{os_['net']:>+9.2f} "
                  f"{ot['base_net']:>+7.1f}/{ot['opt_net']:>+7.1f} "
                  f"{r['five']['passed']:>3d} {v:>9s}  end={r['data_end_ts']}", flush=True)
        else:
            print(f"{sym:8s} {str(r.get('bars', '?')):>7s}  {v:>24s}  {r.get('reason', '')}",
                  flush=True)
    # 家族 rollup
    fams = {}
    params = json.load(open(os.path.join(W.DATA, "practice_params_all_symbols.json"),
                            encoding="utf-8"))
    for sym in LIQ12:
        cat = (params.get(sym) or {}).get("category", "unknown")
        fams.setdefault(cat, {})[sym] = results[sym]["verdict"]
    family_rollup = {cat: dict(counts={}, verdicts=symdict)
                     for cat, symdict in fams.items()}
    for cat, d in family_rollup.items():
        for v in d["verdicts"].values():
            d["counts"][v] = d["counts"].get(v, 0) + 1
    flip_ready = []
    for sym in LIQ12:
        r = results[sym]
        if r["verdict"] == "APPROVE":
            flip_ready.append(dict(
                symbol=sym,
                g_params={k: (r["opt_g"][k]) for k in
                          ("adx_min", "break_margin", "vol_k", "min_body", "h1_on",
                           "max_hold_h", "giveback", "sl_mult", "tp_mult")},
                evidence=dict(
                    five=r["five"], sweet_adx=r["sweet_adx"],
                    oos_opt_net=r["oos_test"]["opt_net"],
                    oos_base_net=r["oos_test"]["base_net"],
                    sample_opt_net=r["opt_sample"]["net"],
                    sample_base_net=r["base_sample"]["net"],
                    stress=r["stress"]["pass_"],
                    data_end_ts=r["data_end_ts"]),
            ))
    out = dict(
        meta=dict(
            ts=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            cost=COST, cost_ref=COST_REF,
            symbols=LIQ12,
            protocol=("同分母五门WFO: 每品种自身M15 40000根; 70/30 时间切分, 仅train坐标下降"
                      "(3轮/n_req60/裁剪网格), test评估OOS; 五门five_final在最终g上"
                      "(T4甜区ADX扫[12..30步2]); 成本0.095主+0.10参考; "
                      "BASE=引擎ADX35/破0.6ATR/波动扩0.7/实体0.3/H1共振/18h/giveback0.6"
                      "+JSON分品种sl/tp(REAL 1.2ATR封顶)"),
            kline_source={s: results[s].get("kline_source", "MISSING") for s in LIQ12},
            data_end={s: results[s].get("data_end_ts") for s in LIQ12},
            guardrails=("研究专用: 未改 tools/、l24_feature_flags.json、cron/watchdog; "
                       "未重启进程; 未下单。JPN225/US30 经 MT5 只读抓取(演示户60137964)"),
        ),
        per_symbol=results,
        family_rollup=family_rollup,
        flip_ready=flip_ready,
    )
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=float)
    print(f"\n用时 {time.time()-t0:.1f}s -> {OUT}", flush=True)
    print("FLIP_READY:", [x["symbol"] for x in flip_ready], flush=True)


if __name__ == "__main__":
    main()
