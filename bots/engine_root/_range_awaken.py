# -*- coding: utf-8 -*-
# 震荡腿唤醒工程 STEP1: 同事件全集多变体五验 (外部学习假设 → 全史验证)
import json, math
import numpy as np
import MetaTrader5 as mt5

SYMS = ["BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD"]
mt5.initialize(); assert mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")

def bb(c, period=20, k=2.0):
    n = len(c); up = np.zeros(n); dn = np.zeros(n); mid = np.zeros(n)
    for i in range(period, n):
        w = c[i-period+1:i+1]; m = w.mean(); sd = w.std()
        mid[i] = m; up[i] = m + k*sd; dn[i] = m - k*sd
    return up, mid, dn

def rsi2(c):
    n = len(c); out = np.zeros(n); ag = al = 0.0
    for i in range(1, n):
        d = c[i]-c[i-1]
        g = max(d, 0); lo = max(-d, 0)
        ag = (ag*(2-1) + g) / 2; al = (al*(2-1) + lo) / 2
        out[i] = 100.0 if al == 0 else 100 - 100/(1+ag/al)
    return out

def adx_arr(h, l, c, period=14):
    n = len(c); tr = np.zeros(n); tr[0] = h[0]-l[0]
    pdm = np.zeros(n); mdm = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
        upmv = h[i]-h[i-1]; dnmv = l[i-1]-l[i]
        pdm[i] = upmv if (upmv > dnmv and upmv > 0) else 0
        mdm[i] = dnmv if (dnmv > upmv and dnmv > 0) else 0
    atr = np.zeros(n); sp = np.zeros(n); sm = np.zeros(n)
    atr[period] = tr[1:period+1].sum(); sp[period] = pdm[1:period+1].sum(); sm[period] = mdm[1:period+1].sum()
    for i in range(period+1, n):
        atr[i] = atr[i-1]-atr[i-1]/period+tr[i]
        sp[i] = max(0, sp[i-1]-sp[i-1]/period+pdm[i])
        sm[i] = max(0, sm[i-1]-sm[i-1]/period+mdm[i])
    dx = np.zeros(n)
    for i in range(period, n):
        if atr[i] > 0:
            p = 100*sp[i]/atr[i]; m = 100*sm[i]/atr[i]; s = p+m
            dx[i] = (abs(p-m)/s*100) if s > 0 else 0
    out = np.zeros(n)
    for i in range(2*period-1, n):
        out[i] = np.mean(dx[i-period+1:i+1])
    return out

def atr14(h, l, c, period=14):
    n = len(c); tr = np.zeros(n); tr[0] = h[0]-l[0]
    for i in range(1, n):
        tr[i] = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
    out = np.zeros(n); out[period] = tr[1:period+1].mean()
    for i in range(period+1, n):
        out[i] = (out[i-1]*(period-1)+tr[i])/period
    return out

def d1_up(d1c, d1t, t):
    m = np.where(d1t + 86400 <= int(t))[0]
    if len(m) == 0: return None
    j = m[-1]
    return (1 if d1c[j] > d1c[j-1] else 0) if j >= 1 else None

VARIANTS = [
    "A0_现参数",        # ADX<=25 触带反做, 目标中轨, SL带外2ATR, 3天超时
    "A1_RSI2极值",      # 买需RSI2<=5 卖需RSI2>=95
    "A2_压缩后破位",    # 前20根带宽扩张>1.5x(40根中位) 的带外触
    "A3_时间退出",      # 4根H4内没到目标→按第4根收盘平(保留浮盈亏)
    "A5_低波动闸",      # 日ATR < 自身20日中位×0.7
]

def gate(v, side, i, hh, ll, cc, r2, adx, a, atr, up_arr, dn_arr):
    if adx[i-1] > 30: return False
    if side == "sell":
        if v == "A1_RSI2极值" and r2[i-1] < 95: return False
        if v == "A2_压缩后破位":
            win = (hh[i-1]-ll[i-1])
            hist = np.array([ (up_arr[k]-dn_arr[k]) for k in range(i-41, i-21) ])
            if len(hist) < 10 or np.median(hist) <= 0: return False
            if win < 1.5*np.median(hist): return False
        if v == "A5_低波动闸":
            med = np.median(atr[i-21:i-1])
            if med <= 0 or a > 0.7*med: return False
    else:
        if v == "A1_RSI2极值" and r2[i-1] > 5: return False
        if v == "A2_压缩后破位":
            win = (hh[i-1]-ll[i-1])
            hist = np.array([ (up_arr[k]-dn_arr[k]) for k in range(i-41, i-21) ])
            if len(hist) < 10 or np.median(hist) <= 0: return False
            if win < 1.5*np.median(hist): return False
        if v == "A5_低波动闸":
            med = np.median(atr[i-21:i-1])
            if med <= 0 or a > 0.7*med: return False
    return True

