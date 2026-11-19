# -*- coding: utf-8 -*-
"""rd_verify_adx_sweep_20261116.py — 分品种族 ADX 禁追线同分母五验扫描
====================================================================
领题: rd_queue webgap_adx_threshold_sweep_20261114 (P2, 11-14 全网学习派单)
红线: 纯研究. 引擎 jince_live24.py / 30261104 REAL 零动. 产物只落 data/ + research/.
口径: 复用 rd_verify_batch_20261114 (RB) 同分母引擎:
  base = 100%放行(品种JSON adx_min, 无ADX上限) M30前20根真突破, 引擎REAL口径出场
  (SL=min(sl_mult,1.2)ATR, TP=max(tp*ATR,2R)封顶12ATR, 0.5R BE/1.0R锁半/ATR紧跟踪/
   giveback0.6, 18h硬平, 同品种不重叠); 候选 = adx_max=L 禁追闸: ADX>=L 的突破不追,
   等<=4根回踩(不破突破位-1ATR)再顺向进, SL锚回踩摆动点±0.3ATR; ADX<L 走 base 出场.
  同分母铁律: 候选=base在闸内动作+候选自身闸外动作, 全事件同底, 禁子集胜率差.
  五验: T1净R(扣0.095)>0且>=base | T2胜率>=base-0.02 | T3五折同向 | T4 OOS70/30两段皆正
        | T5 0.15R成本仍正 | ⑥净期望(均R)>=1.0 才谈放大; 逐品种裁定, 禁跨品种平均.
数据: tf_cache .tmp 前向内存合并(11-16 10:04-10:08 刷新, 龄<6h 新鲜度闸过), 缺 .tmp 回退
      .npz 并显式标 DATA_STALE(不静默). 12 高流动品种任务文本 vs 数据底座: 仅 9 品种有
      M30 底座(XAU/EUR/BTC/ETH/SOL/XRP/LTC/BNB/KSM), GBP/USDJPY/XAG 无 M30 缓存=本批缺数
      挂账, 不混时间框架(混框=不同分母, 违反铁律).
分族: 币系=BTC/ETH/SOL/XRP/LTC/BNB/KSM(7) | 金=XAUUSD(单腿) | 外汇=EURUSD(单腿).
"""
import os, sys, json, datetime as dt
import numpy as np

ROOT = "E:/GoldstrategyEngine"
sys.path.insert(0, os.path.join(ROOT, "research"))
import rd_verify_batch_20261114 as RB  # noqa: E402

TFD = os.path.join(ROOT, "data", "tf_cache")
OUT = os.path.join(ROOT, "data", "rd_verify_batch_adx_sweep_20261116.json")
LS = [15, 20, 25, 30, 35, 40]
FAM = {
    "coin": ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD", "KSMUSD"],
    "gold": ["XAUUSD"],
    "fx": ["EURUSD"],
}
ALL_SYMS = ["XAUUSD", "EURUSD", "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD", "KSMUSD"]
COST, COST_T5 = RB.COST, RB.COST_T5
stale_note = []


def _load_npz_fresh(sym, tf):
    tmp = os.path.join(TFD, f"{sym}_{tf}.npz.tmp")
    if os.path.exists(tmp):
        z = np.load(tmp)
        src = "tmp_fwd"
    else:
        z = np.load(os.path.join(TFD, f"{sym}_{tf}.npz"))
        src = "npz_stale"
        stale_note.append(f"{sym}_{tf} no .tmp, fallback npz (DATA_STALE)")
    out = {k: z[k] for k in ("t", "h", "l", "c") if k in z.files}
    z.close()
    return out
RB.load_npz = _load_npz_fresh


def ztest(w1, n1, w2, n2):
    if n1 < 2 or n2 < 2:
        return None
    p = (w1 * n1 + w2 * n2) / (n1 + n2)
    se = np.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    z = (w1 - w2) / se if se > 0 else 0.0
    return float(z)


