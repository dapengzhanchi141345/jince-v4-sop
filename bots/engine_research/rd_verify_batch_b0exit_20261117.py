# -*- coding: utf-8 -*-
"""rd_verify_batch_b0exit_20261117.py — 金策P1修复批 同分母五验回测 (纯研究, 0下单 0改引擎 0翻闸)
件1 b0_exit_upgrade_20261117: B0进出场 4组 × 8主流, 30d窗
  A=现行: M30追突破进场 + B0_inval秒退(双确认+R<=-0.2+>=2根) + 现行BE/棘轮/TP/18h
  B=结构失效离场: 同A进场, 秒退改 M15 2连收破结构(运行结构位) 且 MFE>=0.5R 时持有不秒退(纯结构离场, 保留灾难SL/TP/18h, 无BE棘轮)
  C=扫掠确认进场: M15 sweep(外沿>=0.15ATR15+收回) + 位移K实体>=70%且>=0.3ATR15, 次根open进场, SL锚扫掠极值-0.3ATR15, 离场=同B
  D=A+B+C组合: C的进场 + B的结构离场 + A的BE/棘轮兜底
件2 large_lot_struct_sl_20261117 (M15结构SL部分): 1.0手通道 m20261105 30d 4单(TSLA/KLAC/BLK/AVGO, MT5实读开平仓),
  结构SL(M15 5-bar分形摆动点±0.3ATR15) vs 现行SL 同分母净R差 + 1%净值帽预检($9.89@989.29)
口径: 成本0.095R(T5压力0.15R), winsor[-3,8], OOS70/30, 五验T1-T5+⑥线1.0, 逐品种裁定禁跨品种平均
数据: data/tf_cache M30/M15 npz (MT5只读60137964回填, 末端 2026-11-17), 30d窗=t末-30d
红线: REAL 30261104 零动; 引擎/tools 只读; 产物只落 data/ 与 research/; 翻闸走 chief R11; 1.0手去留 L5 报李彦明
"""
import os, json, datetime as dt
import numpy as np

ROOT = "E:/GoldstrategyEngine"
SYMS = ["XAUUSD", "EURUSD", "GBPUSD", "US30", "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"]
COST, COST_T5 = 0.095, 0.15
WINLO, WINHI = -3.0, 8.0
DAY30 = 30 * 86400
EQUITY, RISK_CAP = 989.29, 9.89


def rollmean(x, w):
    cs = np.concatenate(([0.0], np.cumsum(x)))
    e = np.arange(len(x)) + 1
    s = np.clip(e - w, 0, len(x))
    return (cs[e] - cs[s]) / np.maximum(e - s, 1)


def load(sym, tf):
    z = np.load(os.path.join(ROOT, "data", "tf_cache", f"{sym}_{tf}.npz"))
    out = {k: z[k] for k in ("t", "h", "l", "c") if k in z.files}
    o = np.empty_like(out["c"])
    o[0] = out["c"][0]
    o[1:] = out["c"][:-1]
    out["o"] = o
    z.close()
    return out


def prep(sym, tf):
    M = load(sym, tf)
    keep = M["t"] >= (M["t"][-1] - DAY30)
    M = {k: v[keep] for k, v in M.items()}
    N = len(M["t"])
    pc = np.concatenate(([M["c"][0]], M["c"][:-1]))
    tr = np.maximum(np.maximum(M["h"] - M["l"], np.abs(M["h"] - pc)), np.abs(M["l"] - pc))
    M["atr"] = rollmean(tr, 14)
    M["m5"], M["m20"] = rollmean(M["c"], 5), rollmean(M["c"], 20)
    up = M["h"] - np.concatenate(([M["h"][0]], M["h"][:-1]))
    dn = np.concatenate(([M["l"][0]], M["l"][:-1])) - M["l"]
    pj = np.where((up > dn) & (up > 0), up, 0.0)
    mj = np.where((dn > up) & (dn > 0), dn, 0.0)
    cp = np.concatenate(([0.0], np.cumsum(pj)))
    cm = np.concatenate(([0.0], np.cumsum(mj)))
    kk = np.arange(N)
    st = np.maximum(0, kk - 13)
    sp = cp[kk + 1] - cp[st]
    sm = cm[kk + 1] - cm[st]
    dd = sp + sm
    M["dx"] = np.where(dd > 0, np.abs(sp - sm) / np.maximum(dd, 1e-12) * 100.0, 0.0)
    M["body"] = np.abs(M["c"] - pc)
    M["rng"] = M["h"] - M["l"]
    M["up_m"] = M["c"] > pc
    M["down_m"] = M["c"] < pc
    hi, lo = M["h"].copy(), M["l"].copy()
    M["rng_hi"], M["rng_lo"] = np.zeros(N), np.zeros(N)
    for k in range(20, N):
        M["rng_hi"][k] = hi[k - 20:k].max()
        M["rng_lo"][k] = lo[k - 20:k].min()
    M["n"] = N
    M["end_ts"] = int(M["t"][-1])
    return M


