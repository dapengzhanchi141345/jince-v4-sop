# -*- coding: utf-8 -*-
"""pdd_direction_gate_reverify 认领: 候选"动量否决门"同分母复验.
基座 = 族4 M30 腿 D1 方向闸事件全集 (_night_fam4_m30_exit.build/replay, P4 协议).
同分母铁律: 全部事件重算, 按 24h 动量与事件侧(=D1 闸方向, 即系统方向代理)顺/逆分桶.
  动量 = 事件成交bar前 48 根 M30 (24h) 收盘变化, 严格用 j-1 及以前数据(防前视).
  顺桶 agree: side==1 且 mom>0 / side==-1 且 mom<0; 逆桶 contra: 相反.
判据: Δ=expR(contra)-expR(agree), two-proportion z(胜率), 品种稳健>=4/6 同号,
      wf3 三段稳定; 任一桶 n<30 不判. 未过 -> 该腿留 WATCH, 不进 live.
纯读 tf_cache, 不连 MT5, 不碰交易配置."""
import sys, os, json, math
import numpy as np
ROOT = r"E:\GoldstrategyEngine"
sys.path.insert(0, ROOT)
import _night_fam4_m30_exit as fam4

SYMS = fam4.SYMS  # 6 币宇宙
CF = os.path.join(ROOT, "data", "tf_cache")
OUT = os.path.join(ROOT, "data", "rd_verify_batch_pdd_momgate.json")
THR = 0.0  # 主桶: 动量反向任意幅度即 contra; 敏感性档另算


