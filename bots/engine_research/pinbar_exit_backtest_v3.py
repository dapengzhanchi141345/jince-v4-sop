# -*- coding: utf-8 -*-
"""
PINBAR_EXIT 高样本横向回测 v3: baseline(固定2R) vs v1(纯影线) vs v2(三确认) vs v2.1(三确认+放量+新鲜度)
复用原已验证框架(入场=swing breakout, SL=2ATR, 即时平仓零延迟), 仅扩展 pin 出场条件。
数据: data/*_H1.csv (含 tick_volume)。 即时平仓 = 满足棒j即以极值平, 无H1下根延迟。
"""
import csv, os, glob, statistics

DATA = "E:/GoldstrategyEngine/data"
N_SWING = 20
ATR_P = 14
SLM = 2.0
TPR = 2.0
TRIG = 0.5
MAXH = 240
MREC = 10

def load(sym):
    rows = []
    with open(f"{DATA}/{sym}_H1.csv", encoding="utf-8", errors="replace") as f:
        for d in csv.DictReader(f):
            row = {}
            for k, v in d.items():
                try: row[k] = float(v)
                except (ValueError, TypeError): row[k] = v
            rows.append(row)
    return rows

def atr(rows, i, n=ATR_P):
    if i < n: return None
    trs = []
    for j in range(i-n+1, i+1):
        h, l = rows[j]["high"], rows[j]["low"]
        pc = rows[j-1]["close"] if j>0 else rows[j]["close"]
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs)/n

def smax_high(rows, a, b):
    a=max(0,a); b=min(len(rows),b)
    return max(rows[k]["high"] for k in range(a,b)) if b>a else rows[a]["high"]

def smin_low(rows, a, b):
    a=max(0,a); b=min(len(rows),b)
    return min(rows[k]["low"] for k in range(a,b)) if b>a else rows[a]["low"]

def wick_ratio(rows, j):
    o,h,l,c = rows[j]["open"],rows[j]["high"],rows[j]["low"],rows[j]["close"]
    rng=h-l
    if rng<=0: return 0.0,0.0
    return (h-max(o,c))/rng, (min(o,c)-l)/rng

def _rl(px):
    if px>=1000: return round(px/50)*50
    if px>=100: return round(px/10)*10
    if px>=10: return round(px/1)*1
    if px>=1: return round(px/0.1)*0.1
    return round(px/0.01)*0.01

