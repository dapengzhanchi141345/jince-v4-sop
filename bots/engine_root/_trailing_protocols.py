# -*- coding: utf-8 -*-
# M30 趋势腿格 (Donchian20*1.003 stop成交 + D1方向闸, SLM=3.0) 上测移动保护协议全家桶 vs 纯TP/SL
# P0 纯TP/SL(TP=2R) | P1 1R保本 | P2 吊灯(无TP, CH=HH22+/-3ATR22 棘尾, close过线) |
# P3 半仓锁利(1R平半仓+余仓吊灯) | P4 吊灯+保本
# 铁律: 同分母同一事件全集; 对称自检(SELL=数据翻号镜像BUY, 逐笔R相等); close口径; 扣0.5R滑点
import json, os
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
CF = os.path.join(ROOT, "data", "tf_cache")
SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]
SLM = 3.0
LOOK_AHEAD = 42
FILL_WINDOW = 4
CHAND_N = 22
CHAND_M = 3.0
BRCUT = 42
SLIP = 0.5
PROTS = ["P0", "P1", "P2", "P3", "P4"]


def load(sym):
    m = np.load(os.path.join(CF, f"{sym}_M30.npz"))
    d = np.load(os.path.join(CF, f"{sym}_D1.npz"))
    for a in (m, d):
        assert np.all(np.diff(a["t"]) > 0)
    M = dict(t=m["t"].astype(np.int64), o=m["o"].astype(float),
             h=m["h"].astype(float), l=m["l"].astype(float), c=m["c"].astype(float))
    D = dict(t=d["t"].astype(np.int64), c=d["c"].astype(float))
    return M, D


def donc20(h, l, n=20):
    hi = np.full_like(h, np.nan)
    lo = np.full_like(h, np.nan)
    for i in range(n, len(h)):
        hi[i] = h[i - n + 1:i + 1].max()
        lo[i] = l[i - n + 1:i + 1].min()
    return hi, lo


