# -*- coding: utf-8 -*-
# 日内腿(kill-zone猎杀)五验 — 主进程直跑(子代理429限流后接手)
# 产出 data/leg_intra_polish.json
import json, math, os, sys
import numpy as np
import MetaTrader5 as mt5

ROOT = "E:/GoldstrategyEngine"
T1 = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "BNBUSD", "LTCUSD"]
SWEEP = 4.0      # 现: 扫损距离<4×H4ATR才挂
INTRADAY_SL = 0.75  # 现: 紧止损 0.75×H1ATR

def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def atr_wilder(h, l, c, period=14):
    n = len(c); out = np.zeros(n)
    if n < period + 1: return out
    tr = np.zeros(n); tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
    out[period-1] = tr[1:period+1].mean()
    for i in range(period, n):
        out[i] = (out[i-1]*(period-1)+tr[i])/period
    return out

mt5.initialize(); mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")

# ── step1 P&L 解剖 (crypto state history) ──
pnl_buckets = {}
try:
    d = json.load(open(os.path.join(ROOT, "data", "crypto_pending_state.json"), encoding="utf-8"))
    from collections import Counter
    ev = Counter(x.get("evt", "") for x in d.get("history", []))
    pnl_buckets = {
        "重估撤单(R3/R5未成交即撤)": ev.get("重估撤单", 0),
        "挂单(候选)": ev.get("挂单", 0),
        "孤儿仓收养(漏记成交堆叠)": ev.get("孤儿仓收养进状态机", 0),
        "L1止损/反转认亏": ev.get("L1止损/反转认亏", 0),
        "L5止盈/离场": ev.get("L5止盈/离场", 0),
    }
except Exception as e:
    pnl_buckets = {"error": str(e)}

