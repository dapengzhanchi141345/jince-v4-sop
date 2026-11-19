#!/usr/bin/env python
# 3 桶固定 0.01 手数回测 (用户 2026-10-17 口径: 手数不扩大, 全 0.01, EURJPY 6mo)
# A 基线: 首单, 浮亏不加  |  C 对照: 加 1 次(到区)  |  B 用户方案: 加 2 次(下区中点 1 + 到区 1)
# 同分母: 同一批 PASD 信号 × 同数据 × 同成本面. 0 LLM, 0 写闸源, 0 改 live.
import os, sys, json, datetime
os.chdir(r"E:\GoldstrategyEngine"); sys.path.insert(0, r"E:\GoldstrategyEngine")
import numpy as np, pandas as pd, MetaTrader5 as mt5
import symbol_universe as su, backtest_engine as BE
import pasd_fusion as PF

SYM="EURJPY"; DAYS=180; RR=2.5; LOT=0.01

def rates(sym,tf,d=DAYS):
    F=[];p=0
    while True:
        c=mt5.copy_rates_from_pos(sym,tf,p,5000)
        if c is None or len(c)==0:break
        F.append(pd.DataFrame(c));p+=len(c)
        if len(c)<5000 or p>=40000:break
    if not F:return None
    df=pd.concat(F).drop_duplicates("time").sort_values("time").reset_index(drop=True)
    df["t"]=pd.to_datetime(df["time"],unit="s")
    return df[df["t"]>=df["t"].max()-pd.Timedelta(days=d)].reset_index(drop=True)

def add_lv(sig,zd,zs,mode):
    """mode=A: 不加 | C: 加1次(到区) | B: 加2次(下区中点+到区). 全部同 0.01 手数(手数在 sim 里锁死, 与 lv 数无关)."""
    E,side=sig["entry"],sig["side"];lv=[]
    if mode=="A":return []
    if side>0:
        z=[x for x in zd if x["bottom"]<E]
        if z:
            z=z[0]
            if mode=="C": lv=[z["bottom"]]
            else: lv=[(z["top"]+z["bottom"])/2.0, z["bottom"]]
    else:
        z=[x for x in zs if x["top"]>E]
        if z:
            z=z[0]
            if mode=="C": lv=[z["top"]]
            else: lv=[(z["top"]+z["bottom"])/2.0, z["top"]]
    return lv

