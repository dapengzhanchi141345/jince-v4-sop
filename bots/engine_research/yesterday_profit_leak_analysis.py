# -*- coding: utf-8 -*-
"""
深度复盘 2026-11-10 真实单子 · 利润泄漏分析 (v3)
方法: 按 ticket 聚合当日全部事件 -> 终端出场行自带 entry/sl/exit 价 => 直接算落袋R;
      浮盈峰值(MFE)代理 = max(价格反推MFE[若有文件], 日志SL_TRAIL浮盈峰值, 落袋R);
      泄漏 = MFE代理 - 落袋R。
回答: 昨天大量单子是否"有大浮盈但没吃到"。
"""
import csv, os, datetime as dt, re
from collections import Counter, defaultdict

ROOT="E:/GoldstrategyEngine"; CSV=os.path.join(ROOT,"data","live24_trades.csv")
DATA=os.path.join(ROOT,"data"); DAY="2026-11-10"

def pnum(x):
    try: return float(x)
    except: return None
def pts(s):
    try: return dt.datetime.strptime(s.strip(),"%Y-%m-%d %H:%M:%S")
    except: return None

_price_cache={}
def load_price(sym):
    if sym in _price_cache: return _price_cache[sym]
    for fn in (f"{sym}_M15.csv",f"{sym}_H1.csv"):
        p=os.path.join(DATA,fn)
        if os.path.exists(p):
            bars=[]
            with open(p,encoding="utf-8") as f:
                r=csv.reader(f); next(r,None)
                for row in r:
                    if len(row)<5: continue
                    t=pts(row[0])
                    if t is None: continue
                    try: o,h,l,c=float(row[1]),float(row[2]),float(row[3]),float(row[4])
                    except: continue
                    bars.append((t,h,l,c))
            _price_cache[sym]=bars; return bars
    _price_cache[sym]=None; return None

def price_mfe(sym,entry,sl,direction,entry_ts,exit_ts):
    bars=load_price(sym)
    if not bars or sl is None or entry is None: return None
    sld=abs(entry-sl)
    if sld<=0: return None
    mfe=-1e9; seen=False
    for (t,h,l,c) in bars:
        if t<entry_ts: continue
        if t>exit_ts: break
        seen=True
        mfe=max(mfe,(h-entry)/sld) if direction>0 else max(mfe,(entry-l)/sld)
    return None if not seen else (0.0 if mfe<-1e8 else mfe)

TERMINAL=("MAXHOLD硬平","B0_EXIT","LOSECUT斩亏","IDX_BLEED斩亏","PINBAR_TOP","PINBAR_BOTTOM","MAGIC_DUP_EXIT","CLOSE")
def hold_h(note):
    if not note: return 18.0
    m=re.search(r"持仓\s*(\d+\.?\d*)\s*(h|小时|min|分钟)",note)
    if not m: return 18.0
    v=float(m.group(1)); return v/60.0 if m.group(2) in ("min","分钟") else v
def float_r(note):
    if not note: return None
    m=re.search(r"浮(盈|亏)([-+]?\d+\.?\d*)R",note)
    if m:
        v=float(m.group(2)); return v if m.group(1)=="盈" else -v
    return None

# 聚合事件
by_ticket=defaultdict(list)
with open(CSV,encoding="utf-8") as f:
    r=csv.reader(f); next(r,None)
    for row in r:
        if len(row)<12: continue
        if not row[0].startswith(DAY): continue
        try: tki=int(row[4])
        except: tki=0
        if tki<=0: continue
        by_ticket[tki].append(row)

recs=[]
for tki,evs in by_ticket.items():
    term=None
    for row in evs:
        if row[1] in TERMINAL:
            term=row; break
    if term is None: continue
    try: direction=int(term[3])
    except: continue
    if direction==0: continue
    entry=pnum(term[5]); sl=pnum(term[6]); exit_p=pnum(term[8]) if len(term)>8 else None
    if entry is None or sl is None: continue
    sld=abs(entry-sl)
    if sld<=0: continue
    note=term[11] if len(term)>11 else ""
    exit_ts=pts(term[0])
    realized=None
    if exit_p is not None:
        realized=((exit_p-entry)/sld) if direction>0 else ((entry-exit_p)/sld)
    # MFE 代理
    trail_floats=[float_r(e[11]) for e in evs if e[1]=="SL_TRAIL"]
    trail_floats=[x for x in trail_floats if x is not None]
    pmfe=price_mfe(term[2],entry,sl,direction,(exit_ts-dt.timedelta(hours=hold_h(note))) if exit_ts else exit_ts, exit_ts)
    cands=[realized] if realized is not None else []
    cands+=trail_floats
    if pmfe is not None: cands.append(pmfe)
    mfe=max(cands) if cands else None
    recs.append({"ticket":tki,"sym":term[2],"dir":direction,"exit_type":term[1],
                 "realized":realized,"mfe":mfe,
                 "has_price":pmfe is not None})

print("="*84)
print("  2026-11-10 真实单子复盘 · 利润泄漏分析 (按 ticket 聚合全部事件)")
print("="*84)
print(f"  当日聚合出场单数: {len(recs)}")
etc=Counter(x["exit_type"] for x in recs)
print("  【出场类型分布】")
for k,v in etc.most_common(): print(f"    {k:14s} {v:4d} 笔")

