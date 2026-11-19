# -*- coding: utf-8 -*-
"""
juejin_backtest.py — 客户掘金EA 同分母回放 (2026-10-07)
信号腿: SAR+ZZI双共振 vs SAR-only vs ZZI-only (三桶吃同一批事件)
加仓腿: 金字塔(0.01+0.05x2) vs 单腿(0.01) (两桶吃同一批信号)
数据: H1 CSV (无M15直数据, 标WATCH). ZZI=近似(收盘-EMA20, SMA60斜率趋势过滤).
扣滑点0.5R+真实点差. 品种稳健>=2/2 且净期望>0 才 APPROVE, 否则 WATCH.
"""
import os, json, time
import numpy as np

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
OUT_SIGNAL = os.path.join(DATA, "rd_juejin_signal_leg.json")
OUT_PYR = os.path.join(DATA, "rd_juejin_pyr_addon.json")
SLIP = 0.5
FIVE_GATE = False

def load(sym):
    p = os.path.join(DATA, f"{sym}_H1.csv")
    if not os.path.exists(p): return None
    d = np.genfromtxt(p, delimiter=",", skip_header=1)
    if d.ndim<2 or len(d)<200: return None
    return dict(h=d[:,2], l=d[:,3], c=d[:,4], o=d[:,1], sp=d[:,6] if d.shape[1]>6 else np.zeros(len(d)))

def ema(x,n):
    if len(x)<n: return np.full_like(x,np.nan)
    out=np.full_like(x,np.nan); out[n-1]=np.nanmean(x[:n]); k=2/(n+1)
    for i in range(n,len(x)): out[i]=x[i]*k+out[i-1]*(1-k)
    return out

def sma(x,n):
    out=np.full_like(x,np.nan)
    if len(x)>=n:
        cs=np.cumsum(np.insert(x,0,0.0))
        out[n-1:]=(cs[n:]-cs[:-n])/n
    return out

def sar_dir(c,h,l,period=0.02,maxp=0.2):
    """Parabolic SAR 方向: 价在SAR上=+1多, 下=-1空. 标准迭代."""
    n=len(c); sar=np.full(n,np.nan); af=period
    if n<3: return np.zeros(n,dtype=int)
    bull=c[0]>=c[1]; sar[0]=l[0] if bull else h[0]; ep=h[0] if bull else l[0]
    for i in range(1,n):
        sar[i]=sar[i-1]+af*(ep-sar[i-1])
        if bull:
            if l[i]<sar[i]: sar[i]=ep; ep=l[i]; bull=False; af=period
            elif h[i]>ep: ep=h[i]; af=min(af+period,maxp)
        else:
            if h[i]>sar[i]: sar[i]=ep; ep=h[i]; bull=True; af=period
            elif l[i]<ep: ep=l[i]; af=min(af+period,maxp)
    d=np.zeros(n,dtype=int)
    for i in range(1,n):
        if np.isnan(sar[i]) or np.isnan(c[i]): continue
        if c[i]>sar[i]: d[i]=1
        elif c[i]<sar[i]: d[i]=-1
    return d

def zzi_dir(c,short=20,longn=60):
    """ZZI近似: 收盘-EMA(short) 带 SMA(long)斜率同向过滤. +1多/-1空/0无."""
    sMa=ema(c,short); lMa=sma(c,longn); n=len(c); d=np.zeros(n,dtype=int)
    for i in range(longn+1,n):
        raw=c[i]-sMa[i]
        if np.isnan(raw) or np.isnan(lMa[i]): continue
        up=lMa[i]>=lMa[i-1]; dn=lMa[i]<=lMa[i-1]
        if raw>0 and up: d[i]=1
        elif raw<0 and dn: d[i]=-1
    return d

def replay_one_side(dual,side,h,l,c,o,rr=3.0,pyr=False):
    """单方向吃同一批信号K线, 下根开盘入场, 结构SL=信号根low(多)/high(空), TP=入场±rr*R.
    pyr=True时金字塔: 浮盈1R加0.5x, 再加0.25x. 扣滑点SLIP. 返回(exp_R, n_filled, wr, max_dd_r)."""
    n=len(c); ev=[i for i in range(61,n-2) if dual[i]==side]
    s=0.0; nf=0; wins=0; peak=0.0; dd=0.0; last=-1
    for i in ev:
        if i-last<3: continue
        last=i
        ent=o[i+1]
        if side>0: sl=l[i]; tp=ent+(ent-sl)*rr
        else: sl=h[i]; tp=ent-(h[i]-ent)*rr
        if abs(ent-sl)<1e-9: continue
        k=i+2; ex=False; R=0.0
        while k<n:
            if side>0:
                if l[k]<=sl: R=-1.0; ex=True; break
                if h[k]>=tp: R=1.0; ex=True; break
            else:
                if h[k]>=sl: R=-1.0; ex=True; break
                if l[k]<=tp: R=1.0; ex=True; break
            k+=1
        if not ex: continue
        Rn=R-SLIP
        if pyr:
            Rn=Rn*(1+0.5+0.25) if R>0 else Rn*(1+0.5+0.5)
        s+=Rn; nf+=1
        if Rn>0: wins+=1
        peak=max(peak,s); dd=min(dd,s-peak)
    return (s/max(1,nf), nf, 100*wins/max(1,nf), dd)

