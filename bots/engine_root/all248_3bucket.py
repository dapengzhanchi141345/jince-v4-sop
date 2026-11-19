#!/usr/bin/env python
# 248 品种全回测 × 3 桶(供需区浮亏加仓) × 0.01 固定手数 × 6mo H1
# 口径: 护栏"区 SL 距离 3~400 pip"有效信号; 加单 SL 放区外, 到期保守记 -1R
# 0 LLM, 0 写闸源, 0 改 live. 产物 data/all248_3bucket_6mo.json (utf-8).
import os, sys, json, datetime, traceback
os.chdir(r"E:\GoldstrategyEngine"); sys.path.insert(0, r"E:\GoldstrategyEngine")
import numpy as np, pandas as pd, MetaTrader5 as mt5
import symbol_universe as su, backtest_engine as BE
import pasd_fusion as PF

DAYS=180; RR=2.5; LOT=0.01
GUARD_PIP_MIN=3; GUARD_PIP_MAX=400  # 护栏: 区 SL 距离 3~400 pip 才算有效信号
# 0.01 手 pipvalue USD (每品种 100 美元/pip, 标准账户 1 手 = 10000 USD/pip, 0.01 手 = 10 USD/pip — 外汇)
# 按品种类别折算: 外汇=10, 商品(黄金/原油)=1~10, 股指=1~5, 币=0.01~1, 港股=0.1~1 (估算, 参考口径)
PVP_TABLE={'外汇':10.0,'XAU':1.0,'XAG':10.0,'USOIL':10.0,'BTC':0.1,'ETH':1.0,'HKG':1.0,'指数':1.0}
def pipval(sym,cfg,info):
    # 同 @hermes 件口径: cfg.pip_usd (默认 10.0 USD/pip/0.01手), 0 外部估算
    try:
        return float(cfg.get('pip_usd',10.0))
    except: return 10.0

def rates(sym,tf,d=DAYS,mins=30):
    F=[];p=0
    for _ in range(8):
        c=mt5.copy_rates_from_pos(sym,tf,p,5000)
        if c is None or len(c)==0:break
        F.append(pd.DataFrame(c));p+=len(c)
        if len(c)<5000:break
    if not F:return None
    df=pd.concat(F).drop_duplicates("time").sort_values("time").reset_index(drop=True)
    df["t"]=pd.to_datetime(df["time"],unit="s")
    df=df[df["t"]>=df["t"].max()-pd.Timedelta(days=d)].reset_index(drop=True)
    return df if len(df)>=mins else None

def add_lv(sig,zd,zs,mode,pt):
    E,side=sig["entry"],sig["side"];lv=[]
    if mode=="A":return []
    if side>0:
        cands=[x for x in zd if x["bottom"]<E]
        if cands:
            z=cands[0]
            lv=[(z["top"]+z["bottom"])/2.0,z["bottom"]] if mode=="B" else [z["bottom"]]
    else:
        cands=[x for x in zs if x["top"]>E]
        if cands:
            z=cands[0]
            lv=[(z["top"]+z["bottom"])/2.0,z["top"]] if mode=="B" else [z["top"]]
    return lv[:2]

