#!/usr/bin/env python
# REGIME 切分: 证"震荡否决门砍对了人" —— PASD 在震荡段(低波动) vs 单边段(高波动) 的 net_R 差.
# 判据: 若震荡段系统性负 + 单边段转正/不亏 => 否决门(低波动停单)是对症的刀. 确定性0 LLM, 0写闸源.
import os, sys, json, datetime
os.chdir(r"E:\GoldstrategyEngine"); sys.path.insert(0, r"E:\GoldstrategyEngine")
import numpy as np, pandas as pd, MetaTrader5 as mt5
import symbol_universe as su, backtest_engine as BE
import pasd_fusion as PF
OOS4=["CADJPY","EURJPY","EURNZD","GBPCAD"]; DAYS,RR=90,2.5
def rates(sym,tf,d=DAYS):
    F=[];p=0
    while True:
        c=mt5.copy_rates_from_pos(sym,tf,p,5000)
        if c is None or len(c)==0:break
        F.append(pd.DataFrame(c));p+=len(c)
        if len(c)<5000 or p>=20000:break
    if not F:return None
    df=pd.concat(F).drop_duplicates("time").sort_values("time").reset_index(drop=True)
    df["t"]=pd.to_datetime(df["time"],unit="s")
    return df[df["t"]>=df["t"].max()-pd.Timedelta(days=d)].reset_index(drop=True)
def sim(h1,sig,sp,pt,swl,swh):
    return BE.simulate_signal(h1,sig,sp,pt,swl,swh,float(0.1),0.0001,10.0)
def main():
    if not mt5.initialize():print("MT5 fail");return
    out={"generated":datetime.datetime.now().isoformat(),"method":"ATR(14) 入场bar 归一分位, 中位以下=震荡段/低波动, 以上=单边段/高波动"}
    for sym in OOS4:
        cfg=su.UNIVERSE.get(sym,{});info=mt5.symbol_info(sym)
        sp=info.spread or 10;pt=info.point or 1e-5;swl=info.swap_long or 0;swh=info.swap_short or 0
        h1=rates(sym,mt5.TIMEFRAME_H1);h4=rates(sym,mt5.TIMEFRAME_H4);d1=rates(sym,mt5.TIMEFRAME_D1)
        if h1 is None or len(h1)<100:out[sym]={"err":"H1短"};print(sym,"H1短");continue
        sigs=PF.gen_pasd(h1,h4,d1,cfg)
        for s in sigs:s['tp']=s['entry']+s['side']*RR*abs(s['entry']-s['sl'])
        atr=PF._atr(h1['high'].values,h1['low'].values,h1['close'].values,14)
        med=float(np.nanmedian(atr[atr>0]))
        Rr=[];Rt=[]
        for s in sigs:
            i=int(s['bar']);r=sim(h1,s,sp,pt,swl,swh)
            if r is None:continue
            risk=abs(s['entry']-s['sl'])/0.0001*10.0*0.1
            if risk<=0:continue
            rn=r/risk
            (Rr if atr[i]<med else Rt).append(rn)
        def agg(a):
            n=len(a);net=sum(a)/n if n else 0.0
            c=peak=dd=0.0
            for x in a:c+=x;peak=max(peak,c);dd=max(dd,peak-c)
            return dict(n=n,meanR=round(net,3),cumR=round(sum(a),2),dd=round(dd,2))
        rg,tt=agg(Rr),agg(Rt)
        out[sym]=dict(sigs=len(sigs),atr_med=round(med,5),ranging=rg,trending=tt,
                      delta_R=round(rg['meanR']-tt['meanR'],3))
        print(f"{sym}: sigs={len(sigs)} | 震荡段 n={rg['n']} meanR={rg['meanR']:+.3f} | 单边段 n={tt['n']} meanR={tt['meanR']:+.3f} | 差={out[sym]['delta_R']:+.3f}")
    print("\n=== 判词(否决门砍对了人吗) ===")
    for sym in OOS4:
        d=out.get(sym,{});
        if 'ranging' in d:
            rg,tt=d['ranging'],d['trending']
            ok=(rg['meanR']<0 and tt['meanR']>rg['meanR'])
            print(f"  {sym}: 震荡段{rg['meanR']:+.3f} vs 单边段{tt['meanR']:+.3f} → {'否决门对症(震荡停单砍对了)' if ok else '未证实(两段差不开)'}")
    json.dump(out,open('data/pasd_regime_split.json','w'),ensure_ascii=False,indent=1,default=str)
    print("产物: data/pasd_regime_split.json")
    mt5.shutdown()
if __name__=="__main__":main()
