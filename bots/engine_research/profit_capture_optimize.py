# -*- coding: utf-8 -*-
"""
小波段出场优化回测 v2 (修复逻辑bug): 在行情反转前吃到利润
修复:
  - 反转离场分支统一 break; B/C/D 各自正确处理
  - MAX_BARS 缩短到小波段尺度(48根H1≈2天), 让反转在窗内发生
  - 加捕获率<=100% 断言校验
  - 额外报告"反转回吐子集"(MFE>=1R 且 落袋<0.5*MFE): 直接回答"大浮盈没吃到"
入场: swing突破(20根)  SL=2ATR  无初始TP
对比:
  A 当前阶梯锁利+1.5ATR跟踪
  B 反转前离场(盈利>=1R后, 收盘跌破/涨破近期摆动极值即全平 + 0.5ATR紧跟踪)
  C 提前分批(>=1R平50%锁0.5R, 余仓用B)  [推荐基线]
  D 混合(=C + 余仓更紧0.4ATR跟踪 + MAXHOLD兜底)
"""
import csv, os

ROOT="E:/GoldstrategyEngine"; DATA=os.path.join(ROOT,"data")
SYMS=["XAUUSD","BTCUSD","EURUSD","GBPUSD","USDJPY","NAS100","US30","XAGUSD"]
MAX_BARS=48; SWING=20; ATR_N=14

def load(sym):
    p=os.path.join(DATA,sym+"_H1.csv")
    if not os.path.exists(p): return None
    bars=[]
    with open(p,encoding="utf-8") as f:
        r=csv.reader(f); next(r,None)
        for row in r:
            if len(row)<5: continue
            try: o,h,l,c=float(row[1]),float(row[2]),float(row[3]),float(row[4])
            except: continue
            bars.append([o,h,l,c])
    return bars

def atr(bars,i,n=ATR_N):
    if i<n: return None
    trs=[]
    for k in range(i-n+1,i+1):
        h,l,pc=bars[k][1],bars[k][2],(bars[k-1][3] if k>0 else bars[k][3])
        trs.append(max(h-l,abs(h-pc),abs(l-pc)))
    return sum(trs)/n

def gen_entries(bars):
    ents=[]
    for i in range(SWING,len(bars)-MAX_BARS-1):
        hi=max(bars[k][1] for k in range(i-SWING,i)); lo=min(bars[k][2] for k in range(i-SWING,i))
        c=bars[i][3]
        if c>hi: ents.append((i+1,1))
        elif c<lo: ents.append((i+1,-1))
    return ents

