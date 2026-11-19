"""
v10.4 一年实盘回测 v2 — 自包含稳健版
基于 Sam Seiden 供需理论核心理念，自行实现可靠的区检测
"""
import sys, os, json, warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
warnings.filterwarnings('ignore')

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ═══════════════════════════════════════════════
# Phase 1: 数据
# ═══════════════════════════════════════════════
def ensure_data():
    """确保数据已下载"""
    files = [os.path.join(DATA_DIR, f"XAUUSD_{tf}.csv") for tf in ["H1", "H4", "D1"]]
    if all(os.path.exists(f) for f in files):
        print("数据已缓存")
        return
    import MetaTrader5 as mt5
    MT5_PATH = r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe"
    if not mt5.initialize(path=MT5_PATH):
        mt5.shutdown()
        if not mt5.initialize():
            print(f"[ERR] MT5 init: {mt5.last_error()}")
            return
    mt5.login(60043976, password="", server="TradeMaxGlobal-Demo")
    end = datetime(2026, 7, 1)
    start = datetime(2025, 7, 1)
    utc_from, utc_to = int(start.timestamp()), int(end.timestamp())
    for tf, tf_name, tf_mt5 in [
        ("H1", "H1", 16385), ("H4", "H4", 16388), ("D1", "D1", 16408)
    ]:
        rates = mt5.copy_rates_range("XAUUSD", tf_mt5, utc_from, utc_to)
        if rates is not None and len(rates) > 0:
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            df.to_csv(os.path.join(DATA_DIR, f"XAUUSD_{tf_name}.csv"), index=False)
            print(f"{tf_name}: {len(df)} bars")
    mt5.shutdown()

# ═══════════════════════════════════════════════
# Phase 2: 指标
# ═══════════════════════════════════════════════
def ema(vals, period):
    r = np.full(len(vals), np.nan)
    r[period-1] = np.mean(vals[:period])
    a = 2/(period+1)
    for i in range(period, len(vals)):
        r[i] = vals[i]*a + r[i-1]*(1-a)
    return r

def atr(h, l, c, p=14):
    if len(c) < p+1:
        return np.full(len(c), np.mean(h[-5:]-l[-5:]) if len(h)>=5 else 1)
    tr = np.maximum(h[1:]-l[1:], np.maximum(np.abs(h[1:]-c[:-1]), np.abs(l[1:]-c[:-1])))
    r = np.full(len(c), np.nan)
    r[p] = np.mean(tr[:p])
    a = 1/p
    for i in range(p+1, len(c)):
        r[i] = tr[i-1]*a + r[i-1]*(1-a)
    return pd.Series(r).ffill().fillna(np.mean(tr[:p])).values

def adx(h, l, c, p=14):
    if len(c) < p*2:
        return np.zeros(len(c))
    tr = np.maximum(h[1:]-l[1:], np.maximum(np.abs(h[1:]-c[:-1]), np.abs(l[1:]-c[:-1])))
    u, d = h[1:]-h[:-1], l[:-1]-l[1:]
    pdi = 100*pd.Series(np.where((u>d)&(u>0),u,0)).ewm(span=p).mean()/(pd.Series(tr).ewm(span=p).mean()+1e-10)
    mdi = 100*pd.Series(np.where((d>u)&(d>0),d,0)).ewm(span=p).mean()/(pd.Series(tr).ewm(span=p).mean()+1e-10)
    dx = 100*np.abs(pdi-mdi)/(pdi+mdi+1e-10)
    result = pd.Series(dx).ewm(span=p).mean().values
    return np.concatenate([np.zeros(len(c)-len(result)), result])

# ═══════════════════════════════════════════════
# Phase 3: 供需区检测 (稳健版)
# ═══════════════════════════════════════════════
def find_swing(h, l, lookback=3):
    """找到swing high和swing low的位置和价格"""
    swh, swl = [], []
    for i in range(lookback, len(h)-lookback):
        if h[i] == max(h[i-lookback:i+lookback+1]):
            swh.append((i, h[i]))
        if l[i] == min(l[i-lookback:i+lookback+1]):
            swl.append((i, l[i]))
    return swh, swl

