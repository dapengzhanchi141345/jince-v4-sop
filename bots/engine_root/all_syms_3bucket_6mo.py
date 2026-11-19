#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""全品种×6mo 统一枪 (L5, @user 2026-10-17 钦定: 全品种加大回测力度/手数固定0.01不扩大):
 32 个活体线品种 × (3桶 A不加/C加1/B加2 [跨区最近供需区口径] + 6臂裸奔), 同信号集同分母同成本面.
 取代 supd_mart_6mo / supd_naked_6mo / fixed001_3bucket (口径修正 2 格):
   ① 加仓目标 = entry 外侧【离 entry 最近】的下一供需区 (旧 fixed001 取列表最老区, 脏口径作废);
   ② USD 列 = 真 0.01 手折算 (pip_usd×0.01/标准手, 旧 fixed001 USD 列放大 ~100 倍作废, R 列仍可信).
 每品种只算一次 gen_pasd/供需区/ATR, 3桶+6臂全复用. 逐品种增量落盘 = 崩了断点续跑.
 0 LLM, 0 写闸源, 0 改 live. 数据源 = mt5:60137964 自家终端 6mo(180d) H1/H4/D1 真K线, 0 外部.
 跑法: ALL_SYMS_WORKER=k ALL_SYMS_N=m python all_syms_3bucket_6mo.py  (k 领 SYMS_ALL[k::m] 串行)
