# -*- coding: utf-8 -*-
"""族4 M30趋势腿出场协议专项 (服务趋势腿正格)
事件全集同 _tf_m30.py: Donchian20×1.003 stop成交 + D1方向闸, SLM=3.0.
先复现 P4(滚动22极值∓3×ATR14 棘轮单调 + 1R保本, close判定)≈-0.813 (铁律, 防几何漂移),
再测 E1 吊灯无TP(42根截断) / E2 trail 2×ATR14无TP / E3 1R半仓+余仓吊灯 / E4 固定TP2R+time-stop42根(=P0).
口径(spec §1.4): 固定TP/SL 用 high/low 碰线(同根双触判SL); 吊灯/尾随类用 close 过线;
无SL/TP触发到窗口末端 → 末根 close 计R. 数据只读 tf_cache, 不连MT5.
输出: E:/GoldstrategyEngine/data/night_rd_fam4_m30_exit.json"""
import os, json
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
CF = os.path.join(ROOT, "data", "tf_cache")
OUT = os.path.join(ROOT, "data", "night_rd_fam4_m30_exit.json")
SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]
SLM, TPR = 3.0, 2.0
ATR_P = 14
HH_P = 22
K_CH, K_TR = 3.0, 2.0
BE_R = 1.0
NBAR = 42
FILL_WIN = 4
PROTS = ["E1", "E2", "E3", "E4", "P4"]


def load(sym, tf):
    z = np.load(os.path.join(CF, f"{sym}_{tf}.npz"))
    return dict(t=z["t"].astype(np.int64), o=z["o"].astype(float),
                h=z["h"].astype(float), l=z["l"].astype(float), c=z["c"].astype(float))


def atr_wilder(h, l, c, p):
    tr = np.empty(len(c)); tr[0] = h[0]-l[0]
    tr[1:] = np.maximum(h[1:]-l[1:],
                        np.maximum(np.abs(h[1:]-c[:-1]), np.abs(l[1:]-c[:-1])))
    out = np.zeros(len(c))
    if len(c) <= p:
        return out
    out[p] = tr[1:p+1].mean()
    for i in range(p+1, len(c)):
        out[i] = (out[i-1]*(p-1) + tr[i]) / p
    return out


def build(sym):
    """事件全集 = _tf_m30.py 几何: D1方向闸 + close 曾低于/高于 Donchian20×1.003, 事件bar i."""
    d1, m = load(sym, "D1"), load(sym, "M30")
    T, H, L, C = m["t"], m["h"], m["l"], m["c"]
    n = len(C)
    hi20 = np.full(n, np.nan); lo20 = np.full(n, np.nan)
    for i in range(20, n):
        hi20[i] = H[i-19:i+1].max()
        lo20[i] = L[i-19:i+1].min()
    atr = atr_wilder(H, L, C, ATR_P)
    hh22 = np.full(n, np.nan); ll22 = np.full(n, np.nan)
    for i in range(HH_P, n):
        hh22[i] = H[i-HH_P+1:i+1].max()
        ll22[i] = L[i-HH_P+1:i+1].min()
    dt, dc = d1["t"], d1["c"]
    gate_ok = dt + 86400
    gside = np.full(len(dc), -1)
    for j in range(1, len(dc)):
        gside[j] = 1 if dc[j] > dc[j-1] else 0
    ev = []
    for i in range(21, n-1):
        if np.isnan(hi20[i-1]) or hi20[i-1] <= 0:
            continue
        ts = int(T[i])
        pos = int(np.searchsorted(gate_ok, ts, side="right")) - 1
        d = gside[pos] if pos >= 1 else None
        if d is None:
            continue
        if d == 1 and C[i-1] < hi20[i-1]*1.003:
            trig, side = float(hi20[i-1]*1.003), 1
        elif d == 0 and C[i-1] > lo20[i-1]/1.003:
            trig, side = float(lo20[i-1]/1.003), -1
        else:
            continue
        ev.append((i, ts, trig, side))
    ctx = dict(T=T, H=H, L=L, C=C, atr=atr, hh=hh22, ll=ll22, n=n)
    return ev, ctx


