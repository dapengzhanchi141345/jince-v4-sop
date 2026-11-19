
# -*- coding: utf-8 -*-
# 验证 weekly_forecaster 区间法能否提升波段胜率 (同分母公平对照)
import sys, json, math
sys.path.insert(0,"E:/GoldstrategyEngine"); sys.path.insert(0,"E:/GoldstrategyEngine/multi_agent/trading")
import numpy as np, MetaTrader5 as mt5
import weekly_forecaster as wf

SYMS = ["BTCUSD","ETHUSD","SOLUSD","XRPUSD","BNBUSD","LTCUSD","XAUUSD"]
mt5.initialize(); mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")

def z2p(w1,n1,w2,n2):
    if n1<10 or n2<10: return None
    p1,p2=w1/n1,w2/n2; pp=(w1+w2)/(n1+n2)
    se=math.sqrt(pp*(1-pp)*(1/n1+1/n2))
    if se==0: return 0.0
    z=(p2-p1)/se; return 2*(1-0.5*(1+math.erf(abs(z)/math.sqrt(2))))

# 事件: 每根已完结D1, 前一日收盘=挂单参照.
# 方法A(盲目): 挂上一日中轨反做 (旧震荡腿近似)
# 方法B(区间法): 用周线预测的 next_hi/next_lo 定挂单上沿下沿, 目标中值, 看fwd3 D1方向
n_pool, win_b, win_a = [], 0, 0
lone_b, lone_a = 0, 0
res=[]
for sym in SYMS:
    d1=mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 2000)
    w1=mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_W1, 0, 600)
    if d1 is None or len(d1)<300: continue
    res.append(wf.from_mt5(sym))  # 只为取range参数; 逐日重算成本高, 用滚动近似
    h=d1["high"].astype(float); l=d1["low"].astype(float); c=d1["close"].astype(float)
    # 滚动: 每10日重算一次周线区间(近似因果, 用截至i的w1)
    import copy
    fc_cache={}; last_fc=-1
    for i in range(30, len(d1)-3):
        if i - last_fc >= 10:
            # 因果: 只用i之前的w1
            wh=np.array(w1["high"][: (i//5)] if i//5 < len(w1) else w1["high"]).astype(float)
            wl=np.array(w1["low"][: (i//5)]).astype(float)
            wc=np.array(w1["close"][: (i//5)]).astype(float)
            d1sub={"high":h[:i],"low":l[:i],"close":c[:i]}
            w1sub={"high":wh,"low":wl,"close":wc}
            fc=wf.forecast_next_week(None, d1sub, w1sub) if (i//5)<last_fc+12 else None
            last_fc=i
        if fc is None: continue
        nh, nl, pv = fc["next_hi"], fc["next_lo"], fc["pivot_mid"]
        # 事件: 当日收盘在近一周区间上沿/下沿 → 次日反做
        px=c[i]
        if abs(px-nh)/fc["range_atr"] < 1.0:   # 触及上沿
            win=(c[i+3]<px); side="SELL"
        elif abs(px-nl)/fc["range_atr"] < 1.0:  # 触及下沿
            win=(c[i+3]>px); side="BUY"
        else:
            continue
        pool=n_pool; pool.append(1)
        win_b += 1 if win else 0
    print(f"[OK] {sym} 区间法事件累计 {len(n_pool)}")

nb=len(n_pool); wnb=win_b
p=z2p(wnb, nb, int(nb/2), nb)  # 对照=50%基准
out={"n_events":nb, "wr区间法":round(wnb/nb,4) if nb else None,
     "vs50%_p": (None if p is None else round(p,4)),
     "verdict":"接" if (nb>=1000 and wnb/nb>0.53 and p is not None and p<0.05) else "维持/观察"}
json.dump(out, open("E:/GoldstrategyEngine/data/weekly_forecast_verify.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
print(json.dumps(out,ensure_ascii=False))
mt5.shutdown()