def find_zones(h4_df):
    """
    检测供需区 — 基于Sam Seiden核心理念
    返回: list of (type, top, bottom, strength)
    """
    h = h4_df["high"].values
    l = h4_df["low"].values
    c = h4_df["close"].values
    
    zones = []
    swh, swl = find_swing(h, l, 3)
    
    # 需求区: swing low + 上破确认
    for idx, low_val in swl:
        if idx < 2 or idx > len(c) - 3:
            continue
        # 寻找从左侧高点到swing low的下跌
        left_high = max(h[max(0,idx-10):idx+1])
        down_move = left_high - low_val
        if down_move <= 0:
            continue
        # 检查右侧是否有突破
        for j in range(idx+1, min(idx+8, len(c))):
            if c[j] > low_val + down_move * 0.2:  # 至少反弹20%
                base_high = max(h[idx:j+1])
                base_low = min(l[idx:j+1])
                rally = base_high - base_low
                retrace = rally / down_move if down_move > 0 else 0
                if 0.15 <= retrace <= 0.95:
                    strength = min(5.0, retrace * 5 + 0.5)
                    zones.append({
                        "type": "D",
                        "top": base_high,
                        "bottom": max(base_low, low_val - (base_high - base_low) * 0.1),
                        "strength": strength,
                        "fresh": (len(c) - idx) <= 20,
                    })
                break
    
    # 供给区: swing high + 下破确认
    for idx, high_val in swh:
        if idx < 2 or idx > len(c) - 3:
            continue
        left_low = min(l[max(0,idx-10):idx+1])
        up_move = high_val - left_low
        if up_move <= 0:
            continue
        for j in range(idx+1, min(idx+8, len(c))):
            if c[j] < high_val - up_move * 0.2:
                base_high = max(h[idx:j+1])
                base_low = min(l[idx:j+1])
                rally = base_high - base_low
                retrace = rally / up_move if up_move > 0 else 0
                if 0.15 <= retrace <= 0.95:
                    strength = min(5.0, retrace * 5 + 0.5)
                    zones.append({
                        "type": "S",
                        "top": min(base_high, high_val + (base_high - base_low) * 0.1),
                        "bottom": base_low,
                        "strength": strength,
                        "fresh": (len(c) - idx) <= 20,
                    })
                break
    
    # 去重合并
    merged = []
    for z in zones:
        is_dup = False
        for m in merged:
            if m["type"] == z["type"] and abs(m["top"] - z["top"]) / max(m["top"], 1) < 0.01 and \
               abs(m["bottom"] - z["bottom"]) / max(m["bottom"], 1) < 0.01:
                m["strength"] = max(m["strength"], z["strength"])
                is_dup = True
                break
        if not is_dup:
            merged.append(z)
    
    return {"demand": [z for z in merged if z["type"] == "D"],
            "supply": [z for z in merged if z["type"] == "S"]}


