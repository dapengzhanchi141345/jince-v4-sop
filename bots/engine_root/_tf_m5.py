# -*- coding: utf-8 -*-
# M5 周期回放: 趋势腿几何(同 M15 轮统一引擎) + 吊灯/尾随协议
# 几何: D1方向闸 + M5 Donchian20*1.003 stop成交, SL=SLM*ATR14, TP=2R, 前向42根M5
# 协议: P0纯TP/SL, P2吊灯(HH22-3ATR), P4吊灯+1R保本; SLM{1.5,2.0,3.0}
# 同 M15 轮 _tf_m15.py 几何, 输出 data/intra_tf_m5.json
import json, os, time
import numpy as np
import MetaTrader5 as mt5

ROOT = os.path.dirname(os.path.abspath(__file__))
SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]
SLM = 3.0          # 默认口径对齐 M15 轮 (SLM网格另跑 1.5/2.0)
LOOK_AHEAD = 42    # 前向42根M5 (3.5h, 日内量级)
FILL_WINDOW = 4
N_BARS = 50000

mt5.initialize()
assert mt5.login(60137964, password="", server="TradeMaxGlobal-Demo"), "mt5 login fail"


def load(sym, tf, n):
    for _ in range(3):
        mt5.symbol_select(sym, True)
        r = mt5.copy_rates_from_pos(sym, tf, 0, n)
        if r is not None and len(r) >= min(n // 10, 1000):
            return dict(t=r["time"].astype(np.int64), o=r["open"].astype(float),
                        h=r["high"].astype(float), l=r["low"].astype(float),
                        c=r["close"].astype(float))
        time.sleep(2)
    return None


def donc20(h, l):
    hi = np.full_like(h, np.nan); lo = np.full_like(h, np.nan)
    for i in range(20, len(h)):
        hi[i] = h[i-19:i+1].max(); lo[i] = l[i-19:i+1].min()
    return hi, lo


def atr_wilder(h, l, c, p=14):
    tr = np.empty(len(c)); tr[0] = h[0] - l[0]
    tr[1:] = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    out = np.zeros(len(c))
    if len(c) <= p:
        return out
    out[p] = tr[1:p + 1].mean()
    for i in range(p + 1, len(c)):
        out[i] = (out[i - 1] * (p - 1) + tr[i]) / p
    return out


def d1_gate(d1, ts):
    ok = d1["t"] + 86400 <= ts
    if not ok.any():
        return None
    j = int(np.where(ok)[0][-1])
    if j < 1:
        return None
    return 1 if d1["c"][j] > d1["c"][j - 1] else 0


def chandelier(h, l, c, atr, i0, side, k=3.0, n=22):
    """吊灯线: HH(22)*1.0 if side=1 else LL(22); close口径棘轮"""
    m = max(0, i0 - n + 1)
    if side == 1:
        hh = h[m:i0].max()
        return hh - k * atr[i0 - 1]
    else:
        ll = l[m:i0].min()
        return ll + k * atr[i0 - 1]


def replay(sym, slm, proto):
    """proto: 'P0'=纯TP/SL, 'P2'=吊灯, 'P4'=吊灯+1R保本"""
    d1 = load(sym, mt5.TIMEFRAME_D1, 3000)
    m = load(sym, mt5.TIMEFRAME_M5, N_BARS)
    if not (d1 and m):
        return [], 0
    hi, lo = donc20(m["h"], m["l"])
    atr = atr_wilder(m["h"], m["l"], m["c"])
    th, tl, tc, tt = m["h"], m["l"], m["c"], m["t"]
    fills, n_events = [], 0
    for i in range(21, len(tt) - 1):
        if np.isnan(hi[i-1]) or np.isnan(lo[i-1]) or hi[i-1] <= 0:
            continue
        ts = int(tt[i])
        d = d1_gate(d1, ts)
        if d is None:
            continue
        side, trig = 0, 0.0
        if d == 1 and tc[i-1] < hi[i-1] * 1.003:
            side, trig = 1, hi[i-1] * 1.003
        elif d == 0 and tc[i-1] > lo[i-1] / 1.003:
            side, trig = -1, lo[i-1] / 1.003
        else:
            continue
        n_events += 1
        j = int(np.searchsorted(tt, ts, side="right"))
        if j >= len(tt) or j + FILL_WINDOW > len(tt):
            continue
        a = atr[j] if atr[j] > 0 else 1e-9
        sl = trig - slm * a if side == 1 else trig + slm * a
        r0 = abs(trig - sl)
        if r0 <= 0:
            continue
        tp = trig + 2 * r0 if side == 1 else trig - 2 * r0
        seg_h = th[j:j+FILL_WINDOW]; seg_l = tl[j:j+FILL_WINDOW]
        f = np.where(seg_h >= trig)[0] if side == 1 else np.where(seg_l <= trig)[0]
        if len(f) == 0:
            continue
        fidx = int(f[0])
        fill_ts = int(tt[j + fidx])
        fill_px = float(trig)
        seg_h2 = th[j:j+LOOK_AHEAD]; seg_l2 = tl[j:j+LOOK_AHEAD]
        res, exit_px = None, None
        be_armed = False
        eff_sl = sl
        for k2 in range(fidx, len(seg_h2)):
            hh, ll = seg_h2[k2], seg_l2[k2]
            ck = j + k2
            sl_hit = tp_hit = None
            if proto in ("P2", "P4"):
                # 吊灯线: 滚动22根极值 ∓3×ATR14, 单调棘轮; P4 先到+1R先保本
                if side == 1:
                    cline = (th[ck-21:ck+1].max() - 3.0 * atr[ck]) if ck >= 21 else None
                    if cline is not None:
                        if not be_armed and tc[ck] >= trig + r0:
                            be_armed = True
                            eff_sl = max(eff_sl, trig)
                        eff_sl = max(eff_sl, cline)
                    sl_hit = ll <= eff_sl
                else:
                    cline = (tl[ck-21:ck+1].min() + 3.0 * atr[ck]) if ck >= 21 else None
                    if cline is not None:
                        if not be_armed and tc[ck] <= trig - r0:
                            be_armed = True
                            eff_sl = min(eff_sl, trig)
                        eff_sl = min(eff_sl, cline)
                    sl_hit = hh >= eff_sl
            else:
                sl_hit = (ll <= eff_sl) if side == 1 else (hh >= eff_sl)
            tp_hit = (hh >= tp) if side == 1 else (ll <= tp)
            if sl_hit:
                if proto == "P0":
                    res = -1.0
                else:
                    res = (eff_sl - trig) / r0 if side == 1 else (trig - eff_sl) / r0
                break
            if tp_hit:
                res = 2.0
                break
        if res is None:
            last = j + len(seg_h2) - 1
            exit_px = float(tc[last])
            res = (exit_px - fill_px) / r0 if side == 1 else (fill_px - exit_px) / r0
        fills.append(dict(ts=fill_ts, side=side, R=round(float(res), 4), sym=sym, slm=slm, proto=proto))
    return fills, n_events


def agg(fills):
    if not fills:
        return None, None, {}
    Rs = np.array([f["R"] for f in fills])
    expR = round(float(Rs.mean()), 4)
    wr = round(float((Rs > 0).mean()), 4)
    per = {}
    for s in SYMS:
        r = Rs[[f["sym"] == s for f in fills]]
        per[s] = round(float(r.mean()), 4) if len(r) else None
    return expR, wr, per


if __name__ == "__main__":
    out = {"tf": "M5", "SLM默认": SLM, "前向窗口": LOOK_AHEAD, "N_bars": N_BARS}
    for proto in ["P0", "P2", "P4"]:
        fl = []
        for sym in SYMS:
            f2, ne = replay(sym, SLM, proto)
            fl.extend(f2)
        e, w, per = agg(fl)
        out[proto] = {"n": len(fl), "exp_R": e, "wr": w, "per_sym": per}
        print(f"{proto} n={len(fl)} exp_R={e} wr={w} {per}")
    # walk-forward 3段 (P0为主)
    fl0 = []
    for sym in SYMS:
        f2, _ = replay(sym, SLM, "P0")
        fl0.extend(f2)
    fl0.sort(key=lambda x: x["ts"])
    if fl0:
        tmin, tmax = fl0[0]["ts"], fl0[-1]["ts"]
        third = (tmax - tmin) / 3
        wf = {}
        for k in range(3):
            seg = np.array([f["R"] for f in fl0
                            if (k == 0 and f["ts"] < tmin + third)
                            or (k == 1 and tmin + third <= f["ts"] < tmin + 2 * third)
                            or (k == 2 and f["ts"] >= tmin + 2 * third)])
            wf[str(k + 1)] = {"n": int(len(seg)),
                              "exp_R": round(float(seg.mean()), 4) if len(seg) else None,
                              "dir": ("+" if len(seg) and seg.mean() > 0 else
                                      ("-" if len(seg) and seg.mean() < 0 else "0"))}
        out["三段方向_P0"] = {k: v["dir"] for k, v in wf.items()}
        out["三段明细_P0"] = wf
    # SLM 网格 (P0)
    slm_grid = {}
    for slm in [1.5, 2.0, 3.0]:
        fls = []
        for sym in SYMS:
            f2, _ = replay(sym, slm, "P0")
            fls.extend(f2)
        e, w, _ = agg(fls)
        slm_grid[str(slm)] = e
        print(f"SLM={slm} P0 exp_R={e} n={len(fls)}")
    out["SLM网格_P0"] = slm_grid
    p = os.path.join(ROOT, "data", "intra_tf_m5.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("WROTE", p)
    mt5.shutdown()
