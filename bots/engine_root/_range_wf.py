# -*- coding: utf-8 -*-
# 震荡腿唤醒 STEP2: A0 现参数 walk-forward 三段 + 按年切片 (几何与 _range_awaken 完全一致)
import json
import numpy as np
import MetaTrader5 as mt5

SYMS = ["BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD"]
mt5.initialize(); assert mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")

def bb(c, period=20, k=2.0):
    n=len(c); up=np.zeros(n); dn=np.zeros(n)
    for i in range(period,n):
        w=c[i-period+1:i+1]; m=w.mean(); sd=w.std()
        up[i]=m+k*sd; dn[i]=m-k*sd
    return up, dn

def adx_arr(h,l,c,period=14):
    n=len(c); tr=np.zeros(n); tr[0]=h[0]-l[0]
    pdm=np.zeros(n); mdm=np.zeros(n)
    for i in range(1,n):
        tr[i]=max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1]))
        upmv=h[i]-h[i-1]; dnmv=l[i-1]-l[i]
        pdm[i]=upmv if (upmv>dnmv and upmv>0) else 0
        mdm[i]=dnmv if (dnmv>upmv and dnmv>0) else 0
    atr=np.zeros(n); sp=np.zeros(n); sm=np.zeros(n)
    atr[period]=tr[1:period+1].sum(); sp[period]=pdm[1:period+1].sum(); sm[period]=mdm[1:period+1].sum()
    for i in range(period+1,n):
        atr[i]=atr[i-1]-atr[i-1]/period+tr[i]
        sp[i]=max(0,sp[i-1]-sp[i-1]/period+pdm[i])
        sm[i]=max(0,sm[i-1]-sm[i-1]/period+mdm[i])
    dx=np.zeros(n)
    for i in range(period,n):
        if atr[i]>0:
            p=100*sp[i]/atr[i]; m=100*sm[i]/atr[i]; s=p+m
            dx[i]=(abs(p-m)/s*100) if s>0 else 0
    out=np.zeros(n)
    for i in range(2*period-1,n):
        out[i]=np.mean(dx[i-period+1:i+1])
    return out

def atr14(h,l,c,period=14):
    n=len(c); tr=np.zeros(n); tr[0]=h[0]-l[0]
    for i in range(1,n):
        tr[i]=max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1]))
    out=np.zeros(n); out[period]=tr[1:period+1].mean()
    for i in range(period+1,n):
        out[i]=(out[i-1]*(period-1)+tr[i])/period
    return out

def d1_up(d1c,d1t,t):
    m=np.where(d1t+86400<=int(t))[0]
    if len(m)==0: return None
    j=m[-1]
    return (1 if d1c[j]>d1c[j-1] else 0) if j>=1 else None

def replay(i,hh,ll,cc,up,dn,a,side):
    """A0 现参数几何 (与 _range_awaken 一致)"""
    tgt=(hh[i-1]+ll[i-1])/2.0
    if side=="sell": trig=up[i-1]; sl=trig+2*a
    else: trig=dn[i-1]; sl=trig-2*a
    risk=abs(trig-sl)
    if risk<=0: return 0.0,"未成交"
    k0=i+1; filled=False; fill_k=-1
    end=min(k0+4,len(hh))
    for k in range(k0,end):
        if side=="sell" and hh[k]>=trig: filled=True; fill_k=k; break
        if side=="buy" and ll[k]<=trig: filled=True; fill_k=k; break
    if not filled: return 0.0,"未成交"
    if side=="sell" and hh[fill_k]>=sl: return -1.0,"SL"
    if side=="buy" and ll[fill_k]<=sl: return -1.0,"SL"
    last=cc[fill_k]
    for k in range(fill_k+1,min(fill_k+1+42,len(cc))):
        if side=="sell":
            if hh[k]>=sl: return -1.0,"SL"
            if ll[k]<=tgt: return 1.0,"TP"
        else:
            if ll[k]<=sl: return -1.0,"SL"
            if hh[k]>=tgt: return 1.0,"TP"
        last=cc[k]
    r=(last-trig)/risk* (-1 if side=="sell" else 1)
    r=max(min(r,1.0),-1.0)
    return r,"TIME"

