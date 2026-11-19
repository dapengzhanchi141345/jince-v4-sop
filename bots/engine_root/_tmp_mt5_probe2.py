import MetaTrader5 as mt5
from datetime import datetime, timedelta
mt5.initialize()
now=datetime.now()
for days in [14,21,30,45,60,90]:
    dl=mt5.history_deals_get(now-timedelta(days=days), now+timedelta(hours=6))
    outs=[d for d in dl if d.entry==1] if dl else []
    if outs:
        w=[d.profit for d in outs if d.profit>0]; l=[d.profit for d in outs if d.profit<=0]
        gp=sum(w); gl=abs(sum(l))
        print(f"WIN{days}D n={len(outs):3d} WR={len(w)/len(outs)*100:6.2f}% PF={(gp/gl if gl else 99):.4f} net={gp-gl:+.2f}")
    else:
        print(f"WIN{days}D n=0")
# per symbol 60d
dl=mt5.history_deals_get(now-timedelta(days=60), now+timedelta(hours=6))
agg={}
for d in (dl or []):
    if d.entry==1:
        a=agg.setdefault(d.symbol,[0,0,0.0,0.0])
        a[0]+=1
        if d.profit>0: a[1]+=1; a[2]+=d.profit
        else: a[3]+=abs(d.profit)
print("--- 60D per symbol ---")
for k,v in sorted(agg.items()):
    print(f"{k:8s} n={v[0]:3d} WR={v[1]/v[0]*100:6.2f}% PF={(v[2]/v[3] if v[3] else 99):.4f} net={v[2]-v[3]:+.2f}")
mt5.shutdown()
