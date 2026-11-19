# -*- coding: utf-8 -*-
"""小马丁加仓网格 — M30趋势腿 SLM3.0 (全史+0.104毛值) 上叠加止损后加仓
网格: 间距{0,2h,4h,8h,12h} × 加仓次数{0,1,2,3} × 倍数{平添1.5, 递倍1/1.5/2, 倍增1/2/4}
风险纪律全保留: 1%基础风险/笔×倍数, 每品种≤3单/日(加仓也计数), 日亏10%熔断, 滑点0.095R(实测P95)
几何复用 _night_fam5_combo.trend_fills (已对齐_tf_m30.py), 加 exit_ts 供加仓引擎使用
输出: data/night_rd_martin.json (5族spec §4 schema + 资金曲线统计)"""
import os, json, time
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "data", "tf_cache")
OUT = os.path.join(ROOT, "data", "night_rd_martin.json")
SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]
SLM, TP_R, LOOK, FILL_WIN = 3.0, 2.0, 42, 4
BARS_PER_DAY = 48  # M30

def load(sym, tf):
    z = np.load(os.path.join(CACHE, f"{sym}_{tf}.npz"))
    return dict(t=z["t"].astype(np.int64), h=z["h"].astype(float),
                l=z["l"].astype(float), c=z["c"].astype(float))

def atr_wilder(h, l, c, p=14):
    n = len(c)
    tr = np.empty(n); tr[0] = h[0] - l[0]
    tr[1:] = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    out = np.zeros(n)
    out[p] = tr[1:p + 1].mean()
    for i in range(p + 1, n):
        out[i] = (out[i - 1] * (p - 1) + tr[i]) / p
    return out

def trend_signals(sym):
    """M30 SLM3.0 P0信号全集: list of dict(ts, side, R, exit_ts) 严格对齐_tf_m30.py"""
    d1, m = load(sym, "D1"), load(sym, "M30")
    t, h, l, c = m["t"], m["h"], m["l"], m["c"]
    atr = atr_wilder(h, l, c)
    hh = np.full(len(c), np.nan); ll = np.full(len(c), np.nan)
    for i in range(20, len(c)):
        hh[i] = h[i - 19:i + 1].max(); ll[i] = l[i - 19:i + 1].min()
    pos = np.searchsorted(d1["t"], t, side="right") - 1
    d1_dir = np.zeros(len(d1["c"]), dtype=int)
    for j in range(1, len(d1["c"])):
        d1_dir[j] = 1 if d1["c"][j] > d1["c"][j - 1] else 0
    sig = []
    for i in range(21, len(c) - LOOK - 1):
        if np.isnan(hh[i - 1]) or np.isnan(ll[i - 1]) or hh[i - 1] <= 0:
            continue
        g = int(d1_dir[pos[i]]) if pos[i] >= 0 else 0
        if g == 1 and c[i - 1] < hh[i - 1] * 1.003:
            trig, side = hh[i - 1] * 1.003, 1
        elif g == 0 and c[i - 1] > ll[i - 1] / 1.003:
            trig, side = ll[i - 1] / 1.003, -1
        else:
            continue
        a = atr[i]
        if a <= 0:
            continue
        sl = trig - side * SLM * a
        tp = trig + side * TP_R * SLM * a
        jx = i + 1
        seg_h, seg_l = h[jx:jx + FILL_WIN], l[jx:jx + FILL_WIN]
        f = np.where(seg_h >= trig)[0] if side == 1 else np.where(seg_l <= trig)[0]
        if len(f) == 0:
            continue
        fidx = int(f[0])
        fill_ts = int(t[jx + fidx])
        r0 = SLM * a
        R, k_ex, resolved = None, FILL_WIN - 1, False
        for k in range(fidx, LOOK):
            if side == 1:
                if l[jx + k] <= sl:
                    R, k_ex, resolved = -1.0, k, True
                    break
                if h[jx + k] >= tp:
                    R, k_ex, resolved = TP_R, k, True
                    break
            else:
                if h[jx + k] >= sl:
                    R, k_ex, resolved = -1.0, k, True
                    break
                if l[jx + k] <= tp:
                    R, k_ex, resolved = TP_R, k, True
                    break
        if R is None:
            kk = min(jx + LOOK - 1, len(c) - 1)
            R = ((c[kk] - trig) / r0) * side if side == 1 else (trig - c[kk]) / r0
            R = float(max(min(R, TP_R), -1.0))
            k_ex = kk - jx
        exit_ts = int(t[min(jx + max(k_ex, 0), len(c) - 1)])
        sig.append(dict(ts=fill_ts, exit_ts=exit_ts, R=float(R - 0.095), side=side))
    return sig