def replay(i, hh, ll, cc, up_arr, dn_arr, a, side, v, FWD=42, MAXBAR=4):
    """side 'sell'=触上沿挂SELL_LIMIT / 'buy'=触下沿挂BUY_LIMIT.
    几何 (因果, 只用 i-1 已完结K线):
      sell: trig=上沿, SL=trig+2a(上), 目标=前一根中值(下)
      buy : trig=下沿, SL=trig-2a(下), 目标=前一根中值(上)
    成交: sell限价=价格涨到trig (high>=trig); buy限价=价格跌到trig (low<=trig)
    同根先判SL(保守). 返回 (R, bucket)."""
    tgt = (hh[i-1]+ll[i-1]) / 2.0     # 前一根中值 (因果)
    if side == "sell":
        trig = up_arr[i-1]; sl = trig + 2*a; d = -1.0
        fill_cond = "high"; sl_cond = "high_ge"
    else:
        trig = dn_arr[i-1]; sl = trig - 2*a; d = +1.0
        fill_cond = "low"; sl_cond = "low_le"
    risk = abs(trig - sl)
    if risk <= 0: return 0.0, "未成交"
    k0 = i + 1
    filled = False; fill_k = -1
    end = min(k0 + MAXBAR, len(hh))
    for k in range(k0, end):
        if side == "sell" and hh[k] >= trig: filled = True; fill_k = k; break
        if side == "buy" and ll[k] <= trig: filled = True; fill_k = k; break
    if not filled: return 0.0, "未成交"
    # 成交当根: 同根既到trig又越SL → 保守判SL
    if side == "sell" and hh[fill_k] >= sl: return -1.0, "SL(成交当根)"
    if side == "buy" and ll[fill_k] <= sl: return -1.0, "SL(成交当根)"
    last_exit = cc[fill_k]
    for k in range(fill_k + 1, min(fill_k + 1 + FWD, len(cc))):
        if side == "sell":
            if hh[k] >= sl: return -1.0, "SL打掉"
            if ll[k] <= tgt: return 1.0, "中轨止盈"
        else:
            if ll[k] <= sl: return -1.0, "SL打掉"
            if hh[k] >= tgt: return 1.0, "中轨止盈"
        last_exit = cc[k]
    if v == "A3_时间退出":
        r = (last_exit - trig) / risk if d > 0 else (trig - last_exit) / risk
        return max(min(r, 1.0), -1.0), "时间退出(4根)"
    return -1.0, "超时计负"

data = {}
for sym in SYMS:
    h4 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, 2600)
    d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 500)
    if h4 is None or d1 is None: continue
    hh = h4["high"].astype(float); ll = h4["low"].astype(float); cc = h4["close"].astype(float)
    d1c = d1["close"].astype(float); d1t = d1["time"].astype(np.int64)
    up, mid, dn = bb(cc)
    r2 = rsi2(cc); adx = adx_arr(hh, ll, cc); a14 = atr14(hh, ll, cc)
    results = {v: {"wins":0, "losses":0, "cancels":0, "R":0.0, "buckets":{}} for v in VARIANTS}
    for i in range(60, len(cc)-2):
        if up[i-1] <= 0 or a14[i-1] <= 0: continue
        a = float(a14[i-1])
        du = d1_up(d1c, d1t, int(h4["time"][i-1]))
        if du is None: continue
        # 触上沿
        if cc[i-1] < up[i-1] and hh[i] >= up[i-1]:
            for v in VARIANTS:
                if not gate(v, "sell", i, hh, ll, cc, r2, adx, a, a14, up, dn): continue
                R, b = replay(i, hh, ll, cc, up, dn, a, "sell", v)
                d = results[v]
                if b == "未成交": d["cancels"] += 1
                else:
                    if R >= 0: d["wins"] += 1
                    else: d["losses"] += 1
                    d["R"] += R
                    d["buckets"][b] = d["buckets"].get(b, 0) + 1
        if cc[i-1] > dn[i-1] and ll[i] <= dn[i-1]:
            for v in VARIANTS:
                if not gate(v, "buy", i, hh, ll, cc, r2, adx, a, a14, up, dn): continue
                R, b = replay(i, hh, ll, cc, up, dn, a, "buy", v)
                d = results[v]
                if b == "未成交": d["cancels"] += 1
                else:
                    if R >= 0: d["wins"] += 1
                    else: d["losses"] += 1
                    d["R"] += R
                    d["buckets"][b] = d["buckets"].get(b, 0) + 1
    data[sym] = results
    for v in VARIANTS:
        d = results[v]; n = d["wins"]+d["losses"]
        if n: print(f"[{sym}] {v}: n={n} wr={d['wins']/n:.3f} avgR={d['R']/n:.4f} cancels={d['cancels']}")
        else: print(f"[{sym}] {v}: n=0 (无事件) cancels={d['cancels']}")
json.dump(data, open("E:/GoldstrategyEngine/data/range_awaken_scan.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
# 汇总
print("\n=== 汇总 (7品种合计) ===")
tot = {v: {"w":0, "l":0, "R":0.0, "c":0, "buckets":{}} for v in VARIANTS}
for sym in data:
    for v in VARIANTS:
        d = data[sym][v]; t = tot[v]
        t["w"] += d["wins"]; t["l"] += d["losses"]; t["R"] += d["R"]; t["c"] += d["cancels"]
        for b, n in d["buckets"].items():
            t["buckets"][b] = t["buckets"].get(b, 0) + n
for v in VARIANTS:
    t = tot[v]; n = t["w"]+t["l"]
    exp = t["R"]/n if n else 0.0
    wr = t["w"]/n if n else 0.0
    print(f"{v}: n={n} wr={wr:.3f} 期望R={exp:.4f} cancels={t['c']} 桶={t['buckets']}")
best = max(VARIANTS, key=lambda v: (tot[v]["R"]/(tot[v]["w"]+tot[v]["l"]) if (tot[v]["w"]+tot[v]["l"]) else -9))
cur = tot["A0_现参数"]
cur_n = cur["w"]+cur["l"]
cur_exp = cur["R"]/cur_n if cur_n else 0.0
print(f"\n最优={best}  vs  现参数期望R={cur_exp:.4f} (n={cur_n})")
mt5.shutdown()
