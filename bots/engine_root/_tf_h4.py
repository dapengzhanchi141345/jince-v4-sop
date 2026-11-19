"""H4-only intra-bar replay, unified geometry (self-contained).
event = H4 Donchian20 x1.003 breakout + D1 direction gate; stop orders; pure TP/SL.
long : trig=dc_hi[i-1]*1.003, require c[i-1]<trig and d1_bull
short: trig=dc_lo[i-1]/1.003, require c[i-1]>trig and d1_bear
d1 gate: last COMPLETED D1 bar before H4 bar i closes (d1t+86400<=ts_h4[i]): close>prev => bull, close<prev => bear.
stop fill: BUY when high>=trig / SELL when low<=trig within 4 H4 bars forward incl. trigger bar; else event=0R (unfilled).
after fill: SL=trig-/+SLM*ATR14(Wilder,H4,causal at trigger bar); TP=trig+/-2R, R=|trig-sl|.
BUY: low<=sl SL, high>=tp TP; SELL: high>=sl SL, low<=tp TP; both on same bar -> SL (conservative).
42 H4 bars incl. trigger bar unresolved -> R=(last_close-trig)*side/R, no truncation.
Symmetry self-check: mirror series (h'=-l,l'=-h,c'=-c, bull/bear swapped) must give SELL-side R identical to BUY-side.
"""
import json, os
import numpy as np
import MetaTrader5 as mt5

ROOT = r"E:/GoldstrategyEngine"
SYMS = ["BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD"]
SLMS = [1.5,2.0,3.0]
MAIN_SLM = 2.0
SLA = 1.003
FILL_WIN, RESOLVE_WIN = 4, 42

def atr_wilder(h,l,c,p=14):
    n=len(c); tr=np.empty(n); tr[0]=h[0]-l[0]
    if n>1:
        pc=c[:-1]
        tr[1:]=np.maximum(h[1:]-l[1:], np.maximum(np.abs(h[1:]-pc),np.abs(l[1:]-pc)))
    atr=np.full(n,np.nan)
    if n>p:
        v=tr[1:p+1].mean(); atr[p]=v
        for i in range(p+1,n):
            v=(v*(p-1)+tr[i])/p; atr[i]=v
    return atr

def d1_gate(t_h4,d1):
    t=d1["time"].astype(np.int64); cc=d1["close"]
    n=len(t_h4); bull=np.zeros(n,bool); bear=np.zeros(n,bool)
    idx=np.searchsorted(t, t_h4.astype(np.int64)-86400, side="right")-1
    ok=idx>=1
    bull[ok]=cc[idx[ok]]>cc[idx[ok]-1]; bear[ok]=cc[idx[ok]]<cc[idx[ok]-1]
    return bull,bear

def sim(h,l,c,bull,bear,slm):
    """Returns (events, filled_flags, trigger_bars, expR)."""
    n=len(c)
    dc_hi=np.full(n,np.nan); dc_lo=np.full(n,np.nan)
    for i in range(1,n):
        k=max(0,i-20); dc_hi[i]=h[k:i].max(); dc_lo[i]=l[k:i].min()
    atr=atr_wilder(h,l,c)
    ev=[]; filled=[]; tibs=[]
    i=1
    while i<n-RESOLVE_WIN+1:
        th=None; side=0
        if bull[i] and c[i-1]<dc_hi[i-1]*SLA:
            th=dc_hi[i-1]*SLA; side=1
        elif bear[i] and c[i-1]>dc_lo[i-1]/SLA:
            th=dc_lo[i-1]/SLA; side=-1
        if th is None or np.isnan(th):
            i+=1; continue
        a=atr[i]
        if np.isnan(a):
            i+=1; continue
        R=slm*a
        sl=th-R if side==1 else th+R
        tp=th+2*R if side==1 else th-2*R
        fb=None
        for j in range(i,min(i+FILL_WIN,n)):
            if (side==1 and h[j]>=th) or (side==-1 and l[j]<=th):
                fb=j; break
        if fb is None:
            ev.append(0.0); filled.append(False); tibs.append(i)
            i+=1; continue
        res=None
        for j in range(fb,min(i+RESOLVE_WIN,n)):
            sl_hit=(l[j]<=sl) if side==1 else (h[j]>=sl)
            tp_hit=(h[j]>=tp) if side==1 else (l[j]<=tp)
            if sl_hit or tp_hit:
                res=-1.0 if sl_hit else 1.0
                break
        if res is None:
            res=((c[min(i+RESOLVE_WIN,n)-1]-th)*side)/R
        ev.append(float(res)); filled.append(True); tibs.append(i)
        i+=RESOLVE_WIN
    ev=np.array(ev,dtype=np.float64)
    return ev, np.array(filled), np.array(tibs,dtype=np.int64), (float(ev.mean()) if len(ev) else 0.0)

