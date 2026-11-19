# -*- coding: utf-8 -*-
# M30 周期回放: 趋势腿几何 (D1方向闸 + Donchian20*1.003 stop成交, SL=SLM*ATR14 Wilder, TP=2R, 前向42根M30)
# 一次跑通: 事件n/成交n/exp_R/wr/walk-forward3段/品种稳健/对称自检/SLM网格 → data/intra_tf_m30.json
import json, os
import numpy as np
import MetaTrader5 as mt5

ROOT = os.path.dirname(os.path.abspath(__file__))
SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]
SLM_DEFAULT = 2.0
LOOK_AHEAD = 42   # 前向42根M30 (= 21天, 趋势腿量级)
FILL_WINDOW = 4   # stop单 当期4根内未成交 = 未成交

mt5.initialize()
assert mt5.login(60137964, password="", server="TradeMaxGlobal-Demo"), "mt5 login fail"

def load(sym, tf, n):
    r = mt5.copy_rates_from_pos(sym, tf, 0, n)
    if r is None or len(r) == 0:
        return None
    return dict(t=r["time"].astype(np.int64), h=r["high"].astype(float),
                l=r["low"].astype(float), c=r["close"].astype(float))

def donc20(h, l):
    hi = np.full_like(h, np.nan); lo = np.full_like(h, np.nan)
    for i in range(20, len(h)):
        hi[i] = h[i-19:i+1].max(); lo[i] = l[i-19:i+1].min()
    return hi, lo

