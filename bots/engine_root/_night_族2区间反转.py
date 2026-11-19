# -*- coding: utf-8 -*-
"""族2 区间反转族(服务震荡腿) — 一夜全知流水线
数据: E:/GoldstrategyEngine/data/tf_cache/{SYM}_{TF}.npz (M30/H4, 6品种)
事件: 前20根高低(Donchian) Limit 挂单等反转 — 同分母
候选: C1 裸边沿Limit(出对侧) / C2 RSI(2)极值门(出中点) / C3 BB中值回归 / C4 ADX<20门控
出场: 回归中值/对侧 或 SL=0.75*ATR14(野德), 窗口末端close计R (M30=48根24h, H4=6根24h)
对称自检: BUY限(下边) vs SELL限(上边) 镜像几何
"""
import os, json, time
import numpy as np
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")

CACHE="E:/GoldstrategyEngine/data/tf_cache"
OUT="E:/GoldstrategyEngine/data/night_rd_族2区间反转.json"
SYMS=["BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD"]
TFS=["M30","H4"]
FILL=4            # event bar 之后 FILL 根内触价成交
SL_ATR=0.75       # SL = trig ∓ 0.75*ATR14
MAX_HOLD={"M30":48, "H4":6}   # ≥24h

def load(sym,tf):
    d=np.load(os.path.join(CACHE,f"{sym}_{tf}.npz"))
    return d["t"].astype(np.int64),d["o"].astype(np.float64),d["h"].astype(np.float64),d["l"].astype(np.float64),d["c"].astype(np.float64)

def atr14(h,l,c):
    n=len(c); a=np.zeros(n)
    if n<=14: return a
    tr=np.zeros(n); tr[1:]=np.maximum(h[1:]-l[1:],np.maximum(np.abs(h[1:]-c[:-1]),np.abs(l[1:]-c[:-1])))
    a[14:]=np.nan
    a[14]=np.mean(tr[1:15])
    for i in range(15,n): a[i]=(a[i-1]*13+tr[i])/14
    return a

def rsi2(c):
    n=len(c); out=np.full(n,np.nan)
    if n<=2: return out
    out[1]=100.0 if (c[1]>=c[0]) else (0.0 if c[1]<c[0] else 50.0)
    if c[1]>=c[0]: ru,rd=1.0,0.0
    else: ru,rd=0.0,1.0
    for i in range(2,n):
        ch=c[i]-c[i-1]
        ru=(ru*1+max(ch,0))/2; rd=(rd*1+max(-ch,0))/2
        out[i]=100.0 if rd==0 else 100-100/(1+ru/rd)
    return out

def adx14(h,l,c):
    """ADX14 Wilder: 分号 = Wilder 平滑 (上一平滑值*(13/14) + 本期), 期初=前14期之和."""
    n=len(c); out=np.full(n,np.nan)
    if n<28: return out
    up=np.maximum(np.diff(h, prepend=h[0]),0.0)
    dn=np.maximum(-np.diff(l, prepend=l[0]),0.0)
    pdm=np.where((up>dn)&(up>0),up,0.0); mdm=np.where((dn>up)&(dn>0),dn,0.0)
    tr=np.zeros(n); tr[1:]=np.maximum(h[1:]-l[1:],np.maximum(np.abs(h[1:]-c[:-1]),np.abs(l[1:]-c[:-1])))
    # Wilder 平滑 (期初种子 = 前14期求和, 与 spec §2 的 ATR 同口径)
    spw=np.zeros(n); smw=np.zeros(n); trw=np.zeros(n)
    for i in range(1,15): spw[i]=spw[i-1]+pdm[i]; smw[i]=smw[i-1]+mdm[i]; trw[i]=trw[i-1]+tr[i]
    for i in range(15,n):
        spw[i]=spw[i-1]*13/14+pdm[i]; smw[i]=smw[i-1]*13/14+mdm[i]; trw[i]=trw[i-1]*13/14+tr[i]
    dx=np.zeros(n)
    for i in range(14,n):
        if trw[i]==0: continue
        pdi=100*spw[i]/trw[i]; mdi=100*smw[i]/trw[i]; s=pdi+mdi
        dx[i]=0.0 if s==0 else 100*abs(pdi-mdi)/s
    out[14]=np.nanmean(dx[14:28])
    for i in range(15,n): out[i]=(out[i-1]*13+dx[i])/14
    return out

