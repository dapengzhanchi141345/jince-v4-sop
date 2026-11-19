#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""分析枪: 248 品种全量 × 6mo, 读 data/cache248/ 缓存 (0 MT5, 纯 CPU, 8 worker 并发安全).
每品种: gen_pasd 信号集 × (3桶 A不加/C加1到区/B加2中点+到区 [跨区修脏口径] + 6臂裸奔), 同分母.
手数固定 0.01 (@user 钦定不扩大); R 口径=逐笔净/首单风险(品种内自洽), USD列=真 0.01 折算(非UNIVERSE品种USD列仅供参考, R列准).
逐品种增量落盘断点续跑. 0 LLM, 0 写闸源, 0 改 live.
跑法: A248_WORKER=k A248_N=8 python analyze248_all.py
"""
import os, sys, json, datetime, math, pickle, time
os.chdir(r"E:\GoldstrategyEngine"); sys.path.insert(0, r"E:\GoldstrategyEngine")
import numpy as np, pandas as pd
import symbol_universe as su
import pasd_fusion as PF

LOT = 0.01; RR = 2.5
MAXH = 480  # = backtest_engine.MAX_HOLD_H1(最多持仓 480 根 H1 ~20交易日), 内联以解耦 MetaTrader5 import(analyze 枪 0 碰 MT5 终端, 纯 CPU 读缓存)
W = int(os.environ.get("A248_WORKER", "0")); N = int(os.environ.get("A248_N", "8"))
CACHE = "data/cache248"
OUT = f"data/analyze248_w{W}.json"

def all_pkls():
    fs = sorted(f for f in os.listdir(CACHE) if f.endswith(".pkl"))
    return [f[:-4] for f in fs]

def add_levels(sig, zd, zs, mode):
    E, side = sig["entry"], sig["side"]
    if mode == "A": return []
    if side > 0:
        cands = [z for z in zd if z["top"] < E]
        z = max(cands, key=lambda q: q["top"]) if cands else None
        if z is None: return []
        edge, mid = z["bottom"], (z["top"] + z["bottom"]) / 2.0
    else:
        cands = [z for z in zs if z["bottom"] > E]
        z = min(cands, key=lambda q: q["bottom"]) if cands else None
        if z is None: return []
        edge, mid = z["top"], (z["top"] + z["bottom"]) / 2.0
    return [edge] if mode == "C" else [mid, edge]

def slgate(atr_i, entry, point):
    """最小止损闸 (ATR 退化治脏, 2026-10-19): 贴脸 SL 信号风险分母塌缩 → R 物理爆炸.
    口径: 下限 = max(0.5*ATR_i, 1e-5*|entry|, 1e-5*point*100); sl_dist < 下限 → 该信号 SKIP."""
    floor = 1e-5 * abs(entry) if abs(entry) > 0 else 0.0
    if atr_i and atr_i > 0 and not math.isnan(atr_i):
        floor = max(floor, 0.5 * atr_i)
    floor = max(floor, 1e-5 * point * 100)
    return floor

def sim(pkt, h1, sig, lv, cfg, atr_v=None):
    i = int(sig['bar']); side = 1 if sig['side'] > 0 else -1
    if i + 1 >= len(h1): return None
    pip = float(cfg.get('pip', pkt['point'])); pusd = float(cfg.get('pip_usd', 10.0)) * LOT
    sd0 = abs(sig["entry"] - sig["sl"]); td0 = abs(sig["entry"] - sig["tp"])
    a_i = float(atr_v[i]) if atr_v is not None else 0.0
    if sd0 < slgate(a_i, sig["entry"], pkt['point']): return None
    o = float(h1['open'].iloc[i + 1]); a = pkt['spread'] * pkt['point']
    e0 = o + a * side
    S = e0 - side * sd0; TP0 = e0 + side * td0
    end = min(i + 1 + MAXH, len(h1))
    hi = h1['high'].values[i + 1:end]; lo = h1['low'].values[i + 1:end]
    tm = h1['time'].values[i + 1:end]; cl = h1['close'].values[i + 1:end]
    if len(hi) == 0: return None
    pos = [e0]; adds = 0; exit = None
    for k in range(len(hi)):
        avg = sum(pos) / len(pos)
        if side > 0: slh = lo[k] <= S; tph = hi[k] >= TP0
        else:        slh = hi[k] >= S; tph = lo[k] <= TP0
        if adds < len(lv) and ((lo[k] <= lv[adds]) if side > 0 else (hi[k] >= lv[adds])):
            pos.append(lv[adds]); adds += 1
        if slh and tph: exit = S if abs(e0 - S) <= abs(e0 - TP0) else TP0; break
        elif slh: exit = S; break
        elif tph: exit = TP0; break
    if exit is None: exit = float(cl[-1])
    tot = len(pos); avg = sum(pos) / tot
    pnl = (exit - avg) * side / pip * pusd * tot
    hd = int(max(0, (tm[len(hi) - 1] - tm[0]) // 86400))
    pnl -= abs((pkt['swap_long'] if side > 0 else pkt['swap_short'])) * hd * LOT * tot
    risk0 = sd0 / pip * pusd
    return dict(pnl=pnl, R=pnl / max(risk0, 1e-9), adds=adds, win=1 if pnl > 0 else 0)

def replay_arm(pkt, h1, sigs, sl_mult, use_tp, cfg, atr_v, no_limits):
    pip = float(cfg.get('pip', pkt['point'])); pusd = float(cfg.get('pip_usd', 10.0)) * LOT
    rows = []; last_bar = {"long": -999, "short": -999}
    for s in sigs:
        i, side = int(s["bar"]), 1 if s["side"] > 0 else -1
        if i + 1 >= len(h1): continue
        if not no_limits:
            key = "long" if side > 0 else "short"
            if i - last_bar[key] < 30: continue
            last_bar[key] = i
        a = atr_v[i]
        if np.isnan(a) or a <= 0: continue
        sd0 = a * sl_mult if sl_mult is not None else abs(s["entry"] - s["sl"])
        if sl_mult is None and sd0 < slgate(a, s["entry"], pkt['point']): continue
        o = float(h1["open"].iloc[i + 1]); px = pkt['spread'] * pkt['point']
        e = o + px * side
        S = e - side * sd0
        T = e + side * RR * sd0 if use_tp else None
        end = min(i + 1 + MAXH, len(h1))
        hi, lo = h1["high"].values[i + 1:end], h1["low"].values[i + 1:end]
        tm = h1["time"].values[i + 1:end]; cl = h1["close"].values[i + 1:end]
        if len(hi) == 0: continue
        exit_ = None
        for k in range(len(hi)):
            sl_hit = (lo[k] <= S) if side > 0 else (hi[k] >= S)
            tp_hit = (hi[k] >= T) if (T is not None and side > 0) else ((T is not None) and (lo[k] <= T))
            if sl_hit: exit_ = S; break
            elif T is not None and tp_hit: exit_ = T; break
        if exit_ is None: exit_ = float(cl[-1])
        pnl = (exit_ - e) * side / pip * pusd - abs((pkt['swap_long'] if side > 0 else pkt['swap_short'])) * max(0, (int(tm[-1]) - int(tm[0])) // 86400) * LOT
        rows.append(pnl / (sd0 / pip * pusd))
    return rows

def run_dd(xs):
    c = peak = dd = 0.0
    for x in xs:
        c += x; peak = max(peak, c); dd = max(dd, peak - c)
    return dd

def stat(rows):
    if not rows: return {"n": 0}
    return {"n": len(rows), "cumR": round(sum(rows), 2), "meanR": round(sum(rows) / len(rows), 3),
            "wr": round(sum(1 for x in rows if x > 0) / len(rows), 3),
            "dd_R": round(run_dd(rows), 2), "maxloss_R": round(min(rows), 2)}

def ztest(p1, n1, p2, n2):
    if n1 < 2 or n2 < 2: return None
    ppool = (n1 * p1 + n2 * p2) / (n1 + n2)
    se = math.sqrt(max(ppool * (1 - ppool) * (1 / n1 + 1 / n2), 1e-12))
    return round((p2 - p1) / se, 3)

def main():
    t_start = time.time()
    syms = all_pkls()
    mine = syms[W::N]
    print(f"analyze248 worker{W}/{N}: 缓存 {len(syms)} 品种, 领 {len(mine)}", flush=True)
    res = {"generated": datetime.datetime.now().isoformat(), "worker": W, "n_workers": N,
           "lot_fixed": LOT, "rr": RR, "window_days": 180,
           "data_source": "mt5:60137964 自家终端 6mo(180d) H1/H4/D1 真K线(预取缓存), 0 外部; 手数固定0.01",
           "cross_zone_rule": "加仓目标=entry外侧离entry最近的下一供需区(修脏口径), B=中点+到区各1, C=到区1",
           "note": "R口径=品种内自洽(逐笔净/首单风险), 非UNIVERSE品种USD列仅参考; 纯回测 0写闸源 0进live"}
    if os.path.exists(OUT):
        try: res.update(json.load(open(OUT, encoding="utf-8")))
        except Exception: pass
    done = set(res.get("syms", {}))
    for j, sym in enumerate(mine, 1):
        if sym in done: continue
        t0 = time.time()
        fp = os.path.join(CACHE, f"{sym.replace('.', '_')}.pkl")
        try:
            pkt = pickle.load(open(fp, "rb"))
        except Exception as e:
            res.setdefault("syms", {})[sym] = {"err": f"缓存读不出: {str(e)[:60]}"}
            json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1); continue
        h1, h4, d1 = pkt["h1"], pkt["h4"], pkt["d1"]
        cfg = dict(su.UNIVERSE.get(sym, {}))
        try:
            sigs = PF.gen_pasd(h1, h4, d1, cfg)
        except Exception as e:
            res.setdefault("syms", {})[sym] = {"err": f"gen_pasd崩: {str(e)[:60]}"}
            json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"{j}/{len(mine)} {sym}: gen_pasd崩 {str(e)[:60]}", flush=True); continue
        for s in sigs: s['tp'] = s['entry'] + s['side'] * RR * abs(s['entry'] - s['sl'])
        zs = PF._detect_supply_demand_zones(h1['high'].values, h1['low'].values, h1['close'].values)
        atr_v = PF._atr(h1['high'].values.astype(float), h1['low'].values.astype(float), h1['close'].values.astype(float))
        sy = {"n_h1": len(h1), "n_sigs": len(sigs), "in_universe": sym in su.UNIVERSE}
        wrs = {}
        for mode, tag in [("A", "A_基线_不加"), ("C", "C_加1到区"), ("B", "B_加2中点+到区")]:
            rows = []
            for s in sigs:
                r = sim(pkt, h1, s, add_levels(s, zs['demand'], zs['supply'], mode), cfg, atr_v)
                if r is not None: rows.append(r)
            st = stat([r["R"] for r in rows])
            if rows:
                st["netUSD_001"] = round(sum(r["pnl"] for r in rows), 2)
                st["dd_USD_001"] = round(run_dd([r["pnl"] for r in rows]), 2)
                st["加仓触发笔数"] = sum(1 for r in rows if r["adds"] > 0)
            sy[tag] = st; wrs[tag] = st.get("wr", 0.0)
        sy["z_B_vs_A"] = ztest(wrs["A_基线_不加"], sy["A_基线_不加"]["n"], wrs["B_加2中点+到区"], sy["B_加2中点+到区"]["n"])
        base_pos = sy["A_基线_不加"].get("n", 0) > 0 and sy["A_基线_不加"].get("cumR", 0) > 0
        arms = {}
        for tag, (slm, use_tp, nl) in {"arm0_现状": (None, True, False), "arm1_扩SL2.4ATR": (2.4, True, True),
                                       "arm2_大SL4.0ATR": (4.0, True, True), "arm3_无TP扛单": (None, False, True),
                                       "arm4_全裸": (4.0, False, True), "arm5_无限制": (None, True, True)}.items():
            arms[tag] = stat(replay_arm(pkt, h1, sigs, slm, use_tp, cfg, atr_v, nl))
        sy["arms"] = arms
        a0, a4 = arms["arm0_现状"].get("cumR", 0), arms["arm4_全裸"].get("cumR", 0)
        worse = sum(1 for k in ("arm1_扩SL2.4ATR", "arm2_大SL4.0ATR", "arm3_无TP扛单", "arm4_全裸")
                    if arms[k].get("n") and arms[k]["cumR"] < a0)
        sy["judge_naked"] = "REJECT裸奔(各臂未改善现状)" if worse >= 2 or a4 <= a0 else "WATCH裸奔臂改善→五验+L4+demo"
        if sy["A_基线_不加"].get("n", 0) == 0:
            sy["judge_add"] = "SKIP: 0 信号"
        elif not base_pos:
            sy["judge_add"] = "REJECT加仓: 底仓6mo netR负(fam6铁律, 负底仓堆风险)"
        else:
            b_, a_ = sy["B_加2中点+到区"], sy["A_基线_不加"]
            sy["judge_add"] = ("加仓扭亏(B>A且回撤没顶大)" if b_.get("netUSD_001", 0) > a_.get("netUSD_001", 0)
                               and b_.get("dd_USD_001", 0) <= a_.get("dd_USD_001", 1) * 1.5
                               else "加仓顶大回撤/无增益(维持A)")
        res.setdefault("syms", {})[sym] = sy
        json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        if j % 10 == 0 or j == len(mine):
            el = time.time() - t0
            print(f"{sym}: sigs={len(sigs)} A={sy['A_基线_不加'].get('cumR')} B={sy['B_加2中点+到区'].get('cumR')} "
                  f"{sy['judge_add']} | {sy['judge_naked']} | {el:.0f}s (余{len(mine)-j}个)", flush=True)
    res["finished"] = datetime.datetime.now().isoformat()
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"worker{W} 完 → {OUT} 用时 {round((time.time()-t_start)/60,1)}min", flush=True)

if __name__ == "__main__":
    main()