def main():
    if not mt5.terminal_info():
        mt5.initialize()
    res_all={}   # slm -> sym -> (ev,filled,tibs,expR)
    times={}
    for sym in SYMS:
        d1=mt5.copy_rates_from_pos(sym,mt5.TIMEFRAME_D1,0,3000)
        h4=mt5.copy_rates_from_pos(sym,mt5.TIMEFRAME_H4,0,2600)
        t=h4["time"].astype(np.int64)
        h=h4["high"].astype(np.float64); l=h4["low"].astype(np.float64); c=h4["close"].astype(np.float64)
        bull,bear=d1_gate(t,d1)
        times[sym]=t
        for slm in SLMS:
            res_all.setdefault(slm,{})[sym]=sim(h,l,c,bull,bear,slm)
    # main SLM 2.0 stats
    ev_m=np.concatenate([res_all[MAIN_SLM][s][0] for s in SYMS])
    fl_m=np.concatenate([res_all[MAIN_SLM][s][1] for s in SYMS])
    n_ev=len(ev_m); fills=int(fl_m.sum())
    expR=float(ev_m.mean()) if n_ev else 0.0
    wr=float((ev_m[fl_m]>0).mean()) if fills else 0.0
    per_sym={s:(float(res_all[MAIN_SLM][s][0].mean()) if len(res_all[MAIN_SLM][s][0]) else 0.0) for s in SYMS}
    grid={str(slm):float(np.concatenate([res_all[slm][s2][0] for s2 in SYMS]).mean()) for slm in SLMS}
    # walk-forward: equal-time 3 segments; attribute each event by its trigger bar
    wf=[0.0,0.0,0.0]; wfn=[0,0,0]
    for s in SYMS:
        n=len(times[s]); L=max(1,n//3)
        ev,fl,ti,_=res_all[MAIN_SLM][s]
        for k,ii in enumerate(ti):
            seg=min(int(ii//L),2)
            wf[seg]+=float(ev[k]); wfn[seg]+=1
    wf3={f"seg{k+1}":(wf[k]/wfn[k] if wfn[k] else 0.0) for k in range(3)}
    # symmetry self-check: mirror h'=-l,l'=-h,c'=-c, bull/bear swapped, same slm
    s0=SYMS[0]
    d1=mt5.copy_rates_from_pos(s0,mt5.TIMEFRAME_D1,0,3000)
    h4=mt5.copy_rates_from_pos(s0,mt5.TIMEFRAME_H4,0,2600)
    h=h4["high"].astype(np.float64); l=h4["low"].astype(np.float64); c=h4["close"].astype(np.float64)
    bull,bear=d1_gate(h4["time"].astype(np.int64),d1)
    ev_b,_,_,_=sim(h,l,c,bull,bear,MAIN_SLM)
    ev_s,_,_,_=sim(-l,-h,-c,bear,bull,MAIN_SLM)
    m=min(len(ev_b),len(ev_s))
    sym_pass=bool(m>0 and np.array_equal(ev_b[:m],ev_s[:m])) and (np.max(np.abs(ev_b[:m]-ev_s[:m]))<=1e-9)
    out={"tf":"H4","事件n":n_ev,"成交n":fills,"exp_R":round(expR,6),"wr":round(wr,4),
         "品种稳健":{k:round(v,6) for k,v in per_sym.items()},
         "walk_forward_3seg":{k:round(v,6) for k,v in wf3.items()},
         "对称自检pass":sym_pass,"SLM网格":{k:round(v,6) for k,v in grid.items()}}
    os.makedirs(os.path.join(ROOT,"data"),exist_ok=True)
    json.dump(out,open(os.path.join(ROOT,"data","intra_tf_h4.json"),"w"),indent=1,ensure_ascii=False)
    print(json.dumps(out,ensure_ascii=False))

if __name__=="__main__":
    main()
