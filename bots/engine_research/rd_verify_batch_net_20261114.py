# -*- coding: utf-8 -*-
"""rd_verify_batch_net_20261114.py —— 网络证据四候选 同分母五验 (M30+D1 引擎复现器 + M15 真读 CVD)
====================================================================
红线: 纯研究. 引擎 jince_live24.py / tools / REAL 30261104 参数零动. 产物只落 research/.
同分母: 复用 research/rd_verify_batch_20261114.py 的引擎信号复现器 (prepare30/gen_signals/simulate,
       base=现行突破追进场 100%放行口径), 候选只在事件流上预交易过滤, 出场规则全部保持 base 引擎口径.
候选 (网络证据只当料):
  killhour  ② 杀伤时段: 禁入 London 02-05UTC/纽约 07-10UTC (冬令), 夏令+1h 自动 (EU 末3月周日~首10月周日, US 次3月周日~首11月周日).
  wick13    ③ 扫掠K收盘外1/3强拒=反转风险: 信号K收盘落在逆向1/3 (多头=下1/3, 空头=上1/3) 的单剔除.
  ict_d1    ④ ICT 日偏+时段偏对齐: D1 日K阴阳偏 (上一已完成日K close vs open) 与方向一致才放行, 且禁杀伤时段 (砍单量提质).
  cvd_gate  ④ CVD 否决门 (只否决不新增): M15 真读 tick_volume CVD, 信号时刻回看2h(8根M15) CVD 斜率逆向则否决;
            M15 窗口外门不激活 (保留). 窗口: XAU/EUR 2025-03/04~11-13, 币系 2025-09~11-14.
五验(逐品种, 禁跨品种平均): T1 净R(扣0.095)>0 且>=base | T2 胜率>=base-0.02 | T3 5折时间切分同向(全正)
| T4 OOS70/30 两段皆正 | T5 成本0.15R 仍正 | ⑥净期望(均R)>=1.0.
裁定: APPROVE=T1-T5+⑥全过 | WATCH=T1-T5>=3/5 且 ⑥<1.0 | REJECT=其余.
"""
import os, sys, json, datetime as dt, calendar
import numpy as np

ROOT = "E:/GoldstrategyEngine"
sys.path.insert(0, os.path.join(ROOT, "research"))
import rd_verify_batch_20261114 as RB  # noqa: E402  (复用引擎复现器, 该模块只在 __main__ 跑 main)

SYMS = RB.SYMS
COST, COST_T5 = RB.COST, RB.COST_T5
M15DIR = os.path.join(ROOT, "research", "net20261114_m15")


# ── DST (UTC) ─────────────────────────────────────────────────────
def _nth_sunday(year, month, n):
    last = calendar.monthrange(year, month)[1]
    d = dt.datetime(year, month, last)
    while d.weekday() != 6:
        d -= dt.timedelta(days=1)
    for _ in range(n - 1):
        d -= dt.timedelta(days=7)
    return d  # naive datetime at UTC midnight


def _dst_bounds(years, kind):
    lo, hi = [], []
    for y in years:
        if kind == "eu":
            s = _nth_sunday(y, 3, 4) + dt.timedelta(hours=1)   # 末3月周日 01:00 UTC
            e = _nth_sunday(y, 10, 1) + dt.timedelta(hours=1)  # 首10月周日 01:00 UTC
        else:  # us
            s = _nth_sunday(y, 3, 2) + dt.timedelta(hours=2)   # 次3月周日 02:00 UTC
            e = _nth_sunday(y, 11, 1) + dt.timedelta(hours=2)  # 首11月周日 02:00 UTC
        lo.append(s.timestamp()); hi.append(e.timestamp())
    return np.array(lo), np.array(hi)


def dst_mask(times, kind):
    lo, hi = _dst_bounds(range(2008, 2027), kind)
    m = np.zeros(len(times), dtype=bool)
    for i in range(len(lo)):
        m |= (times >= lo[i]) & (times < hi[i])
    return m


