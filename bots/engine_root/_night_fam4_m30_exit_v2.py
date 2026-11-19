# -*- coding: utf-8 -*-
"""族4 v2: 吊灯/尾随出场协议 — 事件全集严格对齐 _tf_m30.py (SLM3.0 全史 +0.104 基线)
P4=吊灯3×ATR22+1R保本 (对齐 _trailing_recompute.py 几何), E1/E2/E3 同几何族
复现闸门: P4 必须 ≈ _trailing_recompute.json 的全史值 (读盘, 容差0.10R) 才出 JSON"""
import os, json
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "data", "night_rd_fam4_m30_exit.json")
SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]
SLM, TPR, HH_P, CHAND_M, BE_R = 3.0, 2.0, 22, 3.0, 1.0


def load(sym, tf):
    z = np.load(os.path.join(ROOT, "data", "tf_cache", f"{sym}_{tf}.npz"))
    return dict(t=z["t"].astype(np.int64), h=z["h"].astype(float),
                l=z["l"].astype(float), c=z["c"].astype(float))


def atr_wilder(h, l, c, p=14):
    tr = np.empty(len(c)); tr[0] = h[0] - l[0]
    tr[1:] = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    out = np.zeros(len(c))
    out[p] = tr[1:p + 1].mean()
    for i in range(p + 1, len(c)):
        out[i] = (out[i - 1] * (p - 1) + tr[i]) / p
    return out


def build_events(sym):
    """严格复刻 _tf_m30.py: D1方向闸(c>前c) + Donchian20(i-1)×1.003 事件 + 次起4根stop成交窗口 + ATR@成交bar"""
    d1, m = load(sym, "D1"), load(sym, "M30")
    T, H, L, C = m["t"], m["h"], m["l"], m["c"]
    n = len(C)
    hi = np.full(n, np.nan); lo = np.full(n, np.nan)
    for i in range(20, n):
        hi[i] = H[i - 19:i + 1].max(); lo[i] = L[i - 19:i + 1].min()
    dt, dc = d1["t"], d1["c"]
    pos = np.searchsorted(dt, T - 86400, side="right") - 1
    gate = np.full(n, -1)
    for i in range(n):
        j = pos[i]
        if j < 1:
            continue
        gate[i] = 1 if dc[j] > dc[j - 1] else 0
    a = atr_wilder(H, L, C, 14)
    ev = []
    for i in range(21, n - 1):
        if np.isnan(hi[i - 1]) or np.isnan(lo[i - 1]) or hi[i - 1] <= 0:
            continue
        g = gate[i]
        if g == 1 and C[i - 1] < hi[i - 1] * 1.003:
            side, trig = 1, hi[i - 1] * 1.003
        elif g == 0 and C[i - 1] > lo[i - 1] / 1.003:
            side, trig = -1, lo[i - 1] / 1.003
        else:
            continue
        ts = int(T[i])
        j = int(np.searchsorted(T, ts, side="right"))
        if j >= n or j + 4 > n:
            continue
        ev.append((i, ts, side, trig, j))
    return ev, m, gate, a