def replay(ev, ctx, prot):
    T, H, L, C = ctx["T"], ctx["H"], ctx["L"], ctx["C"]
    atr, hh, ll, n = ctx["atr"], ctx["hh"], ctx["ll"], ctx["n"]
    use_ch = prot in ("E1", "P4")          # 吊灯 3×ATR14
    use_tr = prot == "E2"                  # trail 2×ATR14
    use_be = prot == "P4"                 # +1R 保本
    use_e3 = prot == "E3"                 # 1R半仓 + 余仓吊灯
    use_e4 = prot == "E4"                 # 纯 TP2R + time-stop, 无尾随
    out = []
    for i0, ts, trig, side in ev:
        j = int(np.searchsorted(T, ts, side="right"))
        if j >= n or j + FILL_WIN > n:
            continue
        a = atr[j] if atr[j] > 0 else 1e-9
        r0 = SLM * a
        sl0 = trig - side*r0
        seg = H[j:j+FILL_WIN] if side == 1 else L[j:j+FILL_WIN]
        f = np.where(seg >= trig)[0] if side == 1 else np.where(seg <= trig)[0]
        if len(f) == 0:
            continue
        j0 = j + int(f[0])
        jend = min(j0 + NBAR, n)
        ch = None                     # 单调棘轮锚
        be_armed = False
        half_done = False
        half_R = None
        R = None
        for k in range(j0, jend):
            cur = C[k]
            hk, lk = H[k], L[k]
            hhk, llk, ak = hh[k-1], ll[k-1], atr[k-1]
            # 1) 更新锚: 吊灯(3×ATR) 或 trail2(2×ATR, 仅在已有浮盈区k>j0), 用 k-1 数据(前视禁令)
            if (use_ch or use_e3) and np.isfinite(hhk) and hhk > 0:
                if side == 1:
                    cand = hhk - K_CH*ak
                    ch = cand if ch is None else max(ch, cand)
                else:
                    cand = llk + K_CH*ak
                    ch = cand if ch is None else min(ch, cand)
            if use_tr and np.isfinite(hhk) and hhk > 0 and k > j0:
                if side == 1:
                    cand = hhk - K_TR*ak
                    ch = cand if ch is None else max(ch, cand)
                else:
                    cand = llk + K_TR*ak
                    ch = cand if ch is None else min(ch, cand)
            # 2) 保本武装 (P4: close到 +1R)
            if use_be and not be_armed and ((side == 1 and cur >= trig + BE_R*r0) or
                                            (side == -1 and cur <= trig - BE_R*r0)):
                be_armed = True
            # 3) E3 半仓锁 1R
            if use_e3 and not half_done and ((side == 1 and cur >= trig + r0) or
                                             (side == -1 and cur <= trig - r0)):
                half_done = True
                half_R = (cur - trig)*side/r0
            # 4) E4: 纯固定 TP/SL + time-stop (high/low 碰线, 同根双触判SL)
            if use_e4:
                sl_hit = (lk <= sl0) if side == 1 else (hk >= sl0)
                tp_hit = (hk >= trig + TPR*r0) if side == 1 else (lk <= trig - TPR*r0)
                if sl_hit:
                    R = -1.0
                    break
                if tp_hit:
                    R = TPR
                    break
                if k == jend - 1:
                    R = (C[k]-trig)*side/r0
                continue
            # 5) 尾随族: 有效线 = 原始SL(未抬前 line口径) → 保本/吊灯抬升后 close口径
            eff = sl0
            if be_armed:
                eff = max(eff, trig) if side == 1 else min(eff, trig)
            if ch is not None and (use_ch or use_tr or use_e3):
                eff = max(eff, ch) if side == 1 else min(eff, ch)
            if (use_ch or use_tr or use_e3) and ch is None and not be_armed:
                hit = (lk <= sl0) if side == 1 else (hk >= sl0)
                if hit:
                    R = -1.0
                    break
            else:
                hit = (cur <= eff) if side == 1 else (cur >= eff)
                if hit:
                    R = (cur - trig)*side/r0
                    break
            if k == jend - 1:
                R = (cur - trig)*side/r0
        if R is None:
            R = (C[jend-1]-trig)*side/r0
        if use_e3 and half_done:
            R = 0.5*half_R + 0.5*R
        out.append((int(T[j0]), side, float(R)))
    return out