# 每品种: 回放全史, 每笔记录 (ts, R)  → 分三段 + 按年
per_sym_events = {}
for sym in SYMS:
    h4 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, 2600)
    d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 500)
    if h4 is None or d1 is None: continue
    hh=h4["high"].astype(float); ll=h4["low"].astype(float); cc=h4["close"].astype(float)
    tt=h4["time"].astype(np.int64)
    d1c=d1["close"].astype(float); d1t=d1["time"].astype(np.int64)
    up,dn = bb(cc); adx=adx_arr(hh,ll,cc); a14=atr14(hh,ll,cc)
    evs=[]
    for i in range(60,len(cc)-2):
        if up[i-1]<=0 or a14[i-1]<=0: continue
        a=float(a14[i-1])
        if adx[i-1]>30: continue
        du=d1_up(d1c,d1t,int(tt[i-1]))
        if du is None: continue
        if cc[i-1]<up[i-1] and hh[i]>=up[i-1]:
            R,b=replay(i,hh,ll,cc,up,dn,a,"sell")
            if b!="未成交": evs.append((int(tt[i]),R))
        if cc[i-1]>dn[i-1] and ll[i]<=dn[i-1]:
            R,b=replay(i,hh,ll,cc,up,dn,a,"buy")
            if b!="未成交": evs.append((int(tt[i]),R))
    per_sym_events[sym]=evs
    print(f"[{sym}] events={len(evs)}")

import datetime
allts=[t for evs in per_sym_events.values() for t,_ in evs]
tmin,tmax=min(allts),max(allts)
b1=tmin+(tmax-tmin)//3; b2=tmin+2*(tmax-tmin)//3
segs={"前段":(tmin,b1),"中段":(b1,b2),"后段":(b2,tmax)}
print("\n=== walk-forward 三段 ===")
for name,(lo,hi) in segs.items():
    R_all=[]
    for sym,evs in per_sym_events.items():
        for t,R in evs:
            if lo<=t<hi: R_all.append(R)
    n=len(R_all)
    if n:
        print(f"{name}: n={n} wr={(np.array(R_all)>0).mean():.3f} 期望R={np.mean(R_all):.4f}")
    else:
        print(f"{name}: n=0")

# 按年
print("\n=== 按年 ===")
for year in sorted({datetime.datetime.utcfromtimestamp(t).year for evs in per_sym_events.values() for t,_ in evs}):
    R_all=[R for sym,evs in per_sym_events.items() for t,R in evs
           if datetime.datetime.utcfromtimestamp(t).year==year]
    if R_all:
        print(f"{year}: n={len(R_all)} wr={(np.array(R_all)>0).mean():.3f} 期望R={np.mean(R_all):.4f}")

out={"walk_forward_3seg":{}, "by_year":{}}
for name,(lo,hi) in segs.items():
    R_all=[R for sym,evs in per_sym_events.items() for t,R in evs if lo<=t<hi]
    out["walk_forward_3seg"][name]={"n":len(R_all),"wr":round(float((np.array(R_all)>0).mean()),4) if R_all else None,
                                    "exp_R":round(float(np.mean(R_all)),4) if R_all else None}
for year in sorted({datetime.datetime.utcfromtimestamp(t).year for evs in per_sym_events.values() for t,_ in evs}):
    R_all=[R for sym,evs in per_sym_events.items() for t,R in evs if datetime.datetime.utcfromtimestamp(t).year==year]
    out["by_year"][str(year)]={"n":len(R_all),"wr":round(float((np.array(R_all)>0).mean()),4) if R_all else None,
                               "exp_R":round(float(np.mean(R_all)),4) if R_all else None}
json.dump(out, open("E:/GoldstrategyEngine/data/range_wf.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("\nwritten data/range_wf.json")
mt5.shutdown()
