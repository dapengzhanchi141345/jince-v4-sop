# -*- coding: utf-8 -*-
# 日内腿时间周期扫描 (2026-09-26 进化轮): H4粗回放 vs H1逐K回放 × kill-zone 时段 × 超时口径
# 事件 (同分母, 每日双向): SELL_STOP@PDH×1.002 / BUY_STOP@PDL×0.998, SL=0.75×H1ATR, 目标=前日中值
# 因果: 只用已完结前日 D1; 成交/出场逐 H1 回放 (保守同根先SL)
import json, sys
import numpy as np
import MetaTrader5 as mt5
sys.path.insert(0, "E:/GoldstrategyEngine"); sys.path.insert(0, "E:/GoldstrategyEngine/multi_agent/trading")
import intraday_swing as isw

SYMS = ["BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD"]
mt5.initialize(); assert mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")

def load(sym, tf, n):
    import time as _t
    min_bars = min(n // 10, 100)
    for _attempt in range(3):
        try:
            mt5.symbol_select(sym, True)   # 触发该 symbol 的行情/历史同步
        except Exception:
            pass
        _t.sleep(1)
        r = mt5.copy_rates_from_pos(sym, tf, 0, n)
        if r is not None and len(r) >= min_bars:
            return dict(t=r["time"].astype(np.int64), h=r["high"].astype(float),
                        l=r["low"].astype(float), c=r["close"].astype(float),
                        high=r["high"].astype(float), low=r["low"].astype(float))
        # 数据截断 → 重连重试
        _t.sleep(2)
        mt5.shutdown(); mt5.initialize(); mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
    return None

def build_days(sym):
    """返回 [(day_ts, pdh, pdl, mid, h1a, h1_day_indices)] 当日可回放的日内事件 (同日分母)"""
    d1 = load(sym, mt5.TIMEFRAME_D1, 3000)
    h1 = load(sym, mt5.TIMEFRAME_H1, 50000)
    if not (d1 and h1):
        print(f"[!] {sym} 数据加载失败 d1={0 if d1 is None else len(d1)} h1={0 if h1 is None else len(h1)}")
        return []
    d1t, d1h, d1l, d1c = d1["t"], d1["high"], d1["low"], d1["c"]
    t1, h1h, h1l, h1c = h1["t"], h1["h"], h1["l"], h1["c"]
    out = []
    # 服务器日对齐 (2026-09-26 修复): 用 D1 服务器日 [dts, dts+86400) 匹配 H1 段, 不碰 UTC 归一化
    # (前视修复: pdh/pdl 用 i-1 前一日; H1 ATR 用当日 0 点之前已完结 H1)
    c_skip_atr = c_skip_no_h1 = 0
    for i in range(60, len(d1t) - 1):
        dts = int(d1t[i])                     # D1 服务器日起点 (自带 broker 时区偏移, 不归一化)
        if d1c[i-1] <= 0: continue
        pdh, pdl = float(d1h[i-1]), float(d1l[i-1])     # 前一日高低 (因果)
        mid = (pdh + pdl) / 2.0
        # 当日 H1 段 = [dts, dts+86400) (服务器日, 与 D1 口径一致)
        i0 = int(np.searchsorted(t1, dts, side="left"))
        i1 = int(np.searchsorted(t1, dts + 86400, side="left"))
        i1 = min(i1, len(t1) - 1)
        if i1 <= i0:
            c_skip_no_h1 += 1
            continue
        # H1 ATR (因果: 只用当日之前已完结 H1, 不含当天 — 防前视)
        idx_end = i0
        seg = slice(max(0, idx_end - 30), idx_end)
        a = isw.atr(h1h[seg], h1l[seg], h1c[seg])
        h1a = float(a[-1]) if len(a) > 0 and a[-1] > 0 else 1e-9
        if h1a < 1e-6:
            c_skip_atr += 1
            continue
        out.append((dts, pdh, pdl, mid, h1a, i0, i1))
    if not out:
        print(f"[!] {sym} days=0 skip_atr={c_skip_atr} skip_noH1={c_skip_no_h1} d1={len(d1)} h1={len(h1)}")
    return out

def replay_day(day, t1, h1h, h1l, h1c, zone_h, timeout_bars, target="mid"):
    """单方向 SELL(上扫) / BUY(下扫): zone_h = (start_h, end_h) 当日小时窗 (UTC), timeout_bars 从成交起算"""
    dts, pdh, pdl, mid, h1a, i0, i1 = day
    z0, z1 = zone_h
    zi0 = int(np.searchsorted(t1, dts + z0*3600, side="left"))
    zi1 = int(np.searchsorted(t1, dts + z1*3600, side="left"))
    zi0 = max(zi0, 0); zi1 = min(zi1, len(t1)-1)
    res = {}
    for side, trig_raw in [("SELL", pdh*1.002), ("BUY", pdl*0.998)]:
        d = -1 if side == "SELL" else 1
        risk = 0.75 * h1a
        if risk < 1e-9: continue
        sl = trig_raw - d * risk      # SELL(d=-1): SL=trig+risk(上方); BUY(d=+1): SL=trig-risk(下方) — 与 live 几何一致
        tp = mid
        fill_k = None
        for k in range(zi0, zi1+1):
            if (h1h[k] >= trig_raw) if d < 0 else (h1l[k] <= trig_raw):
                fill_k = k; break
        if fill_k is None:
            res[side] = None
            continue
        R = None
        for k in range(fill_k, min(fill_k + timeout_bars, zi1+1)):
            kh, kl, kc = h1h[k], h1l[k], h1c[k]
            hit_sl = (kh >= sl) if d < 0 else (kl <= sl)   # SELL stop: SL在上方, 价涨到打掉; BUY stop: SL在下方, 价跌到打掉
            if hit_sl: R = -1.0; break
            hit_tp = (kc <= tp) if d < 0 else (kc >= tp)   # SELL 目标在中值(下方), 收盘到即平; BUY 目标在上方
            if hit_tp: R = abs(tp-trig_raw)/risk; break
        if R is None:
            kk = min(fill_k + timeout_bars - 1, zi1)
            R = max(min(d*(h1c[kk]-trig_raw)/risk, abs(tp-trig_raw)/risk), -1.0)
        res[side] = R
    return res

ZONES = {"08-16": ((8,16), 48), "08-12": ((8,12), 48), "00-24": ((0,24), 24)}
out = {}
day_cache, h1_cache = {}, {}
for sym in SYMS:
    days = build_days(sym)
    day_cache[sym] = days
    h1_cache[sym] = load(sym, mt5.TIMEFRAME_H1, 50000)
    print(f"[{sym}] days={len(days)}")

for zname, (zh, to_bars) in ZONES.items():
    Rs, Ts = [], []
    for sym in SYMS:
        h1 = h1_cache[sym]
        for day in day_cache[sym]:
            r = replay_day(day, h1["t"], h1["h"], h1["l"], h1["c"], zh, to_bars)
            for side, R in r.items():
                if R is not None:
                    Rs.append(R); Ts.append(day[0])
    arr = np.array(Rs)
    tmin, tmax = min(Ts), max(Ts)
    b1 = tmin + (tmax-tmin)//3; b2 = tmin + 2*(tmax-tmin)//3
    wf = [float(np.mean([r for r,t in zip(Rs,Ts) if t < b1])),
          float(np.mean([r for r,t in zip(Rs,Ts) if b1 <= t < b2])),
          float(np.mean([r for r,t in zip(Rs,Ts) if t >= b2]))]
    per_sym = {}
    for sym in SYMS:
        rs = []
        h1 = h1_cache[sym]
        for day in day_cache[sym]:
            r = replay_day(day, h1["t"], h1["h"], h1["l"], h1["c"], zh, to_bars)
            rs.extend(x for x in r.values() if x is not None)
        per_sym[sym] = round(float(np.mean(rs)), 4) if rs else None
    out[zname] = {"n": len(Rs), "exp_R": round(float(arr.mean()),4), "wr": round(float((arr>0).mean()),4),
                  "exp_slip0.5R": round(float((arr-0.5).mean()),4), "wf3": [round(x,4) for x in wf],
                  "wf_all_pos": all(x>0 for x in wf), "per_sym": per_sym}
    print(f"[H1回放 {zname}] n={len(Rs)} exp_R={arr.mean():+.4f} wr={(arr>0).mean():.3f} "
          f"(扣0.5R={arr.mean()-0.5:+.4f}) wf3={[round(x,3) for x in wf]} per_sym={per_sym}")

json.dump(out, open("E:/GoldstrategyEngine/data/intra_tfsweep.json","w",encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("written data/intra_tfsweep.json")
mt5.shutdown()
