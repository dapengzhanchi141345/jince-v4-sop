"""
SDP v6.2 — 快速定向优化
每个品种只测最有希望的参数组合，不暴力枚举
"""
import sys, os, json, time
import numpy as np, pandas as pd
import warnings
warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from strategies.supply_demand import SupplyDemandSMC

MAX_LOT = 0.01

# ─── 定向参数范围（基于品种特性） ───
SYM_SEARCH = {
    "XAUUSD": {"sl": [1.0, 1.5, 2.0], "rr": [2.0, 2.5], "adx": [22, 26], "zs": [1.5, 2.0]},
    "EURUSD": {"sl": [0.3, 0.5, 0.8], "rr": [1.5, 2.0, 2.5], "adx": [18, 22], "zs": [1.0, 1.5]},
    "GBPUSD": {"sl": [0.5, 0.8, 1.0], "rr": [1.5, 2.0, 2.5], "adx": [18, 22], "zs": [1.0, 1.5]},
    "BTCUSD": {"sl": [1.0, 1.5, 2.0], "rr": [2.0, 2.5, 3.0], "adx": [20, 24], "zs": [1.5, 2.0]},
    "ETHUSD": {"sl": [0.8, 1.0, 1.5], "rr": [2.0, 2.5], "adx": [18, 22], "zs": [1.0, 1.5]},
}

def load_all():
    import MetaTrader5 as mt5
    mt5.initialize(path=r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe")
    mt5.login(60043976, password="", server="TradeMaxGlobal-Demo")
    
    all_d = {}
    for sym in SYM_SEARCH:
        def to_df(d):
            if d is None or len(d)==0: return None
            df = pd.DataFrame(d); df["time"] = pd.to_datetime(df["time"],unit="s"); return df
        h4 = to_df(mt5.copy_rates_range(sym, mt5.TIMEFRAME_H4, int(pd.Timestamp("2026-06-20").timestamp()), int(pd.Timestamp("2026-07-05").timestamp())))
        h1 = to_df(mt5.copy_rates_range(sym, mt5.TIMEFRAME_H1, int(pd.Timestamp("2026-06-20").timestamp()), int(pd.Timestamp("2026-07-05").timestamp())))
        m5 = to_df(mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, int(pd.Timestamp("2026-06-20").timestamp()), int(pd.Timestamp("2026-07-05").timestamp())))
        if h1 is not None:
            h1["ema20"] = h1["close"].ewm(span=20).mean()
            h1["ema50"] = h1["close"].ewm(span=50).mean()
        all_d[sym] = {"h4": h4, "h1": h1, "m5": m5}
        print(f"  {sym}: H4={len(h4) if h4 is not None else 0}")
    mt5.shutdown()
    return all_d

