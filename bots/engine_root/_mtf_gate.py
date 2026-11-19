# -*- coding: utf-8 -*-
# MTF gate probe: M30 回放 Donchian20x1.003 突破事件 + SLM3.0, 高级别偏置门
# G1_D1偏置 / G2_H4偏置 / G3_D1+H4双偏置 / G4_周线状态机
# 铁律: 同分母(闸只删事件不造新事件, 报告被删比例), SELL镜像自检, close口径, 扣0.5R滑点
import json, os
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
TC = os.path.join(ROOT, "data", "tf_cache")
SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]
SLM = 3.0
LOOK_AHEAD = 42   # 前向42根M30
FILL_WINDOW = 4   # stop单当期4根内成交
SLIP = 0.5        # 滑点 R
BASELINE = 0.104  # P0_无门 + SLM3.0 基线

def load(sym, tf):
    d = np.load(os.path.join(TC, f"{sym}_{tf}.npz"))
    return dict(t=d["t"].astype(np.int64), o=d["o"].astype(float),
                h=d["h"].astype(float), l=d["l"].astype(float), c=d["c"].astype(float))

def ema(x, p):
    out = np.empty_like(x, dtype=float)
    a = 2.0 / (p + 1)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out

def donchian20(h, l):
    n = len(h)
    hi = np.full(n, np.nan); lo = np.full(n, np.nan)
    for i in range(20, n):
        hi[i] = h[i-20:i].max(); lo[i] = l[i-20:i].min()
    return hi, lo

