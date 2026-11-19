#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SUPD-MART 马丁结构加仓回测 (L5 sweep 执行线, 用户指令 10-16):
在 PASD 基础信号上, 浮亏时挂 1 次/2 次小马丁加仓, 加仓点位 = 下一(反向)供需结构区
  中间(mid) 或 底部(下沿), 间距 = 结构区上沿(供给)/下沿(需求) vs 市价, 无区=不加.
确定性: 0 LLM. 成本面 = 引擎 simulate_signal 口径(真实点差+swap+R 归一化).
产物: data/supd_mart_backtest.json + 群报实数表. 0 写闸源, 0 改 live.
"""
import os, sys, json, time, math, datetime
os.chdir(r"E:\GoldstrategyEngine"); sys.path.insert(0, r"E:\GoldstrategyEngine")
import numpy as np, pandas as pd, MetaTrader5 as mt5
import symbol_universe as su, advanced_strategies as ast, backtest_engine as BE
import pasd_fusion as PF

OOS4 = ["CADJPY","EURJPY","EURNZD","GBPCAD"]
DAYS = 90
MULTS = [0.5, 1.0]          # 每次加仓手数 = 基础手数 * mult
COUNTS = [1, 2]            # 加仓次数上限 (用户: 只加两次)
MID_MODE = ["mid","edge"]  # 加仓点位: 区中间 / 区下沿(边缘)

def rates_3mo(sym, tf, days=DAYS):
    frames=[]; pos=0; CAP=5000
    while True:
        c = mt5.copy_rates_from_pos(sym, tf, pos, CAP)
        if c is None or len(c)==0: break
        frames.append(pd.DataFrame(c)); pos+=len(c)
        if len(c)<CAP: break
        if pos >= 20000: break
    if not frames: return None
    df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    df["t"]=pd.to_datetime(df["time"], unit="s")
    return df[df["t"] >= df["t"].max()-pd.Timedelta(days=days)].reset_index(drop=True)

def sim_one(h1, sig, cfg, spread_pts, point, swl, swh,
            add_count=0, add_mult=1.0, add_mode="mid"):
    """单信号(含马丁)回放. 返回 net_pnl$ / max_dd$ / 加仓次数 / 是否止损.
    马丁规则(用户口径): 开单后价格向不利方向移动达到 gap(结构区上/下沿 vs 市价) 时挂第1加;
    再加 gap2(下一区) 时挂第2加(若 count>=2). 加仓价 = 区中间或区下沿.
    SL 统一挂所有仓; TP = 加权均价 RR.
    """
    import pandas as _pd
    l = sig['entry']; sl = sig['sl']; side = 1 if l>sl else -1
    risk0 = abs(l-sl)
    lot=float(cfg.get('lot',0.1)); pip=float(cfg.get('pip',0.0001)); pusd=float(cfg.get('pip_usd',10.0))
    # 先模拟基础仓, 拿到逐 bar close
    pnl_base = BE.simulate_signal(h1, sig, spread_pts, point, swl, swh, lot, pip, pusd)
    if add_count==0:
        return dict(net=pnl_base, dd=abs(pnl_base) if pnl_base<0 else 0.0, add=0, sl_hit=pnl_base<0)
    # 马丁: 在 H1 序列里回放. 找到开单 bar(时间戳), 之后价格触到 gap 时加仓.
    t0 = int(sig.get('time', h1['time'].iloc[0]))
    idx0 = int(h1.index[h1['time']==t0][0]) if t0 in set(h1['time']) else 0
    hi = h1['high'].values; lo = h1['low'].values; cl = h1['close'].values
    zones = sig.get('zones_after', [])  # 上游 gen 预计算的反向区列表
    added=0; total_lot=lot; prices=[(l, lot)]
    total_spread = 0.0
    for zi in range(min(add_count, len(zones))):
        z = zones[zi]
        gap = z['top'] if side==1 else z['bottom']   # 多头: 下一个供给区顶; 空头: 下一个需求区底
        add_price = (z['top']+z['bottom'])/2.0 if add_mode=="mid" else (z['bottom'] if side==1 else z['top'])
        # 触价: 多头看 low<=gap 或 空头看 high>=gap
        touched = (lo[idx0:] <= gap).any() if side==1 else (hi[idx0:] >= gap).any()
        if not touched: break
        add_lot = lot*add_mult
        prices.append((add_price, add_lot)); total_lot += add_lot; added+=1
    if added==0:
        return dict(net=pnl_base, dd=abs(pnl_base) if pnl_base<0 else 0.0, add=0, sl_hit=pnl_base<0)
    # 加仓后重算统一 SL(不变, 跟基础仓同 SL), 加 TP(按均价 RR), 重新模拟到 TP 或 SL 先触
    avg = sum(p*wl for p,wl in prices)/total_lot
    rr = abs(sig['tp']-l)/risk0
    tp = avg + side*rr*risk0
    new_sig = dict(sig); new_sig['entry']=avg; new_sig['lot']=total_lot; new_sig['tp']=tp; new_sig['sl']=sl
    pnl_m = BE.simulate_signal(h1, new_sig, spread_pts, point, swl, swh, total_lot, pip, pusd)
    # 逐 bar 回撤: 简化用最终 pnl 与 SL 距离估计 (加仓均价到 SL 的风险)
    risk_m = abs(avg-sl)/pip*pusd*total_lot
    dd = risk_m if pnl_m<0 else min(risk_m, abs(pnl_m))
    return dict(net=pnl_m, dd=dd, add=added, sl_hit=pnl_m<0)

def main():
    if not mt5.initialize(): print("MT5 init fail"); sys.exit(1)
    out={"generated":datetime.datetime.now().isoformat(),"window_days":DAYS,
         "design":"用户指令: 浮亏加仓, 间距=下结构区 mid/edge, 最多加 2 次; fam6 铁律对照=负期望上堆风险, 0 转正除非五验全过",
         "cost":"引擎 simulate_signal 口径(真实点差+swap), R 归一化 pnl$/risk$"}
    for sym in OOS4:
        cfg=su.UNIVERSE.get(sym,{})
        info=mt5.symbol_info(sym)
        sp=info.spread if info and info.spread>0 else 10
        pt=info.point if info else 1e-5
        swl=info.swap_long if info else 0; swh=info.swap_short if info else 0
        h1=rates_3mo(sym, mt5.TIMEFRAME_H1); h4=rates_3mo(sym, mt5.TIMEFRAME_H4); d1=rates_3mo(sym, mt5.TIMEFRAME_D1)
        if h1 is None or len(h1)<100: out[sym]={"error":"H1 不足"}; print(sym,"H1不足"); continue
        sigs=PF.gen_pasd(h1, h4, d1, cfg)
        # 给每个信号预计算"其后(反向)结构区列表" — 按信号 bar 之后 1..2 个反向区
        h1z = PF._detect_supply_demand_zones(h1['high'].values, h1['low'].values, h1['close'].values)
        for s in sigs:
            side=1 if s['entry']>s['sl'] else -1
            idx_s = int(h1.index[h1['time']==int(s.get('time',0))][0]) if s.get('time') in set(h1['time']) else 0
            if side==1:  # 多头: 后续下一个供给区(顶在上方)
                zones = [z for z in h1z['supply'] if z['bottom'] > s['entry']][:2]
            else:        # 空头: 后续下一个需求区(底在下方)
                zones = [z for z in h1z['demand'] if z['top'] < s['entry']][:2]
            s['zones_after']=zones
        res={}
        for mc in [0]+[m for m in MULTS for c in COUNTS]:
            m, c = (0,0) if mc==0 else ((m, c) if isinstance(mc,tuple) else (m,c))
            for mult in ([0]+MULTS):
                for cnt in ([0]+COUNTS):
                    tag = f"m{cnt}x{mult}" if cnt>0 else "base"
                    rows=[]; net_R=0.0; add_cnt=0
                    for s in sigs:
                        r = sim_one(h1, s, cfg, sp, pt, swl, swh, add_count=cnt, add_mult=mult, add_mode="mid")
                        risk = abs(s['entry']-s['sl'])/pip*pusd*float(cfg.get('lot',0.1))
                        if risk<=0: continue
                        rows.append(r); net_R += r['net']/risk; add_cnt += r['add']
                    n=len(rows); pf = sum(max(0,r['net']) for r in rows)/max(1e-9, abs(sum(min(0,r['net']) for r in rows)))
                    res[tag] = dict(n=n, net_R=round(net_R,2), pf=round(pf,3),
                                    avg_dd_R=round(sum(r['dd'] for r in rows)/max(1,n)/max(1e-9,risk),2),
                                    avg_adds=round(add_cnt/max(1,n),2))
        out[sym]={"spread":sp, "base_sigs":len(sigs), "grid":res}
        line = " | ".join(f"{k}: R={v['net_R']:+.1f} pf={v['pf']:.2f} add={v['avg_adds']}" for k,v in res.items())
        print(f"\n=== {sym} (sigs={len(sigs)}, {line})")
    json.dump(out, open("data/supd_mart_backtest.json","w",encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("\n=== 马丁是否真能救负 edge (判词: 看同分母 net_R + 回撤 + 加仓次数) ===")
    for sym in OOS4:
        if sym in out and "grid" in out[sym]:
            g=out[sym]["grid"]
            base=g.get("base",{}); best=max((k,v) for k,v in g.items() if k!="base"), key=None
            print(f"{sym}: base R={base.get('net_R')} → 最优马丁 R={best[1]['net_R']} (add={best[1]['avg_adds']} 次/信号)")
    print("\n产物: data/supd_mart_backtest.json")
    mt5.shutdown()

if __name__=="__main__": main()
