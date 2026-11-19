#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SUPD-MART 6mo 跨区加仓深测 (L5, @user 2026-10-17 要 6mo 详细汇报, 规格卡 l1_supd_crosszone_add_spec.md)
判尺(@chief 四格 22:00 grep 销):
 1) 数据源标 mt5:60137964 自家终端 6mo H1 (0 外部, 脏=件作废)
 2) 先报 6mo 底仓 netR 正负 (底仓仍负 → 加仓必 REJECT, 负底仓堆风险 fam6 铁律)
 3) 跨区确认行: add_lv 取 entry 外侧【离 entry 最近】的下一供需区 (非同区/非列表最老区)
 4) 加仓/不加仓 同分母 A/B Δnet_R + z + 最大回撤 (逐笔 net_R 同一套 sim, tpB 保守口径作判据, tpA 摊平仅作假胜对照)
确定性 0 LLM, 0 写闸源, 0 改 live. 产物 data/supd_mart_6mo.json.
"""
import os, sys, json, datetime, math
os.chdir(r"E:\GoldstrategyEngine"); sys.path.insert(0, r"E:\GoldstrategyEngine")
import numpy as np, pandas as pd, MetaTrader5 as mt5
import symbol_universe as su, backtest_engine as BE
import pasd_fusion as PF
OOS4 = ["EURJPY", "CADJPY", "EURNZD", "GBPCAD"]
DAYS, MAXH, RR = 180, BE.MAX_HOLD_H1, 2.5
LOT = 0.01  # @user 2026-10-17 钦定: 手数不扩大, 固定 0.01

def rates(sym, tf, d=DAYS):
    F = []; p = 0
    while True:
        c = mt5.copy_rates_from_pos(sym, tf, p, 5000)
        if c is None or len(c) == 0: break
        F.append(pd.DataFrame(c)); p += len(c)
        if len(c) < 5000 or p >= 20000: break
    if not F: return None
    df = pd.concat(F).drop_duplicates("time").sort_values("time").reset_index(drop=True)
    df["t"] = pd.to_datetime(df["time"], unit="s")
    return df[df["t"] >= df["t"].max() - pd.Timedelta(days=d)].reset_index(drop=True)

def add_lv_cross(sig, zd, zs):
    """跨区加仓(修 spec 判据3坑): 取 entry 外侧离 entry 最近的【下一个供需区】, 中点+到区 各加 1, 固定 2 次.
    long: demand 区底边 bottom<E 且 top<E 的区(整个区在 entry 下方), 取 top 最大者(=离 entry 最近的下一区).
    short: supply 区顶边 top>E 且 bottom>E 的区(整个区在 entry 上方), 取 bottom 最小者.
    同区(信号所在区)不进候选, 保证跨区."""
    E, side = sig["entry"], sig["side"]
    lv = []; cross_ok = True
    if side > 0:
        cands = [z for z in zd if z["top"] < E]          # 整个需求区在 entry 下方 = 下一区(跨区)
        z = max(cands, key=lambda zz: zz["top"]) if cands else None
    else:
        cands = [z for z in zs if z["bottom"] > E]        # 整个供应区在 entry 上方 = 下一区(跨区)
        z = min(cands, key=lambda zz: zz["bottom"]) if cands else None
    if z is None:
        return [], False                                    # 外侧无下一区 → 0 加仓(不加仓, 非同区摊平)
    lv = [(z["top"] + z["bottom"]) / 2.0, (z["bottom"] if side > 0 else z["top"])]
    return lv[:2], True

def sim(h1, sig, lv, cfg, sp, pt, swl, swh, tpA):
    """逐bar状态机(同v3). tpA=True 摊平(假胜对照); False=保守 TP 固定原始(判据口径)."""
    lot = float(cfg.get('lot', .1)); pip = float(cfg.get('pip', .0001)); pusd = float(cfg.get('pip_usd', 10.))
    i = int(sig['bar']); side = 1 if sig['side'] > 0 else -1
    if i + 1 >= len(h1): return None
    sd0 = abs(sig["entry"] - sig["sl"]); td0 = abs(sig["entry"] - sig["tp"])
    o = float(h1['open'].iloc[i + 1]); a = sp * pt
    e0 = o + a * side
    S = e0 - side * sd0; TP0 = e0 + side * td0
    end = min(i + 1 + MAXH, len(h1))
    hi = h1['high'].values[i + 1:end]; lo = h1['low'].values[i + 1:end]
    tm = h1['time'].values[i + 1:end]; cl = h1['close'].values[i + 1:end]
    if len(hi) == 0: return None
    pos = [(e0, lot)]; adds = 0; exit = None
    for k in range(len(hi)):
        tot = sum(w for _, w in pos); avg = sum(p * w for p, w in pos) / tot
        Tc = (avg + side * RR * sd0) if (tpA and adds > 0) else TP0
        if side > 0: slh = lo[k] <= S; tph = hi[k] >= Tc
        else:        slh = hi[k] >= S; tph = lo[k] <= Tc
        if adds < len(lv) and ((lo[k] <= lv[adds]) if side > 0 else (hi[k] >= lv[adds])):
            pos.append((lv[adds], lot)); adds += 1
        if slh and tph: exit = S if abs(e0 - S) <= abs(e0 - Tc) else Tc; break
        elif slh: exit = S; break
        elif tph: exit = Tc; break
    if exit is None: exit = float(cl[-1])
    tot = sum(w for _, w in pos); avg = sum(p * w for p, w in pos) / tot
    pnl = (exit - avg) * side / pip * pusd * tot
    hd = int(max(0, (tm[len(hi) - 1] - tm[0]) // 86400))
    pnl -= abs((swl if side > 0 else swh) * hd * tot)
    risk = sum(max(0, (p - S) * side) * w for p, w in pos) / pip * pusd
    return dict(net=pnl, risk=risk, adds=adds)

def run_dd(nets):
    c = peak = dd = 0.0
    for x in nets:
        c += x; peak = max(peak, c); dd = max(dd, peak - c)
    return dd

def ztest(p1, n1, p2, n2):
    if n1 < 2 or n2 < 2: return None
    ppool = (n1 * p1 + n2 * p2) / (n1 + n2)
    se = math.sqrt(ppool * (1 - ppool) * (1 / n1 + 1 / n2))
    return round((p2 - p1) / se, 3) if se > 0 else None

def main():
    print("supd_mart_6mo 起跑", datetime.datetime.now().isoformat(), flush=True)
    if not mt5.initialize():
        print("MT5 fail"); return
    res = {"generated": datetime.datetime.now().isoformat(), "rr": RR, "window_days": DAYS,
           "lot_fixed": LOT,
           "data_source": "mt5:60137964 自家终端 EURJPY/CADJPY/EURNZD/GBPCAD 6mo(180d) H1/H4/D1 真K线 (mt5.copy_rates_from_pos), 0 外部数据源; 手数固定0.01(@user 2026-10-17 钦定), USD列全折算0.01",
           "cross_zone_rule": "add_lv 取 entry 外侧离 entry 最近的下一供需区(整个区在 entry 下方long/上方short), 同区不入候选, 中点+到区各1, 固定2次",
           "tpA": "加仓后TP随均价摊平(假胜对照)", "tpB": "TP固定原始(保守真胜口径, 判据用)",
           "judge_order": "先报底仓6mo正负, 再报加仓Δ/z/MDD"}
    _OUT = os.path.join("data", "supd_mart_6mo.json")
    for sym in OOS4:
        cfg = dict(su.UNIVERSE.get(sym, {})); cfg['lot'] = LOT   # @user 钦定 0.01 固定手数(USD列口径), net_R 口径不受手数影响
        info = mt5.symbol_info(sym)
        sp = info.spread or 10; pt = info.point or 1e-5; swl = info.swap_long or 0; swh = info.swap_short or 0
        h1 = rates(sym, mt5.TIMEFRAME_H1); h4 = rates(sym, mt5.TIMEFRAME_H4); d1 = rates(sym, mt5.TIMEFRAME_D1)
        if h1 is None or len(h1) < 100:
            res[sym] = {"err": "H1短", "n_h1": len(h1) if h1 is not None else 0}; print(sym, "H1短"); continue
        sigs = PF.gen_pasd(h1, h4, d1, cfg)
        for s in sigs: s['tp'] = s['entry'] + s['side'] * RR * abs(s['entry'] - s['sl'])
        zs = PF._detect_supply_demand_zones(h1['high'].values, h1['low'].values, h1['close'].values)
        g = {}; cross_hits = 0
        base_nets = None; mart_nets = None
        for tpA in (False, True):
            key = 'B' if not tpA else 'A'
            for tag, lf in (('base', lambda s, zd, zz: []),
                            ('mart', lambda s, zd, zz: add_lv_cross(s, zd, zz)[0] if add_lv_cross(s, zd, zz)[1] else [])):
                nets = []; ad = []
                for s in sigs:
                    ok = add_lv_cross(s, zs['demand'], zs['supply'])[1]
                    if ok: cross_hits += 1
                    lv = lf(s, zs['demand'], zs['supply'])
                    r = sim(h1, s, lv, cfg, sp, pt, swl, swh, tpA)
                    if r is None: continue
                    nets.append(r['net'] / max(r['risk'], 1e-9)); ad.append(r['adds'])
                if key == 'B':
                    if tag == 'base': base_nets = nets
                    else: mart_nets = nets
                g[f'{tag}_{key}'] = dict(n=len(nets),
                                         netR=round(sum(nets) / max(1, len(nets)), 3) if nets else 0.0,
                                         cumR=round(sum(nets), 2), dd=round(run_dd(nets), 2),
                                         adds=round(sum(ad) / max(1, len(ad)), 2))
        # 同分母 z: base vs mart 胜率(同一全信号集, 逐笔netR同一套sim, B保守口径)
        wr_base = round(sum(1 for x in (base_nets or []) if x > 0) / max(1, len(base_nets or [])), 3)
        wr_mart = round(sum(1 for x in (mart_nets or []) if x > 0) / max(1, len(mart_nets or [])), 3)
        z = ztest(wr_base, len(base_nets or []), wr_mart, len(mart_nets or []))
        base = g['base_B']; mB = g['mart_B']; mA = g['mart_A']
        res[sym] = dict(sigs=len(sigs), spread=sp, n_h1=len(h1), g=g, z_同分母=z,
                        wr_base_B=wr_base, wr_mart_B=wr_mart,
                        cross_zone_confirmed=f"{cross_hits}/{len(sigs) if len(sigs) else 0} 信号外侧有下一供需区(跨区成立); 无区=0加仓非同区摊平")
        Bb = g['base_B']; mb = g['mart_B']; ma = g['mart_A']
        delta_B = mb.get('netR', 0) - Bb.get('netR', 0)
        delta_A = ma.get('netR', 0) - Bb.get('netR', 0)
        base_pos = Bb.get('netR', 0) > 0
        if Bb.get('n', 0) == 0:
            judge = "无信号"
        elif not base_pos:
            judge = "底仓6mo仍负 → 加仓判死(负底仓堆风险, fam6铁律), 0提权"
        else:
            judge = "底仓转正+加仓Δ>0 → WATCH候选(过五验才谈0.01)" if delta_B > 0 else "底仓转正但加仓无增益 → 不加仓"
        print(f"{sym}: 底仓netR={Bb.get('netR'):+.3f}(正:{base_pos}) | martB ΔR={delta_B:+.3f} dd={mb.get('dd')} | martA ΔR={delta_A:+.3f} | {judge}", flush=True)
        res[sym]['judge'] = judge
        res[sym]['delta_B'] = round(delta_B, 3); res[sym]['delta_A'] = round(delta_A, 3)
        res[sym]['base_positive_6mo'] = bool(base_pos)
        json.dump(res, open(_OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)  # 逐品种增量落盘, 崩了也留住
        print(f"  [{sym} 已增量落盘 {_OUT}]", flush=True)
    json.dump(res, open(_OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
    print("产物:", _OUT, flush=True)
    mt5.shutdown()

if __name__ == "__main__":
    main()
