#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""裸奔枪: @user 2026-10-17 "扩止损+全取消限制参数裸奔试试, 详细数据汇报"
L5 纯回测模拟 (0 改 live / 0 翻闸源 / 实盘先报后动铁律不动; 数据好也只出 WATCH 提案走五验+demo):
  信号集 = 同一份自家 6mo H1 (mt5:60137964) gen_pasd 现状信号 (底仓, 无加仓), 同分母.
  对照矩阵 (4品种 × 6臂):
    arm0 现状:     SL=1.2×ATR(gen_pasd原SL) + TP=RR2.5 + 全限制(日3单/冷却/仅趋势时段信号)
    arm1 扩SL:     SL=2.4×ATR(同entry) + TP=RR2.5×新SL距
    arm2 大SL:     SL=4.0×ATR + TP=RR2.5×新SL距
    arm3 裸TP:     现状SL + 无TP(扛到MAXH超时或反向SL)
    arm4 裸全:     大SL 4×ATR + 无TP (全裸)
    arm5 无限制:   现状SL/TP, 但取消冷却/日限过滤(信号集全入sim, 即"限制取消"效果)
  每臂逐笔净R(扣spread+swap, 同v3/replay口径) → cumR/meanR/wr/MDD/单笔最大亏.
  判尺: 裸奔若 cumR 或 MDD 恶化 → REJECT 裸奔(维持现状限制); 若显著改善 → WATCH 提案(走五验+L4+demo, 0直改live).