def kill_hour_mask(times):
    """杀伤时段: London 02-05UTC(冬)/03-06(夏), NY 07-10(冬)/08-11(夏). 夏令自动+1h."""
    h = (times // 3600).astype(np.int64) % 24
    eu_s, us_s = dst_mask(times, "eu"), dst_mask(times, "us")
    lon = np.where(eu_s, (h >= 3) & (h <= 6), (h >= 2) & (h <= 5))
    ny = np.where(us_s, (h >= 8) & (h <= 11), (h >= 7) & (h <= 10))
    return lon | ny


# ── 候选过滤器 (事件级, 预交易) ──────────────────────────────────
def f_killhour(P, k, s):
    te = P["t"][k] + 1800  # M30 信号根收线 = 进场参考时刻
    return ~kill_hour_mask(te)


def f_wick13(P, k, s):
    """信号K收盘落在逆向1/3 (多头=下1/3, 空头=上1/3) => 剔除 (网络③强拒)."""
    rng = P["h"] - P["l"]
    keep = np.ones(len(k), dtype=bool)
    for i, kk in enumerate(k):
        r = rng[kk]
        if r <= 0:
            continue
        ckk = P["c"][kk]
        if s[i] > 0:
            keep[i] = not (ckk <= P["l"][kk] + rng[kk] / 3.0)
        else:
            keep[i] = not (ckk >= P["h"][kk] - rng[kk] / 3.0)
    return keep


def d1_bias(P, P_d1, k, s):
    """上一已完成 D1 K线 阴阳偏: 长需 d1c>d1o, 短需 d1c<d1o, 平K/无数据剔除."""
    t1, c1 = P_d1["t"], P_d1["c"]
    o1 = np.concatenate(([c1[0]], c1[:-1]))
    bias = np.sign(c1 - o1)
    te = P["t"][k] + 1800
    j = np.searchsorted(t1, te - 86400, side="right") - 1  # 最后已完成日K
    ok = j >= 0
    b = np.where(ok, bias[np.clip(j, 0, None)], 0.0)
    keep = np.ones(len(k), dtype=bool)
    keep[s > 0] &= (b[s > 0] > 0) & ok[s > 0]
    keep[s < 0] &= (b[s < 0] < 0) & ok[s < 0]
    return keep


def f_ict_d1(P, P_d1, k, s):
    keep = f_killhour(P, k, s) & d1_bias(P, P_d1, k, s)
    return keep


def cvd_gate_keep(P, k, s, m15):
    """M15 CVD 否决门 (只否决): 信号时刻回看 8 根 M15 (2h) CVD 斜率逆向 => 剔除; 窗口外保留."""
    if m15 is None or len(m15["t"]) == 0:
        return np.ones(len(k), dtype=bool), None, None
    t15, c15, tv15 = m15["t"], m15["c"], m15["tv"]
    ret = np.sign(np.diff(c15, prepend=c15[0]))
    cvd = np.cumsum(tv15 * ret)
    te = P["t"][k] + 1800
    j = np.searchsorted(t15, te - 900, side="right") - 1  # 最后已完成 M15 根
    in_win = (j >= 8) & (j < len(cvd))
    slope = np.full(len(k), np.nan)
    jj = j[in_win]
    slope[in_win] = cvd[jj] - cvd[jj - 8]
    keep = np.ones(len(k), dtype=bool)
    longm, shortm = s > 0, s < 0
    veto = np.isfinite(slope)
    keep[longm] &= ~veto[longm] | (slope[longm] >= 0)
    keep[shortm] &= ~veto[shortm] | (slope[shortm] <= 0)
    return keep, in_win, (int(t15[0]), int(t15[-1]))


def eval_events(P, g, k, s, dist, tp_d, cost=COST):
    res = RB.simulate(P, g, k, s, dist=dist, tp_d=tp_d, cost=cost)
    R = res["R"]
    n = len(R)
    return dict(n=n, net=float(R.sum()) if n else 0.0,
                avg=float(R.mean()) if n else 0.0,
                win=float((R > 0).mean()) if n else 0.0, R=R, et=res["et"])


def run_candidate(P, P_d1, g, cand, m15):
    kb, sb, db, tb = RB.gen_signals(P, g)  # base 事件流 (同分母)
    base = eval_events(P, g, kb, sb, db, tb)
    base015 = eval_events(P, g, kb, sb, db, tb, cost=COST_T5)
    oos_cut = float(np.quantile(P["t"], 0.70))

    rows = {"base": base, "base015": base015}
    if cand == "killhour":
        kk = f_killhour(P, kb, sb)
    elif cand == "wick13":
        kk = f_wick13(P, kb, sb)
    elif cand == "ict_d1":
        kk = f_ict_d1(P, P_d1, kb, sb)
    elif cand == "cvd_gate":
        kk, in_win, win_range = cvd_gate_keep(P, kb, sb, m15)
        rows["cvd_window"] = [int(win_range[0]), int(win_range[1])] if win_range else None
        rows["n_in_window"] = int(in_win.sum()) if in_win is not None else 0
        rows["n_vetoed"] = int((~kk).sum())
    else:
        raise ValueError(cand)
    kc, sc, dc, tc = kb[kk], sb[kk], db[kk], tb[kk]
    c = eval_events(P, g, kc, sc, dc, tc)
    c015 = eval_events(P, g, kc, sc, dc, tc, cost=COST_T5)
    if cand == "cvd_gate" and in_win is not None:
        inw = in_win[kk]  # 候选事件中落在 M15 窗口内的 (事件级, 非交易级)
        kw, sw, dw, tw = kc[inw], sc[inw], dc[inw], tc[inw]
        cw = eval_events(P, g, kw, sw, dw, tw)
        rows["window"] = dict(n=cw["n"], net=round(cw["net"], 2),
                              avg=round(cw["avg"], 4), win_rate=round(cw["win"], 4),
                              m15_window_start=int(win_range[0]), m15_window_end=int(win_range[1]))
    tr_mask = c["et"] <= oos_cut
    tr = dict(n=int(tr_mask.sum()), net=float(c["R"][tr_mask].sum()),
              avg=float(c["R"][tr_mask].mean()) if tr_mask.any() else 0.0)
    te = dict(n=int((~tr_mask).sum()), net=float(c["R"][~tr_mask].sum()),
              avg=float(c["R"][~tr_mask].mean()) if (~tr_mask).any() else 0.0)
    g6 = c["avg"] >= 1.0
    gates = dict(T1=bool(c["net"] > 0 and c["net"] >= base["net"]),
                 T2=bool(c["win"] >= base["win"] - 0.02),
                 T3=bool(c["n"] >= 5 and all(x.sum() > 0 for x in np.array_split(c["R"], 5))),
                 T4=bool(tr["net"] > 0 and te["net"] > 0),
                 T5=bool(c015["net"] > 0), g6=bool(g6))
    gates["passed"] = int(gates["T1"]) + int(gates["T2"]) + int(gates["T3"]) + int(gates["T4"]) + int(gates["T5"]) + int(gates["g6"])
    for d in (base, base015):
        d.pop("R", None); d.pop("et", None)
    t15 = gates["passed"] - int(gates["g6"])
    if gates["passed"] == 6:
        verdict = "APPROVE"
    elif t15 >= 3 and (gates["T4"] or gates["T3"]):
        verdict = "WATCH"
    else:
        verdict = "REJECT"
    rows["cand_n"] = int(c["n"]); rows["cand_net"] = round(c["net"], 2)
    rows["cand_avg_netR"] = round(c["avg"], 4)
    rows["cand_win"] = round(c["win"], 4)
    rows["cand_netR_015"] = round(c015["net"], 2)
    rows["oos_cut_ts"] = int(oos_cut)
    rows["train"], rows["test"] = tr, te
    rows["gates"], rows["verdict"] = gates, verdict
    return rows


def main():
    params = json.load(open(os.path.join(ROOT, "data", "practice_params_all_symbols.json"), encoding="utf-8"))
    results = {}
    for s in SYMS:
        P = RB.prepare30(s)
        P_d1 = RB.load_npz(s, "D1")
        p = params.get(s, {})
        g = dict(adx_min=float(p.get("adx_min", 35.0)), break_margin=0.6, min_body=0.3,
                 h1_on=False, max_hold_h=18, giveback=0.6,
                 sl_mult=float(p.get("sl_mult", 1.0)), tp_mult=float(p.get("tp_mult", 3.0)))
        m15p = os.path.join(M15DIR, f"{s}_M15.npz")
        m15 = np.load(m15p) if os.path.exists(m15p) else None
        m15d = dict(t=m15["t"], c=m15["c"], tv=m15["tv"]) if m15 is not None else None
        if m15 is not None:
            m15.close()
        out = {"sym": s, "adx_min": g["adx_min"], "sl_mult": g["sl_mult"], "tp_mult": g["tp_mult"]}
        out["base"] = run_candidate(P, P_d1, g, "base__noop", None) if False else None
        # base row
        kb, sb, db, tb = RB.gen_signals(P, g)
        b = eval_events(P, g, kb, sb, db, tb)
        b015 = eval_events(P, g, kb, sb, db, tb, cost=COST_T5)
        oos_cut = float(np.quantile(P["t"], 0.70))
        mtr = b["et"] <= oos_cut
        out["base_row"] = dict(n=b["n"], net=round(b["net"], 2), avg=round(b["avg"], 4),
                               win=round(b["win"], 4), netR_015=round(b015["net"], 2),
                               train_net=round(float(b["R"][mtr].sum()), 2), test_net=round(float(b["R"][~mtr].sum()), 2),
                               verdict="BASE")
        for cand in ("killhour", "wick13", "ict_d1", "cvd_gate"):
            out[cand] = run_candidate(P, P_d1, g, cand, m15d)
            print(s, cand, out[cand]["cand_n"], out[cand]["cand_net"],
                  out[cand]["gates"]["passed"], out[cand]["verdict"], flush=True)
        results[s] = out
    with open(os.path.join(ROOT, "research", "rd_verify_batch_net_20261114.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1, default=float)
    print("DONE json written", flush=True)


if __name__ == "__main__":
    main()