def atr_wilder(h, l, c, p):
    tr = np.empty(len(c))
    tr[0] = h[0] - l[0]
    tr[1:] = np.maximum(h[1:] - l[1:],
                       np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    out = np.zeros(len(c))
    if len(c) <= p:
        return out
    out[p] = tr[1:p + 1].mean()
    for i in range(p + 1, len(c)):
        out[i] = (out[i - 1] * (p - 1) + tr[i]) / p
    return out


def rolling_max(a, n):
    out = np.full_like(a, np.nan, dtype=float)
    for i in range(n, len(a)):
        out[i] = a[i - n + 1:i + 1].max()
    return out


def d1_gate(d1, ts):
    ok = d1["t"] + 86400 <= ts
    if not ok.any():
        return None
    j = int(np.where(ok)[0][-1])
    if j < 1:
        return None
    return 1 if d1["c"][j] > d1["c"][j - 1] else 0


def stream_events(M, D):
    """BUY 事件流: D1闸=1, close 上穿 HH20*1.003, stop成交 (真实空间)"""
    hi, lo = M["h"], M["l"]
    t, H, L, C = M["t"], M["h"], M["l"], M["c"]
    d1t, d1c = D["t"], D["c"]
    dd, dlo = donc20(H, L)
    a20 = atr_wilder(H, L, C, 20)
    hh22 = rolling_max(H, CHAND_N)
    aa22 = atr_wilder(H, L, C, 22)
    N = len(t)
    gate_ok, gate_side = d1t + 86400, np.full(len(d1c), -1)
    for j in range(1, len(d1c)):
        gate_side[j] = 1 if d1c[j] > d1c[j - 1] else 0
    fills = []
    for i in range(21, N - 1):
        if np.isnan(dd[i - 1]) or dd[i - 1] <= 0:
            continue
        ts = int(t[i])
        pos = int(np.searchsorted(gate_ok, ts, side="right")) - 1
        g = gate_side[pos] if pos >= 1 else -1
        if g != 1:                      # 镜像口径: 方向闸必须=1 才出 BUY(几何本身已含方向)
            continue
        if C[i - 1] < dd[i - 1] * 1.003:
            continue                   # 需 close 上穿 (close 曾低于阈值)
        jx = int(np.searchsorted(t, ts, side="right"))
        if jx >= N or jx + FILL_WINDOW > N:
            continue
        a = a20[jx] if a20[jx] > 0 else 1e-9
        trig = dd[i - 1] * 1.003
        seg = H[jx:jx + FILL_WINDOW]
        f = np.where(seg >= trig)[0]
        if len(f) == 0:
            continue
        fidx = int(f[0])
        fill_ts = int(t[jx + fidx])
        fill_px = float(trig)
        r0 = SLM * a
        sl0 = trig - r0
        j0 = jx + fidx - 1
        fills.append(dict(ts=fill_ts, fill_px=fill_px, r0=r0, sl0=sl0, j0=j0,
                          hh=hh22, cc=C, aa=aa22, end=min(N - 1, jx + LOOK_AHEAD)))
    return fills


def stream_events_sell(M, D):
    """真实空间 SELL 流: D1闸=0, close 下穿 LL20/1.003, stop 成交"""
    t, H, L, C = M["t"], M["h"], M["l"], M["c"]
    d1t, d1c = D["t"], D["c"]
    hi, lo = donc20(H, L)
    a20 = atr_wilder(H, L, C, 20)
    a22 = atr_wilder(H, L, C, 22)
    # 吊灯镜像: 取前22根 LL 最小 (负号域 = HH22 of L')
    ll22 = np.full_like(L, np.nan)
    for i in range(CHAND_N, len(L)):
        ll22[i] = L[i - CHAND_N + 1:i + 1].min()
    N = len(t)
    gate_ok, gate_side = d1t + 86400, np.full(len(d1c), -1)
    for j in range(1, len(d1c)):
        gate_side[j] = 1 if d1c[j] > d1c[j - 1] else 0
    fills = []
    for i in range(21, N - 1):
        if np.isnan(lo[i - 1]) or lo[i - 1] <= 0:
            continue
        ts = int(t[i])
        pos = int(np.searchsorted(gate_ok, ts, side="right")) - 1
        g = gate_side[pos] if pos >= 1 else -1
        if g != 0:
            continue
        if C[i - 1] > lo[i - 1] / 1.003:
            continue
        jx = int(np.searchsorted(t, ts, side="right"))
        if jx >= N or jx + FILL_WINDOW > N:
            continue
        a = a20[jx] if a20[jx] > 0 else 1e-9
        trig = lo[i - 1] / 1.003
        f = np.where(L[jx:jx + FILL_WINDOW] <= trig)[0]
        if len(f) == 0:
            continue
        fidx = int(f[0])
        fill_ts = int(t[jx + fidx])
        fill_px = float(trig)
        r0 = SLM * a
        sl0 = trig + r0
        j0 = jx + fidx - 1
        fills.append(dict(ts=fill_ts, fill_px=fill_px, r0=r0, sl0=sl0, j0=j0,
                          side=-1, hh=ll22, cc=C, aa=a22, end=min(N - 1, jx + LOOK_AHEAD)))
    return fills


    chand_now = None
    sl_eff = sl0
    R = None
    for q in range(j0 + 1, end + 1):
        close = cc[q]
        prev = q - 1
        hhq = hh[prev]
        aaq = aa[prev]
        if chand and not np.isnan(hhq) and hhq > 0:
            if side == 1:
                cand = hhq - CHAND_M * aaq
            else:
                cand = hhq + CHAND_M * aaq
            chand_anchor = cand if chand_anchor is None else \
                (max(chand_anchor, cand) if side == 1 else min(chand_anchor, cand))
            chand_now = chand_anchor
        sl_eff = sl0
        if breakeven_on is not None and close >= breakeven_on:
            sl_eff = max(sl_eff, fill_px)
        if chand_now is not None:
            sl_eff = chand_now
        # 吊灯类最久持有到 BRCUT 根
        if chand and q - j0 >= BRCUT:
            R = (close - fill_px) / r0
            break
        # 离场判定 (close 口径, 不碰极值)
        if chand_now is not None and close <= chand_now:
            R = (close - fill_px) / r0
            break
        if p in ("P0", "P1") and close >= tp_fixed:
            R = (close - fill_px) / r0
            break
        if p == "P3" and not half_cut_done and close >= fill_px + r0:
            half_cut_done = True
            half_R = (close - fill_px) / r0        # 半仓部分 R
        if close <= sl_eff:
            R = 0.5 * half_R + 0.5 * ((close - fill_px) / r0) if p == "P3" and half_cut_done \
                else (close - fill_px) / r0
            break
    else:
        close = cc[end]
        R = (close - fill_px) / r0
        if p == "P3" and half_cut_done:
            R = 0.5 * half_R + 0.5 * R
    return float(R)


def play_sell(tr, p):
    """SELL close 口径回放 (真实空间), R=(fill-close)/r0"""
    fill_px, r0, sl0 = tr["fill_px"], tr["r0"], tr["sl0"]
    hh, cc, aa = tr["hh"], tr["cc"], tr["aa"]   # hh = LL22
    j0, end = tr["j0"], tr["end"]
    tp_fixed = None
    breakeven_on = None
    chand = False
    half_cut_done = False
    half_R = 0.0
    if p == "P0":
        tp_fixed = fill_px - 2 * r0
    elif p == "P1":
        tp_fixed = fill_px - 2 * r0
        breakeven_on = fill_px - r0
    elif p == "P2":
        chand = True
    elif p == "P3":
        chand = True
    elif p == "P4":
        chand = True
        breakeven_on = fill_px - r0
    chand_anchor = None
    sl_eff = sl0
    R = None
    for q in range(j0 + 1, end + 1):
        close = cc[q]
        hhq = hh[q - 1]
        aaq = aa[q - 1]
        chand_now = None
        if chand and not np.isnan(hhq) and hhq > 0:
            cand = hhq + CHAND_M * aaq
            chand_anchor = cand if chand_anchor is None else min(chand_anchor, cand)
            chand_now = chand_anchor
        sl_eff = sl0
        if breakeven_on is not None and close <= breakeven_on:
            sl_eff = min(sl_eff, fill_px)
        if chand_now is not None:
            sl_eff = min(sl_eff, chand_now)
        if chand and q - j0 >= BRCUT:
            R = (fill_px - close) / r0
            break
        if chand_now is not None and close >= chand_now:
            R = (fill_px - close) / r0
            break
        if p in ("P0", "P1") and close <= tp_fixed:
            R = (fill_px - close) / r0
            break
        if p == "P3" and not half_cut_done and close <= fill_px - r0:
            half_cut_done = True
            half_R = (fill_px - close) / r0
        if close >= sl_eff:
            R = 0.5 * half_R + 0.5 * ((fill_px - close) / r0) if p == "P3" and half_cut_done \
                else (fill_px - close) / r0
            break
    else:
        close = cc[end]
        R = (fill_px - close) / r0
        if p == "P3" and half_cut_done:
            R = 0.5 * half_R + 0.5 * R
    return float(R)


def wf3(ts_arr, R_arr):
    """按 ts 均分三段"""
    if len(ts_arr) == 0:
        return {str(k): {"n": 0, "exp_R": None, "dir": "0"} for k in (1, 2, 3)}
    order = np.argsort(ts_arr, kind="stable")
    ts_s = np.asarray(ts_arr)[order]
    R_s = np.asarray(R_arr)[order]
    t0, t2 = ts_s[0], ts_s[-1]
    third = (t2 - t0) / 3.0
    out = {}
    for k in range(3):
        sel = (R_s if k == 0 else
               R_s[(ts_s >= t0 + third * k) & (ts_s < t0 + third * (k + 1))] if k in (1, 2)
               else R_s[ts_s >= t0 + third * 2])
        if k == 0:
            sel = R_s[ts_s < t0 + third]
        out[str(k + 1)] = {
            "n": int(len(sel)),
            "exp_R": round(float(sel.mean()), 4) if len(sel) else None,
            "dir": ("+" if len(sel) and sel.mean() > 0 else "-" if len(sel) and sel.mean() < 0 else "0")}
    return out


def main():
    data = {}
    allR = {p: [] for p in PROTS}
    allts = {p: [] for p in PROTS}
    for sym in SYMS:
        M, D = load(sym)
        b = stream_events(M, D)
        s = stream_events_sell(M, D)
        n_events = len(b) + len(s)
        rec = {"n_events": n_events, "n_fills_buy": len(b), "n_fills_sell": len(s)}
        for p in PROTS:
            rb = [play(t, p) for t in b]
            rs = [play_sell(t, p) for t in s]
            tsb, tss = [t["ts"] for t in b], [t["ts"] for t in s]
            allR[p].extend(rb); allR[p].extend(rs)
            allts[p].extend(tsb); allts[p].extend(tss)
            rec[p] = {
                "n": len(rb) + len(rs),
                "exp_R": round(float(np.mean(rb + rs)), 4) if (rb or rs) else None,
                "exp_R_net": round(float(np.mean(rb + rs) - SLIP), 4) if (rb or rs) else None,
                "win_rate": round(float(np.mean([x > 0 for x in rb + rs])), 4) if (rb or rs) else None,
                "per_sym_exp_R": round(float(np.mean(rb + rs)), 4) if (rb or rs) else None,
                "buy_n": len(rb), "sell_n": len(rs),
                "buy_exp_R": round(float(np.mean(rb)), 4) if rb else None,
                "sell_exp_R": round(float(np.mean(rs)), 4) if rs else None,
            }
            # 对称自检: 同品种 BUY/SELL 笔数接近 (±30%) 且 exp_R 差 < 0.5R
            if rb and rs:
                nb, ns = len(rb), len(rs)
                rec[p]["sym_mirror_pass"] = bool(nb >= 0.3*(nb+ns) and ns >= 0.3*(nb+ns)
                                                 and abs(np.mean(rb) - np.mean(rs)) < 0.5)
            else:
                rec[p]["sym_mirror_pass"] = False
        rec["wf3"] = {p: wf3(allts[p], allR[p]) for p in PROTS}
        data[sym] = rec
    # 全局汇总
    agg = {}
    for p in PROTS:
        R, T = allR[p], allts[p]
        agg[p] = {
            "n": len(R),
            "exp_R": round(float(np.mean(R)), 4) if R else None,
            "exp_R_net": round(float(np.mean(R) - SLIP), 4) if R else None,
            "win_rate": round(float(np.mean([x > 0 for x in R])), 4) if R else None,
            "per_sym": {s: data[s][p].get("per_sym_exp_R") for s in SYMS},
            "per_sym_pos": sum(1 for s in SYMS if (data[s][p].get("per_sym_exp_R") or 0) > 0),
            "wf3": wf3(T, R),
            "sym_pass": all(data[s][p]["sym_mirror_pass"] for s in SYMS if data[s][p]["n"]),
        }
    out = {"meta": {"slm": SLM, "slip": SLIP, "chand": f"{CHAND_N}/{CHAND_M}",
                    "look_ahead": LOOK_AHEAD, "fill_window": FILL_WINDOW},
           "per_sym": data, "agg": agg}
    json.dump(out, open(os.path.join(ROOT, "data", "trailing_protocols.json"),
                         "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    for p in PROTS:
        a = agg[p]
        print(f"{p}: n={a['n']} exp_R={a['exp_R']} net={a['exp_R_net']} wr={a['win_rate']} "
              f"pos={a['per_sym_pos']}/6 wf3={a['wf3']} sym_pass={a['sym_pass']}")


if __name__ == "__main__":
    main()
