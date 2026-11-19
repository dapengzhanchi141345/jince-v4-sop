# -*- coding: utf-8 -*-
"""rd_verify_s5s6_fwd_oos_20261115.py — 灵魂 S5/S6 家窗口·定位 前向 OOS 接力 同分母五验
====================================================================
红线: 纯研究. 引擎 jince_live24.py / 30261104 REAL 零动. 产物落 data/ + research/.
背景: 11-14 批 soul_s5s8 五验 XAU/EUR/BTC/ETH/BNB = 5 WATCH(T1 全过但未过⑥净期望线1.0, 0放大),
      轮转指针 = 前向 OOS 接力攒样. 本批把 K线延到 11-16(M30 .tmp 新读 + M15 tv 前向)再跑同分母五验,
      看 5 WATCH 是否前进(过⑥=APPROVE 候选进 chief R11 双裁; 未过=维持 WATCH 0放大).
同分母铁律: 5 品种用同一批前向数据(M30 .tmp 11-16 / M15 11-16 04:00)同滑点0.095/OOS70-30/5折/成本0.15/⑥线1.0,
      逐品种裁定, 禁跨品种平均; 子集胜率差=选择效应不算 edge.
数据源: M30/D1 读 tf_cache .tmp(影子采集锁 npz 的内存合并新读, 11-16 前向); M15(tick_volume) 读 net20261115_m15.
      若某品种 .tmp 缺失=回退旧 npz 并显式标 DATA_STALE(不静默).
口径: 复用 rd_verify_batch_soul_s5s8_20261114 的 S5 家时段窗闸(kill) + S6 定位图闸(level) + RB 信号复现器 + 五验 gates.
"""
import os, sys, json, datetime as dt
import numpy as np

ROOT = "E:/GoldstrategyEngine"
sys.path.insert(0, os.path.join(ROOT, "research"))
import rd_verify_batch_20261114 as RB          # noqa: E402
import rd_verify_batch_soul_s5s8_20261114 as S58  # noqa: E402

M15DIR = os.path.join(ROOT, "research", "net20261115_m15")
TFD = os.path.join(ROOT, "data", "tf_cache")
OUT = os.path.join(ROOT, "data", "rd_verify_batch_s5s6_obs_tag_oos_20261115.json")
SYMS = ["XAUUSD", "EURUSD", "BTCUSD", "ETHUSD", "BNBUSD"]   # 11-14 批 5 WATCH
COST, COST_T5 = RB.COST, RB.COST_T5
stale_note = []


def _load_npz_fresh(sym, tf):
    """优先读 .tmp(前向内存合并新读), 缺失回退 npz 并标 stale."""
    tmp = os.path.join(TFD, f"{sym}_{tf}.npz.tmp")
    src = None
    if os.path.exists(tmp):
        z = np.load(tmp)
        src = "tmp_fwd"
    else:
        z = np.load(os.path.join(TFD, f"{sym}_{tf}.npz"))
        src = "npz_stale"
        stale_note.append(f"{sym}_{tf} 无 .tmp 前向, 回退旧 npz(DATA_STALE)")
    out = {k: z[k] for k in ("t", "h", "l", "c") if k in z.files}
    z.close()
    return out, src


# monkey-patch RB.load_npz 让 prepare30 走前向数据
def _patched_load_npz(sym, tf):
    out, src = _load_npz_fresh(sym, tf)
    return out
RB.load_npz = _patched_load_npz