def sim(h1,sig,lv,sp,pt,swl,swh,MAXH):
    i=int(sig['bar']);side=1 if sig['side']>0 else -1
    if i+1>=len(h1):return None
    sd0=abs(sig['entry']-sig['sl']);td0=abs(sig['entry']-sig['tp'])
    o=float(h1['open'].iloc[i+1]);a=sp*pt
    e0=o+a*side
    S=e0-side*sd0; TP0=e0+side*td0
    end=min(i+1+MAXH,len(h1));hi=h1['high'].values[i+1:end];lo=h1['low'].values[i+1:end]
    tm=h1['time'].values[i+1:end];cl=h1['close'].values[i+1:end]
    if len(hi)==0:return None
    pos=[e0];adds=0;exit=None;dd=peak=cum=0.0
    # 0.01 手 EURJPY: 1 pip=0.0001, 1000 USD/pip (标准账户), 手数直接乘
    pusd_per_pip=10.0*LOT/0.01  # 0.01 手 => 10 USD/pip (跟 v3 pip_usd=10 同口径)
    for k in range(len(hi)):
        tot=len(pos);avg=sum(pos)/tot
        Tc=TP0
        if side>0:slh=lo[k]<=S;tph=hi[k]>=Tc
        else:slh=hi[k]>=S;tph=lo[k]<=Tc
        if adds<len(lv) and ((lo[k]<=lv[adds]) if side>0 else (hi[k]>=lv[adds])):
            pos.append(lv[adds]);adds+=1
        if slh and tph:exit=S if abs(e0-S)<=abs(e0-Tc) else Tc;break
        elif slh:exit=S;break
        elif tph:exit=Tc;break
    if exit is None:exit=float(cl[-1])
    tot=len(pos);avg=sum(pos)/tot
    pnl=(exit-avg)*side/pt*pusd_per_pip*tot  # pips × USD/pip(0.01手) × 在仓位置数
    hd=int(max(0,(tm[len(hi)-1]-tm[0])//86400))
    pnl-=abs((swl if side>0 else swh))*hd*tot/100.0  # swap 按 0.01 手(=1/100 标准手)缩放
    # R 归一(首单风险): 便于跟 90d v3 口径互核 — 只首单风险, 不含加仓放大
    risk_usd=sd0/pt*pusd_per_pip
    return dict(pnl=pnl, R=pnl/max(risk_usd,1e-9), adds=adds, win=1 if pnl>0 else 0, hold_h=len(hi))

def run_dd(pnls):
    """按序列累计的最大回撤(USD)."""
    c=peak=dd=0.0
    for x in pnls:
        c+=x;peak=max(peak,c);dd=max(dd,peak-c)
    return dd

def main():
    import mt5_login
    mt5.initialize()  # 先连终端, 否则 ensure_login 的"已登录态"分支 account_info() 返回 None 误判
    ok,why=mt5_login.ensure_login(60137964)
    if not ok:
        print("LOGIN FAIL:",why);return
    info=mt5.symbol_info(SYM)
    sp=info.spread or 10;pt=info.point or 1e-5;swl=info.swap_long or 0;swh=info.swap_short or 0
    h1=rates(SYM,mt5.TIMEFRAME_H1);h4=rates(SYM,mt5.TIMEFRAME_H4);d1=rates(SYM,mt5.TIMEFRAME_D1)
    if h1 is None or len(h1)<100:print("H1 短");return
    cfg=su.UNIVERSE.get(SYM,{})
    sigs=PF.gen_pasd(h1,h4,d1,cfg)
    for s in sigs:s['tp']=s['entry']+s['side']*RR*abs(s['entry']-s['sl'])
    zs=PF._detect_supply_demand_zones(h1['high'].values,h1['low'].values,h1['close'].values)
    MAXH=BE.MAX_HOLD_H1
    out={"generated":datetime.datetime.now().isoformat(),"sym":SYM,"window_days":DAYS,
         "lot_fixed":LOT,"n_sigs":len(sigs),"spread":sp,"point":pt,
         "note":"3桶同分母同成本面, 手数全锁 0.01(不扩大), 源=mt5:60137964 自家终端, 0 外部数据. 仅参考数据, 0 写闸源 0 进 live."}
    for mode,tag in [("A","A_基线_不加"),("C","C_对照_加1"),("B","B_用户方案_加2(中点+到区)")]:
        pnls=[];Rs=[];adds_n=0;wins=0;hold_sum=0
        for s in sigs:
            lv=add_lv(s,zs['demand'],zs['supply'],mode)
            r=sim(h1,s,lv,sp,pt,swl,swh,MAXH)
            if r is None:continue
            pnls.append(r['pnl']);Rs.append(r['R']);adds_n+=1 if r['adds']>0 else 0
            wins+=r['win'];hold_sum+=r['hold_h']
        if not pnls:
            out[tag]={"err":"0 信号"};continue
        net=sum(pnls)
        out[tag]=dict(n=len(pnls),
            净USD=round(net,2),
            单笔均值USD=round(net/len(pnls),2),
            单笔净R=round(sum(Rs)/len(Rs),3),
            累计R=round(sum(Rs),2),
            胜率=round(wins/len(pnls)*100,1),
            加仓触发笔数=adds_n,
            最大回撤USD=round(run_dd(pnls),2),
            平均持仓h=round(hold_sum/len(pnls),1),
            best=round(max(pnls),2), worst=round(min(pnls),2))
    # 判词(保守口径): B vs A 的 Δ 与 回撤顶没顶大
    a=out.get("A_基线_不加",{});b=out.get("B_用户方案_加2(中点+到区)",{})
    if "净USD" in a and "净USD" in b:
        out["verdict"]=dict(delta_B_vs_A_USD=round(b["净USD"]-a["净USD"],2),
            dd_B= b["最大回撤USD"], dd_A=a["最大回撤USD"],
            judge="加仓扭亏(B>A 且回撤没顶大)" if (b["净USD"]>a["净USD"] and b["最大回撤USD"]<=a["最大回撤USD"]*1.5)
            else "加仓顶大回撤/无增益(维持 A 基线)")
    json.dump(out,open('data/fixed001_3bucket_6mo.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
    print(json.dumps(out,ensure_ascii=False,indent=1))
    print("产物: data/fixed001_3bucket_6mo.json (utf-8)")
    mt5.shutdown()

if __name__=="__main__":main()