def prep30_m15(sym):
    P = prep(sym, "M30")
    M = prep(sym, "M15")
    return P, M


def m15_start(M, t0):
    i = int(np.searchsorted(M["t"], t0, side="left"))
    return i if i < M["n"] else -1


def base_events(P, g):
    """M30 追突破 base 事件 (1114 gen_signals base 口径, 30d窗内, warmup>=20根)."""
    N = P["n"]
    kmask = np.arange(N) >= 20
    adx_ok = P["dx"] >= g["adx_min"]
    body_ok = np.where(P["atr"] > 0, P["body"] >= g["min_body"] * P["atr"], False)
    long_s = adx_ok & (P["c"] >= P["rng_hi"] - g["break_margin"] * P["atr"]) & (P["m5"] > P["m20"]) & P["up_m"] & body_ok & kmask
    short_s = adx_ok & (P["c"] <= P["rng_lo"] + g["break_margin"] * P["atr"]) & (P["m5"] < P["m20"]) & P["down_m"] & body_ok & kmask
    ev = []
    for k0, sig in ((np.nonzero(long_s)[0], 1), (np.nonzero(short_s)[0], -1)):
        for k0 in k0:
            e = k0 + 1
            if e >= N:
                continue
            a0 = max(P["atr"][k0], 1e-9)
            dist = min(g["sl_mult"], 1.2) * a0
            tp_d = min(max(g["tp_mult"] * a0, 2.0 * dist), 12.0 * a0)
            ev.append(dict(k=int(k0), e=int(e), s=sig, dist=dist, tp_d=tp_d,
                           t_entry=float(P["t"][e]), px=float(P["o"][e]), a15ref=a0))
    return ev


def sweep_events(M, g):
    """M15 扫掠确认进场事件: sweep>=0.15ATR15 + 收回 + 位移K实体>=70%(且>=0.3ATR15), 次根open进场, SL锚扫掠极值-0.3ATR15."""
    N = M["n"]
    a = M["atr"]
    ev = []
    for k in range(21, N - 3):
        a0 = max(a[k], 1e-9)
        # buy sweep: 外沿低穿前20根低点>=0.15ATR15 且 收回收回
        if M["l"][k] <= M["rng_lo"][k] - 0.15 * a0 and M["c"][k] > M["rng_lo"][k]:
            j = k + 1
            if M["up_m"][j] and M["body"][j] >= 0.7 * max(M["rng"][j], 1e-9) and M["body"][j] >= 0.3 * max(a[j], 1e-9):
                e = j + 1
                px = float(M["o"][e])
                sl = min(M["l"][k], M["l"][j]) - 0.3 * max(a[e], 1e-9)
                dist = float(np.clip(abs(px - sl), 0.5 * max(a[e], 1e-9), 2.0 * max(a[e], 1e-9)))
                tp_d = float(np.clip(max(2.0 * dist, g["tp_mult"] * a[e]), 2.0 * dist, 12.0 * a[e]))
                ev.append(dict(e=e, s=1, dist=dist, tp_d=tp_d, t_entry=float(M["t"][e]), px=px))
        # sell sweep: 外沿高穿前20根高点>=0.15ATR15 且 收回
        if M["h"][k] >= M["rng_hi"][k] + 0.15 * a0 and M["c"][k] < M["rng_hi"][k]:
            j = k + 1
            if M["down_m"][j] and M["body"][j] >= 0.7 * max(M["rng"][j], 1e-9) and M["body"][j] >= 0.3 * max(a[j], 1e-9):
                e = j + 1
                px = float(M["o"][e])
                sl = max(M["h"][k], M["h"][j]) + 0.3 * max(a[e], 1e-9)
                dist = float(np.clip(abs(px - sl), 0.5 * max(a[e], 1e-9), 2.0 * max(a[e], 1e-9)))
                tp_d = float(np.clip(max(2.0 * dist, g["tp_mult"] * a[e]), 2.0 * dist, 12.0 * a[e]))
                ev.append(dict(e=e, s=-1, dist=dist, tp_d=tp_d, t_entry=float(M["t"][e]), px=px))
    ev.sort(key=lambda x: x["e"])
    return ev