def stat(res, ts_arr):
    R = np.array([x[2] for x in res])
    ts = np.array(ts_arr)
    n = len(R)
    sd = np.array([x[1] for x in res])
    b, s = R[sd == 1], R[sd == -1]
    mir = bool(n > 0 and len(b) >= 0.3*(len(b)+len(s)) and len(s) >= 0.3*(len(b)+len(s))
               and abs(float(b.mean()) - float(s.mean())) < 0.5)
    wf3 = [None, None, None]
    if n > 2:
        t0, t2 = ts.min(), ts.max()
        third = (t2 - t0) / 3.0
        for k in range(3):
            sel = R[ts < t0 + third] if k == 0 else \
                  R[(ts >= t0 + third*k) & (ts < t0 + third*(k+1))] if k == 1 else \
                  R[ts >= t0 + 2*third]
            wf3[k] = round(float(sel.mean()), 4) if len(sel) else None
    expR = float(R.mean()) if n else 0.0
    return dict(n=n, exp_R=round(expR, 4),
                wr=round(float((R > 0).mean()), 4) if n else None,
                mirror_pass=mir, buy_n=int(len(b)), sell_n=int(len(s)),
                buy_expR=round(float(b.mean()), 4) if len(b) else None,
                sell_expR=round(float(s.mean()), 4) if len(s) else None,
                wf3=wf3,
                net_P95=round(expR - 0.095, 4), net_P95x2=round(expR - 0.19, 4))


def main():
    gres, gts = {p: [] for p in PROTS}, {p: [] for p in PROTS}
    per_sym = {p: {} for p in PROTS}
    n_events_total = 0
    for sym in SYMS:
        ev, ctx = build(sym)
        n_events_total += len(ev)
        for p in PROTS:
            res = replay(ev, ctx, p)
            gres[p].extend(res)
            gts[p].extend([x[0] for x in res])
            st = stat(res, [x[0] for x in res])
            per_sym[p][sym] = st["exp_R"]
        print(f"[{sym}] events={len(ev)} fills(E4)={len(res)}" if False else
              f"[{sym}] events={len(ev)} fills={ {p: len([x for x in gres[p] if x[0] is not None] ) for p in PROTS} }")
    agg = {}
    for p in PROTS:
        st = stat(gres[p], gts[p])
        st["per_sym"] = per_sym[p]
        st["sym_pos"] = sum(1 for s in SYMS if per_sym[p][s] is not None and per_sym[p][s] > 0)
        agg[p] = st
    json.dump({
        "meta": dict(slm=SLM, tp=TPR, chand=f"{HH_P}x{K_CH}ATR{ATR_P}", trail=f"2xATR{ATR_P}",
                     nbar=NBAR, fill_win=FILL_WIN, be=BE_R, syms=SYMS, n_events=n_events_total),
        "agg": agg, "per_sym": per_sym},
        open(OUT, "w"), ensure_ascii=False, indent=1)
    for p in PROTS:
        a = agg[p]
        print(f"{p}: n={a['n']} expR={a['exp_R']} netP95={a['net_P95']} wr={a['wr']} "
              f"pos={a['sym_pos']}/6 wf3={a['wf3']} mirror={a['mirror_pass']}")
    p4 = agg["P4"]["exp_R"]
    ok = abs(p4 - (-0.813)) < 0.05
    print(f"P4复现 {p4} (目标≈-0.813, 容差0.05) → { 'PASS' if ok else 'FAIL: 几何漂移, 结果作废' }")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