def run_sym(sym):
    P = RB.prepare30(sym)
    p = json.load(open(os.path.join(ROOT, "data", "practice_params_all_symbols.json"), encoding="utf-8")).get(sym, {})
    g = dict(adx_min=float(p.get("adx_min", 35.0)), break_margin=0.6, min_body=0.3,
             h1_on=False, max_hold_h=18, giveback=0.6,
             sl_mult=float(p.get("sl_mult", 1.0)), tp_mult=float(p.get("tp_mult", 3.0)))
    kb, sb, db, tb = RB.gen_signals(P, g)
    base = S58.ev(RB.simulate(P, g, kb, sb, dist=db, tp_d=tb))
    base015 = S58.ev(RB.simulate(P, g, kb, sb, dist=db, tp_d=tb, cost=COST_T5))
    oos_cut = float(np.quantile(P["t"], 0.70))
    fam = S58.FAM[sym]
    te_wall = P["t"][kb] + 1800
    utc_te, off_te = S58.utc_of(te_wall.astype(np.int64))

    m15f = os.path.join(M15DIR, f"{sym}_M15.npz")
    n_inwin = 0
    s6_keep = np.ones(len(kb), dtype=bool)
    if os.path.exists(m15f):
        z = np.load(m15f)
        m15d = {k: z[k] for k in ("t", "h", "l", "c", "tv") if k in z.files}
        z.close()
        lv = S58.build_levels(m15d)
        lv["h"] = m15d["h"]; lv["l"] = m15d["l"]
        j = np.searchsorted(lv["t"], te_wall.astype(np.int64) - 900, side="right") - 1
        s6_keep, s7c_keep, s7b_delay, s7b_drop, s7b_k_new, n_inwin = \
            S58.masks_s6_s7(P, kb, sb, db, tb, lv, te_wall, utc_te, j)

    kill = S58.s5_kill_mask(utc_te, fam)

    rows = {"base": dict(n=base["n"], net=round(base["net"], 2), avg=round(base["avg"], 4),
                         win=round(base["win"], 4), netR_015=round(base015["net"], 2), verdict="BASE")}

    def run_row(name, k, ss, dd, tt):
        if len(k) == 0:
            rows[name] = dict(n=0, net=0.0, avg=0.0, win=0.0, netR_015=0.0,
                              gates=dict(T1=False, T2=False, T3=False, T4=False, T5=False,
                                         g6=False, passed=0), verdict="REJECT", empty=True)
            return
        res = RB.simulate(P, g, k, ss, dist=dd, tp_d=tt)
        c = S58.ev(res)
        res0 = RB.simulate(P, g, k, ss, dist=dd, tp_d=tt, cost=COST_T5)
        c015 = S58.ev(res0)
        gt = S58.gates_of(c, base, c015, oos_cut)
        rows[name] = dict(n=c["n"], net=round(c["net"], 2), avg=round(c["avg"], 4),
                          win=round(c["win"], 4), netR_015=round(c015["net"], 2),
                          gates={k2: v2 for k2, v2 in gt.items() if k2 not in ("train", "test", "verdict")},
                          train=gt["train"], test=gt["test"], verdict=gt["verdict"])

    k5 = kb[~kill]
    run_row("s5", k5, sb[~kill], db[~kill], tb[~kill])
    rows["s5"]["n_killed"] = int(kill.sum())
    run_row("s6", kb[s6_keep], sb[s6_keep], db[s6_keep], tb[s6_keep])
    rows["s6"]["n_killed"] = int((~s6_keep).sum())
    rows["n_events"] = len(kb)
    rows["n_inwin_m15"] = n_inwin
    rows["fam"] = fam
    return rows


def main():
    results = {}
    for s in SYMS:
        rows = run_sym(s)
        results[s] = rows
        print(s, "fam=%s n_events=%d inwin=%d base_net=%.1f" %
              (rows["fam"], rows["n_events"], rows["n_inwin_m15"], rows["base"]["net"]),
              {nm: r["verdict"] for nm, r in rows.items() if isinstance(r, dict) and "verdict" in r and nm != "base"},
              flush=True)
    out = dict(
        meta=dict(ts=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                  task="s5s6_obs_tag_oos_20261115",
                  kline_source=("M30/D1=tf_cache .tmp 前向内存合并新读(XAU/EUR/BTC/ETH/BNB 至 2026-11-16 10:00/08:00 UTC, "
                                "影子采集锁 npz 的 tmp 兜底口径) | M15(tick_volume)=net20261115_m15(至 11-16 04:00 UTC, MT5活读60137964)"),
                  cost=COST, cost_t5=COST_T5,
                  stale_note=stale_note,
                  protocol=("同分母五验 S5/S6 前向OOS接力: base=RB引擎复现100%放行(18h硬平, 与11-14批同底); "
                            "T1净R扣0.095>0且>=base / T2胜率不劣 / T3五折全正 / T4 OOS70/30两段皆正 / "
                            "T5 0.15R成本仍正 / ⑥净期望(均R)>=1.0; 逐品种裁定, 禁跨品种平均; "
                            "过⑥=APPROVE候选进chief R11双裁翻闸; 未过=维持WATCH 0放大; 历史回测≠未来收益"),
                  real_account_untouched="60137964 只读; 30261104 REAL 零动; 引擎只读"),
        symbols=results)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=float)
    print("DONE json written:", OUT, flush=True)
    print("STALE_NOTE:", stale_note, flush=True)


if __name__ == "__main__":
    main()