def backtest(sym, mode="v1", wick=0.55, rows=None):
    if rows is None: rows=load(sym)
    n=len(rows)
    if n < N_SWING+MAXH+5: return None
    trades=[]
    i=N_SWING+1
    while i<n-1:
        a,b=i-N_SWING,i
        hh,ll=smax_high(rows,a,b),smin_low(rows,a,b)
        cur_h,cur_l=rows[i]["high"],rows[i]["low"]
        av=atr(rows,i)
        if av is None or av<=0: i+=1; continue
        side=1 if cur_h>hh else (-1 if cur_l<ll else None)
        if side is None: i+=1; continue
        entry=rows[i+1]["open"]
        sld=SLM*av
        sl = entry-sld if side==1 else entry+sld
        tp = entry+TPR*sld if side==1 else entry-TPR*sld
        exit_r=None
        for j in range(i+1, min(i+MAXH,n-1)+1):
            hj,lj,cj=rows[j]["high"],rows[j]["low"],rows[j]["close"]
            if side==1:
                if lj<=sl: exit_r=-1.0; break
                if mode=="baseline" and hj>=tp: exit_r=TPR; break
                if mode in ("v1","v2","v2.1") and (hj-entry)/sld>=TRIG:
                    up,_=wick_ratio(rows,j)
                    cond = up>wick and hj>=smax_high(rows,max(0,j-MREC),j+1)
                    if mode in ("v2","v2.1"):
                        rng=hj-rows[j]["low"]
                        _kmax=min(52,j+1); _lo_i=2+5+1
                        _sw_h=smax_high(rows,_lo_i,_kmax) if _kmax>_lo_i else smax_high(rows,2,_kmax)
                        _rh=_rl(hj)
                        pool=(hj>=_sw_h-rng*0.15) or (_rh is not None and abs(hj-_rh)<=rng*0.25)
                        cj_ok = cj < hj  # 收盘回位(Sweep非Run)
                        cond = cond and pool and cj_ok
                    if mode=="v2.1":
                        _tkv=rows[j]["tick_volume"]
                        _vavg=sum(rows[k]["tick_volume"] for k in range(max(0,j-20),j))/20.0
                        if _vavg>0 and _tkv<_vavg*1.35: cond=False
                    if cond: exit_r=(hj-entry)/sld; break
                if j==min(i+MAXH,n-1): exit_r=(cj-entry)/sld
            else:
                if hj>=sl: exit_r=-1.0; break
                if mode=="baseline" and lj<=tp: exit_r=TPR; break
                if mode in ("v1","v2","v2.1") and (entry-lj)/sld>=TRIG:
                    _,dn=wick_ratio(rows,j)
                    cond = dn>wick and lj<=smin_low(rows,max(0,j-MREC),j+1)
                    if mode in ("v2","v2.1"):
                        rng=rows[j]["high"]-lj
                        _kmax=min(52,j+1); _lo_i=2+5+1
                        _sw_l=smin_low(rows,_lo_i,_kmax) if _kmax>_lo_i else smin_low(rows,2,_kmax)
                        _rlv=_rl(lj)
                        pool=(lj<=_sw_l+rng*0.15) or (_rlv is not None and abs(lj-_rlv)<=rng*0.25)
                        cj_ok = cj > lj
                        cond = cond and pool and cj_ok
                    if mode=="v2.1":
                        _tkv=rows[j]["tick_volume"]
                        _vavg=sum(rows[k]["tick_volume"] for k in range(max(0,j-20),j))/20.0
                        if _vavg>0 and _tkv<_vavg*1.35: cond=False
                    if cond: exit_r=(entry-lj)/sld; break
                if j==min(i+MAXH,n-1): exit_r=(entry-cj)/sld
        if exit_r is not None: trades.append(exit_r)
        i+=1
    return trades

def summarize(t):
    if not t: return None
    g=sum(x for x in t if x>0); l=-sum(x for x in t if x<0)
    return dict(n=len(t), win=sum(1 for x in t if x>0)/len(t), avgR=statistics.mean(t), pf=(g/l if l>0 else 99))

if __name__=="__main__":
    CORE=["XAUUSD","BTCUSD","EURUSD","GBPUSD","USDJPY","NAS100","US30","XAGUSD"]
    print(f"{'品种':<9} {'n':>5} {'base':>6} {'v1':>6} {'v2':>6} {'v2.1':>6} | v2.1Δbase 胜率(v2.1)")
    print("-"*72)
    S={m:[] for m in ["baseline","v1","v2","v2.1"]}
    for sym in CORE:
        res={m:summarize(backtest(sym,m)) for m in S}
        if any(r is None for r in res.values()): print(f"{sym:<9} 不足"); continue
        for m in S: S[m].append(res[m]["avgR"])
        b=res["baseline"]["avgR"]; v=res["v2.1"]["avgR"]
        print(f"{sym:<9} {res['baseline']['n']:>5} {b:>6.3f} {res['v1']['avgR']:>6.3f} {res['v2']['avgR']:>6.3f} {v:>6.3f} | {v-b:>+6.3f}   {res['v2.1']['win']*100:4.0f}%")
    print("-"*72)
    print("8品种均值: "+"  ".join(f"{m}={statistics.mean(S[m]):.3f}" for m in S))
    b=statistics.mean(S["baseline"]); v=statistics.mean(S["v2.1"])
    print(f"v2.1 vs baseline 均值ΔavgR = {v-b:+.3f} (正=更优); v2.1胜出品种={sum(1 for x,y in zip(S['baseline'],S['v2.1']) if y>x)}/8")