def run_bt(data, sb, rr, adx_min, z_min):
    h4, h1, m5 = data["h4"], data["h1"], data["m5"]
    if h4 is None or len(h4) < 15: return None
    sd = SupplyDemandSMC({"swing_lookback":20,"base_min_bars":1,"base_max_bars":5,"retracement_min":0.20,"retracement_max":0.90})
    
    pos, trades, bal = None, [], 1000.0
    for i in range(5, len(h4)):
        bar = h4.iloc[i]; t, c, hi, lo = bar["time"], bar["close"], bar["high"], bar["low"]
        h4_atr = float((h4["high"].iloc[max(0,i-14):i+1] - h4["low"].iloc[max(0,i-14):i+1]).mean())
        
        if pos:
            hit = ("SL" if lo<=pos["sl"] else "TP" if hi>=pos["tp"] else None) if pos["side"]==1 else \
                  ("SL" if hi>=pos["sl"] else "TP" if lo<=pos["tp"] else None)
            if hit:
                cp = pos["sl"] if hit=="SL" else pos["tp"]
                pft = (cp-pos["entry"])*pos["side"]*0.01*100
                trades[-1]["ct"],trades[-1]["ex"],trades[-1]["pr"],trades[-1]["r"]=t,cp,pft,"W" if pft>0 else"L"
                bal+=pft; pos=None; continue
        
        zones = sd.detect_zones(h4.iloc[max(0,i-60):i+1])
        zc = None
        for z in zones.get("demand",[]):
            if z.strength>=z_min and c>z.top and c-z.top<h4_atr*2: zc=(z,"DEMAND"); break
        if not zc:
            for z in zones.get("supply",[]):
                if z.strength>=z_min and c<z.bottom and z.bottom-c<h4_atr*2: zc=(z,"SUPPLY"); break
        if not zc: continue
        
        h1b = h1[h1["time"]<=t]
        if len(h1b)<28: continue
        hl = h1b.iloc[-1]; p, e50 = hl["close"], hl["ema50"]
        ch = h1b["high"].iloc[-30:].values; cl = h1b["low"].iloc[-30:].values; cc = h1b["close"].iloc[-30:].values
        prd=14; tr=np.maximum(ch[1:]-cl[1:],np.maximum(abs(ch[1:]-cc[:-1]),abs(cl[1:]-cc[:-1])))
        up=ch[1:]-ch[:-1]; dn=cl[:-1]-cl[1:]
        pdi=100*pd.Series(np.where((up>dn)&(up>0),up,0)).ewm(span=prd).mean()/(pd.Series(tr).ewm(span=prd).mean()+1e-10)
        mdi=100*pd.Series(np.where((dn>up)&(dn>0),dn,0)).ewm(span=prd).mean()/(pd.Series(tr).ewm(span=prd).mean()+1e-10)
        dx=100*abs(pdi-mdi)/(pdi+mdi+1e-10); adx=float(dx.ewm(span=prd).mean().iloc[-1])
        
        trend="BULLISH" if adx>=adx_min and p>e50 else "BEARISH" if adx>=adx_min and p<e50 else "RANGING"
        dr="BUY" if trend=="BULLISH" and zc[1]=="DEMAND" else "SELL" if trend=="BEARISH" and zc[1]=="SUPPLY" else None
        if not dr: continue
        
        if m5 is not None:
            m5b=m5[(m5["time"]>t-pd.Timedelta(hours=4))&(m5["time"]<=t)]
            cf=False
            for k in range(3,len(m5b)):
                ck,cpk=m5b.iloc[k],m5b.iloc[k-1]; b=abs(ck["close"]-ck["open"]); bp=abs(cpk["close"]-cpk["open"])
                lw=min(ck["close"],ck["open"])-ck["low"]; hw=ck["high"]-max(ck["close"],ck["open"])
                if dr=="BUY":
                    if lw>b*2 and ck["close"]>ck["open"]: cf=True
                    elif b>bp*1.5 and ck["close"]>ck["open"] and cpk["close"]<cpk["open"]: cf=True
                else:
                    if hw>b*2 and ck["close"]<ck["open"]: cf=True
                    elif b>bp*1.5 and ck["close"]<ck["open"] and cpk["close"]>cpk["open"]: cf=True
            if not cf: continue
        
        z=zc[0]
        if dr=="BUY": entry=c; sl_pos=z.bottom-max(h4_atr*sb,2.0); tp=entry+(entry-sl_pos)*rr
        else: entry=c; sl_pos=z.top+max(h4_atr*sb,2.0); tp=entry-(sl_pos-entry)*rr
        pos={"side":1 if dr=="BUY" else -1,"entry":entry,"sl":sl_pos,"tp":tp}
        trades.append({"ot":t,"dir":dr,"en":entry,"sl":sl_pos,"tp":tp,"ct":None,"ex":None,"pr":None,"r":None})
    
    if pos and trades:
        lp=h4["close"].iloc[-1]; pft=(lp-pos["entry"])*pos["side"]*0.01*100
        trades[-1]["ct"],trades[-1]["ex"],trades[-1]["pr"],trades[-1]["r"]=h4["time"].iloc[-1],lp,pft,"W" if pft>0 else"L"
        bal+=pft
    
    closed=[t for t in trades if t.get("pr") is not None]
    if len(closed)<3: return None
    profits=[t["pr"] for t in closed]; wins=[p for p in profits if p>0]; losses=[p for p in profits if p<0]
    wr=len(wins)/len(closed); pf=sum(wins)/abs(sum(losses)) if losses and sum(losses)!=0 else 0
    peak,dd,eq=1000,0,1000
    for p in profits:
        eq+=p
        if eq>peak: peak=eq
        ddp=(peak-eq)/peak*100
        if ddp>dd: dd=ddp
    return {"trades":len(closed),"wr":wr*100,"pf":pf,"dd":dd,"np":bal-1000,"score":wr*pf*100}