def atr_wilder(h, l, c, p=14):
    tr = np.empty(len(c)); tr[0] = h[0] - l[0]
    tr[1:] = np.maximum(h[1:] - l[1:],
                        np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    out = np.zeros(len(c))
    out[p] = tr[1:p+1].mean()
    for i in range(p+1, len(c)):
        out[i] = (out[i-1]*(p-1) + tr[i]) / p
    return out

def prepare(sym):
    """M30 事件 + 门标签. 高级别 close口径: 事件ts处最近已完结bar."""
    m, d1, h4 = load(sym, "M30"), load(sym, "D1"), load(sym, "H4")
    hi, lo = donchian20(m["h"], m["l"])
    atr = atr_wilder(m["h"], m["l"], m["c"])
    th, tl, tc, tt = m["h"], m["l"], m["c"], m["t"]

    # 高级别 close vs EMA20 → 偏好方向 (+1 / -1 / 0未决), 向量化: 每根bar完结时间
    def bias_series(data, ema20, step):
        c, t = data["c"], data["t"]
        pref = np.sign(c - ema20).astype(int)
        end_time = t + step          # bar完结时间
        return end_time, pref

    d1_e, d1_p = bias_series(d1, ema(d1["c"], 20), 86400)
    h4_e, h4_p = bias_series(h4, ema(h4["c"], 20), 14400)
    # G4: D1 50EMA 斜率(5根) 向上=趋势市(1), 向下=震荡市(0)
    e50 = ema(d1["c"], 50)
    slope_up = np.zeros(len(d1["c"]), dtype=bool)
    slope_up[5:] = e50[5:] > e50[:-5]
    d1_slope_end = d1["t"] + 86400

    evs = []
    for i in range(21, len(tt)):
        if np.isnan(hi[i-1]) or np.isnan(lo[i-1]) or hi[i-1] <= 0:
            continue
        ts = int(tt[i])
        if tc[i-1] < hi[i-1] * 1.003:
            side, trig = 1, hi[i-1] * 1.003
        elif tc[i-1] > lo[i-1] / 1.003:
            side, trig = -1, lo[i-1] / 1.003
        else:
            continue
        j = int(np.searchsorted(d1_e, ts, side="left")) - 1
        g1 = d1_p[j] if j >= 0 else 0
        j2 = int(np.searchsorted(h4_e, ts, side="left")) - 1
        g2 = h4_p[j2] if j2 >= 0 else 0
        j3 = int(np.searchsorted(d1_slope_end, ts, side="left")) - 1
        g4 = int(slope_up[j3]) if j3 >= 0 else 0   # 未决保守=震荡市(关)
        a = atr[i] if atr[i] > 0 else 1e-9
        evs.append((ts, side, float(trig), g1, g2, g4, float(a)))
    return evs, m

def fills_for(sym, evs, m, gate):
    """gate: np数组(与evs同长) 0/1. 返回 [(ts, side, R), ...] 按事件序."""
    th, tl, tt = m["h"], m["l"], m["t"]
    out = []
    for idx, (ts, side, trig, g1, g2, g4, a) in enumerate(evs):
        if not gate[idx]:
            continue
        j = int(np.searchsorted(tt, ts, side="right"))
        if j >= len(tt) or j + FILL_WINDOW > len(tt):
            continue
        sl = trig - SLM * a if side == 1 else trig + SLM * a
        r0 = abs(trig - sl)
        if r0 <= 0:
            continue
        tp = trig + 2 * r0 if side == 1 else trig - 2 * r0
        seg_h = th[j:j+FILL_WINDOW]; seg_l = tl[j:j+FILL_WINDOW]
        f = np.where(seg_h >= trig)[0] if side == 1 else np.where(seg_l <= trig)[0]
        if len(f) == 0:
            continue
        fidx = int(f[0])
        seg_h2 = th[j:j+LOOK_AHEAD]; seg_l2 = tl[j:j+LOOK_AHEAD]
        res = None
        for k in range(fidx, len(seg_h2)):
            hh, ll = seg_h2[k], seg_l2[k]
            if side == 1:
                if ll <= sl:
                    res = -1.0; break
                if hh >= tp:
                    res = 2.0; break
            else:
                if hh >= sl:
                    res = -1.0; break
                if ll <= tp:
                    res = 2.0; break
        if res is None:
            exit_px = float(seg_h2[-1]) if side == 1 else float(seg_l2[-1])
            res = (exit_px - trig) / r0 if side == 1 else (trig - exit_px) / r0
        out.append((ts, side, float(res), sym))
    return out

def stats(fills, n_ev_kept, n_ev_total):
    """fills: [(ts, side, R, sym)...] 已按 ts 升序."""
    Rs = np.array([f[2] for f in fills])
    n_fill = len(Rs)
    expR = round(float(Rs.mean()), 4) if n_fill else None
    wr = round(float((Rs > 0).mean()), 4) if n_fill else None
    per_sym = {}
    for sym in SYMS:
        r = np.array([f[2] for f in fills if f[3] == sym])
        per_sym[sym] = round(float(r.mean()), 4) if len(r) else None
    # wf3 按成交时间均分
    wf = {}
    if n_fill:
        tmin, tmax = fills[0][0], fills[-1][0]
        third = (tmax - tmin) / 3.0
        for k in range(3):
            lo_t, hi_t = (tmin if k == 0 else tmin + k * third,
                          tmin + (k+1) * third if k < 2 else tmax + 1)
            seg = np.array([f[2] for f in fills if lo_t <= f[0] < hi_t])
            wf[str(k+1)] = {"n": int(len(seg)),
                            "exp_R": round(float(seg.mean()), 4) if len(seg) else None,
                            "dir": ("+" if len(seg) and seg.mean() > 0
                                    else ("-" if len(seg) and seg.mean() < 0 else "0"))}
    else:
        wf = {str(k+1): {"n": 0, "exp_R": None, "dir": "0"} for k in range(3)}
    # 对称自检: 多/空 fills 各≥30% 且 exp_R 差<0.5R
    b = np.array([f[2] for f in fills if f[1] == 1])
    s = np.array([f[2] for f in fills if f[1] == -1])
    eb = float(b.mean()) if len(b) else 0.0
    es = float(s.mean()) if len(s) else 0.0
    symm_pass = bool(len(b) > 0 and len(s) > 0
                     and len(b) >= 0.3 * n_fill and len(s) >= 0.3 * n_fill
                     and abs(eb - es) < 0.5)
    return {
        "放行事件比例": round(n_ev_kept / n_ev_total, 4) if n_ev_total else 0,
        "n_kept_events": int(n_ev_kept),
        "n_deleted_events": int(n_ev_total - n_ev_kept),
        "n_fills": int(n_fill),
        "exp_R": expR,
        "wr": wr,
        "exp_R_slip0.5": round(expR - SLIP, 4) if expR is not None else None,
        "delta_vs_P0": round(expR - BASELINE, 4) if expR is not None else None,
        "wf3": {k: wf[k]["dir"] for k in wf},
        "wf3_detail": wf,
        "per_sym": per_sym,
        "对称自检pass": symm_pass,
        "对称明细": {"多n": int(len(b)), "多expR": round(eb, 4),
                    "空n": int(len(s)), "空expR": round(es, 4)},
    }

def main():
    data = {sym: prepare(sym) for sym in SYMS}
    evs_by_sym = {sym: data[sym][0] for sym in SYMS}
    m_by_sym = {sym: data[sym][1] for sym in SYMS}
    n_ev_total = sum(len(v) for v in evs_by_sym.values())

    def make_gate(gname, evs_all, evs_by_sym):
        gates = {}
        gates["P0_无门"] = np.ones(sum(len(v) for v in evs_by_sym.values()), dtype=bool)
        for g in ["G1_D1偏置", "G2_H4偏置", "G3_D1H4双偏置", "G4_周线状态机"]:
            g_arr = np.ones(sum(len(v) for v in evs_by_sym.values()), dtype=bool)
            off = 0
            for sym in SYMS:
                evs = evs_by_sym[sym]
                n = len(evs)
                seg = np.array([[e[3], e[4], e[5], e[1]] for e in evs])
                g1, g2, g4, side = seg[:, 0], seg[:, 1], seg[:, 2], seg[:, 3]
                if g == "G1_D1偏置":
                    ok = (g1 == side) & (g1 != 0)
                elif g == "G2_H4偏置":
                    ok = (g2 == side) & (g2 != 0)
                elif g == "G3_D1H4双偏置":
                    ok = (g1 == side) & (g2 == side) & (g1 != 0) & (g2 != 0)
                else:  # G4: 趋势市(50EMA斜率上)全放行, 震荡市全拒
                    ok = (g4 == 1)
                g_arr[off:off+n] = ok
                off += n
            gates[g] = g_arr
        return gates

    gate_arrays = make_gate(None, None, evs_by_sym)
    out = {"SLM": SLM, "LOOK_AHEAD": LOOK_AHEAD, "FILL_WINDOW": FILL_WINDOW,
           "slip_R": SLIP, "基线_P0无门预期exp_R": BASELINE,
           "n_events_total": int(n_ev_total), "gates": {}}
    fills_cache = {}
    for gname, garr in gate_arrays.items():
        off = 0
        all_fills = []
        n_kept = 0
        for sym in SYMS:
            evs = evs_by_sym[sym]
            n = len(evs)
            seg = garr[off:off+n]
            fills = fills_for(sym, evs, m_by_sym[sym], seg)
            all_fills.extend(fills)
            n_kept += int(seg.sum())
            off += n
        all_fills.sort(key=lambda x: x[0])
        st = stats(all_fills, n_kept, n_ev_total)
        out["gates"][gname] = st
    p0 = out["gates"]["P0_无门"]
    out["基线_P0无门实际exp_R"] = p0["exp_R"]
    winners = {}
    for g in ["G1_D1偏置", "G2_H4偏置", "G3_D1H4双偏置", "G4_周线状态机"]:
        v = out["gates"][g]
        d = v["delta_vs_P0"]
        wf_pos = all(v["wf3"][str(k)] == "+" for k in [1, 2, 3])
        slip_pos = v["exp_R_slip0.5"] is not None and v["exp_R_slip0.5"] > 0
        winners[g] = bool(d is not None and d >= 0.05 and wf_pos and slip_pos)
    out["winners"] = winners
    wnames = [g for g, ok in winners.items() if ok]
    if wnames:
        verdict = "通过门: " + "+".join(wnames) + " (Δ≥0.05R且三段全正且扣0.5R滑点后仍正)"
    else:
        verdict = "无门通过: G1~G4 均未达 Δ≥0.05R 或三段不全正或扣滑点后转负; P0无门 exp_R=" + str(p0["exp_R"])
    out["verdict"] = verdict
    out["sym_pass"] = bool(p0["对称自检pass"])
    p = os.path.join(ROOT, "data", "mtf_gate.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False))

if __name__ == "__main__":
    main()
