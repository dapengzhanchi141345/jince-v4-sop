#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""IN-04 RR 平顶区扫描 (L5 sweep 执行线, @hermes 内化台账点名).
同分母纪律: 固定 SL_Atr_mult(=风险单位), 只扫 TP_RR 四档(1.5/2.0/2.5/3.0),
用引擎自己 simulate_signal(扣真实点差+swap) 回放, R 归一化 = pnl$ / 该信号风险$ (同分母),
找「扣成本后 mean_R 最大且邻域不翻转」的平顶区. 0 LLM, 确定性.
产物: data/pasd_rr_sweep.json + 群可报的平顶判词. 0 改 live 参数, 只出"该锁哪个 RR".
"""
import os, sys, json, time, datetime, itertools
os.chdir(r"E:\GoldstrategyEngine"); sys.path.insert(0, r"E:\GoldstrategyEngine")
import numpy as np, pandas as pd, MetaTrader5 as mt5
import symbol_universe as su, advanced_strategies as ast, backtest_engine as BE
import pasd_fusion as PF

OOS4 = ["CADJPY","EURJPY","EURNZD","GBPCAD"]
RR_TIERS = [1.5, 2.0, 2.5, 3.0]
DAYS = 90

def rates_3mo(sym, tf, days=DAYS):
    frames=[]; pos=0; CAP=5000
    while True:
        c = mt5.copy_rates_from_pos(sym, tf, pos, CAP)
        if c is None or len(c)==0: break
        frames.append(pd.DataFrame(c)); pos+=len(c)
        if len(c)<CAP: break
        if pos >= 20000: break
    if not frames: return None
    df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    df["t"]=pd.to_datetime(df["time"], unit="s")
    df = df[df["t"] >= df["t"].max()-pd.Timedelta(days=days)].reset_index(drop=True)
    return df

def simulate_set(h1, sigs, cfg, spread_pts, point, swl, swh):
    """复用引擎 simulate_signal 逐信号回放, R 归一化."""
    lot=float(cfg.get('lot',0.1)); pip=float(cfg.get('pip',0.0001)); pusd=float(cfg.get('pip_usd',10.0))
    Rsum=0.0; n=0; w=0; gw=0.0; gl=0.0
    for s in sigs:
        pnl = BE.simulate_signal(h1, s, spread_pts, point, swl, swh, lot, pip, pusd)
        if pnl is None: continue
        risk = abs(float(s['entry'])-float(s['sl']))/pip*pusd*lot
        if risk<=0: continue
        Rsum += pnl/risk; n+=1; gw+=max(0,pnl); gl+=max(0,-pnl)
        if pnl>=0: w+=1
    pf = (gw/gl) if gl>1e-9 else (float('inf') if gw>0 else 0.0)
    return dict(n=n, wr=round(w/n,3) if n else 0.0, pf=round(pf,3),
                mean_R=round(Rsum/n,3) if n else 0.0, net_R_total=round(Rsum,2))

def sweep_symbol(sym):
    cfg=su.UNIVERSE.get(sym,{})
    info=mt5.symbol_info(sym)
    sp=info.spread if info and info.spread>0 else 10
    pt=info.point if info else 1e-5
    swl=info.swap_long if info else 0; swh=info.swap_short if info else 0
    h1=rates_3mo(sym, mt5.TIMEFRAME_H1); h4=rates_3mo(sym, mt5.TIMEFRAME_H4); d1=rates_3mo(sym, mt5.TIMEFRAME_D1)
    if h1 is None or len(h1)<100: return {sym:{"error":"H1不足"}}
    # [关键优化] TP_RR 只改 TP 落点, 不影响信号生成 -> gen_pasd 只跑 1 次(慢头),
    #   RR 四档复用同一信号集, 只重算 tp = entry ± risk*rr 再 simulate(快). 避免 16 次 gen_pasd.
    try:
        sigs_base = PF.gen_pasd(h1, h4, d1, cfg)
    except Exception as e:
        return {sym:{"error":"gen_pasd: "+str(e)[:60]}}
    rows={}
    for rr in RR_TIERS:
        sigs=[]
        for s in sigs_base:
            s2=dict(s)
            risk=abs(s2["entry"]-s2["sl"])
            s2["tp"]= s2["entry"]+risk*rr if s2["side"]>0 else s2["entry"]-risk*rr
            sigs.append(s2)
        rows[str(rr)] = simulate_set(h1, sigs, cfg, sp, pt, swl, swh)
    return {sym:{"spread_pts":sp,"tiers":rows}}

def main():
    if not mt5.initialize(): print("MT5 init fail"); sys.exit(1)
    out={"generated":datetime.datetime.now().isoformat(),"window_days":DAYS,
         "rr_tiers":RR_TIERS,"note":"IN-04 平顶区扫描, 固定SL_Atr, 只扫TP_RR, 引擎simulate_signal扣真实点差, R归一化同分母"}
    for sym in OOS4:
        r=sweep_symbol(sym); out.setdefault("per_symbol",{}).update(r)
        d=r[sym]; 
        if "error" in d: print(sym,d["error"]); continue
        line=" ".join("RR%s n=%d R=%s pf=%s"%(k,v["n"],v["mean_R"],v["pf"]) for k,v in d["tiers"].items())
        print(sym,"|",line)
    json.dump(out, open("data/pasd_rr_sweep.json","w",encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    # 平顶判词: 找每腿 mean_R 最大档 + 邻域(前后档)是否同侧(不翻转)
    print("\n=== 平顶判词 (mean_R 最大档 + 邻域不翻转) ===")
    for sym,d in out["per_symbol"].items():
        if "error" in d: continue
        ts=d["tiers"]; best=max(ts, key=lambda k: ts[k]["mean_R"])
        idx=RR_TIERS.index(float(best))
        flat=(idx>0 and idx<len(RR_TIERS)-1 and ts[RR_TIERS[idx-1]]["mean_R"]>0 and ts[RR_TIERS[idx+1]]["mean_R"]>0)
        mono=all(0<ts[RR_TIERS[i]]["mean_R"]<=ts[RR_TIERS[i+1]]["mean_R"] for i in range(len(RR_TIERS)-1))
        print("%-8s best=RR%s mean_R=%s n=%d | 平顶=%s 单调升=%s" % (sym,best,ts[best]["mean_R"],ts[best]["n"],flat,mono))
    print("产物: data/pasd_rr_sweep.json")
    mt5.shutdown()

if __name__=="__main__": main()