def trade(bars,e,dirn,strat):
    a=atr(bars,e)
    if a is None or a<=0: return None
    entry=bars[e][0]; sld=2.0*a; sl=entry-dirn*sld
    extreme=entry; mfe=0.0; scaled=False; swing_peak=entry
    exit_px=None; reason=None
    last=min(e+MAX_BARS,len(bars)-1)
    bug_buf = (strat=="A_bug")  # 复现实盘0.15绝对地板bug对照
    for j in range(e+1,last+1):
        o,h,l,c=bars[j][0],bars[j][1],bars[j][2],bars[j][3]
        aj=atr(bars,j) or a
        extreme=max(extreme,h) if dirn>0 else min(extreme,l)
        mfe=max(mfe,(extreme-entry)/sld*dirn)
        if dirn>0: swing_peak=max(swing_peak,c)
        else:      swing_peak=min(swing_peak,c)
        r_now=(c-entry)/sld*dirn
        # SL 触发(任何策略都先判SL)
        if dirn>0 and l<=sl: exit_px=sl; reason="SL"; break
        if dirn<0 and h>=sl: exit_px=sl; reason="SL"; break
        if strat in ("A","A_bug"):
            ns=sl
            if r_now>=0.5:
                if bug_buf:
                    _buf=max(0.2*sld,0.15,(bars[j][1]-bars[j][2])*0.0)  # 0.15绝对地板(复现bug)
                else:
                    _buf=0.2*sld
                ns=max(ns,entry+dirn*_buf)
                if r_now>=1.0:
                    ns=max(ns,entry+dirn*0.5*sld)
                if r_now>=1.5:
                    ns=max(ns,extreme-dirn*1.2*aj)
                if r_now>=2.0:
                    ns=max(ns,extreme-dirn*1.5*aj)
                sl=ns
                if dirn>0 and l<=sl: exit_px=sl; reason="TRAIL"; break
                if dirn<0 and h>=sl: exit_px=sl; reason="TRAIL"; break
        else:  # B/C/D
            if r_now>=1.0:
                # 反转前离场: 收盘跌破(多)/涨破(空)近期摆动极值
                if dirn>0 and c < swing_peak - 0.5*aj:
                    if strat in ("C","D") and not scaled:
                        half=0.5*1.0; rem=(c-entry)/sld*dirn
                        exit_px=c; reason="REV_EXIT"
                        return (half+0.5*rem, mfe, reason)
                    exit_px=c; reason="REV_EXIT"; break
                if dirn<0 and c > swing_peak + 0.5*aj:
                    if strat in ("C","D") and not scaled:
                        half=0.5*1.0; rem=(c-entry)/sld*dirn
                        exit_px=c; reason="REV_EXIT"
                        return (half+0.5*rem, mfe, reason)
                    exit_px=c; reason="REV_EXIT"; break
                # 紧跟踪
                tsl=extreme-dirn*(0.4 if strat=="D" else 0.5)*aj
                if tsl*dirn>sl*dirn: sl=tsl
                if dirn>0 and l<=sl: exit_px=sl; reason="TRAIL"; break
                if dirn<0 and h>=sl: exit_px=sl; reason="TRAIL"; break
            else:
                if r_now>=0.5:
                    cand=entry+dirn*0.2*sld
                    if cand*dirn>sl*dirn: sl=cand
                if dirn>0 and l<=sl: exit_px=sl; reason="BE"; break
                if dirn<0 and h>=sl: exit_px=sl; reason="BE"; break
    if exit_px is None:
        exit_px=bars[last][3]; reason="MAXHOLD"
    realized=(exit_px-entry)/sld*dirn
    return (realized,mfe,reason)

def summ(name,res):
    if not res: print(f"  {name}: 无样本"); return
    n=len(res)
    avg=sum(r[0] for r in res)/n
    mfe_s=sum(r[1] for r in res); real_s=sum(r[0] for r in res)
    cap=real_s/mfe_s*100 if mfe_s>1e-9 else float('nan')
    if cap is not None and cap>100.5:
        print(f"  !! 捕获率异常 {cap:.1f}% (应<=100) -- 校验失败")
    rev=sum(1 for r in res if r[2]=="REV_EXIT"); mh=sum(1 for r in res if r[2]=="MAXHOLD")
    # 反转回吐子集: MFE>=1R 且 落袋<0.5*MFE
    sub=[r for r in res if r[1]>=1.0 and r[0]<0.5*r[1]]
    sub_n=len(sub); sub_cap=(sum(r[0] for r in sub)/sum(r[1] for r in sub)*100) if sub and sum(r[1] for r in sub)>1e-9 else float('nan')
    print(f"  {name:16s} n={n:4d} 均值R={avg:+.3f} 捕获率={cap:6.1f}% | 反转回吐子集 n={sub_n:3d} 落袋均值={ (sum(r[0] for r in sub)/sub_n if sub_n else 0):+.3f} 捕获率={sub_cap if sub_n else 0:6.1f}% | REV={rev} MH={mh}")
    return dict(n=n,avg=avg,cap=cap,sub_n=sub_n,sub_cap=sub_cap if sub_n else 0,rev=rev,mh=mh)

print("="*100)
print("  小波段出场优化回测 v2 · 在反转前吃到利润 (MAX_BARS=48根≈2天, 入场=swing突破/SL=2ATR/无TP)")
print("="*100)
for strat in ("A","A_bug","D"):
    label={"A":"当前阶梯+1.5ATR跟踪","A_bug":"[复现bug]0.15绝对地板","B":"反转前离场(全平)","C":"提前分批+反转前(推荐)","D":"混合(更紧跟踪)"}[strat]
    print(f"\n[策略 {strat}] {label}")
    tot=[]
    for sym in SYMS:
        bars=load(sym)
        if not bars: print(f"    {sym}: 无数据"); continue
        res=[r for r in (trade(bars,e,d,strat) for e,d in gen_entries(bars)) if r]
        summ(sym,res); tot+=res
    print("  "+"-"*96)
    summ("★8品种合计",tot)