def bb_mid(c):
    n=len(c); out=np.full(n,np.nan)
    for i in range(19,n): out[i]=c[i-19:i+1].mean()
    return out

def donchian(h,l):
    n=len(h); hi=np.full(n,np.nan); lo=np.full(n,np.nan)
    if n<20: return hi,lo
    for i in range(19,n):
        hi[i]=h[i-19:i+1].max(); lo[i]=l[i-19:i+1].min()
    return hi,lo

CANDS=[
 ("C1_裸边限单出对侧", dict(tp="opp", gate=None)),
 ("C2_RSI2极值门出中点", dict(tp="mid", gate="rsi")),
 ("C3_BB中值回归", dict(tp="mid", gate=None)),
 ("C4_ADX20门控", dict(tp="opp", gate="adx")),
]

def replay(sym, tf, spec):
    """返回 (trades, meta). trades: list of dict(fill_i, R, side, sym, tf)"""
    t,o,h,l,c=load(sym,tf)
    n=len(c); MH=MAX_HOLD[tf]
    A=atr14(h,l,c); R2=rsi2(c); AD=adx14(h,l,c); BM=bb_mid(c)
    HI,LO=donchian(h,l)
    tp_mode=spec["tp"]; gate=spec["gate"]
    trades=[]; i=20
    while i < n-MH-FILL-2:
        # ---- 事件判定仅用 i-1 及以前 ----
        th,tl=HI[i-1],LO[i-1]
        at=A[i-1]
        if np.isnan(th) or np.isnan(tl) or np.isnan(at) or at<=0:
            i+=1; continue
        ok=True
        if gate=="adx":
            if np.isnan(AD[i-1]) or AD[i-1]>=20: ok=False
        if gate=="rsi":
            if np.isnan(R2[i-1]): ok=False
        # 双侧事件: BUY限@tl, SELL限@th (镜像几何)
        pending={}
        if ok and th-tl>0:
            if gate!="rsi" or (not np.isnan(R2[i-1]) and R2[i-1]<15):
                pending["BUY"]=tl
            if gate!="rsi" or (not np.isnan(R2[i-1]) and R2[i-1]>85):
                pending["SELL"]=th
        if not pending:
            i+=1; continue
        # ---- 成交: event bar 之后 FILL 根内触价 (limit: 价格回踩边沿) ----
        filled=None
        for j in range(i+1, min(i+1+FILL,n)):
            for sd in list(pending):
                trig=pending[sd]
                if sd=="BUY" and l[j]<=trig:
                    filled=(sd,trig,j); pending.pop(sd)
                elif sd=="SELL" and h[j]>=trig:
                    filled=(sd,trig,j); pending.pop(sd)
            if not pending: break
        if filled is None:
            i+=1; continue
        sd,trig,fj=filled
        risk=SL_ATR*at
        # 几何 (镜像): BUY@下边 → SL下 TP上; SELL@上边 → SL上 TP下
        if sd=="BUY":
            sl=trig-risk
            if tp_mode=="opp": tp=th
            else: tp=BM[i-1]
            if np.isnan(tp) or tp<=trig+0.2*risk: tp=trig+risk   # 兜底1R, 中值异常
        else:
            sl=trig+risk
            if tp_mode=="opp": tp=tl
            else: tp=BM[i-1]
            if np.isnan(tp) or tp>=trig-0.2*risk: tp=trig-risk
        end=min(fj+MH,n-1)
        exitp=None
        for j in range(fj+1,end+1):
            hit_sl = (l[j]<=sl) if sd=="BUY" else (h[j]>=sl)
            hit_tp = (h[j]>=tp) if sd=="BUY" else (l[j]<=tp)
            if hit_sl:      exitp=sl; break   # 同根双触判SL保守
            if hit_tp:      exitp=tp; break
        if exitp is None: exitp=c[end]        # 窗口末端close计R
        R=(exitp-trig)/risk if sd=="BUY" else (trig-exitp)/risk
        trades.append(dict(fill_i=fj,R=R,side=sd,sym=sym,tf=tf))
        i=fj+1   # 持仓期间不挂新单
    return trades