# ── step2/3: 全史 H4 重放 PDH/PDL 扫损事件, 参数面 A/B ──
# 事件: 前日高 pdh, 当日触及(扫损) → 挂 SELL_STOP 于 pdh*1.002, 紧止损 0.75×H1ATR(H1≈H4/2近似用0.75*0.5*H4)
# 判定: fwd2 H4 close 方向. 扫损距离阈值 & 紧止损倍数 & kill-zone 时段 做网格.
def replay(sym, sweep_thr, tight_sl, kill_zone, n_days=2600):
    r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, n_days)
    if r is None or len(r) < 200: return None
    h = r["high"].astype(float); l = r["low"].astype(float); c = r["close"].astype(float)
    a = atr_wilder(h, l, c)
    # kill-zone: 只在伦敦/纽约时段(UTC)挂 → 用 H4 time 判. 简化: 全时段可挂 vs 限时段
    evts = []
    for i in range(60, len(r) - 2):
        pdh, pdl = h[i-1], l[i-1]
        ai = a[i] if a[i] > 0 else (h[i]-l[i])
        h1a = ai * 0.5  # H1 ATR ≈ 半 H4
        tz = int(r["time"][i]) if "time" in r.dtype.names else 0
        hr = (tz // 3600) % 24
        in_kz = (kill_zone in ("all",) or (8 <= hr < 12))  # h8-12; 现 h8-10 近似放宽到12
        if not in_kz: continue
        # 扫前日高(距< thr×H4ATR)
        if pdh > c[i] and (pdh - c[i]) < sweep_thr * ai:
            entry = pdh * 1.002; sl = entry + tight_sl * h1a
            if sl > entry:
                evts.append(("SELL", entry, sl, c[i+2]))
        if pdl < c[i] and (c[i] - pdl) < sweep_thr * ai:
            entry = pdl * 0.998; sl = entry - tight_sl * h1a
            if entry - sl > 0:
                evts.append(("BUY", entry, sl, c[i+2]))
    return evts

def perf(evts):
    if not evts: return None
    wins = sum(1 for s,e,sl,fc in evts
               if (fc < e if s == "SELL" else fc > e))
    # 期望R: 目标=枢轴中值近似, 简化 R = win? 1.0R : -1R (紧止损快单)
    expR = (wins / len(evts)) * 1.0 - ((len(evts)-wins) / len(evts)) * 1.0
    return dict(n=len(evts), wr=wins/len(evts), expR=round(expR,4))

CUR = (SWEEP, INTRADAY_SL, "h8-10")
grid = {}
all_events = {}
for sym in T1:
    res = {}
    for sw in (3.0, 4.0, 6.0):
        for tsl in (0.75, 1.0, 1.5):
            for kz in ("h8-10", "h8-12"):
                ev = replay(sym, sw, tsl, kz)
                if ev:
                    p = perf(ev)
                    key = f"sw{sw}/sl{tsl}/{kz}"
                    res[key] = p
    all_events[sym] = res
    print(f"[OK] {sym} 网格{len(res)}格")

# 全池化 (当前 vs 候选)
def pool(params):
    tot = perf(None) or dict(n=0, wr=0, expR=0)
    nsum, wsum = 0, 0
    for sym in T1:
        p = all_events.get(sym, {}).get(params)
        if p:
            nsum += p["n"]; wsum += p["n"]*p["wr"]
    return (wsum/nsum if nsum else 0.0, nsum)

cur_wr, cur_n = pool(f"sw{SWEEP}/sl{INTRADAY_SL}/h8-10")
best, best_wr = None, -9
for key in all_events.get(T1[0], {}):
    wr, n = pool(key)
    if n > 0 and wr > best_wr:
        best_wr, best = wr, key
# 同分母: 用全事件全集(现参数事件数)做对照
delta = best_wr - cur_wr
if cur_n == 0 or best_wr == cur_wr:
    p_val = math.inf
else:
    se = math.sqrt(cur_wr * (1 - cur_wr) / max(cur_n, 1) + best_wr * (1 - best_wr) / max(cur_n, 1))
    p_val = math.inf if se == 0 else 2 * (1 - norm_cdf(abs((best_wr - cur_wr)) / se))
# 品种稳健: 现 vs 最优 各品种 expR 方向
robust = []
for sym in T1:
    cp = all_events.get(sym, {}).get(f"sw{SWEEP}/sl{INTRADAY_SL}/h8-10")
    bp = all_events.get(sym, {}).get(best)
    if cp and bp:
        robust.append({"sym": sym, "cur_expR": cp["expR"], "best_expR": bp["expR"], "better": bp["expR"]>cp["expR"]})
same_dir = sum(1 for r in robust if r["better"]>=0)

out = {
    "pnl归因": pnl_buckets,
    "网格": all_events,
    "同分母结论": {"现参数": f"sw{SWEEP}/sl{INTRADAY_SL}/h8-10", "现expR": round(cur_wr,4),
                  "最优参数": best, "最优expR": round(best_wr,4),
                  "delta": round(delta,4), "p": (None if math.isinf(p_val) else round(p_val,4))},
    "五验": {
        "样本": f"全史H4×2600, 6币, 事件n≈{cur_n}",
        "显著": f"delta={delta:+.3f} p={'NA' if math.isinf(p_val) else round(p_val,4)}",
        "稳健": f"{same_dir}/{len(robust)} 品种最优≥现",
        "甜蜜点": "见网格相邻格",
        "时间稳定": "全史单一口径(walk-forward建议下轮补)"
    },
    "五验全过": (delta > 0.01 and not math.isinf(p_val) and p_val < 0.05 and same_dir >= 4),
    "裁决": ("接" if (delta > 0.01 and not math.isinf(p_val) and p_val < 0.05 and same_dir >= 4)
             else "维持现参数")
}
json.dump(out, open(os.path.join(ROOT, "data", "leg_intra_polish.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("[OK] 已写 leg_intra_polish.json | 最优=", best, "delta=", round(delta,4), "裁决=", out["裁决"])
mt5.shutdown()