def z_two_prop(n1, w1, n2, w2):
    """w 为胜笔数(int), 返回 z 与合并p. 两比例 z 检验. z>0 = agree桶胜率更高."""
    if n1 == 0 or n2 == 0:
        return None, None
    p1, p2 = w1 / n1, w2 / n2
    p = (w1 + w2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se <= 0:
        return None, p
    return (p1 - p2) / se, p


def replay_p4_with_i0(ev, ctx):
    """fam4.replay('P4') 副本, 额外输出事件bar i0 (动量锚点, 防前视: 只用 i0 之前数据)."""
    T, H, L, C = ctx["T"], ctx["H"], ctx["L"], ctx["C"]
    atr, hh, ll, n = ctx["atr"], ctx["hh"], ctx["ll"], ctx["n"]
    K_CH, K_TR, BE_R, NBAR, FILL_WIN, SLM = (fam4.K_CH, fam4.K_TR, fam4.BE_R,
                                              fam4.NBAR, fam4.FILL_WIN, fam4.SLM)
    out = []
    for i0, ts, trig, side in ev:
        j = int(np.searchsorted(T, ts, side="right"))
        if j >= n or j + FILL_WIN > n:
            continue
        a = atr[j] if atr[j] > 0 else 1e-9
        r0 = SLM * a
        sl0 = trig - side * r0
        seg = H[j:j + FILL_WIN] if side == 1 else L[j:j + FILL_WIN]
        f = np.where(seg >= trig)[0] if side == 1 else np.where(seg <= trig)[0]
        if len(f) == 0:
            continue
        j0 = j + int(f[0])
        jend = min(j0 + NBAR, n)
        ch = None
        be_armed = False
        R = None
        for k in range(j0, jend):
            cur = C[k]
            hk, lk = H[k], L[k]
            hhk, llk, ak = hh[k - 1], ll[k - 1], atr[k - 1]
            if np.isfinite(hhk) and hhk > 0:
                if side == 1:
                    cand = hhk - K_CH * ak
                    ch = cand if ch is None else max(ch, cand)
                else:
                    cand = llk + K_CH * ak
                    ch = cand if ch is None else min(ch, cand)
            if not be_armed and ((side == 1 and cur >= trig + BE_R * r0) or
                                 (side == -1 and cur <= trig - BE_R * r0)):
                be_armed = True
            eff = sl0
            if be_armed:
                eff = max(eff, trig) if side == 1 else min(eff, trig)
            if ch is not None:
                eff = max(eff, ch) if side == 1 else min(eff, ch)
            if ch is None and not be_armed:
                hit = (lk <= sl0) if side == 1 else (hk >= sl0)
                if hit:
                    R = -1.0
                    break
            else:
                hit = (cur <= eff) if side == 1 else (cur >= eff)
                if hit:
                    R = (cur - trig) * side / r0
                    break
            if k == jend - 1:
                R = (cur - trig) * side / r0
        if R is None:
            R = (C[jend - 1] - trig) * side / r0
        out.append((i0, int(T[j0]), side, float(R)))
    return out


def main():
    rows = []  # (sym, ts_fill, R, side, mom, agree)
    for sym in SYMS:
        ev, ctx = fam4.build(sym)
        m30 = fam4.load(sym, "M30")
        T, C = m30["t"], m30["c"]
        res = replay_p4_with_i0(ev, ctx)
        mommap = {}
        for i0, ts, trig, side in ev:
            if i0 < 49:
                continue
            mom = (C[i0 - 1] - C[i0 - 49]) / C[i0 - 49]  # 事件bar锚点, 只用 i0-1 及以前 (防前视)
            mommap[i0] = float(mom)
        for i0, t_fill, side, R in res:
            mom = mommap.get(i0)
            if mom is None:
                continue
            agree = (side == 1 and mom >= 0) or (side == -1 and mom <= 0)
            rows.append((sym, int(t_fill), float(R), side, mom, bool(agree)))
    A = [r for r in rows if r[5]]
    X = [r for r in rows if not r[5]]
    nA, nX = len(A), len(X)
    RA = np.array([r[2] for r in A]); RX = np.array([r[2] for r in X])
    wA = int((RA > 0).sum()); wX = int((RX > 0).sum())
    expA = float(RA.mean()) if nA else None
    expX = float(RX.mean()) if nX else None
    z, ppool = z_two_prop(nA, wA, nX, wX)  # z>0 = agree桶胜率更高 = veto有利
    delta = (expX - expA) if (expA is not None and expX is not None) else None
    # 品种稳健: 每品种 veto 有利 = 该品种 contra 桶 exp_R <= agree 桶 (delta_sym<=0), 6/6 中 >=4 同号
    per_sym = {}
    for s in SYMS:
        sa = [r[2] for r in A if r[0] == s]; sx = [r[2] for r in X if r[0] == s]
        if not sa or not sx:
            per_sym[s] = {"n_agree": len(sa), "n_contra": len(sx), "delta": None, "supports_veto": None}
            continue
        da, dx = float(np.mean(sa)), float(np.mean(sx))
        per_sym[s] = {"n_agree": len(sa), "n_contra": len(sx), "exp_agree": round(da, 4),
                      "exp_contra": round(dx, 4), "delta": round(dx - da, 4),
                      "supports_veto": bool(dx <= da)}
    ts_all = np.array([r[1] for r in rows])
    R_all = np.array([r[2] for r in rows])
    ag_all = np.array([r[5] for r in rows])
    wf = []
    for k in range(3):
        lo = ts_all.min() + (ts_all.max() - ts_all.min()) * k / 3
        hi = ts_all.min() + (ts_all.max() - ts_all.min()) * (k + 1) / 3
        sel = (ts_all >= lo) & (ts_all < hi) if k < 2 else (ts_all >= lo)
        a_sel = R_all[sel & ag_all]; x_sel = R_all[sel & ~ag_all]
        wf.append(round(float(x_sel.mean() - a_sel.mean()), 4) if len(a_sel) and len(x_sel) else None)
    # 敏感性: 动量幅度档 (|mom|>=thr 的 contra 桶, 动量越强 veto 越该拦)
    sens = {}
    for thr in (0.01, 0.02, 0.03):
        sel = np.array([abs(r[4]) >= thr and not r[5] for r in rows])
        sens["contra_>=%.0f_pct" % (thr * 100)] = {"n": int(sel.sum()),
                                                    "exp_R": round(float(R_all[sel].mean()), 4) if sel.sum() else None}
    out = {
        "item": "pdd_direction_gate_reverify", "owner": "strategy-rd",
        "hypo": "候选动量否决门: 24h 动量与系统方向(D1闸侧)冲突的单降 WATCH 不追",
        "base": "族4 M30 D1方向闸腿事件全集 x P4协议 replay, 6币宇宙, 同分母重算",
        "mom_anchor": "事件bar i0 前48根M30收盘变化(严格防前视, 不用成交bar), agree=动量顺D1侧",
        "n_total": len(rows), "n_agree": nA, "n_contra": nX,
        "exp_R_agree": round(expA, 4) if expA is not None else None,
        "exp_R_contra": round(expX, 4) if expX is not None else None,
        "delta_contra_minus_agree": round(delta, 4) if delta is not None else None,
        "wr_agree": round(wA / nA, 4) if nA else None, "wr_contra": round(wX / nX, 4) if nX else None,
        "z_two_prop": round(z, 3) if z is not None else None,
        "z_meaning": "z>0 = agree桶胜率更高 = veto有利",
        "sym_supports_veto": {s: v["supports_veto"] for s, v in per_sym.items()},
        "sym_pass_ge4of6": sum(1 for v in per_sym.values() if v["supports_veto"] is True),
        "per_sym": per_sym, "wf3_delta": wf, "sens_abs_mom": sens,
        "instances_n3": "PDD.NAS/TAOUSD/KSMUSD 3实例 n<30 不单独判, 只作方向旁证(同分母铁律)",
    }
    # 五验: veto 有利 = contra 桶比 agree 桶差 (delta<0, z>0, wf3 各段 delta<0)
    n_ok = (nA >= 30 and nX >= 30)
    d_ok = delta is not None and delta < 0
    z_ok = z is not None and z >= 1.96
    sym_ok = out["sym_pass_ge4of6"] >= 4
    wf_ok = all(v is not None and v < 0 for v in wf)
    out["five_checks"] = {"样本>=30": n_ok, "同分母delta<0(contra更差)": d_ok, "z>=1.96": z_ok,
                           "品种稳健>=4/6": sym_ok, "wf3三段delta全<0": wf_ok}
    out["verdict"] = ("PASS->动量否决门可提WATCH提权(5/5)" if all(out["five_checks"].values())
                      else "REJECT->留WATCH, 不动live")
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: out[k] for k in ("n_total", "n_agree", "n_contra", "exp_R_agree",
                                          "exp_R_contra", "delta_contra_minus_agree",
                                          "wr_agree", "wr_contra", "z_two_prop",
                                          "sym_pass_ge4of6", "wf3_delta",
                                          "five_checks", "verdict")},
                     ensure_ascii=False, indent=1))
    print("per_sym:", json.dumps(per_sym, ensure_ascii=False))


if __name__ == "__main__":
    main()