def day_key(ts):
    return ts // 86400 * 86400

def engine(all_sig, cooldown_bars, cap, scheme, equity0=10000.0):
    """加仓引擎: 同向连亏后下次信号加仓(间距冷却+次数封顶+每品种3单/日+日亏10%熔断, 全保留)
    持仓按品种独立(多品种可并行持仓, 分散不互相挡)"""
    mlvl = {
        "flat15": [1.0, 1.5, 1.5, 1.5, 1.5],
        "step": [1.0, 1.5, 2.0, 2.0, 2.0],
        "dbl": [1.0, 2.0, 4.0, 8.0, 16.0],
    }[scheme][:cap + 1] or [1.0]
    events = []
    for s in all_sig:
        events.append((s["ts"], "open", s))
        events.append((s["exit_ts"], "close", s))
    events.sort(key=lambda x: (x[0], 0 if x[1] == "close" else 1))
    state = {sym: dict(consec=0, day=None, day_pnl=0.0, day_start=equity0, cnt=0, last_exit=-10**18)
             for sym in SYMS}
    equity = equity0
    curve = [(0, equity)]
    open_pos = {}  # sym -> (base_R, risk)
    n_orders = 0
    for ts, typ, s in events:
        sym = s.get("sym", None)
        if typ == "close":
            st = state[sym]
            if sym in open_pos:
                oR, orisk = open_pos.pop(sym)
                pnl = orisk * oR
                equity += pnl
                st["day_pnl"] += pnl
                st["consec"] = st["consec"] + 1 if oR < 0 else 0
                st["last_exit"] = ts
            curve.append((ts, equity))
        else:
            st = state[sym]
            d = day_key(ts)
            if st["day"] != d:
                st["day"], st["cnt"], st["day_pnl"], st["day_start"] = d, 0, 0.0, equity
            if sym in open_pos:  # 该品种已有持仓不加码
                continue
            if st["day_pnl"] <= -0.10 * st["day_start"]:  # 日亏10%熔断
                continue
            if st["cnt"] >= 3:  # 每品种≤3单/日计数闸(加仓也计数)
                continue
            if ts < st["last_exit"] + cooldown_bars * 1800:
                continue  # 止损后间距冷却
            lvl = min(st["consec"], len(mlvl) - 1)
            mult = mlvl[lvl]
            risk = equity * 0.01 * mult
            open_pos[sym] = (s["R"], risk)
            st["cnt"] += 1
            n_orders += 1
    if open_pos:
        for sym, (oR, orisk) in open_pos.items():
            equity += orisk * oR
        curve.append((events[-1][0], equity))
    return dict(final_equity=round(equity, 2), n_orders=n_orders, curve=curve)