def sym_stat(sym, tf, spec):
    tr=replay(sym,tf,spec)
    Rs=np.array([x["R"] for x in tr])
    d=dict(n=int(len(Rs)), exp_R=float(Rs.mean()) if len(Rs) else None,
           wr=float((Rs>0).mean()) if len(Rs) else None,
           Rs=Rs.tolist())
    return d

def main():
    t0=time.time()
    report=[]
    for name,spec in CANDS:
        all_tr=[]
        per_sym={}
        for tf in TFS:
            for sym in SYMS:
                tr=replay(sym,tf,spec)
                all_tr.extend(tr)
                Rs=np.array([x["R"] for x in tr])
                per_sym[f"{sym}@{tf}"]=float(Rs.mean()) if len(Rs) else None
        # 全局wf3: 按 (tf,sym,fill_i) 时间排序后三等分
        all_tr.sort(key=lambda x:(TFS.index(x["tf"]),SYMS.index(x["sym"]),x["fill_i"]))
        Rs=np.array([x["R"] for x in all_tr]) if all_tr else np.array([])
        n=len(all_tr)
        if n:
            wf3=[float(Rs[:n//3].mean()), float(Rs[n//3:2*n//3].mean()), float(Rs[2*n//3:].mean())]
            exp=float(Rs.mean()); wr=float((Rs>0).mean())
        else:
            exp=wr=None; wf3=[None]*3
        buys=[x for x in all_tr if x["side"]=="BUY"]; sells=[x for x in all_tr if x["side"]=="SELL"]
        mb=float(np.mean([x["R"] for x in buys])) if buys else 0.0
        ms=float(np.mean([x["R"] for x in sells])) if sells else 0.0
        ratio_ok = n>0 and len(buys)>=0.3*n and len(sells)>=0.3*n
        mirror_ok = ratio_ok and abs(mb-ms)<0.5
        psym={s:(per_sym.get(f"{s}@M30"),per_sym.get(f"{s}@H4")) for s in SYMS}
        npos=sum(1 for s in SYMS for e in psym[s] if e is not None and e>0)
        sym_pass = npos>=4
        psd={}
        for s in SYMS:
            a,b=psym[s]
            psd[s]={"M30":round(a,4) if a is not None else None,
                    "H4":round(b,4) if b is not None else None,
                    "pos":bool((a is not None and a>0)or(b is not None and b>0))}
        report.append(dict(
            name=name, tf="M30+H4", n=int(n),
            exp_R=round(exp,4) if exp is not None else None,
            wr=round(wr,4) if wr is not None else None,
            wf3=[round(x,4) if x is not None else None for x in wf3],
            per_sym=psd,
            sym_pass=sym_pass, same_denom=True, close_basis=True,
            net_P95=round(exp-0.095,4) if exp is not None else None,
            net_P95x2=round(exp-0.19,4) if exp is not None else None,
            mirror_buy_n=len(buys), mirror_sell_n=len(sells),
            mirror_exp_diff=round(abs(mb-ms),4),
            mirror_pass=bool(mirror_ok),
            note=f"n={n} BUY{len(buys)}/SELL{len(sells)} exp-diff{abs(mb-ms):.3f}R "
                 f"sym_pos={npos}/6 " + ("mirror PASS" if mirror_ok else "mirror FAIL"),
        ))
        print(name, "n=",n, "exp_R=",exp, "wr=",wr, "wf3=",wf3, "mirror=",mirror_ok, "net_P95=",None if exp is None else exp-0.095)
    json.dump(report, open(OUT+".candidates.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
    # 选top: 优先 mirror pass & net_P95>0; 否则 exp_R 最高
    valid=[r for r in report if r["mirror_pass"] and (r["net_P95"] or -9)>0]
    top = max(valid, key=lambda r:r["exp_R"])["name"] if valid else (max(report,key=lambda r:(r["exp_R"] or -9))["name"] if any(r["exp_R"] is not None for r in report) else report[0]["name"])
    json.dump({"top":top}, open(OUT+".top.json","w"))
    print("TOP=",top, "ELAPSED=",round(time.time()-t0,1))

if __name__=="__main__":
    main()
