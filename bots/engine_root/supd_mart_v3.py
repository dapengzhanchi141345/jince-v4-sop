#!/usr/bin/env python
# SUPD-MART v3: 修初版3个口径bug(net_R每笔归一/加仓锁基础仓持仓窗/摊平假胜vs保守对照)+最大回撤.
# 成本=引擎口径. 确定性0 LLM, 0写闸源, 0改live. 产物 data/supd_mart_v3.json.
import os, sys, json, datetime
os.chdir(r"E:\GoldstrategyEngine"); sys.path.insert(0, r"E:\GoldstrategyEngine")
import numpy as np, pandas as pd, MetaTrader5 as mt5
import symbol_universe as su, backtest_engine as BE
import pasd_fusion as PF
OOS4=["CADJPY","EURJPY","EURNZD","GBPCAD"]
DAYS,MAXH,RR=90,BE.MAX_HOLD_H1,2.5

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

def add_lv(sig,zd,zs):
    E,side=sig["entry"],sig["side"];lv=[]
    if side>0:
        for z in [x for x in zd if x["bottom"]<E][:1]: lv+=[(z["top"]+z["bottom"])/2.0,z["bottom"]]
    else:
        for z in [x for x in zs if x["top"]>E][:1]: lv+=[(z["top"]+z["bottom"])/2.0,z["top"]]
    return lv[:2]

def sim(h1,sig,lv,cfg,sp,pt,swl,swh,tpA):
    """逐bar状态机. tpA=True:加仓后止盈随均价摊平下移(马丁假胜陷阱); False:止盈位固定原始TP(保守)."""
    lot=float(cfg.get('lot',.1));pip=float(cfg.get('pip',.0001));pusd=float(cfg.get('pip_usd',10.))
    i=int(sig['bar']);side=1 if sig['side']>0 else -1
    if i+1>=len(h1):return None
    sd0=abs(sig['entry']-sig['sl']);td0=abs(sig['entry']-sig['tp'])
    o=float(h1['open'].iloc[i+1]);a=sp*pt
    e0=o+a*side
    S=e0-side*sd0; TP0=e0+side*td0
    end=min(i+1+MAXH,len(h1));hi=h1['high'].values[i+1:end];lo=h1['low'].values[i+1:end]
    tm=h1['time'].values[i+1:end];cl=h1['close'].values[i+1:end]
    if len(hi)==0:return None
    pos=[(e0,lot)];adds=0;exit=None
    for k in range(len(hi)):
        tot=sum(w for _,w in pos);avg=sum(p*w for p,w in pos)/tot
        Tc=(avg+side*RR*sd0) if (tpA and adds>0) else TP0
        if side>0:slh=lo[k]<=S;tph=hi[k]>=Tc
        else:slh=hi[k]>=S;tph=lo[k]<=Tc
        if adds<len(lv) and ((lo[k]<=lv[adds]) if side>0 else (hi[k]>=lv[adds])):
            pos.append((lv[adds],lot));adds+=1
        if slh and tph:exit=S if abs(e0-S)<=abs(e0-Tc) else Tc;break
        elif slh:exit=S;break
        elif tph:exit=Tc;break
    if exit is None:exit=float(cl[-1])
    tot=sum(w for _,w in pos);avg=sum(p*w for p,w in pos)/tot
    pnl=(exit-avg)*side/pip*pusd*tot
    hd=int(max(0,(tm[len(hi)-1]-tm[0])//86400))
    pnl-=abs((swl if side>0 else swh)*hd*tot)
    risk=sum(max(0,(p-S)*side) for p,w in pos for _ in [0])*lot/pip*pusd + 0  # 占位
    risk=sum(max(0,(p-S)*side)*w for p,w in pos)/pip*pusd
    return dict(net=pnl,risk=risk,adds=adds)

def run_dd(nets):
    c=peak=dd=0.0
    for x in nets:
        c+=x;peak=max(peak,c);dd=max(dd,peak-c)
    return dd

def main():
    if not mt5.initialize():print("MT5 fail");return
    res={"generated":datetime.datetime.now().isoformat(),"rr":RR,
         "tpA":"加仓后TP随均价摊平(假胜陷阱)","tpB":"TP固定原始(保守真胜口径)"}
    for sym in OOS4:
        cfg=su.UNIVERSE.get(sym,{});info=mt5.symbol_info(sym)
        sp=info.spread or 10;pt=info.point or 1e-5;swl=info.swap_long or 0;swh=info.swap_short or 0
        h1=rates(sym,mt5.TIMEFRAME_H1);h4=rates(sym,mt5.TIMEFRAME_H4);d1=rates(sym,mt5.TIMEFRAME_D1)
        if h1 is None or len(h1)<100:res[sym]={"err":"H1短"};print(sym,"H1短");continue
        sigs=PF.gen_pasd(h1,h4,d1,cfg)
        for s in sigs:s['tp']=s['entry']+s['side']*RR*abs(s['entry']-s['sl'])
        zs=PF._detect_supply_demand_zones(h1['high'].values,h1['low'].values,h1['close'].values)
        g={}
        for tpA in (False,True):
            key='B' if not tpA else 'A'
            for tag,lf in (('base',lambda s:[]),('mart',lambda s:add_lv(s,zs['demand'],zs['supply']))):
                nets=[];ad=[]
                for s in sigs:
                    r=sim(h1,s,lf(s),cfg,sp,pt,swl,swh,tpA)
                    if r is None:continue
                    nets.append(r['net']/max(r['risk'],1e-9));ad.append(r['adds'])
                g[f'{tag}_{key}']=dict(n=len(nets),netR=round(sum(nets)/max(1,len(nets)),3) if nets else 0.0,
                                       cumR=round(sum(nets),2),dd=round(run_dd(nets),2),adds=round(sum(ad)/max(1,len(ad)),2))
        res[sym]=dict(sigs=len(sigs),spread=sp,g=g)
        B=b=g['base_B'];m=g['mart_B'];mA=g['mart_A']
        print(f"{sym}: sigs={len(sigs)} | base R={B['netR']:+.3f}/dd{B['dd']} | martB R={m['netR']:+.3f}/dd{m['dd']}/加{m['adds']} | martA(摊平) R={mA['netR']:+.3f}")
    print("\n=== 判词(保守口径B, 摊平A=假胜) ===")
    for sym in OOS4:
        d=res.get(sym,{});g=d.get('g',{})
        if not g:continue
        base=g.get('base_B',{});mB=g.get('mart_B',{});mA=g.get('mart_A',{})
        delta_B=mB.get('netR',0)-base.get('netR',0);delta_A=mA.get('netR',0)-base.get('netR',0)
        judge='不转正(马丁无保守增益)' if delta_B<=0 else ('摊平假胜,不可信' if delta_A>delta_B else '保守转正候选')
        print(f"  {sym}: base R={base.get('netR')} → 保守B ΔR={delta_B:+.3f} / 摊平A ΔR={delta_A:+.3f} → {judge}")
    json.dump(res,open('data/supd_mart_v3.json','w'),ensure_ascii=False,indent=1,default=str)
    print("产物: data/supd_mart_v3.json")
    mt5.shutdown()

if __name__=="__main__":main()