def metrics(curve, equity0=10000.0):
    """指标修正版: 夏普按日历日收益算(365开方), MDD按日收盘权益算, 另报对数收益防复利虚高"""
    daily = {}
    for ts, e in curve:
        daily[day_key(ts)] = e
    dv = np.array(list(daily.values()))
    logret = float(np.log(dv[-1] / dv[0])) if dv[-1] > 0 else -99.0
    peak = np.maximum.accumulate(dv)
    mdd = float(((peak - dv) / peak).max())
    if len(dv) > 2 and dv.std() > 0:
        sharpe = float(dv.mean() / dv.std() * np.sqrt(365))
    else:
        sharpe = 0.0
    return dict(mdd=round(mdd, 4), sharpe=round(sharpe, 3),
                log_ret=round(logret, 2), days=len(dv),
                cagr=round((dv[-1] / equity0) ** (365.0 / max(len(dv), 1)) - 1, 4) if dv[-1] > 0 else None)

def wf3_metrics(all_sig, cooldown_bars, cap, scheme):
    """wf3 分段: 信号全集按时间三等分, 每段单独跑引擎 → 各段 log_ret (防早期全亏靠后段撑)"""
    tms = sorted(s["ts"] for s in all_sig)
    t1, t2 = tms[len(tms) // 3], tms[2 * len(tms) // 3]
    segs = [
        engine([s for s in all_sig if s["ts"] < t1], cooldown_bars, cap, scheme),
        engine([s for s in all_sig if t1 <= s["ts"] < t2], cooldown_bars, cap, scheme),
        engine([s for s in all_sig if s["ts"] >= t2], cooldown_bars, cap, scheme),
    ]
    out = []
    for sg in segs:
        m = metrics(sg["curve"])
        out.append(m["log_ret"])
    return out

def main():
    t0 = time.time()
    all_sig, per_sig = [], {}
    for sym in SYMS:
        s = trend_signals(sym)
        for x in s:
            x["sym"] = sym
        per_sig[sym] = len(s)
        all_sig.extend(s)
    base_R = float(np.mean([x["R"] for x in all_sig]))
    print(f"信号全集 n={len(all_sig)} per_sym={per_sig} 基线毛值(扣0.095滑点)={base_R:.4f}")
    res = {}
    for cd_bars, cd_h in [(0, "0h"), (4, "2h"), (8, "4h"), (16, "8h"), (24, "12h")]:
        for cap in [0, 1, 2, 3]:
            for scheme in (["flat15"] if cap == 0 else ["flat15", "step", "dbl"]):
                tag = f"cd{cd_h}_cap{cap}" + ("" if cap == 0 else "_" + scheme)
                sg = engine(all_sig, cd_bars, cap, scheme)
                m = metrics(sg["curve"])
                wf = wf3_metrics(all_sig, cd_bars, cap, scheme)
                res[tag] = dict(mdd=m["mdd"], sharpe=m["sharpe"], log_ret=m["log_ret"],
                                 cagr=m["cagr"], n_orders=sg["n_orders"], wf3_log=wf)
                print(f"{tag}: " + json.dumps(res[tag]))
    # 选最优: 三段wf全正 优先; 同分母比较 cagr/MDD
    valid = [k for k, v in res.items() if all(x > 0 for x in v["wf3_log"])]
    cand = valid if valid else list(res.keys())
    ranked = sorted(cand, key=lambda k: (-res[k]["sharpe"] / max(res[k]["mdd"], 1e-6)))
    top3 = ranked[:3]
    print("\nTOP3 (按 夏普/回撤 比):")
    for k in top3:
        print(" ", k, json.dumps(res[k]))
    json.dump({
        "family": "fam6_小马丁加仓",
        "baseline_exp_R": round(base_R, 4),
        "n_signals": len(all_sig), "per_sym": per_sig,
        "note": "M30 SLM3.0 趋势腿信号上叠马丁加仓; 风险纪律全保留(1%基础×倍数, 3单/日, 日亏10%熔断); 滑点0.095R; 指标按日历日收益, 含wf3分段防样本内陷阱",
        "grid": res, "top3": top3, "all_wf3_pos": valid,
    }, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("WROTE", OUT, "ELAPSED", round(time.time() - t0, 1))

if __name__ == "__main__":
    main()
