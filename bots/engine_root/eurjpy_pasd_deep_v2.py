#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""EURJPY-PASD 深枪 v2 轻化版 (原版被回收, 日志0字节无进程).
轻化核心: 过滤型假设(H1首踩/H3时段)不重放 — 它们只改变"算哪些笔",
  同 RR2.5 下直接切 base 每笔 R 值; 只有 RR3.5/4.0 需重放. 总回放 6组→3组.
  每笔 R 逐笔存盘(flush), 被杀也能 salvage 进度. 假设卡见 eurjpy_pasd_deep_hypo_cards.json.
"""
import os, sys, json, datetime
os.chdir(r"E:\GoldstrategyEngine"); sys.path.insert(0, r"E:\GoldstrategyEngine")
import numpy as np, pandas as pd, MetaTrader5 as mt5
import symbol_universe as su, backtest_engine as BE
import pasd_fusion as PF
SYM, DAYS = "EURJPY", 180
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

def main():
    if not mt5.initialize(): print("MT5 fail"); return
    cfg = su.UNIVERSE.get(SYM, {}); info = mt5.symbol_info(SYM)
    sp, pt = info.spread or 10, info.point or 1e-5
    swl, swh = info.swap_long or 0, info.swap_short or 0
    h1, h4, d1 = rates(SYM, mt5.TIMEFRAME_H1), rates(SYM, mt5.TIMEFRAME_H4), rates(SYM, mt5.TIMEFRAME_D1)
    sigs = PF.gen_pasd(h1, h4, d1, cfg)
    zs = PF._detect_supply_demand_zones(h1["high"].values, h1["low"].values, h1["close"].values)
    lo_v, hi_v = h1["low"].values, h1["high"].values
    for s in sigs:
        i, E, side = int(s["bar"]), s["entry"], s["side"]
        cand = ([z for z in zs["demand"] if z["top"]<E] if side>0 else [z for z in zs["supply"] if z["bottom"]>E])
        z = min(cand, key=lambda zz: abs((zz["top"] if side>0 else zz["bottom"])-E)) if cand else None
        if z is not None:
            if side>0: in_z = (lo_v[:i+1]<=z["top"])&(lo_v[:i+1]>=z["bottom"])
            else:      in_z = (hi_v[:i+1]>=z["bottom"])&(hi_v[:i+1]<=z["top"])
            s["revisit"] = int(np.sum(np.diff(np.concatenate(([0], in_z.astype(int))))>0))
        else:
            s["revisit"] = 99
        s["hour"] = int(pd.to_datetime(h1["time"].iloc[i], unit="s").hour)
        s["time"] = int(h1["time"].iloc[i])
    # 4 段 WF (各 45 天)
    tmin, tmax = h1["time"].iloc[0], h1["time"].iloc[-1]
    day45 = int((tmax-tmin)//86400//4)
    def segs_of(ss):
        out=[]
        for k in range(4):
            lo,hi_ = tmin+k*day45*86400, (tmin+(k+1)*day45*86400 if k<3 else tmax+86400)
            out.append([s for s in ss if lo<=s["time"]<hi_])
        return out
    out = {"generated":datetime.datetime.now().isoformat(),"symbol":SYM,"window_days":DAYS,
           "total_sigs":len(sigs),"wf":"6mo切4段x45天","note":"轻化版: H1/H3/H1+H3 切 base R 值(不重放), 仅 RR3.5/4.0 重放"}
    # base 回放一次 (RR2.5) — 逐笔 R + 存盘 salvage
    MAXH = BE.MAX_HOLD_H1
    base_rows = []
    for s in sigs:
        i, side = int(s["bar"]), 1 if s["side"]>0 else -1
        if i+1>=len(h1): continue
        sd0 = abs(s["entry"]-s["sl"]); rr = 2.5
        o = float(h1["open"].iloc[i+1]); a = sp*pt
        e = o+a if side>0 else o-a
        S = e-sd0 if side>0 else e+sd0
        T = e+side*rr*sd0
        end = min(i+1+MAXH, len(h1))
        hi, lo = h1["high"].values[i+1:end], h1["low"].values[i+1:end]
        tm, op = h1["time"].values[i+1:end], h1["open"].values[i+1:end]
        if len(hi)==0: continue
        exit = float(op[-1])
        for k in range(len(hi)):
            if side>0: slh,tph = lo[k]<=S, hi[k]>=T
            else:      slh,tph = hi[k]>=S, lo[k]<=T
            if slh and tph: exit = S; break
            elif slh: exit = S; break
            elif tph: exit = T; break
        hd = max(0,(tm[len(hi)-1]-tm[0])//86400) if len(hi)>1 else 0
        sw = (swl if side>0 else swh)*hd*0.1
        pnl = (exit-e)*side/0.0001*10.0*0.1 - abs(sw)
        base_rows.append({"time":s["time"],"revisit":s["revisit"],"hour":s["hour"],
                          "R":pnl/(sd0/0.0001*10.0*0.1)})
    base_df = pd.DataFrame(base_rows)
    json.dump({"n":len(base_df),"meanR":round(base_df['R'].mean(),3),"cumR":round(base_df['R'].sum(),2)},
              open("data/eurjpy_pasd_deep_salvage.json","w"))
    print("base 回放完 n=%d 逐笔已存盘 salvage" % len(base_df), flush=True)
    # 分段 helper
    def segstats(ss):
        segs = segs_of(ss); out=[]
        for st in segs: out.append({"n":len(st),"netR":round(float(st['R'].sum()) if len(st) else 0,2),
                                   "meanR":round(float(st['R'].mean()) if len(st) else None,3) if len(st) else None})
        return out
    GRID = {
      "base_RR2.5": base_df,
      "H1_首踩": base_df[base_df["revisit"]<=1],
      "H3_killzone": base_df[(base_df["hour"]>=7)&(base_df["hour"]<16)],
      "组合_H1+H3": base_df[(base_df["revisit"]<=1)&(base_df["hour"]>=7)&(base_df["hour"]<16)]}
    results = {}
    for tag, df in GRID.items():
        per = segstats(df)
        tot = [p for p in per if p["n"]]
        results[tag] = {"per_seg":per, "total_n":int(len(df)), "total_netR":round(float(df['R'].sum()),2),
                        "pos_segs":sum(1 for p in tot if p["netR"]>0),
                        "consistent":(len(tot)>=3 and all(p["netR"]>0 for p in tot))}
        print(f"{tag:14s} seg净R={[p['netR'] for p in per]} n={[p['n'] for p in per]} 一致={results[tag]['consistent']}", flush=True)
    # RR3.5 / 4.0 重放 (仅这两组, 轻化的重点)
    for rr in (3.5, 4.0):
        rows=[]
        for s in sigs:
            i, side = int(s["bar"]), 1 if s["side"]>0 else -1
            if i+1>=len(h1): continue
            sd0 = abs(s["entry"]-s["sl"])
            o = float(h1["open"].iloc[i+1]); a = sp*pt
            e = o+a if side>0 else o-a
            S = e-sd0 if side>0 else e+sd0
            T = e+side*rr*sd0
            end = min(i+1+MAXH, len(h1))
            hi, lo = h1["high"].values[i+1:end], h1["low"].values[i+1:end]
            tm, op = h1["time"].values[i+1:end], h1["open"].values[i+1:end]
            if len(hi)==0: continue
            exit = float(op[-1])
            for k in range(len(hi)):
                if side>0: slh,tph = lo[k]<=S, hi[k]>=T
                else:      slh,tph = hi[k]>=S, lo[k]<=T
                if slh and tph: exit = S; break
                elif slh: exit = S; break
                elif tph: exit = T; break
            hd = max(0,(tm[len(hi)-1]-tm[0])//86400) if len(hi)>1 else 0
            sw = (swl if side>0 else swh)*hd*0.1
            pnl = (exit-e)*side/0.0001*10.0*0.1 - abs(sw)
            rows.append({"time":s["time"],"revisit":s["revisit"],"hour":s["hour"],
                         "R":pnl/(sd0/0.0001*10.0*0.1)})
        df = pd.DataFrame(rows)
        per = segstats(df)
        tot = [p for p in per if p["n"]]
        results[f"H2_RR{rr}"] = {"per_seg":per, "total_n":int(len(df)), "total_netR":round(float(df['R'].sum()),2),
                                  "pos_segs":sum(1 for p in tot if p["netR"]>0),
                                  "consistent":(len(tot)>=3 and all(p["netR"]>0 for p in tot))}
        print(f"H2_RR{rr:4}  seg净R={[p['netR'] for p in per]} 一致={results[f'H2_RR{rr}']['consistent']}", flush=True)
    out["grid"] = results
    # 假设卡对照判词
    b = results["base_RR2.5"]["total_netR"]
    out["verdicts"] = {
      "H1": "PASS" if results["H1_首踩"]["total_netR"]>b and results["H1_首踩"]["consistent"] else "REJECT",
      "H2": ("平顶含3.5" if results["H2_RR3.5"]["total_netR"]>=b else "峰在3.0,锁2.5"),
      "H3": "PASS" if results["H3_killzone"]["total_netR"]>b and results["H3_killzone"]["consistent"] else "REJECT"}
    print("判词:", out["verdicts"])
    json.dump(out, open("data/eurjpy_pasd_deep.json","w"), ensure_ascii=False, indent=1, default=str)
    print("产物: data/eurjpy_pasd_deep.json")
    mt5.shutdown()

if __name__=="__main__": main()