# ═══════════ 主程序 ═══════════
if __name__=="__main__":
    t0=time.time()
    print("="*60)
    print("  SDP v6.2 定向快速优化")
    print("  每品种只测最有希望的参数组合")
    print("="*60)
    print("\n[*] 加载数据...")
    all_d=load_all()
    
    best_all={}
    total=0
    for sym in SYM_SEARCH:
        sr=SYM_SEARCH[sym]
        combos=[(s,r,a,z) for s in sr["sl"] for r in sr["rr"] for a in sr["adx"] for z in sr["zs"]]
        total+=len(combos)
    
    done=0
    for sym in SYM_SEARCH:
        data=all_d[sym]
        if data["h4"] is None or len(data["h4"])<15:
            print(f"\n[SKIP] {sym}")
            continue
        
        sr=SYM_SEARCH[sym]
        best,bp=None,None
        combos=[(s,r,a,z) for s in sr["sl"] for r in sr["rr"] for a in sr["adx"] for z in sr["zs"]]
        
        for sb,rr,adx,zs in combos:
            done+=1
            r=run_bt(data,sb,rr,adx,zs)
            if r and (best is None or r["score"]>best["score"]):
                best,bp=r,{"sl_buffer":sb,"rr_ratio":rr,"adx_min":adx,"zone_min_strength":zs}
            sys.stdout.write(f"\r  进度: {done}/{total}")
            sys.stdout.flush()
        
        if best:
            best_all[sym]=best
            best_all[sym+"_params"]=bp
            p=bp; s=best
            print(f"\n\n🏆 {sym}: SL={p['sl_buffer']}× RR=1:{p['rr_ratio']} ADX>{p['adx_min']} Z>{p['zone_min_strength']}")
            print(f"   成交{s['trades']}笔 | 胜率{s['wr']:.0f}% | 盈亏比{s['pf']:.1f} | 净利=${s['np']:.0f} | 回撤{s['dd']:.1f}%")
    
    print(f"\n\n{'='*60}")
    print("📊 全品种最优参数汇总")
    print(f"{'='*60}")
    print(f"{'品种':<10} {'SL×ATR':<10} {'RR':<8} {'ADX>':<8} {'区强>':<8} {'成交':<8} {'胜率':<8} {'净利':<10} {'回撤':<8}")
    print(f"{'-'*70}")
    
    for sym in SYM_SEARCH:
        bp=best_all.get(sym+"_params"); s=best_all.get(sym)
        if bp and s:
            print(f"{sym:<10} {bp['sl_buffer']:<10} 1:{bp['rr_ratio']:<6} {bp['adx_min']:<8} {bp['zone_min_strength']:<8} {s['trades']:<8} {s['wr']:<7.1f}% ${s['np']:<7.0f} {s['dd']:<7.1f}%")
    
    # 更新self_evolve.py
    import re
    se_path=os.path.join(BASE,"self_evolve.py")
    with open(se_path,"r",encoding="utf-8") as f: c=f.read()
    np_str="DEFAULT_PARAMS = {\n"
    for sym in SYM_SEARCH:
        bp=best_all.get(sym+"_params")
        if bp:
            np_str+=f'    "{sym}": {{"sl_atr": {bp["sl_buffer"]}, "rr_ratio": {bp["rr_ratio"]}, "min_adx": {bp["adx_min"]}, "min_zone_strength": {bp["zone_min_strength"]}, "risk_percent": 1.0}},\n'
    np_str+="}"
    c=re.sub(r"DEFAULT_PARAMS = \{[^}]+\}",np_str,c,flags=re.DOTALL)
    with open(se_path,"w",encoding="utf-8") as f: f.write(c)
    print(f"\n[OK] self_evolve.py 已更新!")
    print(f"\n总用时: {time.time()-t0:.0f}秒")
