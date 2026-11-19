#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SUPD-MART 结构区小马丁回测 v2 (L5, 用户 10-16 指令 + "波动=震荡行情").
规则(用户原话): 浮亏加仓, 间距挂下一结构区 中间/底部分别加, 只加 2 次. 确定性 0 LLM,
成本面=引擎 simulate 口径(下根开盘+点差/逐bar先触/swap按持仓天). 0 写闸源 0 改 live.
产物 data/supd_mart_backtest.json.
"""
import os, sys, json, datetime
os.chdir(r"E:\GoldstrategyEngine"); sys.path.insert(0, r"E:\GoldstrategyEngine")
import numpy as np, pandas as pd, MetaTrader5 as mt5
import symbol_universe as su, backtest_engine as BE
import pasd_fusion as PF

OOS4 = ["CADJPY","EURJPY","EURNZD","GBPCAD"]
DAYS, MAX_HOLD, RR = 90, BE.MAX_HOLD_H1, 2.5   # RR 用 IN-04 锁定保守档

def rates_3mo(sym, tf, days=DAYS):
    frames=[]; pos=0; CAP=5000
    while True:
        c = mt5.copy_rates_from_pos(sym, tf, pos, CAP)
        if c is None or len(c)==0: break
        frames.append(pd.DataFrame(c)); pos+=len(c)
        if len(c)<CAP or pos>=20000: break
    if not frames: return None
    df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    df["t"]=pd.to_datetime(df["time"], unit="s")
    return df[df["t"]>=df["t"].max()-pd.Timedelta(days=days)].reset_index(drop=True)

def add_levels(sig, zs_supply, zs_demand):
    """加仓位: 多头浮亏→下方需求区(中/底加2次); 空头浮亏→上方供给区(中/顶加2次). 最多2."""
    E, side = sig["entry"], sig["side"]
    lv = []
    if side>0:
        cand=[z for z in zs_demand if z["bottom"]<E][:1]
        for z in cand:
            lv.append((z["top"]+z["bottom"])/2.0)   # 加1: 区中间
            lv.append(z["bottom"])                    # 加2: 区底部
    else:
        cand=[z for z in zs_supply if z["top"]>E][:1]
        for z in cand:
            lv.append((z["top"]+z["bottom"])/2.0)
            lv.append(z["top"])
    return lv[:2]

def sim_mart(h1, sig, add_lv, cfg, sp_pts, point, swl, swh):
    """多仓合并回放. 返回 dict(net, risk_R, add). None=数据不足."""
    lot=float(cfg.get('lot',0.1)); pip=float(cfg.get('pip',0.0001)); pusd=float(cfg.get('pip_usd',10.0))
    i=int(sig['bar']); side=1 if sig['side']>0 else -1
    if i+1>=len(h1): return None
    sl_dist=abs(sig['entry']-sig['sl']); tp_dist=abs(sig['entry']-sig['tp'])
    o=float(h1['open'].iloc[i+1]); a=sp_pts*point
    entry=o+a if side>0 else o-a
    S=entry-sl_dist if side>0 else entry+sl_dist
    end=min(i+1+MAX_HOLD, len(h1)); hi=h1['high'].values[i+1:end]; lo=h1['low'].values[i+1:end]
    tm=h1['time'].values[i+1:end]; op=h1['open'].values[i+1:end]
    if len(hi)==0: return None
    poss=[(entry, lot)]; adds=0
    for lvl in add_lv:   # 顺序: 先中间后底部
        if (lo<=lvl).any() if side>0 else (hi>=lvl).any():
            poss.append((lvl, lot)); adds+=1
    if adds:
        tot=sum(w for _,w in poss); avg=sum(p*w for p,w in poss)/tot
        T=avg+side*RR*sl_dist
        risk=sum(abs(p-S)*w for p,w in poss)/pip*pusd
    else:
        tot=lot; T=entry+tp_dist if side>0 else entry-tp_dist
        risk=sl_dist*lot/pip*pusd
    exit_px=float(op[-1])
    for k in range(len(hi)):
        if side>0: slh=(lo[k]<=S); tph=(hi[k]>=T)
        else:      slh=(hi[k]>=S); tph=(lo[k]<=T)
        if slh and tph:
            exit_px = S if abs(entry-S)<=abs(entry-T) else T; break
        elif slh: exit_px=S; break
        elif tph: exit_px=T; break
    hold_days=max(0,(tm[len(hi)-1]-tm[0])//86400) if len(hi)>1 else 0
    sw=swl if side>0 else swh
    pnl=(exit_px-sum(p*w for p,w in poss)/tot)*side/pip*pusd*tot - abs(sw*hold_days*tot)
    return dict(net=pnl, risk=risk, add=adds)

def main():
    if not mt5.initialize(): print("MT5 init fail"); sys.exit(1)
    out={"generated":datetime.datetime.now().isoformat(),"window_days":DAYS,"rr":RR,
         "design":"用户指令: 浮亏加2次(结构区中/底), 震荡市; 对照 fam6 铁律=负期望上堆风险, 0 转正除非同分母net_R转正且回撤不破线"}
    for sym in OOS4:
        cfg=su.UNIVERSE.get(sym,{})
        info=mt5.symbol_info(sym)
        sp=info.spread if info and info.spread>0 else 10
        pt=info.point if info else 1e-5
        swl=info.swap_long if info else 0; swh=info.swap_short if info else 0
        h1=rates_3mo(sym,mt5.TIMEFRAME_H1); h4=rates_3mo(sym,mt5.TIMEFRAME_H4); d1=rates_3mo(sym,mt5.TIMEFRAME_D1)
        if h1 is None or len(h1)<100: out[sym]={"error":"H1 不足"}; print(sym,"H1 不足"); continue
        sigs=PF.gen_pasd(h1,h4,d1,cfg)
        for s in sigs: s["tp"]=s["entry"]+(abs(s["entry"]-s["sl"])*RR)*(1 if s["side"]>0 else -1)
        zs=PF._detect_supply_demand_zones(h1['high'].values,h1['low'].values,h1['close'].values)
        res={}
        for label,lv_fn in [("base",lambda s:[]),("mart2",lambda s:add_levels(s,zs["demand"],zs["supply"]))]:
            net=0.0; n=0; adds_t=0; dd=0.0
            for s in sigs:
                r=sim_mart(h1,s,lv_fn(s),cfg,sp,pt,swl,swh)
                if r is None: continue
                net+=r["net"]/r["risk"]; n+=1; adds_t+=r["add"]; dd=max(dd,r["risk"])
            res[label]=dict(n=n, net_R=round(net,2), avg_add=round(adds_t/max(1,n),2), mdd_R=round(dd/max(1e-9,net if net<0 else 1),2) if n else 0)
        out[sym]={"spread":sp,"sigs":len(sigs),"base":res["base"],"mart2":res["mart2"],
                  "delta_R":round(res["mart2"]["net_R"]-res["base"]["net_R"],2)}
        print(f"{sym}: sigs={len(sigs)} base R={res['base']['net_R']} → mart2 R={res['mart2']['net_R']} ΔR={out[sym]['delta_R']} 加仓/信号={res['mart2']['avg_add']}")
    print("\n=== 判词(同分母 net_R, 马丁是否救负 edge) ===")
    for sym in OOS4:
        d=out.get(sym,{})
        if "base" in d:
            judge = "转正候选" if d["delta_R"]>0 and d["base"]["net_R"]>0 else ("救回但薄边" if d["delta_R"]>0 else "马丁无效/放大亏")
            print(f"  {sym}: base R={d['base']['net_R']} mart2 R={d['mart2']['net_R']} Δ={d['delta_R']:+} → {judge}")
    json.dump(out, open("data/supd_mart_backtest.json","w",encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("产物: data/supd_mart_backtest.json")
    mt5.shutdown()

if __name__=="__main__": main()
