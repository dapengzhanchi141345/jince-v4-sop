# -*- coding: utf-8 -*-
"""soul_scan_1119.py — 全品种灵魂门扫描(李令11-19"全面分析行情,有行情就开")
确定性0LLM. 灵魂门四步前置(机构订单流口径):
  ①D1方向 ②M30 20根区段扫掠(近48根内) ③扫掠后位移>=0.6ATR30 ④位移新鲜度(近2根=可市价, 否则=挂单位)
产物: 逐品种信号 + 赚钱格SL/TP建议(币三=SL0.8ATR30+TP3R, 余品种=参数表值).
"""
import os, json, datetime as dt
import numpy as np

ROOT = "E:/GoldstrategyEngine"
CACHE = os.path.join(ROOT, "data", "tf_cache")
COIN3 = ("BTCUSD", "ETHUSD", "SOLUSD")


def scan(sym):
    m = np.load(os.path.join(CACHE, f"{sym}_M30.npz"))
    h, l, c, t = m["h"], m["l"], m["c"], m["t"]
    m.close()
    N = len(c)
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr30 = np.stack([tr[i-14:i+1].mean() for i in range(14, N)])
    atr_now = float(atr30[-1]) if atr30.size else float(tr[-15:].mean())
    c_now = float(c[-1])
    # ① D1方向: 近12根M30=6h收盘斜率 + 全天高低
    d6h = c[-1] - c[-13]
    day_hi, day_lo = float(h[-48:].max()), float(l[-48:].min())
    rng = day_hi - day_lo or 1e-9
    day_pos = (c_now - day_lo) / rng  # 0=日低 1=日高
    # ② 20根区段扫掠(近48根内): 前高/前低被扫 (全量数组索引, 取最近一次)
    hi20_prev = np.array([h[i-20:i].max() for i in range(20, N)])
    lo20_prev = np.array([l[i-20:i].min() for i in range(20, N)])
    hi20_prev = np.concatenate([np.full(20, np.nan), hi20_prev])
    lo20_prev = np.concatenate([np.full(20, np.nan), lo20_prev])
    sweep_up_i = sweep_dn_i = None
    for gi in range(N-48, N):
        if np.isnan(hi20_prev[gi]):
            continue
        if h[gi] > hi20_prev[gi] and c[gi] < hi20_prev[gi]:
            sweep_up_i = gi   # 上扫掠: 刺破前20根高点但收盘拉回(取最近一次)
        if l[gi] < lo20_prev[gi] and c[gi] > lo20_prev[gi]:
            sweep_dn_i = gi   # 下扫掠: 刺破前20根低点但收盘拉回
    # ③④ 位移: 扫掠后收盘越过扫掠位 >=0.6ATR30
    sig = {"sym": sym, "price": c_now, "atr30": round(atr_now, 5), "day_pos": round(day_pos, 3),
           "d6h_dir": "UP" if d6h > 0 else "DN", "sweeps": {}, "signal": None, "entry_type": None}
    for label, i, swp in (("UP", sweep_up_i, None), ("DN", sweep_dn_i, None)):
        if i is None:
            continue
        gi = i
        swp_price = hi20_prev[i] if label == "UP" else lo20_prev[i]
        after = c[gi+1:]
        if after.size == 0:
            continue
        disp = (after[-1] - swp_price) * (1 if label == "UP" else -1)
        ok_dir = (label == "UP" and d6h > 0) or (label == "DN" and d6h < 0)
        sig["sweeps"][label] = dict(bars_ago=int(N-1-gi), swp=round(float(swp_price), 5),
                                     disp_atr=round(float(disp / atr_now), 3), passed=bool(disp >= 0.6 * atr_now),
                                     dir_align=bool(ok_dir), recent=bool((N-1-gi) <= 2))
        # 可执行 = 扫掠后位移已过线 且 方向与D1一致
        if disp >= 0.6 * atr_now and ok_dir:
            sig["signal"] = "BUY" if label == "UP" else "SELL"
            sig["entry_type"] = "market" if (N-1-gi) <= 2 else "limit_at_sweep"
            sig["swp_price"] = round(float(swp_price), 5)
    return sig


def main():
    params = json.load(open(os.path.join(ROOT, "data", "practice_params_all_symbols.json"), encoding="utf-8"))
    out = []
    for f in sorted(os.listdir(CACHE)):
        if not f.endswith("_M30.npz"):
            continue
        sym = f[:-8]  # "_M30.npz"=8字符
        try:
            s = scan(sym)
            p = params.get(sym, {})
            slm = 0.8 if sym in COIN3 else float(p.get("sl_mult", 1.0))
            tpm = 3.0 if sym in COIN3 else float(p.get("tp_mult", 3.0))
            s["sl_pts"] = round(s["atr30"] * slm, 5)
            s["tp_pts"] = round(s["atr30"] * slm * tpm, 5)
            out.append(s)
        except Exception as ex:
            out.append({"sym": f[:-8], "err": str(ex)[:60]})
    sigs = [s for s in out if s.get("signal")]
    print(f"=== 全品种扫描 {dt.datetime.now():%H:%M} BJT: {len(out)} 品种, {len(sigs)} 过灵魂门 ===")
    for s in sigs:
        print(f"★ {s['sym']:8s} 信号{ s['signal']:4s} 入场{s['entry_type']:12s} 价{s['price']} 扫掠位{s.get('swp_price')} "
              f"SL距{s['sl_pts']} TP距{s['tp_pts']} ATR30={s['atr30']} 日位{s['day_pos']} D6h={s['d6h_dir']} "
              f"扫掠={json.dumps(s['sweeps'], ensure_ascii=False)}")
    if not sigs:
        print("  (0 信号 = 无行情可开, 最近扫掠未过位移线)")
    for s in out:
        if "sweeps" in s and not s.get("signal") and s["sweeps"]:
            print(f"  候 {s['sym']:8s} 有扫掠未过位移线: {json.dumps(s['sweeps'], ensure_ascii=False)[:150]}")
    json.dump(dict(ts=dt.datetime.now().isoformat(), signals=sigs, all=out),
              open(os.path.join(ROOT, "data", "soul_scan_1119.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("产物: data/soul_scan_1119.json")


if __name__ == "__main__":
    main()