# 落袋R 可用(终端带出场价)
rv=[x for x in recs if x["realized"] is not None]
print(f"\n  可算落袋R单数: {len(rv)}")
pos=sum(1 for x in rv if x["realized"]>0); neg=sum(1 for x in rv if x["realized"]<=0)
print(f"    落袋为正(吃到利润): {pos} 笔 ({pos/len(rv)*100:.1f}%)")
print(f"    落袋≤0(未吃到/转亏): {neg} 笔 ({neg/len(rv)*100:.1f}%)")
print(f"    落袋R均值: {sum(x['realized'] for x in rv)/len(rv):.3f}   合计: {sum(x['realized'] for x in rv):.2f} R")

# MFE 代理可用
mv=[x for x in recs if x["mfe"] is not None]
print(f"\n  可估浮盈峰值(MFE代理)单数: {len(mv)}")
print(f"    MFE代理均值: {sum(x['mfe'] for x in mv)/len(mv):.3f} R   峰值合计: {sum(x['mfe'] for x in mv):.2f} R")

# 泄漏 = MFE代理 - 落袋
both=[x for x in recs if x["mfe"] is not None and x["realized"] is not None]
if both:
    total_mfe=sum(x["mfe"] for x in both); total_real=sum(x["realized"] for x in both)
    print(f"\n  【核心: 大浮盈是否吃到】 (MFE代理 & 落袋双有, n={len(both)})")
    print(f"    浮盈峰值合计: {total_mfe:.2f} R")
    print(f"    实际落袋合计: {total_real:.2f} R")
    print(f"    整体捕获率: {total_real/total_mfe*100:.1f} %")
    leak=[x for x in both if x["mfe"]>=2.0 and x["realized"]<x["mfe"]-1.0]
    tl=sum(x["mfe"]-x["realized"] for x in leak)
    print(f"    '大浮盈没吃到'问题单(MFE≥2R且回吐>1R): {len(leak)} 笔, 泄漏合计 {tl:.2f} R")
    wipe=[x for x in both if x["mfe"]>=1.5 and x["realized"]<0]
    print(f"    '浮盈转亏'单(MFE≥1.5R却落袋<0): {len(wipe)} 笔, 转亏合计 {sum(x['realized'] for x in wipe):.2f} R")

# 分出场类型
print("\n  【分出场类型 · 落袋R 与 MFE代理】")
bt=defaultdict(list)
for x in recs: bt[x["exit_type"]].append(x)
for t,lst in sorted(bt.items(),key=lambda kv:-len(kv[1])):
    rr=[y["realized"] for y in lst if y["realized"] is not None]
    mm=[y["mfe"] for y in lst if y["mfe"] is not None]
    rmean=sum(rr)/len(rr) if rr else float('nan')
    mmean=sum(mm)/len(mm) if mm else float('nan')
    print(f"    {t:14s} n={len(lst):3d}  落袋均值={rmean:.3f}  落袋合计={sum(rr):7.2f}  | MFE代理均值={mmean:.3f}" if rr or mm else f"    {t:14s} n={len(lst)}")

# Top 泄漏(用 MFE代理-落袋)
print("\n  【Top 20 泄漏单(按 MFE代理-落袋 降序)】")
both_sorted=sorted(both,key=lambda x:(x["mfe"]-x["realized"]),reverse=True)[:20]
print(f"    {'ticket':>12} {'品种':9} {'方向':4} {'MFE代':>6} {'落袋':>7} {'泄漏':>7} 出场")
for x in both_sorted:
    lr=x["mfe"]-x["realized"]
    print(f"    {x['ticket']:>12} {x['sym']:9} {'多' if x['dir']>0 else '空':4} {x['mfe']:>6.2f} {x['realized']:>7.2f} {lr:>7.2f} {x['exit_type']}")

# 全明细(前60)
print("\n  【全部明细(按落袋R升序, 前60)】")
rv_sorted=sorted(rv,key=lambda x:x["realized"])[:60]
print(f"    {'ticket':>12} {'品种':9} {'方向':4} {'MFE代':>6} {'落袋':>7} 出场")
for x in rv_sorted:
    m=x["mfe"] if x["mfe"] is not None else float('nan')
    print(f"    {x['ticket']:>12} {x['sym']:9} {'多' if x['dir']>0 else '空':4} {m:>6.2f} {x['realized']:>7.2f} {x['exit_type']}")

out=os.path.join(ROOT,"research","yesterday_leak_trades.csv")
with open(out,"w",newline="",encoding="utf-8") as f:
    w=csv.writer(f); w.writerow(["ticket","symbol","dir","exit_type","realized_R","mfe_proxy_R","leak_R","has_price"])
    for x in sorted(recs,key=lambda v:(v["realized"] or 0)):
        w.writerow([x["ticket"],x["sym"],x["dir"],x["exit_type"],
                    round(x["realized"],3) if x["realized"] is not None else "",
                    round(x["mfe"],3) if x["mfe"] is not None else "",
                    round(x["mfe"]-x["realized"],3) if (x["mfe"] is not None and x["realized"] is not None) else "",
                    x["has_price"]])
print(f"\n  明细已存: {out}")