# ═══════════════════════════════════════════════
# Phase 4: 回测
# ═══════════════════════════════════════════════
def run(h1_df, h4_df, d1_df, initial=10000, lot=0.01):
    h1 = h1_df.copy()
    h4 = h4_df.copy()
    
    hc = h1["close"].values
    hh = h1["high"].values
    hl = h1["low"].values
    ht = h1["time"].values
    
    # 指标预计算
    adx_v = adx(hh, hl, hc)
    atr_v = atr(hh, hl, hc)
    e14 = ema(hc, 14)
    e28 = ema(hc, 28)
    
    # D1指标
    dc = d1_df["close"].values
    de9 = ema(dc, 9)
    de21 = ema(dc, 21)
    
    # H4指标
    h4c = h4["close"].values
    h4h = h4["high"].values
    h4l = h4["low"].values
    h4adx = adx(h4h, h4l, h4c)
    # H4 ATR
    h4_tr = np.maximum(h4h[1:]-h4l[1:], np.maximum(np.abs(h4h[1:]-h4c[:-1]), np.abs(h4l[1:]-h4c[:-1])))
    h4_atr_vals = np.full(len(h4c), np.nan)
    h4_atr_vals[14] = np.mean(h4_tr[:14])
    for i in range(15, len(h4c)):
        h4_atr_vals[i] = h4_tr[i-1]/14 + h4_atr_vals[i-1]*13/14
    h4_atr_vals = pd.Series(h4_atr_vals).ffill().fillna(np.mean(h4_tr[:14])).values
    
    trades = []
    pos = None
    bal = float(initial)
    eq = [bal]
    daily_t = 0
    last_d = None
    consec_l = 0
    cool_until = None
    prog_sl = None
    
    # 缓存最近的H4区块检测结果 (每根H4 K线检测一次)
    h4_zone_cache = {}  # h4_index -> zones
    
    for i in range(100, len(h1)):
        bt = pd.Timestamp(ht[i])
        price = hc[i]
        bh = hh[i]
        bl = hl[i]
        
        # 日重置
        cd = bt.date()
        if last_d != cd:
            daily_t = 0
            last_d = cd
        
        # 冷却
        if cool_until and bt < cool_until:
            eq.append(bal)
            continue
        
        # ─── 持仓管理 ───
        if pos:
            effective_sl = prog_sl if prog_sl is not None else pos["sl"]
            hit_sl, hit_tp, reason = False, False, ""
            
            if pos["side"] == 1:  # BUY
                if bl <= min(abs(effective_sl), abs(pos["sl"])):
                    hit_sl, reason = True, "SL"
                elif bh >= pos["tp"]:
                    hit_tp, reason = True, "TP"
            else:  # SELL
                if bh >= max(abs(effective_sl), abs(pos["sl"])):
                    hit_sl, reason = True, "SL"
                elif bl <= pos["tp"]:
                    hit_tp, reason = True, "TP"
            
            if hit_sl:
                exit_p = pos["sl"]
                profit = (exit_p - pos["entry"]) * pos["side"] * lot * 100
            elif hit_tp:
                exit_p = pos["tp"]
                profit = (exit_p - pos["entry"]) * pos["side"] * lot * 100
            else:
                # 渐进止盈 (v10.2)
                r_ = abs(pos["entry"] - pos["sl"])
                if r_ > 0 and prog_sl is None:
                    d_ = (price - pos["entry"]) * pos["side"]
                    mult = d_ / r_
                    if mult > 2.0:
                        prog_sl = pos["entry"] + 1.5 * r_ * pos["side"]
                    elif mult > 1.0:
                        prog_sl = pos["entry"] + 0.5 * r_ * pos["side"]
                    elif mult > 0.5:
                        prog_sl = pos["entry"]
                eq.append(bal)
                continue
            
            trades.append({
                "open_time": pos["ot"].strftime("%Y-%m-%d %H:%M"),
                "close_time": bt.strftime("%Y-%m-%d %H:%M"),
                "direction": "BUY" if pos["side"] == 1 else "SELL",
                "entry": round(pos["entry"], 2),
                "exit": round(exit_p, 2),
                "profit": round(profit, 2),
                "result": "WIN" if profit > 0 else "LOSS",
                "reason": reason,
                "regime": pos.get("regime", ""),
                "zone_type": pos.get("zone", ""),
            })
            
            bal += profit
            if profit < 0:
                consec_l += 1
                if consec_l >= 5:
                    cool_until = bt + timedelta(hours=24)
                elif consec_l >= 3:
                    cool_until = bt + timedelta(hours=4)
                elif consec_l >= 2:
                    cool_until = bt + timedelta(minutes=30)
            else:
                consec_l = 0
            pos = None
            prog_sl = None
            eq.append(bal)
            continue
        
        # ─── 新信号检测 ───
        if daily_t >= 8:
            eq.append(bal)
            continue
        
        # 时段限制 (XAUUSD: 15-00)
        if not (15 <= bt.hour < 24):
            eq.append(bal)
            continue
        
        # ADX
        if np.isnan(adx_v[i]) or adx_v[i] < 22:
            eq.append(bal)
            continue
        
        # 市场状态
        h4i = min(i // 4, len(h4c) - 1)
        h4a = h4_atr_vals[max(0, h4i)]
        hadx = h4adx[max(0, h4i)]
        
        regime = "trend"
        if hadx < 20 and adx_v[i] < 20:
            regime = "ranging"
        if hadx > 35:
            regime = "strong_trend"
        atr_hist = atr_v[max(0, i-30):i+1]
        if len(atr_hist) > 10 and atr_v[i] > np.mean(atr_hist) * 1.8:
            regime = "volatile"
        if regime == "volatile":
            eq.append(bal)
            continue
        
        # EMA方向
        if np.isnan(e14[i]) or np.isnan(e28[i]):
            eq.append(bal)
            continue
        trend = "UP" if e14[i] > e28[i] else "DOWN"
        
        # H4供需区 (每根H4 K线重新检测一次)
        h4_cache_key = h4i
        if h4_cache_key not in h4_zone_cache:
            h4_start = max(0, h4i - 30)
            chunk = h4.iloc[h4_start:h4i+1]
            if len(chunk) >= 15:
                h4_zone_cache[h4_cache_key] = find_zones(chunk)
            else:
                eq.append(bal)
                continue
        zone_dict = h4_zone_cache.get(h4_cache_key, {"demand": [], "supply": []})
        
        zm = 1.2
        zc, zt, flip = None, None, False
        
        for z in zone_dict.get("demand", []):
            if z["strength"] >= zm and price > z["top"] and price - z["top"] < h4a * 3:
                zc, zt = z, "D"
                break
        if not zc:
            for z in zone_dict.get("supply", []):
                if z["strength"] >= zm and price < z["bottom"] and z["bottom"] - price < h4a * 3:
                    zc, zt = z, "S"
                    break
        if not zc:
            # Flip zone
            for z in zone_dict.get("supply", []):
                if price > z["top"]:
                    zc, zt = z, "D"
                    flip = True
                    break
        if not zc:
            for z in zone_dict.get("demand", []):
                if price < z["bottom"]:
                    zc, zt = z, "S"
                    flip = True
                    break
        if not zc:
            eq.append(bal)
            continue
        
        # D1方向过滤
        d1_idx = min(i // 24, len(dc) - 1)
        if d1_idx >= 21 and not np.isnan(de9[d1_idx]) and not np.isnan(de21[d1_idx]):
            d1_dir = "UP" if de9[d1_idx] > de21[d1_idx] else "DOWN"
            direction = "BUY" if d1_dir == "UP" and zt == "D" else "SELL" if d1_dir == "DOWN" and zt == "S" else None
        else:
            direction = "BUY" if trend == "UP" and zt == "D" else "SELL" if trend == "DOWN" and zt == "S" else None
        if not direction:
            eq.append(bal)
            continue
        
        # SL/TP
        sl_mult, rr_mult = 1.5, 2.5
        if regime == "ranging":
            sl_mult = min(sl_mult * 0.7, 0.8)
            rr_mult = max(rr_mult * 0.8, 1.5)
        elif regime == "strong_trend":
            sl_mult = max(sl_mult * 1.2, 1.0)
            rr_mult *= 1.2
        
        buf = max(h4a * 0.1, 0.5)
        if direction == "BUY":
            sl = zc["bottom"] - buf
            tp = price + (price - sl) * rr_mult
        else:
            sl = zc["top"] + buf
            tp = price - (sl - price) * rr_mult
        
        pos = {
            "side": 1 if direction == "BUY" else -1,
            "entry": price,
            "sl": sl,
            "tp": tp,
            "ot": bt,
            "regime": regime,
            "zone": ("F" if flip else zt) + "G",
        }
        daily_t += 1
        eq.append(bal)
    
    # 平最后一笔
    if pos:
        profit = (hc[-1] - pos["entry"]) * pos["side"] * lot * 100
        trades.append({
            "open_time": pos["ot"].strftime("%Y-%m-%d %H:%M"),
            "close_time": pd.Timestamp(ht[-1]).strftime("%Y-%m-%d %H:%M"),
            "direction": "BUY" if pos["side"] == 1 else "SELL",
            "entry": round(pos["entry"], 2),
            "exit": round(hc[-1], 2),
            "profit": round(profit, 2),
            "result": "WIN" if profit > 0 else "LOSS",
            "reason": "回测结束",
            "regime": pos.get("regime", ""),
            "zone_type": pos.get("zone", ""),
        })
        bal += profit
    
    return trades, bal, np.array(eq)


# ═══════════════════════════════════════════════
# Phase 5: 报告
# ═══════════════════════════════════════════════
def report(trades, balance, equity, initial):
    closed = [t for t in trades if t["result"] != "OPEN"]
    if not closed:
        return {"error": "无交易"}
    
    wins = [t for t in closed if t["profit"] > 0]
    losses = [t for t in closed if t["profit"] < 0]
    total = sum(t["profit"] for t in closed)
    wr = len(wins)/len(closed)*100
    
    avg_w = np.mean([t["profit"] for t in wins]) if wins else 0
    avg_l = abs(np.mean([t["profit"] for t in losses])) if losses else 0
    gp = sum(t["profit"] for t in wins) if wins else 0
    gl = abs(sum(t["profit"] for t in losses)) if losses else 0
    pf = gp/gl if gl > 0 else float('inf')
    
    peak = equity[0]
    max_dd = max_dd_pct = 0
    for e in equity:
        if e > peak: peak = e
        dd_pct = (peak-e)/peak*100
        if dd_pct > max_dd_pct: max_dd_pct = dd_pct
    
    rets = np.diff(equity)/(equity[:-1]+1e-10)
    sharpe = np.mean(rets)/np.std(rets)*np.sqrt(365*24) if len(rets) > 1 and np.std(rets) > 0 else 0
    ret_pct = total/initial*100
    calmar = ret_pct/max_dd_pct if max_dd_pct > 0 else 0
    
    cw = cl = mw = ml = 0
    for t in closed:
        if t["profit"] > 0: cw += 1; cl = 0
        else: cl += 1; cw = 0
        mw = max(mw, cw); ml = max(ml, cl)
    
    # 市场状态
    rs = defaultdict(lambda: {"t": 0, "w": 0, "p": 0})
    for t in closed:
        r = t.get("regime", "?").strip()
        rs[r]["t"] += 1
        rs[r]["p"] += t["profit"]
        if t["profit"] > 0: rs[r]["w"] += 1
    
    # 月度
    ms = defaultdict(lambda: {"t": 0, "w": 0, "p": 0})
    for t in closed:
        m = t["close_time"][:7]
        ms[m]["t"] += 1
        ms[m]["p"] += t["profit"]
        if t["profit"] > 0: ms[m]["w"] += 1
    
    return {
        "period": f"{closed[0]['open_time'][:10]} ~ {closed[-1]['close_time'][:10]}",
        "total_trades": len(closed), "wins": len(wins), "losses": len(losses),
        "win_rate": round(wr, 1), "total_pnl": round(total, 2),
        "avg_win": round(avg_w, 2), "avg_loss": round(avg_l, 2),
        "profit_factor": round(pf, 2), "sharpe_ratio": round(sharpe, 2),
        "calmar_ratio": round(calmar, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "max_consec_wins": mw, "max_consec_losses": ml,
        "final_balance": round(initial+total, 2), "return_pct": round(ret_pct, 2),
        "regime_stats": {k: {"trades": v["t"], "wr": round(v["w"]/v["t"]*100, 1) if v["t"]>0 else 0,
                           "pnl": round(v["p"], 2)} for k, v in rs.items()},
        "monthly_stats": {k: {"trades": v["t"], "wr": round(v["w"]/v["t"]*100, 1) if v["t"]>0 else 0,
                              "pnl": round(v["p"], 2)} for k, v in sorted(ms.items())},
    }


# ═══════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 65)
    print("XAUUSD v10.4 — 一年实盘回测 v2")
    print("=" * 65)
    
    ensure_data()
    
    h1 = pd.read_csv(os.path.join(DATA_DIR, "XAUUSD_H1.csv"), parse_dates=["time"])
    h4 = pd.read_csv(os.path.join(DATA_DIR, "XAUUSD_H4.csv"), parse_dates=["time"])
    d1 = pd.read_csv(os.path.join(DATA_DIR, "XAUUSD_D1.csv"), parse_dates=["time"])
    
    print(f"H1: {len(h1)} bars ({str(h1['time'].iloc[0])[:10]} ~ {str(h1['time'].iloc[-1])[:10]})")
    print(f"H4: {len(h4)} bars")
    print(f"D1: {len(d1)} bars")
    
    print("\n回测中...")
    trades, bal, eq = run(h1, h4, d1, 10000, 0.01)
    
    n_closed = len([t for t in trades if t["result"] != "OPEN"])
    print(f"完成: {n_closed} 笔交易, 余额 ${bal:.2f}")
    
    r = report(trades, bal, eq, 10000)
    
    # 打印报告
    print("\n" + "=" * 65)
    print(f"  XAUUSD v10.4  一年实盘回测报告")
    print(f"  期间: {r.get('period', 'N/A')}")
    print(f"  本金: $10,000  |  手数: 0.01")
    print("=" * 65)
    print(f"{'指标':<25} {'值':<20}")
    print("-" * 45)
    
    items = [
        ("总交易数", f"{r.get('total_trades',0)} 笔"),
        ("盈利", f"{r.get('wins',0)} 笔"), ("亏损", f"{r.get('losses',0)} 笔"),
        ("胜率", f"{r.get('win_rate',0)}%"),
        ("总盈亏", f"${r.get('total_pnl',0):.2f}"),
        ("收益率", f"{r.get('return_pct',0):+.2f}%"),
        ("平均盈利", f"${r.get('avg_win',0):.2f}"),
        ("平均亏损", f"${r.get('avg_loss',0):.2f}"),
        ("盈亏比(PF)", f"{r.get('profit_factor',0):.2f}"),
        ("夏普比率", f"{r.get('sharpe_ratio',0):.2f}"),
        ("卡尔玛比率", f"{r.get('calmar_ratio',0):.2f}"),
        ("最大回撤", f"{r.get('max_drawdown_pct',0):.2f}%"),
        ("最大连赢", f"{r.get('max_consec_wins',0)} 笔"),
        ("最大连亏", f"{r.get('max_consec_losses',0)} 笔"),
        ("期末余额", f"${r.get('final_balance',0):.2f}"),
    ]
    for k, v in items:
        print(f"{k:<25} {v:<20}")
    
    print("\n" + "-" * 65)
    print("■ 市场状态分解")
    print("-" * 65)
    print(f"{'状态':<15} {'笔数':<8} {'胜率':<8} {'PnL':<10}")
    for k, v in r.get("regime_stats", {}).items():
        print(f"{k:<15} {v['trades']:<8} {v['wr']:<7.1f}% ${v['pnl']:<8.2f}")
    
    print("\n" + "-" * 65)
    print("■ 月度分解")
    print("-" * 65)
    print(f"{'月份':<10} {'笔数':<8} {'胜率':<8} {'PnL':<10}")
    for k, v in r.get("monthly_stats", {}).items():
        print(f"{k:<10} {v['trades']:<8} {v['wr']:<7.1f}% ${v['pnl']:<8.2f}")
    
    # 评估
    pf = r.get("profit_factor", 0)
    sh = r.get("sharpe_ratio", 0)
    dd = r.get("max_drawdown_pct", 0)
    wrate = r.get("win_rate", 0)
    pnl = r.get("total_pnl", 0)
    trades_n = r.get("total_trades", 0)
    
    print("\n" + "=" * 65)
    print("▶ 评估结论:")
    if trades_n == 0:
        print("  ❌ 零交易 — 信号条件过严")
    elif pnl > 0 and pf > 1.5 and sh > 0.5:
        print("  ✅ 策略表现优秀，风险调整后收益良好")
    elif pnl > 0 and pf > 1.0:
        print("  ✅ 盈利策略，但风控指标需关注")
    elif pnl < 0:
        print("  ❌ 当期亏损")
    print(f"  • 交易频率: {trades_n}/年 = {trades_n/365:.1f} 笔/天")
    print(f"  • 胜率 {wrate}% {'- 良好' if wrate > 35 else '- 偏低，依赖盈亏比'}")
    print(f"  • 盈亏比 {pf} {'- 优秀' if pf > 2 else '- 良好' if pf > 1.5 else '- 及格' if pf > 1 else '- 亏损'}")
    print(f"  • 最大回撤 {dd}% {'- 可控' if dd < 15 else '- 偏高'}")
    print("=" * 65)
    
    # 保存
    out_path = os.path.join(DATA_DIR, "backtest_v104_report.json")
    with open(out_path, "w", encoding='utf-8') as f:
        json.dump(r, f, indent=2, ensure_ascii=False)
    print(f"\n报告已保存: {out_path}")
    if trades:
        pd.DataFrame(trades).to_csv(os.path.join(DATA_DIR, "backtest_v104_trades.csv"), index=False)
        print("交易明细已保存")