def atr_wilder(h, l, c, p=14):
    tr = np.empty(len(c)); tr[0] = h[0] - l[0]
    tr[1:] = np.maximum(h[1:] - l[1:],
                        np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    out = np.zeros(len(c))
    if len(c) <= p:
        return out
    out[p] = tr[1:p+1].mean()
    for i in range(p+1, len(c)):
        out[i] = (out[i-1]*(p-1) + tr[i]) / p
    return out

def d1_gate(d1, ts):
    """ts时刻最近已完结D1: c>前c → 1(多), 否则0(空)"""
    ok = d1["t"] + 86400 <= ts
    if not ok.any():
        return None
    j = int(np.where(ok)[0][-1])
    if j < 1:
        return None
    return 1 if d1["c"][j] > d1["c"][j-1] else 0

def replay(sym, slm):
    """M30回放. fills: list of dict(ts, side, R, slm)"""
    d1 = load(sym, mt5.TIMEFRAME_D1, 3000)
    m = load(sym, mt5.TIMEFRAME_M30, 50000)
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
        j = int(np.searchsorted(tt, ts, side="right"))  # 次根起
        if j >= len(tt) or j + FILL_WINDOW > len(tt):
            continue
        a = atr[j] if atr[j] > 0 else 1e-9
        sl = trig - slm * a if side == 1 else trig + slm * a
        r0 = abs(trig - sl)
        if r0 <= 0:
            continue
        tp = trig + 2 * r0 if side == 1 else trig - 2 * r0
        # stop 单成交: 前向4根(当期)内 BUY high>=trig / SELL low<=trig
        seg_h = th[j:j+FILL_WINDOW]; seg_l = tl[j:j+FILL_WINDOW]
        if side == 1:
            f = np.where(seg_h >= trig)[0]
        else:
            f = np.where(seg_l <= trig)[0]
        if len(f) == 0:
            continue
        fidx = int(f[0])
        fill_ts = int(tt[j + fidx])
        fill_px = float(trig)
        seg_h2 = th[j:j+LOOK_AHEAD]; seg_l2 = tl[j:j+LOOK_AHEAD]
        res, exit_px = None, None
        for k in range(fidx, len(seg_h2)):
            hh, ll = seg_h2[k], seg_l2[k]
            if side == 1:
                sl_hit, tp_hit = ll <= sl, hh >= tp
            else:
                sl_hit, tp_hit = hh >= sl, ll <= tp
            if sl_hit:  # 同根SL/TP双触 → 判SL(保守)
                exit_px, res = sl, -1.0
                break
            if tp_hit:
                exit_px, res = tp, 2.0
                break
        if res is None:  # 前向42根走完无SL/TP → 按最后一根收盘计R(不截断)
            exit_px = float(seg_h2[-1]) if side == 1 else float(seg_l2[-1])
            res = (exit_px - fill_px) / r0 if side == 1 else (fill_px - exit_px) / r0
        fills.append(dict(ts=fill_ts, side=side, R=round(float(res), 4),
                          sym=sym, slm=slm))
    return fills, n_events

def agg(fills):
    Rs = np.array([f["R"] for f in fills])
    expR = round(float(Rs.mean()), 4) if len(Rs) else None
    wr = round(float((Rs > 0).mean()), 4) if len(Rs) else None
    return expR, wr

# ── 主跑: SLM=2.0 默认口径 ──
fills_all, events_per_sym = [], {}
for sym in SYMS:
    fl, ne = replay(sym, SLM_DEFAULT)
    events_per_sym[sym] = ne
    fills_all.extend(fl)
fills_all.sort(key=lambda x: x["ts"])

n_events = sum(events_per_sym.values())
n_fill = len(fills_all)
expR_all, wr_all = agg(fills_all)
per_sym = {}
for sym in SYMS:
    r = np.array([f["R"] for f in fills_all if f["sym"] == sym])
    per_sym[sym] = round(float(r.mean()), 4) if len(r) else None

# walk-forward 3 段 (按成交时间均分)
wf = {}
if n_fill:
    tmin, tmax = fills_all[0]["ts"], fills_all[-1]["ts"]
    third = (tmax - tmin) / 3.0
    for k in range(3):
        seg = np.array([f["R"] for f in fills_all
                        if (k == 0 and f["ts"] < tmin + third)
                        or (k == 1 and tmin + third <= f["ts"] < tmin + 2*third)
                        or (k == 2 and f["ts"] >= tmin + 2*third)])
        wf[str(k+1)] = {"n": int(len(seg)),
                        "exp_R": round(float(seg.mean()), 4) if len(seg) else None,
                        "dir": ("+" if len(seg) and seg.mean() > 0
                                else ("-" if len(seg) and seg.mean() < 0 else "0"))}
else:
    wf = {str(k+1): {"n": 0, "exp_R": None, "dir": "0"} for k in range(3)}

# 对称自检: 多/空两侧填充量级同侧(各≥30%) 且 exp_R 差 < 0.5R
b = np.array([f["R"] for f in fills_all if f["side"] == 1])
s = np.array([f["R"] for f in fills_all if f["side"] == -1])
nb, ns = len(b), len(s)
eb = float(b.mean()) if nb else 0.0
es = float(s.mean()) if ns else 0.0
symmetric_pass = bool(nb > 0 and ns > 0
                      and nb >= 0.3 * (nb + ns) and ns >= 0.3 * (nb + ns)
                      and abs(eb - es) < 0.5)

# SLM 网格
slm_grid = {str(SLM_DEFAULT): expR_all}
for slm in [1.5, 2.0, 3.0]:
    if slm == SLM_DEFAULT:
        continue
    fls = []
    for sym in SYMS:
        f2, _ = replay(sym, slm)
        fls.extend(f2)
    r2, _ = agg(fls)
    slm_grid[str(slm)] = r2

out = {
    "tf": "M30",
    "事件n": int(n_events),
    "成交n": int(n_fill),
    "exp_R": expR_all,
    "wr": wr_all,
    "默认SLM": SLM_DEFAULT,
    "品种稳健": per_sym,
    "三段方向": {k: v["dir"] for k, v in wf.items()},
    "三段明细": wf,
    "对称自检pass": symmetric_pass,
    "对称明细": {"多n": nb, "多expR": round(eb, 4), "空n": ns, "空expR": round(es, 4)},
    "SLM网格": slm_grid,
}
os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
p = os.path.join(ROOT, "data", "intra_tf_m30.json")
with open(p, "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
print(json.dumps(out, ensure_ascii=False))
mt5.shutdown()
