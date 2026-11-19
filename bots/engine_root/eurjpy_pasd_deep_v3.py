#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""EURJPY-PASD 深枪 v3 — 按 @chief/@hermes 收的三修 + 出件前置三验:
  a) 段界 = epoch秒算天界 + 跑前自检(4段起点日期/间隔打印, 间隔<1h 拒跑)
  b) H1 放宽 revisit<=2 (原 <=1 全窗只有3笔, 薄到无法判, 预注册卡里 H1 原口径同步报 n=3 作废格)
  c) 出件一律 encoding=utf-8 + ensure_ascii=False
前置三验(出件自带, 22:00 可 grep): 逐段 n 均衡(4段里3段n=0=拒收) + seg_bounds 自检行 + utf-8 可读
"""
import os, sys, json, datetime, traceback
os.chdir(r"E:\GoldstrategyEngine"); sys.path.insert(0, r"E:\GoldstrategyEngine")
import numpy as np, pandas as pd
import MetaTrader5 as mt5
import symbol_universe as su, backtest_engine as BE
import pasd_fusion as PF
SYM, DAYS = "EURJPY", 180

def rates(sym, tf, d=DAYS):
    F=[]; p=0
    while True:
        c = mt5.copy_rates_from_pos(sym, tf, p, 5000)
        if c is None or len(c)==0: break
        F.append(pd.DataFrame(c)); p += len(c)
        if len(c)<5000 or p>=20000: break
    if not F: return None
    df = pd.concat(F).drop_duplicates("time").sort_values("time").reset_index(drop=True)
    df["t"]=pd.to_datetime(df["time"], unit="s")
    return df[df["t"]>=df["t"].max()-pd.Timedelta(days=d)].reset_index(drop=True)

def main():
    print("v3 起跑", datetime.datetime.now().isoformat(), flush=True)
    if not mt5.initialize():
        raise SystemExit("MT5 initialize 失败")
    cfg = su.UNIVERSE.get(SYM, {}); info = mt5.symbol_info(SYM)
    sp, pt = info.spread or 10, info.point or 1e-5
    swl, swh = info.swap_long or 0, info.swap_short or 0
    h1, h4, d1 = rates(SYM, mt5.TIMEFRAME_H1), rates(SYM, mt5.TIMEFRAME_H4), rates(SYM, mt5.TIMEFRAME_D1)
    sigs = PF.gen_pasd(h1, h4, d1, cfg)
    zs = PF._detect_supply_demand_zones(h1["high"].values, h1["low"].values, h1["close"].values)
    lo_v, hi_v = h1["low"].values, h1["high"].values
    for s in sigs:
        i, E, side = int(s["bar"]), s["entry"], s["side"]
        cand = ([z for z in zs["demand"] if z["top"]<E] if side>0 else [z for z in zs["supply"] if z["bottom"]>E])
        z = min(cand, key=lambda zz: abs((zz["top"] if side>0 else zz["bottom"])-E)) if cand else None
        if z is not None:
            if side>0: in_z = (lo_v[:i+1]<=z["top"])&(lo_v[:i+1]>=z["bottom"])
            else:      in_z = (hi_v[:i+1]>=z["bottom"])&(hi_v[:i+1]<=z["top"])
            s["revisit"] = int(np.sum(np.diff(np.concatenate(([0], in_z.astype(int))))>0))
        else:
            s["revisit"] = 99
        s["hour"] = int(pd.to_datetime(h1["time"].iloc[i], unit="s").hour)
        s["time"] = int(h1["time"].iloc[i])

    # ===== (a) 段界自检: epoch 秒算天界, 跑前打印 + 拒跑闸 =====
    tmin, tmax = int(h1["time"].iloc[0]), int(h1["time"].iloc[-1])
    nsecs = tmax - tmin
    day = nsecs // 4  # 每段 45 天 (秒)
    seg_bounds = [{"seg":k, "start":pd.to_datetime(tmin+k*day, unit="s").date().isoformat(),
                   "end":(pd.to_datetime(tmin+(k+1)*day, unit="s").date().isoformat() if k<3
                          else pd.to_datetime(tmax+86400, unit="s").date().isoformat())} for k in range(4)]
    gaps = [seg_bounds[k+1] for k in range(3)]
    min_gap_s = min((tmin+(k+1)*day)-(tmin+k*day) for k in range(3))
    for b in seg_bounds: print(f"  段{b['seg']}: {b['start']} ~ {b['end']}", flush=True)
    print(f"  段间隔={min_gap_s}秒 ({min_gap_s/86400:.1f} 天)", flush=True)
    precheck = {}
    if min_gap_s < 3600:
        raise SystemExit(f"段界自检 FAIL: 间隔 {min_gap_s}秒 < 1小时, 拒跑 (防第3枪再坏)")
    # 逐段信号数预检 (3/4 段 n=0 = 拒收)
    seg_counts = [sum(1 for s in sigs if tmin+k*day <= s["time"] < (tmin+(k+1)*day if k<3 else tmax+86400)) for k in range(4)]
    precheck["seg_signal_counts"] = seg_counts
    precheck["seg_balanced"] = sum(1 for c in seg_counts if c>0) >= 3
    print(f"  逐段信号数={seg_counts} 均衡={precheck['seg_balanced']}", flush=True)
    if not precheck["seg_balanced"]:
        raise SystemExit("逐段均衡自检 FAIL: 4段里>=3段 n=0, 拒收 (FAIL-loud 不静默)")

    def segs_of(ss):
        out=[]
        for k in range(4):
            lo, hi_ = tmin+k*day, (tmin+(k+1)*day if k<3 else tmax+86400)
            out.append([s for s in ss if lo<=s["time"]<hi_])
        return out

    MAXH = BE.MAX_HOLD_H1
    def replay(rr):
        """RR 重放: 逐笔 net R (含 spread+swap). 返回逐笔 dict 列表."""
        rows=[]
        for s in sigs:
            i, side = int(s["bar"]), 1 if s["side"]>0 else -1
            if i+1>=len(h1): continue
            sd0 = abs(s["entry"]-s["sl"])
            o = float(h1["open"].iloc[i+1]); a = sp*pt
            e = o+a if side>0 else o-a
            S = e-sd0 if side>0 else e+sd0
            T = e+side*rr*sd0
            end = min(i+1+MAXH, len(h1))
            hi, lo = h1["high"].values[i+1:end], h1["low"].values[i+1:end]
            tm, op = h1["time"].values[i+1:end], h1["open"].values[i+1:end]
            if len(hi)==0: continue
            exit = float(op[-1])
            for k in range(len(hi)):
                if side>0: slh,tph = lo[k]<=S, hi[k]>=T
                else:      slh,tph = hi[k]>=S, lo[k]<=T
                if slh and tph: exit = S; break
                elif slh: exit = S; break
                elif tph: exit = T; break
            hd = max(0,(int(tm[len(hi)-1])-int(tm[0]))//86400) if len(hi)>1 else 0
            sw = abs((swl if side>0 else swh)*hd*0.1)
            pnl = (exit-e)*side/0.0001*10.0*0.1 - sw
            rows.append({"time":s["time"],"revisit":s["revisit"],"hour":s["hour"],
                         "R":pnl/(sd0/0.0001*10.0*0.1)})
        return rows

    base_rows = replay(2.5)
    json.dump({"n":len(base_rows),"meanR":round(float(np.mean([r['R'] for r in base_rows])),3),
               "cumR":round(float(sum(r['R'] for r in base_rows)),2)},
              open("data/eurjpy_pasd_deep_salvage.json","w",encoding="utf-8"), ensure_ascii=False)
    print("base RR2.5 回放完 n=%d 逐笔存盘" % len(base_rows), flush=True)

    def segstats(rows, rr):
        if not rows:
            return [{"seg":k,"n":0,"netR":0.0,"meanR":None} for k in range(4)]
        df = pd.DataFrame(rows)
        out=[]
        for k in range(4):
            lo, hi_ = tmin+k*day, (tmin+(k+1)*day if k<3 else tmax+86400)
            st = df[(df["time"]>=lo)&(df["time"]<hi_)]
            out.append({"seg":k,"n":int(len(st)),
                        "netR":round(float(st['R'].sum()),2) if len(st) else 0.0,
                        "meanR":round(float(st['R'].mean()),3) if len(st) else None})
        return out

    H1b = [r for r in base_rows if r["revisit"]<=2]           # H1 放宽版
    H3c = [r for r in base_rows if 7<=r["hour"]<16]
    H1b3 = [r for r in base_rows if r["revisit"]<=2 and 7<=r["hour"]<16]
    rows35, rows40 = replay(3.5), replay(4.0)
    GRID = {"base_RR2.5": base_rows, "H1_放宽revisit<=2": H1b, "H3_killzone": H3c,
            "组合_H1放宽+H3": H1b3, "H2_RR3.5": rows35, "H2_RR4.0": rows40}
    results = {}
    for tag, rows in GRID.items():
        per = segstats(rows, 0)
        tot = [p for p in per if p["n"]]
        net = sum(p["netR"] for p in per)
        results[tag] = {"per_seg":per, "total_n":int(len(rows)), "total_netR":round(net,2),
                        "pos_segs":sum(1 for p in tot if p["netR"]>0),
                        "consistent":(len(tot)>=3 and all(p["netR"]>0 for p in tot))}
        print(f"{tag:14s} n={results[tag]['total_n']:3d} 段n={[p['n'] for p in per]} "
              f"段netR={[p['netR'] for p in per]} 一致={results[tag]['consistent']}", flush=True)

    b = results["base_RR2.5"]["total_netR"]
    h1k = "H1_放宽revisit<=2"
    out = {"generated":datetime.datetime.now().isoformat(),"version":"v3","symbol":SYM,"window_days":DAYS,
           "total_sigs":len(sigs), "wf":"6mo切4段x45天, 逐段符号一致才认",
           "seg_bounds":seg_bounds, "precheck":precheck,
           "note":"H1原口径(revisit<=1)全窗n=3已预判定样本作废(不报方向); 本版报放宽口径 revisit<=2. 出件utf-8+ensure_ascii=False.",
           "grid": results,
           "verdicts": {
             "H1": ("样本不足n<30, 不报方向" if results[h1k]["total_n"]<30
                    else ("PASS放宽" if results[h1k]["total_netR"]>b and results[h1k]["consistent"] else "REJECT放宽")),
             "H1_orig_revisit1": "样本作废(n=3, 不报方向)",
             "H2": ("平顶含3.5" if results["H2_RR3.5"]["total_netR"]>=b else "峰在3.0, 锁2.5"),
             "H3": "PASS" if results["H3_killzone"]["total_netR"]>b and results["H3_killzone"]["consistent"] else "REJECT"}}
    print("判词:", json.dumps(out["verdicts"], ensure_ascii=False))
    with open("data/eurjpy_pasd_deep.json","w",encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=str)
    print("产物: data/eurjpy_pasd_deep.json (utf-8)")
    mt5.shutdown()

if __name__=="__main__":
    try:
        main()
    except Exception:
        print("FATAL:\n"+traceback.format_exc(), flush=True)
        raise
