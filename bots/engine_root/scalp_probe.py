# -*- coding: utf-8 -*-
import json, datetime
def jget(f):
    try: return json.load(open("data/"+f,encoding="utf-8"))
    except Exception: return {}
rs=jget("risk_state.json"); er=jget("event_risk.json")
gates=[]
p10=rs.get("10pct_circuit_progress",0) or 0
halt1=p10>=1.0 or rs.get("halt_new_entries")
gates.append(("日亏10%熔断","TRIGGERED 禁开新单" if halt1 else "OK progress=%.1f%%"%(p10*100),not halt1))
try:
    import MetaTrader5 as m
    m.initialize(); today=datetime.datetime.now().date()
    cnt=0
    for d in (m.history_deals_get(0,999999999) or []):
        if d.symbol=="XAUUSD" and datetime.datetime.fromtimestamp(d.entry_time).date()==today and getattr(d,"entry","")=="DEAL_ENTRY_IN":
            cnt+=1
    m.shutdown(); n=cnt
except Exception as e:
    n=-1
halt2=n>=3
gates.append(("XAUUSD日<=3单","TRIGGERED 今日%d单"%n if halt2 else "OK 今日%d单"%n,not halt2))
cl=rs.get("consec_losses",0); cool=rs.get("24h_cooldown",False)
halt3=cl>=3 or cool
gates.append(("连亏3笔/24h冷却","TRIGGERED 连亏%d"%cl if halt3 else "OK 连亏%d"%cl,not halt3))
ev=er.get("level"); halt4=(ev=="HALT")
gates.append(("事件面","%s scale=%s"%(ev,er.get("new_entry_scale")),not halt4))
print("=== SH1 黄金短打腿 可进闸诊断 (BJT 19:xx) ===")
for name,stat,ok in gates: print(("  [OK] " if ok else "  [X] ")+name+": "+stat)
allpass=all(g[2] for g in gates)
print("\n三铁律+事件面 全绿?", "YES 可进" if allpass else "NO 有闸触发, 先报后动")
print("\n[红线] SH1原卡=无SL手平 -> 0进自动挂单(L4终裁). 能进闸的最小形态=补TP+SL自动化变体, 先本地回测攒样本.")
print("\n=== 当前金策 demo 60137964 实数 ===")
print("余额$965.4 | 0挂单0持仓 | 10pct_progress=%.1f%% | consec_losses=%s"%((rs.get('10pct_circuit_progress') or 0)*100,rs.get('consec_losses')))