"""
import os, sys, json, datetime, math, time
os.chdir(r"E:\GoldstrategyEngine"); sys.path.insert(0, r"E:\GoldstrategyEngine")
import numpy as np, pandas as pd, MetaTrader5 as mt5
import symbol_universe as su, backtest_engine as BE
import pasd_fusion as PF

LOT = 0.01          # @user 钦定: 固定 0.01, 不扩大
RR = 2.5
DAYS = 180
MAXH = BE.MAX_HOLD_H1
# 活体线品种 = 外汇 28 + 金属 2 + 能源 2 (奇异/债券/农产品/币类不在活体路径, 不算, 0 混外部)
SYMS_ALL = ["EURUSD","GBPUSD","USDCHF","AUDUSD","USDCAD","NZDUSD","USDJPY",
            "EURGBP","EURCHF","EURNZD","EURCAD","EURAUD","GBPCHF","GBPNZD","GBPAUD","GBPCAD",
            "AUDNZD","AUDCHF","AUDCAD","CADCHF","NZDCHF","NZDCAD",
            "EURJPY","GBPJPY","AUDJPY","CADJPY","CHFJPY","NZDJPY",
            "XAUUSD","XAGUSD","XTIUSD","XBRUSD"]
W = int(os.environ.get("ALL_SYMS_WORKER", "0"))
N = int(os.environ.get("ALL_SYMS_N", "3"))
OUT = f"data/all_syms_6mo_w{W}.json"
MINE = SYMS_ALL[W::N]

def rates(sym, tf, d=DAYS):
    F = []; p = 0
    while True:
        c = mt5.copy_rates_from_pos(sym, tf, p, 5000)
        if c is None or len(c) == 0: break
        F.append(pd.DataFrame(c)); p += len(c)
        if len(c) < 5000 or p >= 20000: break
    if not F: return None
    df = pd.concat(F).drop_duplicates("time").sort_values("time").reset_index(drop=True)
    df["t"] = pd.to_datetime(df["time"], unit="s")
    return df[df["t"] >= df["t"].max() - pd.Timedelta(days=d)].reset_index(drop=True)

def add_levels(sig, zd, zs, mode):
    """跨区口径(修脏): 取 entry 外侧离 entry 最近的下一供需区. A=不加 C=到区加1 B=中点+到区加2.
    long: 整个 demand 区在 entry 下方(top<E), 取 top 最大者; short: 整个 supply 区在 entry 上方(bottom>E), 取 bottom 最小者."""
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

def sim(h1, sig, lv, cfg, sp, pt, swl, swh):
    """逐bar状态机. TP 固定原始(保守真胜口径, 判据用). 0.01 固定手数, USD=真折算."""
    i = int(sig['bar']); side = 1 if sig['side'] > 0 else -1
    if i + 1 >= len(h1): return None
    pip = float(cfg.get('pip', 0.0001)); pusd = float(cfg.get('pip_usd', 10.0)) * LOT  # USD/pip @0.01手
    sd0 = abs(sig["entry"] - sig["sl"]); td0 = abs(sig["entry"] - sig["tp"])
    o = float(h1['open'].iloc[i + 1]); a = sp * pt
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
    pnl -= abs((swl if side > 0 else swh)) * hd * LOT * tot
    risk0 = sd0 / pip * pusd  # 首单 0.01 手风险 (R 分母, 首单口径)
    return dict(pnl=pnl, R=pnl / max(risk0, 1e-9), adds=adds, win=1 if pnl > 0 else 0)

def replay_arm(h1, sigs, sl_mult, use_tp, cfg, sp, pt, swl, swh, atr_v, no_limits):
    """裸奔臂: 同信号集. sl_mult=None 用 gen_pasd 原SL; 数值 = sl_mult×ATR[bar]. use_tp=False 扛单无TP.
    no_limits=True 取消 30bar 同侧冷却. 0.01 手真折算."""
    pip = float(cfg.get('pip', 0.0001)); pusd = float(cfg.get('pip_usd', 10.0)) * LOT
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
        o = float(h1["open"].iloc[i + 1]); px = sp * pt
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
        pnl = (exit_ - e) * side / pip * pusd - abs((swl if side > 0 else swh)) * max(0, (int(tm[-1]) - int(tm[0])) // 86400) * LOT
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
    print(f"all_syms_3bucket_6mo worker{W}/{N} 起跑 领 {len(MINE)} 品种: {MINE}", flush=True)
    import mt5_login
    if not mt5.initialize(): print("MT5 init fail"); return
    ok, why = mt5_login.ensure_login(60137964)
    if not ok: print("LOGIN FAIL:", why); return
    res = {"generated": datetime.datetime.now().isoformat(), "worker": W, "n_workers": N,
           "lot_fixed": LOT, "rr": RR, "window_days": DAYS,
           "data_source": "mt5:60137964 自家终端 6mo(180d) H1/H4/D1 真K线, 0 外部数据; 手数固定0.01(@user 钦定), USD列真折算",
           "cross_zone_rule": "加仓目标=entry外侧离entry最近的下一供需区(修脏口径), B=中点+到区各1, C=到区1",
           "note": "纯回测参考, 0写闸源 0进live; 数据好也只出WATCH提案(五验+L4+demo). 逐品种增量落盘可断点续跑"}
    if os.path.exists(OUT):
        try: res.update(json.load(open(OUT, encoding="utf-8")))
        except Exception: pass
    done_syms = set(res.get("syms", {}))
    avg_s = 0.0
    for sym in MINE:
        if sym in done_syms: print(f"{sym}: 已有, 跳过(续跑)"); continue
        t0 = time.time()
        cfg = dict(su.UNIVERSE.get(sym, {}))
        info = mt5.symbol_info(sym)
        if info is None:
            res.setdefault("syms", {})[sym] = {"err": "SKIP: 终端无此品种"}; json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"{sym}: 终端无此品种, SKIP", flush=True); continue
        sp, pt = info.spread or 10, info.point or 1e-5
        swl, swh = info.swap_long or 0, info.swap_short or 0
        h1 = rates(sym, mt5.TIMEFRAME_H1); h4 = rates(sym, mt5.TIMEFRAME_H4); d1 = rates(sym, mt5.TIMEFRAME_D1)
        if h1 is None or len(h1) < 100:
            res.setdefault("syms", {})[sym] = {"err": "H1短", "n_h1": 0 if h1 is None else len(h1)}
            json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1); print(sym, "H1短", flush=True); continue
        sigs = PF.gen_pasd(h1, h4, d1, cfg)
        for s in sigs: s['tp'] = s['entry'] + s['side'] * RR * abs(s['entry'] - s['sl'])
        zs = PF._detect_supply_demand_zones(h1['high'].values, h1['low'].values, h1['close'].values)
        atr_v = PF._atr(h1['high'].values.astype(float), h1['low'].values.astype(float), h1['close'].values.astype(float))
        sy = {"n_h1": len(h1), "n_sigs": len(sigs), "spread": sp}
        # 3 桶 (固定 0.01, TP 固定保守口径)
        wrs = {}
        for mode, tag in [("A", "A_基线_不加"), ("C", "C_加1到区"), ("B", "B_加2中点+到区")]:
            rows = []
            for s in sigs:
                lv = add_levels(s, zs['demand'], zs['supply'], mode)
                r = sim(h1, s, lv, cfg, sp, pt, swl, swh)
                if r is not None: rows.append(r)
            st = stat([r["R"] for r in rows])
            st["netUSD_001"] = round(sum(r["pnl"] for r in rows), 2) if rows else 0.0
            st["dd_USD_001"] = round(run_dd([r["pnl"] for r in rows]), 2) if rows else 0.0
            st["加仓触发笔数"] = sum(1 for r in rows if r["adds"] > 0)
            sy[tag] = st
            wrs[tag] = st.get("wr", 0.0)
        # 同分母 z: B vs A 胜率 (同一信号集)
        sy["z_B_vs_A"] = ztest(wrs["A_基线_不加"], sy["A_基线_不加"]["n"], wrs["B_加2中点+到区"], sy["B_加2中点+到区"]["n"])
        base_pos = sy["A_基线_不加"].get("cumR", 0) > 0
        # 6 臂裸奔 (同信号集)
        arms = {}
        for tag, (slm, use_tp, nl) in {"arm0_现状": (None, True, False), "arm1_扩SL2.4ATR": (2.4, True, True),
                                       "arm2_大SL4.0ATR": (4.0, True, True), "arm3_无TP扛单": (None, False, True),
                                       "arm4_全裸": (4.0, False, True), "arm5_无限制": (None, True, True)}.items():
            arms[tag] = stat(replay_arm(h1, sigs, slm, use_tp, cfg, sp, pt, swl, swh, atr_v, nl))
        sy["arms"] = arms
        a0, a4 = arms["arm0_现状"].get("cumR", 0), arms["arm4_全裸"].get("cumR", 0)
        worse = sum(1 for k in ("arm1_扩SL2.4ATR", "arm2_大SL4.0ATR", "arm3_无TP扛单", "arm4_全裸")
                    if arms[k].get("n") and arms[k]["cumR"] < a0)
        sy["judge_naked"] = "REJECT裸奔: 扩SL/无限制各臂均未改善现状" if worse >= 2 or a4 <= a0 else "WATCH: 裸奔臂改善现状 → 提案走五验+L4+demo (0直改live)"
        if not base_pos:
            sy["judge_add"] = "REJECT加仓: 底仓6mo netR负 → 负底仓堆风险(fam6铁律), 加仓不判"
        else:
            b_, a_ = sy["B_加2中点+到区"], sy["A_基线_不加"]
            sy["judge_add"] = ("加仓扭亏(B>A 且回撤没顶大)" if b_.get("netUSD_001", 0) > a_.get("netUSD_001", 0)
                               and b_.get("dd_USD_001", 0) <= a_.get("dd_USD_001", 1) * 1.5
                               else "加仓顶大回撤/无增益(维持A基线)")
        res.setdefault("syms", {})[sym] = sy
        json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)  # 逐品种增量落盘防崩
        avg_s = avg_s * 0.5 + (time.time() - t0) * 0.5
        remain = len(MINE) - MINE.index(sym) - 1
        print(f"{sym}: sigs={len(sigs)} A_cumR={sy['A_基线_不加'].get('cumR')} B_cumR={sy['B_加2中点+到区'].get('cumR')} "
              f"z={sy['z_B_vs_A']} | {sy['judge_add']} | {sy['judge_naked']} | {time.time()-t0:.0f}s 落盘 "
              f"ETA余 {round(remain*avg_s/60, 1)}min", flush=True)
    res["finished"] = datetime.datetime.now().isoformat()
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"worker{W} 全完 → {OUT}", flush=True)
    mt5.shutdown()

if __name__ == "__main__":
    main()