def replay_m15(M, evs, mode, cost=COST):
    """逐单 M15 出场回放. mode: 'A'现行(秒退双确认+BE棘轮) 'B'结构2连收(仅MFE<0.5R时) 'D'=C进场+B离场+A兜底(秒退同B但带BE棘轮)
    返回逐单 R(扣cost, winsor) + 离场类型 + 离场bar."""
    N = M["n"]
    o, h, l, c, atr, t = M["o"], M["h"], M["l"], M["c"], M["atr"], M["t"]
    evs = sorted(evs, key=lambda x: x["t_entry"])
    out_R, out_ty, out_ex = [], [], []
    prev_exit_bar = -1
    for ev in evs:
        i0 = int(np.searchsorted(t, ev["t_entry"], side="left"))
        if i0 < 0 or i0 >= N or i0 <= prev_exit_bar:
            continue
        s, px, dist, tp_d = ev["s"], ev["px"], ev["dist"], ev["tp_d"]
        e_d, SL, TP = px * s, px * s - dist, px * s + tp_d
        SL0, mfe_d, ext_d = SL, 0.0, SL
        Lmax = 36  # 18h硬平 = 36根M15 (交易小时口径, 美股session短=实际更短, 同分母一致)
        R, ty, ex_i, done = None, -1, None, False
        broke_prev = False
        struct_d = None
        i_end = min(i0 + Lmax, N - 1)
        for i in range(i0 + 1, i_end + 1):
            hi_d, lo_d, cl_d = h[i] * s, l[i] * s, c[i] * s
            mfe_d = max(mfe_d, hi_d - e_d)
            rng = max(h[i] - l[i], 1e-9)
            a_i = max(atr[i], 1e-9)
            # 结构位 = 运行结构 (多: 入场后M15低点运行最小; 空: 高点运行最大)
            seg = (l[i0 + 1:i + 1] * s).min() if s > 0 else (h[i0 + 1:i + 1] * s).max()
            broke = (cl_d < seg) if s > 0 else (cl_d > seg)
            r_now = (cl_d - e_d) / dist
            hit_sl = lo_d <= SL
            hit_tp = (not hit_sl) and hi_d >= TP
            early = False
            if mode == "A":
                early = broke and broke_prev and (i - i0) >= 2 and r_now <= -0.2
            else:  # B / D: 2连收破结构, MFE>=0.5R 持有不秒退
                early = broke and broke_prev and (mfe_d / dist) < 0.5
            if early:
                R, ty, ex_i, done = (cl_d - e_d) / dist - cost, 3, i, True
            elif hit_sl:
                px_x = min(SL, hi_d)
                R, ty, ex_i, done = (px_x - e_d) / dist - cost, 0, i, True
            elif hit_tp:
                R, ty, ex_i, done = (TP - e_d) / dist - cost, 1, i, True
            elif (i - i0) >= Lmax - 1:
                R, ty, ex_i, done = (cl_d - e_d) / dist - cost, 2, i, True
            if done:
                break
            # BE/棘轮兜底 (A 与 D 带, B 纯结构离场不带)
            if mode in ("A", "D"):
                r_ext = (ext_d - e_d) / dist if ext_d > e_d else 0.0
                cand = SL
                if r_ext >= 0.5:
                    cand = max(cand, e_d + 0.2 * dist)
                if r_ext >= 1.0:
                    cand = max(cand, ext_d - 0.8 * a_i)
                cand = max(cand, ext_d - 0.6 * dist) if (ext_d - e_d) / dist > 0 else cand
                SL = max(SL, cand) if (ext_d - e_d) > 0 else SL
            ext_d = max(ext_d, hi_d)
            broke_prev = broke
            if (i - i0) >= Lmax - 1:
                break
        if not done:
            i = i_end
            R, ty, ex_i = (c[i] * s - e_d) / dist - cost, 2, i
        out_R.append(float(np.clip(R, WINLO, WINHI)))
        out_ty.append(ty)
        out_ex.append(int(t[i]))
        prev_exit_bar = i
    Rr = np.array(out_R, dtype=float)
    n = len(Rr)
    ty_arr = np.array(out_ty, dtype=int)
    return dict(n=n, net=float(Rr.sum()) if n else 0.0, avg=float(Rr.mean()) if n else 0.0,
                win=float((Rr > 0).mean()) if n else 0.0, R=Rr,
                ex_t=np.array(out_ex, dtype=float), ty=ty_arr,
                n_struct=int((ty_arr == 3).sum()) if n else 0)


