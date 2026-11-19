#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""EURJPY-PASD 深度回测 (分析驱动, 非盲扫). 假设全部来自在盘实数:
H1 首次回踩(SMC实证:回踩>=3次区期望-0.37R) / H2 RR右边界3.5/4.0(IN-04单调升,3.0是端点没探)
/ H3 killzone 07-16UTC(会话研究). 方法: 6个月窗 WF切4段x45天, 同分母A/B, 逐段符号一致性.
确定性0 LLM, 0写闸源, 0改live. 产物 data/eurjpy_pasd_deep.json.
"""
import os, sys, json, datetime
os.chdir(r"E:\GoldstrategyEngine"); sys.path.insert(0, r"E:\GoldstrategyEngine")
import numpy as np, pandas as pd, MetaTrader5 as mt5
import symbol_universe as su, backtest_engine as BE
import pasd_fusion as PF
SYM, DAYS, MAXH = "EURJPY", 180, BE.MAX_HOLD_H1

def rates(sym, tf, d=DAYS):
    F=[]; p=0
    while True:
        c = mt5.copy_rates_from_pos(sym, tf, p, 5000)
        if c is None or len(c)==0: break
        F.append(pd.DataFrame(c)); p += len(c)
        if len(c)<5000 or p>=20000: break
    if not F: return None
    df = pd.concat(F).drop_duplicates("time").sort_values("time").reset_index(drop=True)
    df["t"]=pd.to_datetime(df["time"], unit="s")
    return df[df["t"]>=df["t"].max()-pd.Timedelta(days=d)].reset_index(drop=True)

def sim(h1, sig, sp, pt, swl, swh, rr):
    """引擎口径回放 + RR 可变(TP=entry±risk*rr). 返回每笔 R / 逐bar净盈亏序列."""
    lot, pip, pusd = 0.1, 0.0001, 10.0
    i, side = int(sig["bar"]), 1 if sig["side"]>0 else -1
    if i+1>=len(h1): return None
    sd0 = abs(sig["entry"]-sig["sl"])
    o = float(h1["open"].iloc[i+1]); a = sp*pt
    e = o+a if side>0 else o-a
    S = e-sd0 if side>0 else e+sd0
    T = e+side*rr*sd0
    end = min(i+1+MAXH, len(h1))
    hi, lo = h1["high"].values[i+1:end], h1["low"].values[i+1:end]
    tm, op = h1["time"].values[i+1:end], h1["open"].values[i+1:end]
    if len(hi)==0: return None
    exit = float(op[-1])
    for k in range(len(hi)):
        if side>0: slh, tph = lo[k]<=S, hi[k]>=T
        else:      slh, tph = hi[k]>=S, lo[k]<=T
        if slh and tph: exit = S if sd0<=sd0*rr else T; break
        elif slh: exit=S; break
        elif tph: exit=T; break
    hd = max(0,(tm[len(hi)-1]-tm[0])//86400) if len(hi)>1 else 0
    sw = (swl if side>0 else swh)*hd*lot
    pnl = (exit-e)*side/pip*pusd*lot - abs(sw)
    return pnl/(sd0/pip*pusd*lot)   # 每笔净 R

def main():
    if not mt5.initialize(): print("MT5 fail"); return
    cfg = su.UNIVERSE.get(SYM, {})
    info = mt5.symbol_info(SYM)
    sp, pt = info.spread or 10, info.point or 1e-5
    swl, swh = info.swap_long or 0, info.swap_short or 0
    h1, h4, d1 = rates(SYM, mt5.TIMEFRAME_H1), rates(SYM, mt5.TIMEFRAME_H4), rates(SYM, mt5.TIMEFRAME_D1)
    sigs = PF.gen_pasd(h1, h4, d1, cfg)
    zs = PF._detect_supply_demand_zones(h1["high"].values, h1["low"].values, h1["close"].values)
    lo_v = h1["low"].values
    # --- 每笔信号的结构分析 (分析层, 定假设用) ---
    for s in sigs:
        i, E, side = int(s["bar"]), s["entry"], s["side"]
        # 对应 zone: 多头→下方最近需求区, 空头→上方最近供给区
        if side>0:
            cand = [z for z in zs["demand"] if z["top"] < E]
        else:
            cand = [z for z in zs["supply"] if z["bottom"] > E]
        z = min(cand, key=lambda zz: abs((zz["top"] if side>0 else zz["bottom"])-E)) if cand else None
        s["z"] = z
        if z is not None:
            # 首次回踩计数: 信号 bar 之前, 价格「进入该 zone」的连续段数 (段间不贴算新段)
            hi_v = h1["high"].values
            if side>0:
                in_z = (lo_v[:i+1] <= z["top"]) & (lo_v[:i+1] >= z["bottom"])
            else:
                in_z = (hi_v[:i+1] >= z["bottom"]) & (hi_v[:i+1] <= z["top"])
            # 进入段数 = 0->1 的跳变次数
            edge = np.diff(np.concatenate(([0], in_z.astype(int))))
            s["revisit"] = int(np.sum(edge > 0))
        else:
            s["revisit"] = 99
        s["hour"] = int(pd.to_datetime(h1["time"].iloc[i], unit="s").hour)
    # --- 6个月切 4 段 WF (各 45 天), 同分母 A/B ---
    tmin, tmax = h1["time"].iloc[0], h1["time"].iloc[-1]
    day45 = int((tmax-tmin)//86400//4)
    segs = []
    for k in range(4):
        lo, hi_ = tmin+k*day45, tmin+(k+1)*day45 if k<3 else tmax+86400
        segs.append([s for s in sigs if lo <= s.get("time", h1["time"].iloc[int(s["bar"])]) < hi_])
    # 信号 time 字段: gen_pasd 未存 -> 用 bar 时间补
    for s in sigs: s["time"] = int(h1["time"].iloc[int(s["bar"])])
    segs = []
    for k in range(4):
        lo, hi_ = tmin+k*day45, (tmin+(k+1)*day45 if k<3 else tmax+86400)
        segs.append([s for s in sigs if lo <= s["time"] < hi_])
    out = {"generated": datetime.datetime.now().isoformat(), "symbol": SYM, "window_days": DAYS,
           "total_sigs": len(sigs), "hypotheses": {"H1":"首次回踩(revisit<=1)", "H2":"RR3.5/4.0右边界", "H3":"killzone 07-16UTC"},
           "wf": "6mo切4段x45天, 同分母A/B, 逐段符号一致才认"}
    GRID = {"base_RR2.5": lambda s: (2.5, True),
            "H1_首踩_RR2.5": lambda s: (2.5, s.get("revisit",99)<=1),
            "H2_RR3.5": lambda s: (3.5, True),
            "H2_RR4.0": lambda s: (4.0, True),
            "H3_时段_RR2.5": lambda s: (2.5, 7<=s["hour"]<16),
            "组合_H1+H3": lambda s: (2.5, s.get("revisit",99)<=1 and 7<=s["hour"]<16)}
    results = {}
    for tag, fn in GRID.items():
        per = []
        for seg_i, seg in enumerate(segs):
            kept = [s for s in seg if fn(s)[1]]
            rs = [r for r in (sim(h1, s, sp, pt, swl, swh, fn(s)[0]) for s in kept) if r is not None]
            per.append({"n": len(rs), "netR": round(sum(rs),2) if rs else 0.0,
                       "meanR": round(sum(rs)/len(rs),3) if rs else None})
        tot = [p for p in per if p["n"]]
        cons = (len(tot)>=3 and all(p["netR"]>0 for p in tot))
        results[tag] = {"per_seg": per, "total_n": sum(p["n"] for p in per),
                        "total_netR": round(sum(p["netR"] for p in per),2),
                        "pos_segs": sum(1 for p in tot if p["netR"]>0), "consistent": cons}
        print(f"{tag:16s} seg净R={[p['netR'] for p in per]} n={[p['n'] for p in per]} 一致={cons}")
    out["grid"] = results
    json.dump(out, open("data/eurjpy_pasd_deep.json","w"), ensure_ascii=False, indent=1, default=str)
    print("产物: data/eurjpy_pasd_deep.json")
    mt5.shutdown()

if __name__=="__main__": main()
