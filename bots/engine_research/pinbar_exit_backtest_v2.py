# -*- coding: utf-8 -*-
"""
PINBAR_EXIT 出场策略横向回测: baseline(固定2R) vs v1(纯影线) vs v2(三确认) vs v2.1(三确认+放量+新鲜度)
统一入场(通道突破), 仅变出场逻辑, 公平对比。数据: data/*_H1.csv (含 tick_volume)
"""
import csv, glob, os, sys

DATA = "E:/GoldstrategyEngine/data"
SYMS = ["XAUUSD","BTCUSD","EURUSD","GBPUSD","USDJPY","NAS100","US30","XAGUSD"]

def load(sym):
    rows=[]
    with open(f"{DATA}/{sym}_H1.csv", encoding="utf-8", errors="replace") as f:
        for d in csv.DictReader(f):
            try:
                r={k:float(v) for k,v in d.items() if k!="time"}
                r["time"]=d.get("time","")
                rows.append(r)
            except: pass
    return rows

def backtest(sym, mode):
    rows = load(sym)
    n = len(rows)
    if n < 200: return None
    # 预计算近20根通道 (upper/lower)
    trades=[]
    i=20
    pos=None  # (side, entry, init_dist, ext)  side=1多/-1空
    while i < n-1:
        hi20 = max(rows[k]["high"] for k in range(i-20,i))
        lo20 = min(rows[k]["low"]  for k in range(i-20,i))
        c = rows[i]["close"]; o=rows[i]["open"]; h=rows[i]["high"]; l=rows[i]["low"]
        ch = hi20-lo20
        if ch<=0: i+=1; continue
        if pos is None:
            if c > hi20:   # 突破上沿开多
                pos=(1, c, ch, c)
            elif c < lo20: # 突破下沿开空
                pos=(-1, c, ch, c)
        else:
            side,entry,dist,ext = pos
            # 维护持仓极值
            ext = max(ext,c) if side==1 else min(ext,c)
            pos=(side,entry,dist,ext)
            cur = c
            r_mult = (cur-entry)*side/dist
            # ---- 止损/止盈(baseline) ----
            sl = entry-dist if side==1 else entry+dist
            tp = entry+2*dist if side==1 else entry-2*dist
            exit_px=None; exit_tag=None
            if side==1 and l<=sl: exit_px=sl; exit_tag="SL"
            elif side==-1 and h>=sl: exit_px=sl; exit_tag="SL"
            elif side==1 and h>=tp: exit_px=tp; exit_tag="TP2R"
            elif side==-1 and l<=tp: exit_px=tp; exit_tag="TP2R"
            # ---- PINBAR 出场(v1/v2/v2.1) ----
            if mode!="baseline" and r_mult>=0.5 and i>=20:
                # 上一根已收线棒 = 当前 i (回测里当判定棒); 下一根 i+1 = 确认棒
                _hi=rows[i]["high"]; _lo=rows[i]["low"]; _o=rows[i]["open"]; _c=rows[i]["close"]
                _rng=_hi-_lo
                if _rng>0:
                    _up=_hi-max(_o,_c); _dn=min(_o,_c)-_lo
                    # 流动性池: 近50根(排除最近6根) swing极值 + 整数关口
                    _kmax=min(52, i)
                    _lo_i=2+5+1  # MIN_AGE=5
                    _sw_h=max(rows[k]["high"] for k in range(_lo_i,_kmax)) if _kmax>_lo_i else max(rows[k]["high"] for k in range(2,_kmax))
                    _sw_l=min(rows[k]["low"]  for k in range(_lo_i,_kmax)) if _kmax>_lo_i else min(rows[k]["low"]  for k in range(2,_kmax))
                    def _rl(px):
                        if px>=1000: return round(px/50)*50
                        if px>=100: return round(px/10)*10
                        if px>=10: return round(px/1)*1
                        if px>=1: return round(px/0.1)*0.1
                        return round(px/0.01)*0.01
                    _pool=False
                    if side==1 and _hi>=ext*0.999:
                        _rh=_rl(_hi)
                        if _hi>=_sw_h-_rng*0.15 or (_rh is not None and abs(_hi-_rh)<=_rng*0.25): _pool=True
                    elif side==-1 and _lo<=ext/0.999:
                        _rlv=_rl(_lo)
                        if _lo<=_sw_l+_rng*0.15 or (_rlv is not None and abs(_lo-_rlv)<=_rng*0.25): _pool=True
                    if _pool:
                        _vol_ok=True
                        if mode=="v2.1":
                            _tkv=rows[i]["tick_volume"]
                            _vavg=sum(rows[k]["tick_volume"] for k in range(i-20,i))/20.0
                            if _vavg>0 and _tkv<_vavg*1.35: _vol_ok=False
                        if _vol_ok:
                            _sweep=False
                            if side==1 and (_up/_rng>=0.55) and (_c<_hi): _sweep=True
                            elif side==-1 and (_dn/_rng>=0.55) and (_c>_lo): _sweep=True
                            if _sweep:
                                _conf=True
                                if i+1<n:
                                    _no=rows[i+1]["open"]; _nc=rows[i+1]["close"]
                                    if side==1: _conf=(_nc<_no) and (_no-_nc)>=_rng*0.3
                                    else: _conf=(_nc>_no) and (_nc-_no)>=_rng*0.3
                                if _conf:
                                    exit_px = _c if mode=="v1" else rows[i+1]["close"]
                                    exit_tag="PINBAR"
            if exit_px is not None:
                pnl=(exit_px-entry)*side/dist
                trades.append((pnl, exit_tag))
                pos=None
        i+=1
    if not trades: return None
    pnls=[t[0] for t in trades]
    n_=len(pnls); avgR=sum(pnls)/n_
    win=sum(1 for x in pnls if x>0); wr=win/n_
    g=sum(x for x in pnls if x>0); l=sum(-x for x in pnls if x<0)
    pf=(g/l) if l>0 else 99
    return dict(n=n_, avgR=avgR, wr=wr, pf=pf)

if __name__=="__main__":
    modes=["baseline","v1","v2","v2.1"]
    print("品种      样本  baseR   v1R    v2R   v2.1R | v2.1 vs base ΔR  | WR(v2.1)")
    print("-"*78)
    sums={m:[] for m in modes}
    for sym in SYMS:
        res={m:backtest(sym,m) for m in modes}
        if any(r is None for r in res.values()):
            print(f"{sym:8} 数据不足"); continue
        for m in modes: sums[m].append(res[m]["avgR"])
        b=res["baseline"]["avgR"]; v=res["v2.1"]["avgR"]
        print(f"{sym:8} {res['baseline']['n']:5} {b:6.3f} {res['v1']['avgR']:6.3f} {res['v2']['avgR']:6.3f} {v:6.3f} | Δ{v-b:+6.3f} | {res['v2.1']['wr']*100:4.0f}%")
    print("-"*78)
    print("8品种 avgR均值:",
          "  ".join(f"{m}={sum(sums[m])/len(sums[m]):.3f}" for m in modes))
    b=sum(sums['baseline'])/8; v=sum(sums['v2.1'])/8
    print(f"v2.1 vs baseline 平均ΔavgR = {v-b:+.3f}  (正=更优)")