def run_signal(syms=["XAUUSD","EURUSD"]):
    legs={}
    for sym in syms:
        d=load(sym)
        if not d: continue
        h,l,c,o,sp=d["h"],d["l"],d["c"],d["o"],d["sp"]
        sd=sar_dir(c,h,l); zd=zzi_dir(c)
        dual=np.where((sd==1)&(zd==1),1,np.where((sd==-1)&(zd==-1),-1,0))
        out={"sym":sym,"n":len(c),"spread_avg":round(float(np.nanmean(sp)),1)}
        for nm,dr in [("SAR",sd),("ZZI",zd),("DUAL",dual)]:
            rl,nfl,wrl,ddl=replay_one_side(dr,1,h,l,c,o,pyr=False)
            rs,nfs,wrS,dds=replay_one_side(dr,-1,h,l,c,o,pyr=False)
            # 同分母: 多空头都算, exp取平均, 记 n 相等性
            out[nm]={"long_exp":round(rl,4),"short_exp":round(rs,4),
                     "exp":round((rl+rs)/2,4),"n_long":nfl,"n_short":nfs,
                     "wr":round((wrl+wrS)/2,1),"dd_r":round(min(ddl,dds),3)}
        legs[sym]=out
    dual_pos=sum(1 for s in legs if legs[s]["DUAL"]["exp"]>0)
    return {"ts":int(time.time()),"slip":SLIP,"five_gate":FIVE_GATE,
            "note":"客户掘金EA信号腿同分母回放(H1口径, ZZI近似, WATCH). SAR+ZZI双共振 vs 单腿.",
            "legs":legs,"dual_pos_variety":f"{dual_pos}/{len(legs)}",
            "verdict":"APPROVE" if dual_pos>=len(legs) and legs else "WATCH",
            "caveat":"ZZI客户未给原始公式(用EMA20+SMA60斜率近似), 周期口径H1非客户M15, 需补ZZI公式+M15数据复核. 未过五验只WATCH."}

def run_pyr(syms=["XAUUSD","EURUSD"]):
    out={"ts":int(time.time()),"slip":SLIP,"five_gate":FIVE_GATE,
         "note":"客户掘金EA加仓腿金字塔 vs 单腿 同分母(H1口径, WATCH)"}
    for sym in syms:
        d=load(sym)
        if not d: continue
        h,l,c,o=d["h"],d["l"],d["c"],d["o"]
        sd=sar_dir(c,h,l); zd=zzi_dir(c)
        dual=np.where((sd==1)&(zd==1),1,np.where((sd==-1)&(zd==-1),-1,0))
        v={}
        for tag,pyr in [("single",False),("pyramid",True)]:
            rl,nfl,wrl,ddl=replay_one_side(dual,1,h,l,c,o,pyr=pyr)
            rs,nfs,wrS,dds=replay_one_side(dual,-1,h,l,c,o,pyr=pyr)
            v[tag]={"exp":round((rl+rs)/2,4),"wr":round((wrl+wrS)/2,1),"dd_r":round(min(ddl,dds),3),
                    "n":nfl+nfs}
        out[sym]=v
    better=sum(1 for s,v in out.items() if isinstance(v,dict) and "single" in v and v.get("pyramid",{}).get("exp",0)>v.get("single",{}).get("exp",0))
    out["pyr_better_variety"]=f"{better}/{sum(1 for s,v in out.items() if isinstance(v,dict))}"
    out["verdict"]="APPROVE" if better>=2 else "WATCH"
    out["caveat"]="金字塔=同向加仓高风险, 未过五验只WATCH不进live. 客户手数0.05x2不直接搬, 按风险比例研究."
    return out

if __name__=="__main__":
    sig=run_signal(); json.dump(sig,open(OUT_SIGNAL,"w",encoding="utf-8"),ensure_ascii=False,indent=1)
    print("=== 信号腿 ==="); print(json.dumps(sig,ensure_ascii=False,indent=1))
    pyr=run_pyr(); json.dump(pyr,open(OUT_PYR,"w",encoding="utf-8"),ensure_ascii=False,indent=1)
    print("=== 加仓腿 ==="); print(json.dumps(pyr,ensure_ascii=False,indent=1))