def five_gates(base, cand, cand015, cut_t):
    tr = cand["R"][cand["ex_t"] <= cut_t]
    te = cand["R"][cand["ex_t"] > cut_t]
    T1 = cand["net"] > 0 and cand["net"] >= base["net"]
    T2 = cand["win"] >= base["win"] - 0.02
    T3 = cand["n"] >= 5 and all(x.sum() > 0 for x in np.array_split(cand["R"], 5))
    T4 = (tr.sum() > 0) and (te.sum() > 0)
    T5 = cand015["net"] > 0
    g6 = cand["avg"] >= 1.0
    return dict(T1=bool(T1), T2=bool(T2), T3=bool(T3), T4=bool(T4), T5=bool(T5), g6=bool(g6),
                passed=int(T1) + int(T2) + int(T3) + int(T4) + int(T5) + int(g6),
                train_n=int(tr.size), train_net=round(float(tr.sum()), 2) if tr.size else None,
                test_n=int(te.size), test_net=round(float(te.sum()), 2) if te.size else None)


def verdict_of(gates):
    t15 = gates["passed"] - int(gates["g6"])
    if gates["passed"] == 6:
        return "APPROVE"
    if t15 >= 3 and (gates["T4"] or gates["T3"]):
        return "WATCH"
    return "REJECT"