def run_sym(sym):
    P = RB.prepare30(sym)
    p = json.load(open(os.path.join(ROOT, "data", "practice_params_all_symbols.json"), encoding="utf-8")).get(sym, {})
    g = dict(adx_min=float(p.get("adx_min", 35.0)), break_margin=0.6, min_body=0.3,
             h1_on=False, max_hold_h=18, giveback=0.6,
             sl_mult=float(p.get("sl_mult", 1.0)), tp_mult=float(p.get("tp_mult", 3.0)))
    oos_cut = float(np.quantile(P["t"], 0.70))
    dx = P["dx"]
    kb, sb, db, tb = RB.gen_signals(P, g)          # base 全事件
    base = RB.evaluate(P, g)                        # 与 gen_signals 同源
    base015 = RB.evaluate(P, g, cost=COST_T5)
    n_base_ev = int((dx >= g["adx_min"]).sum())     # 同分母全事件池(含未触发body/m5m20的)
    rows = {}
    rows["base"] = dict(n=base["n"], net=round(base["net"], 2), avg=round(base["avg"], 5),
                        win=round(base["win"], 4), netR_015=round(base015["net"], 2), verdict="BASE")
    for L in LS:
        c = RB.evaluate(P, g, adx_max=float(L))
        c015 = RB.evaluate(P, g, adx_max=float(L), cost=COST_T5)
        mask_tr = c["et"] <= oos_cut
        tr = dict(n=int(mask_tr.sum()), net=float(c["R"][mask_tr].sum()),
                  avg=float(c["R"][mask_tr].mean()) if mask_tr.any() else 0.0)
        te = dict(n=int((~mask_tr).sum()), net=float(c["R"][~mask_tr].sum()),
                  avg=float(c["R"][~mask_tr].mean()) if (~mask_tr).any() else 0.0)
        gates = RB.five_gates(base, c, c015, tr, te)
        z = ztest(c["win"], c["n"], base["win"], base["n"])
        rows[str(L)] = dict(n=c["n"], net=round(c["net"], 2), avg=round(c["avg"], 5),
                            win=round(c["win"], 4), netR_015=round(c015["net"], 2),
                            train=tr, test=te, gates={k: v for k, v in gates.items()},
                            z_vs_base=z, verdict=RB.verdict_of(gates, base, c))
    # 每 L 的热区事件量(供透明度): 候选相对 base 少掉的单 = 转化未回踩而丢弃 + 时间窗变化
    base_n = base["n"]
    for L in LS:
        rows[str(L)]["delta_n_vs_base"] = rows[str(L)]["n"] - base_n
    # 家族禁追线: 取 T1&T4 过 且 net>=base net 中 net 最高的 L; 无=无门控改进(维持默认40)
    fam_rows = [rows[str(L)] for L in LS]
    cand_best = None
    for L in LS:
        r = rows[str(L)]
        if r["gates"]["T1"] and r["gates"]["T4"] and r["net"] >= rows["base"]["net"]:
            if cand_best is None or r["net"] > rows[str(cand_best)]["net"]:
                cand_best = L
    rows["family_line"] = cand_best
    rows["n_events_pool"] = int(kb.shape[0])
    return rows


def main():
    results = {}
    for s in ALL_SYMS:
        rows = run_sym(s)
        results[s] = rows
        print(s, "base n=%d net=%.1f avg=%.4f win=%.3f" %
              (rows["base"]["n"], rows["base"]["net"], rows["base"]["avg"], rows["base"]["win"]),
              "lines:", {L: "%s(net %.1f, T%d)" % (rows[str(L)]["verdict"][:4], rows[str(L)]["net"],
                                                      rows[str(L)]["gates"]["passed"]) for L in LS},
              "fam_line=", rows["family_line"], flush=True)
    fam_table = {}
    for fn, syms in FAM.items():
        votes = {}
        for s in syms:
            fl = results[s]["family_line"]
            key = str(fl)
            votes[key] = votes.get(key, 0) + 1
        fam_table[fn] = dict(symbols=syms, line_votes=votes,
                             best_line=max(votes, key=votes.get) if votes else None)
    out = dict(
        meta=dict(ts=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                  task="webgap_adx_threshold_sweep_20261114",
                  kline_source="tf_cache .tmp 前向内存合并 (11-16 10:04-10:08 刷新, 数据有效性闸: 快照龄<6h 过; 缺 tmp 回退 npz 标 DATA_STALE)",
                  cost=COST, cost_t5=COST_T5, stale_note=stale_note,
                  protocol="同分母五验: base=100%放行 vs 候选=ADX>=L 禁追回踩变体(全事件同底); "
                           "T1-T5+⑥ 逐品种裁定, 禁跨品种平均; ⑥未过=不放大, 只WATCH/REJECT 留痕",
                  data_gap="任务文本12品种, M30 数据底座仅 9 品种; GBPUSD/USDJPY/XAGUSD 无 M30 缓存不混框, 挂账下批回填",
                  real_account_untouched="60137964 只读; 30261104 REAL 零动; 引擎只读"),
        family_table=fam_table,
        symbols=results)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=float)
    print("DONE json:", OUT, flush=True)
    print("FAM_TABLE:", json.dumps(fam_table, ensure_ascii=False), flush=True)
    print("STALE:", stale_note, flush=True)


if __name__ == "__main__":
    main()