产物 data/supd_naked_6mo.json.
"""
import os, sys, json, datetime, math
os.chdir(r"E:\GoldstrategyEngine"); sys.path.insert(0, r"E:\GoldstrategyEngine")
import numpy as np, pandas as pd, MetaTrader5 as mt5
import symbol_universe as su, backtest_engine as BE
import pasd_fusion as PF
OOS4 = ["CADJPY", "EURJPY", "EURNZD", "GBPCAD"]
DAYS, MAXH, RR = 180, BE.MAX_HOLD_H1, 2.5

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

def ztest(p1, n1, p2, n2):
    if n1 < 2 or n2 < 2: return None
    ppool = (n1 * p1 + n2 * p2) / (n1 + n2)
    se = math.sqrt(max(ppool * (1 - ppool) * (1 / n1 + 1 / n2), 1e-12))
    return round((p2 - p1) / se, 3)

def run_dd(nets):
    c = peak = dd = 0.0
    for x in nets:
        c += x; peak = max(peak, c); dd = max(dd, peak - c)
    return dd

def replay_arm(h1, sigs, sl_mult, use_tp, sp, pt, swl, swh, atr_v, no_limits=True):
    """同一信号集, sl_dist = sl_mult*ATR[bar] (sl_mult=None 用 gen_pasd 原SL),
    use_tp=False 扛单(无TP, 到MAXH或反向SL). 逐笔净R扣 spread+swap, 同 v3 口径.
    no_limits=True: 信号全入(限制取消效果); False: 按现状冷却(30bar同侧)过滤."""
    rows = []
    last_bar = {"long": -999, "short": -999}
    for s in sigs:
        i, side = int(s["bar"]), 1 if s["side"] > 0 else -1
        if i + 1 >= len(h1): continue
        if not no_limits:
            key = "long" if side > 0 else "short"
            if i - last_bar[key] < 30: continue
            last_bar[key] = i
        a = atr_v[i]
        if np.isnan(a) or a <= 0: continue
        sd0 = a * sl_mult if sl_mult is not None else abs(s["entry"] - s["sl"])
        o = float(h1["open"].iloc[i + 1]); px = sp * pt
        e = o + px * side
        S = e - side * sd0
        td0 = abs(s["entry"] - s["sl"])
        T = e + side * RR * (td0 if sl_mult is None else sd0) if use_tp else None
        end = min(i + 1 + MAXH, len(h1))
        hi, lo = h1["high"].values[i + 1:end], h1["low"].values[i + 1:end]
        tm = h1["time"].values[i + 1:end]; op = h1["open"].values[i + 1:end]
        if len(hi) == 0: continue
        exit_ = None
        for k in range(len(hi)):
            sl_hit = (lo[k] <= S) if side > 0 else (hi[k] >= S)
            tp_hit = (hi[k] >= T) if (T is not None and side > 0) else ((T is not None) and (lo[k] <= T))
            if sl_hit and tp_hit:
                exit_ = S; break
            elif sl_hit:
                exit_ = S; break
            elif T is not None and tp_hit:
                exit_ = T; break
        if exit_ is None: exit_ = float(op[-1])   # 超时扛单出场
        hd = max(0, (int(tm[len(hi) - 1]) - int(tm[0])) // 86400) if len(hi) > 1 else 0
        sw = abs((swl if side > 0 else swh) * hd * 0.1)
        pnl = (exit_ - e) * side / 0.0001 * 10.0 * 0.1 - sw
        rows.append({"R": pnl / (sd0 / 0.0001 * 10.0 * 0.1), "time": int(s["time"])})
    return rows

def stat(rows):
    R = [r["R"] for r in rows]
    if not R:
        return {"n": 0}
    return {"n": len(R), "cumR": round(sum(R), 2), "meanR": round(sum(R) / len(R), 3),
            "wr": round(sum(1 for x in R if x > 0) / len(R), 3),
            "dd": round(run_dd(R), 2), "maxloss_R": round(min(R), 2)}

def main():
    print("supd_naked_6mo 起跑", datetime.datetime.now().isoformat(), flush=True)
    if not mt5.initialize():
        print("MT5 fail"); return
    res = {"generated": datetime.datetime.now().isoformat(), "rr": RR, "window_days": DAYS,
           "data_source": "mt5:60137964 自家终端 6mo(180d) H1/H4/D1 真K线, 信号=gen_pasd现状, 0外部",
           "arms": {"arm0": "现状 SL=gen_pasd原SL(1.2ATR) + RR2.5TP + 冷却限制",
                    "arm1": "扩SL 2.4×ATR + RR2.5TP",
                    "arm2": "大SL 4.0×ATR + RR2.5TP",
                    "arm3": "现状SL + 无TP扛单(裸TP)",
                    "arm4": "大SL 4.0×ATR + 无TP(全裸)",
                    "arm5": "现状SL/TP + 取消冷却限制(信号集全入)"},
           "note": "纯回测模拟, 0改live 0翻闸源; 结果好也只出WATCH提案(五验+L4+demo), 实盘先报后动"}
    for sym in OOS4:
        cfg = su.UNIVERSE.get(sym, {})
        info = mt5.symbol_info(sym)
        sp, pt = info.spread or 10, info.point or 1e-5
        swl, swh = info.swap_long or 0, info.swap_short or 0
        h1 = rates(sym, mt5.TIMEFRAME_H1); h4 = rates(sym, mt5.TIMEFRAME_H4); d1 = rates(sym, mt5.TIMEFRAME_D1)
        if h1 is None or len(h1) < 100:
            res[sym] = {"err": "H1短"}; print(sym, "H1短", flush=True); continue
        sigs = PF.gen_pasd(h1, h4, d1, cfg)
        for s in sigs:
            s["time"] = int(h1["time"].iloc[int(s["bar"])])
        atr_v = PF._atr(h1["high"].values.astype(float), h1["low"].values.astype(float), h1["close"].values.astype(float))
        arms = {}
        arms["arm0"] = stat(replay_arm(h1, sigs, None, True, sp, pt, swl, swh, atr_v, no_limits=False))
        arms["arm1"] = stat(replay_arm(h1, sigs, 2.4, True, sp, pt, swl, swh, atr_v))
        arms["arm2"] = stat(replay_arm(h1, sigs, 4.0, True, sp, pt, swl, swh, atr_v))
        arms["arm3"] = stat(replay_arm(h1, sigs, None, False, sp, pt, swl, swh, atr_v))
        arms["arm4"] = stat(replay_arm(h1, sigs, 4.0, False, sp, pt, swl, swh, atr_v))
        arms["arm5"] = stat(replay_arm(h1, sigs, None, True, sp, pt, swl, swh, atr_v, no_limits=True))
        b, m = arms["arm0"]["meanR"], arms["arm2"]["meanR"]
        worse = sum(1 for k in ("arm1", "arm2", "arm3", "arm4") if arms[k].get("n") and arms[k]["cumR"] < arms["arm0"].get("cumR", 0))
        res[sym] = dict(sigs=len(sigs), spread=sp, arms=arms,
                        verdict=("REJECT裸奔: 扩SL/无限制各臂均未改善现状" if worse >= 2 or all(arms[k].get("cumR", 0) <= arms["arm0"].get("cumR", 0) for k in ("arm1", "arm2", "arm3", "arm4", "arm5"))
                                 else "WATCH: 存在裸奔臂改善现状 → 提案走五验+L4+demo (0直改live)"))
        json.dump(res, open("data/supd_naked_6mo.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)  # 逐品种增量落盘防崩
        print(f"{sym}: sigs={len(sigs)} | 现状cumR={arms['arm0'].get('cumR')} dd={arms['arm0'].get('dd')} "
              f"| 扩SL2.4={arms['arm1'].get('cumR')} | 大SL4.0={arms['arm2'].get('cumR')} | 无TP={arms['arm3'].get('cumR')} | 全裸={arms['arm4'].get('cumR')} | 无限制={arms['arm5'].get('cumR')} → {res[sym]['verdict']} | 增量落盘", flush=True)
    json.dump(res, open("data/supd_naked_6mo.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("产物: data/supd_naked_6mo.json", flush=True)
    mt5.shutdown()

if __name__ == "__main__":
    main()