def main():
    params = json.load(open(os.path.join(ROOT, "data", "practice_params_all_symbols.json"), encoding="utf-8"))
    ksrc, per_sym = {}, {}
    out_groups = {"A": {}, "B": {}, "C": {}, "D": {}}
    cand = {"B": {}, "C": {}, "D": {}}
    for sym in SYMS:
        P, M = prep30_m15(sym)
        p = params.get(sym, {})
        g = dict(adx_min=float(p.get("adx_min", 35.0)), break_margin=0.6, min_body=0.3,
                 sl_mult=float(p.get("sl_mult", 1.0)), tp_mult=float(p.get("tp_mult", 3.0)))
        ksrc[sym] = dict(M30_end=dt.datetime.utcfromtimestamp(P["end_ts"]).strftime("%m-%d %H:%M") + "Z",
                         M15_end=dt.datetime.utcfromtimestamp(M["end_ts"]).strftime("%m-%d %H:%M") + "Z",
                         src="MT5_LIVE npz 11-17回填", bars_M30=P["n"], bars_M15=M["n"])
        base_ev = base_events(P, g)
        sw_ev = sweep_events(M, g)
        rA = replay_m15(M, base_ev, "A")
        rB = replay_m15(M, base_ev, "B")
        rC = replay_m15(M, sw_ev, "B")          # C: 扫掠进场 + 结构离场
        rD = replay_m15(M, sw_ev, "D")          # D: 扫掠进场 + 结构离场 + BE兜底
        rB015 = replay_m15(M, base_ev, "B", cost=COST_T5)
        rC015 = replay_m15(M, sw_ev, "B", cost=COST_T5)
        rD015 = replay_m15(M, sw_ev, "D", cost=COST_T5)
        cut_t = float(np.quantile(np.concatenate([rA["ex_t"], np.full(1, M["end_ts"])]), 0.70)) if rA["n"] else M["end_ts"]
        for name, r in (("A", rA), ("B", rB), ("C", rC), ("D", rD)):
            out_groups[name][sym] = dict(n=r["n"], net=round(r["net"], 2), avg=round(r["avg"], 4),
                                         win=round(r["win"], 4), n_struct_exit=r.get("n_struct", None) if name != "A" else 0,
                                         ex_mix=dict(sl=int((r["ty"] == 0).sum()), tp=int((r["ty"] == 1).sum()),
                                                     cap=int((r["ty"] == 2).sum()), b0early=int((r["ty"] == 3).sum())))
        for name, r_c, r_c015 in (("B", rB, rB015), ("C", rC, rC015), ("D", rD, rD015)):
            gates = five_gates(rA, r_c, r_c015, cut_t)
            cand[name][sym] = dict(sym=sym, base_n=rA["n"], base_net=round(rA["net"], 2),
                                   cand_n=r_c["n"], cand_net=round(r_c["net"], 2),
                                   cand_avg_netR=round(r_c["avg"], 4), cand_win=round(r_c["win"], 4),
                                   cand_netR_015=round(r_c015["net"], 2), gates=gates,
                                   verdict=verdict_of(gates))
        print(sym, "A n=%d net=%.2f | B n=%d net=%.2f(%s) | C n=%d net=%.2f(%s) | D n=%d net=%.2f(%s)" % (
            rA["n"], rA["net"], rB["n"], rB["net"], cand["B"][sym]["verdict"],
            rC["n"], rC["net"], cand["C"][sym]["verdict"],
            rD["n"], rD["net"], cand["D"][sym]["verdict"]), flush=True)
    # ── 件2: 1.0手 M15 结构SL vs 现行SL ──
    orders = json.load(open(os.path.join(ROOT, "data", "rd_largelot_orders_mt5_20261117.json"), encoding="utf-8"))
    rows = orders["orders_1lot"]
    ent = {}
    for r in rows:
        if r["entry"] == "IN":
            ent[r["sym"]] = r
        elif r["entry"] == "OUT":
            ent.setdefault(r["sym"], {})["out"] = r
    struct_out = {}
    for sym, od in ent.items():
        if "out" not in od:
            continue
        out = od["out"]
        M = prep(sym.replace(".", "_"), "M15")
        t_in, px = int(od["time"]), float(od["px"])
        s = 1 if od["type"] == "BUY" else -1
        i0 = int(np.searchsorted(M["t"], t_in, side="left"))
        if i0 < 0 or i0 >= M["n"]:
            struct_out[sym] = dict(status="BLOCKED_DATA: M15窗口未覆盖开仓时刻", raw=od)
            continue
        # 入场前30根M15 5-bar分形摆动点: 多=入场价下方最近摆动低点(突破型进场的结构锚), 空=入场价上方最近摆动高点
        seg = slice(max(0, i0 - 30), i0 + 1)
        ll, hh = M["l"][seg], M["h"][seg]
        nseg = len(ll)
        cand_v, cand_note = [], []
        for a in range(2, nseg - 2):
            if s > 0 and ll[a] < ll[a - 1] and ll[a] < ll[a + 1] and ll[a] <= ll[a - 2] and ll[a] <= ll[a + 2] and ll[a] < px:
                cand_v.append((a, ll[a]))
            if s < 0 and hh[a] > hh[a - 1] and hh[a] > hh[a + 1] and hh[a] >= hh[a - 2] and hh[a] >= hh[a + 2] and hh[a] > px:
                cand_v.append((a, hh[a]))
        if cand_v:
            swing_v = cand_v[-1][1]
            swing_note = "入场前30根5-bar分形(正确侧: 多取入场下方最近摆动低点/空取上方高点)"
        else:
            swing_v = float(ll.min() if s > 0 else hh.max())
            swing_note = "无正确侧分形, 用30根极值兜底(可能仍偏侧)"
        a_e = max(float(M["atr"][i0]), 1e-9)
        sl_struct = swing_v - 0.3 * a_e if s > 0 else swing_v + 0.3 * a_e
        if (s > 0 and sl_struct >= px) or (s < 0 and sl_struct <= px):
            struct_out[sym] = dict(status="INVALID_ANCHOR: 结构SL在入场价错误一侧, 该单无有效结构锚(突破进场结构全在入场另一侧), 不编数, 挂账",
                                    entry_px=px, side=od["type"], swing_v=float(swing_v), sl_struct=round(sl_struct, 3))
            print(sym, "INVALID_ANCHOR", swing_note), flush=True
            continue
        sl_cur = float(od.get("sl") or 0)
        tp = od.get("tp")
        dist_cur = abs(px - sl_cur) if sl_cur else None
        # 回放: 现行臂 vs 结构臂 (同TP, 无18h帽, 至数据末端)
        def arm(sl_x, i_start):
            SLx, TPx = sl_x, (tp if tp else None)
            for i in range(i_start, M["n"]):
                hi, lo, cl = M["h"][i], M["l"][i], M["c"][i]
                if s > 0:
                    if lo <= SLx:
                        return ("SL", SLx, int(M["t"][i]))
                    if TPx and hi >= TPx:
                        return ("TP", TPx, int(M["t"][i]))
                else:
                    if hi >= SLx:
                        return ("SL", SLx, int(M["t"][i]))
                    if TPx and lo <= TPx:
                        return ("TP", TPx, int(M["t"][i]))
            return ("WINDEOF", float(M["c"][-1]), int(M["t"][-1]))
        a1 = arm(sl_cur, i0) if sl_cur else None
        a2 = arm(sl_struct, i0)
        def r_of(armx):
            if armx is None:
                return None
            kind, px_x, _ = armx
            d = dist_cur if dist_cur else abs(px - sl_struct)
            R = ((px_x - px) * s) / d - COST
            return dict(kind=kind, px=px_x, R=round(float(np.clip(R, WINLO, WINHI)), 4),
                        pnl_usd=round((px_x - px) * s * float(od.get("vol", 1.0)), 2))
        R1, R2 = r_of(a1), r_of(a2)
        risk_cur_usd = dist_cur * float(od.get("vol", 1.0)) if dist_cur else None
        risk_st_usd = abs(px - sl_struct) * float(od.get("vol", 1.0))
        struct_out[sym] = dict(
            entry=dt.datetime.utcfromtimestamp(t_in).strftime("%m-%d %H:%M") + "Z", px=px, side=od["type"], vol=od.get("vol"),
            actual_close=dt.datetime.utcfromtimestamp(int(out["time"])).strftime("%m-%d %H:%M") + "Z", actual_px=out["px"],
            actual_pnl=round(float(out["profit"]), 2),
            sl_cur=sl_cur, sl_struct=round(sl_struct, 3), swing_note=swing_note, atr15_at_entry=round(a_e, 4), tp=tp,
            arm_current=R1, arm_struct=R2,
            dR=round((R2["R"] - R1["R"]), 4) if R1 and R2 else None,
            risk_cur_usd=round(risk_cur_usd, 2) if risk_cur_usd else None,
            risk_struct_usd=round(risk_st_usd, 2),
            cap_1pct=round(risk_st_usd, 2) <= RISK_CAP,
            cap_note=("超帽" if (risk_st_usd or 0) > RISK_CAP else "帽内") + " @%.2f美元上限" % RISK_CAP)
        print(sym, struct_out[sym]["sl_struct"], "vs", sl_cur, "dR=", struct_out[sym]["dR"], flush=True)
    out = dict(
        meta=dict(ts=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                  window="30d (t末-30d)", cost=COST, cost_t5=COST_T5, oos="70/30时间切", gate6=1.0,
                  kline_source=ksrc,
                  protocol="同分母: 件1 A/B 同M30追突破事件集(8主流, 30d), C/D 同M15扫掠确认事件集; 件2 同4单开仓点; 滑点0.095R; 五验T1-T5+⑥线1.0; 逐品种裁定禁跨品种平均",
                  b0_evidence="loss30d_20261117.json: B0_INVAL 52笔0赢-70.09, 横跨38品种, 0笔SL=全被B0提前离场; 11-14量能闸后零复发",
                  real_account_untouched="REAL 30261104 零动; 引擎 jince_live24.py/tools 只读; 0下单; 翻闸走chief R11"),
        groups=out_groups, candidates=cand,
        largelot_m15_struct_sl=struct_out,
        largelot_meta=dict(equity=EQUITY, risk_cap_1pct=RISK_CAP,
                           source="data/rd_largelot_orders_mt5_20261117.json (MT5 60137964 history_deals 实读)",
                           note="dR=结构臂净R-现行臂净R(同分母=现行SL距离); 1.0手去留=L5报李彦明, 本件只出结论; n=4小样本=WATCH级证据"),
    )
    with open(os.path.join(ROOT, "data", "rd_verify_batch_b0exit_20261117.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=float)
    print("DONE data/rd_verify_batch_b0exit_20261117.json")


if __name__ == "__main__":
    main()