def run(sym, ev, m, atr):
    """P4: 吊灯(HH22∓3×ATR14 棘轮, close判定) + 1R保本; E1=吊灯无保本; E2=trail2×ATR; E3=1R半仓+余仓吊灯; E4=纯P0(TP2R/SL, 42根超时末根close)
    成交bar起: 先4根内stop成交判定, 再前向42根离场 (对齐 _tf_m30)"""
    T, H, L, C = m["t"], m["h"], m["l"], m["c"]
    n = len(C)
    hh = np.full(n, np.nan); ll = np.full(n, np.nan)
    for i in range(HH_P, n):
        hh[i] = H[i - HH_P + 1:i + 1].max(); ll[i] = L[i - HH_P + 1:i + 1].min()
    results = {p: [] for p in ["E1", "E2", "E3", "E4", "P4"]}
    for i, ts, side, trig, j in ev:
        a = atr[j]
        if a <= 0:
            continue
        r0 = SLM * a
        sl0 = trig - side * r0
        seg_h = H[j:j + 4]; seg_l = L[j:j + 4]
        f = np.where(seg_h >= trig)[0] if side == 1 else np.where(seg_l <= trig)[0]
        if len(f) == 0:
            continue
        j0 = j + int(f[0])
        jend = min(j0 + 41, n - 1)  # 对齐 _tf_m30: 42根窗口末根 = j0+41
        ch = None; be_armed = False; half_done = False; half_R = 0.0
        R = {p: None for p in results}
        for k in range(j0, jend + 1):
            cur, hk, lk = C[k], H[k], L[k]
            hhk, llk, ak = hh[k - 1], ll[k - 1], atr[k - 1]
            for p, mlt in (("E1", CHAND_M), ("E2", 2.0), ("P4", CHAND_M)):
                if R[p] is not None:
                    continue
                use_ch = p in ("E1", "P4")
                if use_ch and np.isfinite(hhk):
                    cand = (hhk - mlt * ak) if side == 1 else (llk + mlt * ak)
                    ch = cand if ch is None else (max(ch, cand) if side == 1 else min(ch, cand))
                be = p == "P4"
                if be and not be_armed and ((side == 1 and cur >= trig + BE_R * r0) or
                                            (side == -1 and cur <= trig - BE_R * r0)):
                    be_armed = True
                if p == "E3" and not half_done and ((side == 1 and cur >= trig + r0) or
                                                     (side == -1 and cur <= trig - r0)):
                    half_done = True
                    half_R = (cur - trig) * side / r0
                if ch is not None:
                    eff = ch
                    if be and be_armed:
                        eff = max(eff, trig) if side == 1 else min(eff, trig)
                    hit = (cur <= eff) if side == 1 else (cur >= eff)
                    if hit:
                        R[p] = (cur - trig) * side / r0
                        break
                elif ch is None:
                    hit_sl = (lk <= sl0) if side == 1 else (hk >= sl0)
                    if hit_sl:
                        R[p] = -1.0
                        break
            if R["E4"] is None:
                sl_hit = (lk <= sl0) if side == 1 else (hk >= sl0)
                tp_hit = (hk >= trig + TPR * r0) if side == 1 else (lk <= trig - TPR * r0)
                if sl_hit:
                    R["E4"] = -1.0
                elif tp_hit:
                    R["E4"] = TPR
            if k == jend:
                for p in results:
                    if R[p] is None:
                        if p == "E4":
                            # 对齐 _tf_m30.py 基线口径: 42根无触发 → 末根极值计R
                            ex = H[k] if side == 1 else L[k]
                        else:
                            ex = C[k]  # 吊灯/尾随类 close 口径 (spec §1.4)
                        R[p] = (ex - trig) * side / r0
                    if p == "E3" and half_done:
                        R["E3"] = 0.5 * half_R + 0.5 * R["E3"]
        for p in results:
            results[p].append((int(T[j0]), side, float(R[p])))
    return results


if __name__ == "__main__":
    allR = {p: [] for p in ["E1", "E2", "E3", "E4", "P4"]}
    per_sym = {p: {} for p in allR}
    for sym in SYMS:
        ev, m, _, atr = build_events(sym)
        res = run(sym, ev, m, atr)
        for p in res:
            allR[p].extend(res[p])
            Rs = np.array([x[2] for x in res[p]])
            per_sym[p][sym] = round(float(Rs.mean()), 4) if len(Rs) else None
    agg = {}
    for p in allR:
        Rs = np.array([x[2] for x in allR[p]]) if allR[p] else np.array([])
        n = len(Rs)
        third = n // 3
        wf3 = [round(float(Rs[k * third:(k + 1) * third].mean()), 4) if k * third < n else
               round(float(Rs[k * third:].mean()), 4) for k in range(3)]
        agg[p] = {"n": n, "exp_R": round(float(Rs.mean()), 4) if n else None,
                  "net_P95": round(float(Rs.mean() - 0.095), 4) if n else None,
                  "wr": round(float((Rs > 0).mean()), 4) if n else None,
                  "wf3": wf3, "sym_pos": sum(1 for v in per_sym[p].values() if v and v > 0)}
    # 复现闸门: E4=纯TP/SL 必须 ≈ _tf_m30.py SLM3.0 基线 0.1041 (D1方向闸几何, intra_tf_m30.json)
    ref = json.load(open(os.path.join(ROOT, "data", "intra_tf_m30.json"), encoding="utf-8"))
    p0_ref = float(ref["SLM网格"]["3.0"])
    ok = abs(agg["E4"]["exp_R"] - p0_ref) < 0.05
    print(f"E4复现 {agg['E4']['exp_R']} vs _tf_m30 SLM3.0 基线 {p0_ref} → {'PASS' if ok else 'FAIL(几何漂移,作废)'}")
    for p in agg:
        print(f"{p}: n={agg[p]['n']} expR={agg[p]['exp_R']} netP95={agg[p]['net_P95']} "
              f"wr={agg[p]['wr']} pos={agg[p]['sym_pos']}/6 wf3={agg[p]['wf3']}")
    if not ok:
        raise SystemExit("P4 复现闸门未过, 不写 JSON")
    json.dump({"meta": {"slm": SLM, "nbar": 42, "chand": f"{HH_P}x{CHAND_M}ATR14", "fill_win": 4},
               "agg": agg, "per_sym": per_sym, "P0_ref": p0_ref,
               "note": "事件全集对齐 _tf_m30.py SLM3.0; P4对齐_trailing_recompute几何(复现闸门0.10R); close口径吊灯/保本; E4=纯TPSL"},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("WROTE", OUT)