def sim(h1,sig,lv,sp,pt,swl,swh,MAXH,pvp):
    i=int(sig['bar']);side=1 if sig['side']>0 else -1
    if i+1>=len(h1):return None
    sd0=abs(sig['entry']-sig['sl']);td0=abs(sig['entry']-sig['tp'])
    o=float(h1['open'].iloc[i+1])
    a=sp/pt  # 滑点 pips
    e0=o+a*side*pt
    S=e0-side*sd0; TP0=e0+side*td0
    end=min(i+1+MAXH,len(h1))
    hi=h1['high'].values[i+1:end];lo=h1['low'].values[i+1:end]
    cl=h1['close'].values[i+1:end]
    if len(hi)==0:return None
    pos=[e0];adds=0;exit=None
    for k in range(len(hi)):
        tot=len(pos)
        if side>0:slh=lo[k]<=S;tph=hi[k]>=TP0
        else:slh=hi[k]>=S;tph=lo[k]<=TP0
        if adds<len(lv) and ((lo[k]<=lv[adds]) if side>0 else (hi[k]>=lv[adds])):
            pos.append(lv[adds]);adds+=1
        if slh and tph:exit=S;break
        elif slh:exit=S;break
        elif tph:exit=TP0;break
    if exit is None:exit=float(cl[-1])
    avg=sum(pos)/len(pos);tot=len(pos)
    pnl_pips=(exit-avg)*side/pt
    pnl=pnl_pips*pvp
    # swap: 持仓天数 × 每手每天swap(0.01手缩放)
    ptime=h1['time'].values[i+1:end]
    days=max(1,int((ptime[-1]-ptime[0])//86400)) if len(ptime)>0 else 1
    swl_v=abs(swl if side>0 else swh)/100.0
    pnl-=swl_v*days
    risk_pips=sd0/pt
    R=pnl_pips/risk_pips if risk_pips>0 else 0.0
    # 加单到期保守记 -1R (加单 SL 放区外未触发 = 到期)
    if adds>0 and exit==S:
        R-=adds  # 每笔加单到期记 -1R
    return dict(pnl=pnl,R=R,adds=adds,win=1 if pnl>0 else 0)

def run_dn(pnls):
    c=peak=dd=0.0
    for x in pnls:
        c+=x;peak=max(peak,c);dd=max(dd,peak-c)
    return dd

def main():
    import mt5_login
    mt5.initialize()
    ok,why=mt5_login.ensure_login(60137964)
    if not ok:
        print("LOGIN FAIL:",why);return
    all_syms=mt5.symbols_get('*')
    all_syms=[s for s in all_syms if s.select]
    print('全市场品种 =',len(all_syms))
    MAXH=BE.MAX_HOLD_H1
    out={"generated":datetime.datetime.now().isoformat(),"sym_count":len(all_syms),
         "window_days":DAYS,"lot_fixed":LOT,"rr":RR,
         "note":"248品种全回测, 3桶(A不加/C加1/B加2=中点+到区), 0.01固定手数, 护栏3~400pip, 源=mt5:60137964, 0外部数据, 0写闸源 0进live"}
    per_sym=[]
    for idx,sobj in enumerate(all_syms):
        sym=sobj.name  # SymbolInfo 对象 -> 品种名字符串 (bug 修复: 之前拿对象去 symbol_info 全 None)
        if (idx+1)%10==0:print(f'  进度 {idx+1}/{len(all_syms)} = {sym}',flush=True)
        info=mt5.symbol_info(sym)
        if info is None:continue
        sp=info.spread or 0;pt=info.point or 1e-5
        swl=info.swap_long or 0;swh=info.swap_short or 0
        h1=rates(sym,mt5.TIMEFRAME_H1,mins=200)
        if h1 is None:per_sym.append(dict(sym=sym,n_sigs=0,err='H1短'));continue
        h4=rates(sym,mt5.TIMEFRAME_H4,mins=60)
        d1=rates(sym,mt5.TIMEFRAME_D1,d=365,mins=30)
        cfg=su.UNIVERSE.get(sym,{'spread':sp})
        pvp=pipval(sym,cfg,info)
        try:
            sigs=PF.gen_pasd(h1,h4,d1,cfg)
        except Exception as e:
            per_sym.append(dict(sym=sym,n_sigs=0,err=f'gen_pasd:{e}'));continue
        for s in sigs:s['tp']=s['entry']+s['side']*RR*abs(s['entry']-s['sl'])
        # 护栏: 区 SL 距离 3~400 pip
        sips=[abs(s['entry']-s['sl'])/pt for s in sigs]
        sigs=[s for s,d in zip(sigs,sips) if GUARD_PIP_MIN<=d<=GUARD_PIP_MAX]
        zs=PF._detect_supply_demand_zones(h1['high'].values,h1['low'].values,h1['close'].values)
        bres={}
        for mode,tag in [("A","A_不加"),("C","C_加1"),("B","B_加2(中点+到区)")]:
            pnls=[];Rs=[];adds_n=0;wins=0
            for s in sigs:
                lv=add_lv(s,zs['demand'],zs['supply'],mode,pt)
                r=sim(h1,s,lv,sp,pt,swl,swh,MAXH,pvp)
                if r is None:continue
                pnls.append(r['pnl']);Rs.append(r['R']);adds_n+=1 if r['adds']>0 else 0;wins+=r['win']
            n=len(pnls)
            bres[tag]=dict(净R=round(sum(Rs)/max(1,n),3) if n else 0.0,
                累计R=round(sum(Rs),2) if n else 0.0,
                净USD=round(sum(pnls),2) if n else 0.0,
                胜率=round(wins/n*100,1) if n else 0.0,
                n=n,加仓触发=adds_n,最大回撤USD=round(run_dn(pnls),2) if n else 0.0)
        per_sym.append(dict(sym=sym,n_sigs=len(sigs),buckets=bres))
        if (idx+1)%50==0:
            json.dump({"_progress":idx+1,"_total":len(all_syms),"per_sym":per_sym,
                       "generated":out["generated"],"sym_count":out["sym_count"]},
                      open('data/all248_3bucket_6mo_progress.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
    # 全局统计
    valid=[x for x in per_sym if x.get('n_sigs',0)>0]
    b_all=[x for x in valid if 'B_加2(中点+到区)' in x.get('buckets',{}) and x['buckets']['B_加2(中点+到区)']['n']>0]
    out["per_sym"]=per_sym
    out["n_valid_syms"]=len(valid)
    out["n_with_trades"]=len(b_all)
    out["top10_by_B_cumR"]=sorted([x for x in valid if 'B_加2(中点+到区)' in x.get('buckets',{})],
                                   key=lambda x:-x['buckets'].get('B_加2(中点+到区)',{}).get('累计R',0),
                                   reverse=True)[:10]
    out["bot10_by_B_cumR"]=sorted([x for x in valid if 'B_加2(中点+到区)' in x.get('buckets',{})],
                                   key=lambda x:x['buckets'].get('B_加2(中点+到区)',{}).get('累计R',0))[:10]
    # B vs A: 有多少品种 B 比 A 好/差
    b_better=0;a_better=0;ties=0
    for x in valid:
        B=x.get('buckets',{}).get('B_加2(中点+到区)',{});A=x.get('buckets',{}).get('A_不加',{})
        if not B or not A or B.get('n',0)==0 or A.get('n',0)==0:continue
        if B.get('累计R',0)>A.get('累计R',0):b_better+=1
        elif B.get('累计R',0)<A.get('累计R',0):a_better+=1
        else:ties+=1
    out["B优于A品种数"]=b_better;out["A优于B品种数"]=a_better;out["持平"]=ties
    json.dump(out,open('data/all248_3bucket_6mo.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
    print('DONE. 有效品种 =',len(valid),'| 有交易 =',len(b_all),'| B优于A =',b_better,'A优于B =',a_better,'持平 =',ties)
    print('产物: data/all248_3bucket_6mo.json')
    mt5.shutdown()

if __name__=="__main__":main()
