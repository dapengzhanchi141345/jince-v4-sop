"""
SDP v6.2 — 快速全品种参数优化引擎 v2
改进: 一次性加载所有数据，内存中跑720个参数组合，避免重复MT5连接
"""
import sys, os, json, time
import numpy as np, pandas as pd
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from strategies.supply_demand import SupplyDemandSMC

# ─── 参数 ───
MAX_LOT = 0.01
PARAM_GRID = {
    "sl_buffer": [0.3, 0.5, 1.0, 1.5],
    "rr_ratio": [1.5, 2.0, 2.5, 3.0],
    "adx_min": [18, 22, 26],
    "zone_min_strength": [1.0, 1.5, 2.0],
}
TOTAL_COMBO = len(PARAM_GRID["sl_buffer"]) * len(PARAM_GRID["rr_ratio"]) * \
              len(PARAM_GRID["adx_min"]) * len(PARAM_GRID["zone_min_strength"])

SYMBOLS = {
    "XAUUSD": {"start": "2026-06-20", "end": "2026-07-05"},
    "EURUSD": {"start": "2026-06-20", "end": "2026-07-05"},
    "GBPUSD": {"start": "2026-06-20", "end": "2026-07-05"},
    "BTCUSD": {"start": "2026-06-20", "end": "2026-07-05"},
    "ETHUSD": {"start": "2026-06-20", "end": "2026-07-05"},
}

def calc_adx(high, low, close):
    if len(close) < 28: return 0
    period = 14
    tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
    up = high[1:] - high[:-1]; dn = low[:-1] - low[1:]
    pdi = pd.Series(np.where((up > dn) & (up > 0), up, 0)).ewm(span=period).mean()
    mdi = pd.Series(np.where((dn > up) & (dn > 0), dn, 0)).ewm(span=period).mean()
    atr_s = pd.Series(tr).ewm(span=period).mean()
    pdi = 100 * pdi / (atr_s + 1e-10); mdi = 100 * mdi / (atr_s + 1e-10)
    dx = 100 * abs(pdi - mdi) / (pdi + mdi + 1e-10)
    return float(dx.ewm(span=period).mean().iloc[-1])

def load_data_once():
    """一次性加载所有品种数据"""
    import MetaTrader5 as mt5
    MT5_PATH = r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe"
    if not mt5.initialize(path=MT5_PATH):
        print("[ERR] MT5 init failed"); return None
    mt5.login(60043976, password="", server="TradeMaxGlobal-Demo")
    
    all_data = {}
    for sym in SYMBOLS:
        cfg = SYMBOLS[sym]
        utc_from = int(pd.Timestamp(cfg["start"]).timestamp())
        utc_to = int(pd.Timestamp(cfg["end"]).timestamp())
        
        h4 = mt5.copy_rates_range(sym, mt5.TIMEFRAME_H4, utc_from, utc_to)
        h1 = mt5.copy_rates_range(sym, mt5.TIMEFRAME_H1, utc_from, utc_to)
        m5 = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, utc_from, utc_to)
        
        def to_df(d):
            if d is None: return None
            df = pd.DataFrame(d); df["time"] = pd.to_datetime(df["time"], unit="s"); return df
        
        h4d, h1d, m5d = to_df(h4), to_df(h1), to_df(m5)
        
        if h1d is not None:
            h1d["ema20"] = h1d["close"].ewm(span=20).mean()
            h1d["ema50"] = h1d["close"].ewm(span=50).mean()
        
        all_data[sym] = {"h4": h4d, "h1": h1d, "m5": m5d}
        print(f"  [OK] {sym}: H4={len(h4d) if h4d is not None else 0} H1={len(h1d) if h1d is not None else 0}")
    
    mt5.shutdown()
    return all_data

def run_backtest(data, params):
    """内存中跑回测"""
    h4, h1, m5 = data["h4"], data["h1"], data["m5"]
    sd = SupplyDemandSMC({
        "swing_lookback": 20, "base_min_bars": 1, "base_max_bars": 5,
        "retracement_min": 0.20, "retracement_max": 0.90,
    })
    
    sl_buf, rr, adx_min, z_min = params["sl_buffer"], params["rr_ratio"], params["adx_min"], params["zone_min_strength"]
    trades, position, balance = [], None, 1000.0
    
    for i in range(5, len(h4)):
        bar = h4.iloc[i]
        t, c, hi, lo = bar["time"], bar["close"], bar["high"], bar["low"]
        
        # SL/TP
        if position:
            hit = ("SL" if lo <= position["sl"] else "TP" if hi >= position["tp"] else None) if position["side"] == 1 else \
                  ("SL" if hi >= position["sl"] else "TP" if lo <= position["tp"] else None)
            if hit:
                cp = position["sl"] if hit == "SL" else position["tp"]
                profit = (cp - position["entry"]) * position["side"] * 0.01 * 100
                trades[-1]["ct"], trades[-1]["ex"], trades[-1]["pr"], trades[-1]["res"] = t, cp, profit, "W" if profit > 0 else "L"
                balance += profit; position = None; continue
        
        # 供需区
        chunk = h4.iloc[max(0,i-60):i+1]
        zones = sd.detect_zones(chunk)
        zc, zt = None, None
        
        tr = (hi.iloc[:] if hasattr(hi,'iloc') else hi) - (lo.iloc[:] if hasattr(lo,'iloc') else lo)  # simplified
        h4_atr = float((h4["high"].iloc[max(0,i-14):i+1] - h4["low"].iloc[max(0,i-14):i+1]).mean())
        
        for z in zones.get("demand", []):
            if z.strength >= z_min and c > z.top and c - z.top < h4_atr * 2:
                zc, zt = z, "DEMAND"; break
        if not zc:
            for z in zones.get("supply", []):
                if z.strength >= z_min and c < z.bottom and z.bottom - c < h4_atr * 2:
                    zc, zt = z, "SUPPLY"; break
        if not zc: continue
        
        # H1趋势
        h1b = h1[h1["time"] <= t]
        if len(h1b) < 28: continue
        hl = h1b.iloc[-1]
        p, e20, e50 = hl["close"], hl["ema20"], hl["ema50"]
        adx = calc_adx(h1b["high"].iloc[-30:].values, h1b["low"].iloc[-30:].values, h1b["close"].iloc[-30:].values)
        
        trend = "RANGING"
        if adx >= adx_min:
            trend = "BULLISH" if p > e50 else "BEARISH" if p < e50 else "RANGING"
        
        direction = "BUY" if (trend == "BULLISH" and zt == "DEMAND") else \
                    "SELL" if (trend == "BEARISH" and zt == "SUPPLY") else None
        if not direction: continue
        
        # M5确认
        if m5 is not None:
            m5b = m5[(m5["time"] > t - pd.Timedelta(hours=4)) & (m5["time"] <= t)]
            confirmed = False
            for k in range(3, len(m5b)):
                ck, cpk = m5b.iloc[k], m5b.iloc[k-1]
                b = abs(ck["close"] - ck["open"]); bp = abs(cpk["close"] - cpk["open"])
                lw = min(ck["close"], ck["open"]) - ck["low"]; hw = ck["high"] - max(ck["close"], ck["open"])
                if direction == "BUY":
                    if lw > b * 2 and ck["close"] > ck["open"]: confirmed = True
                    elif b > bp * 1.5 and ck["close"] > ck["open"] and cpk["close"] < cpk["open"]: confirmed = True
                else:
                    if hw > b * 2 and ck["close"] < ck["open"]: confirmed = True
                    elif b > bp * 1.5 and ck["close"] < ck["open"] and cpk["close"] > cpk["open"]: confirmed = True
            if not confirmed: continue
        
        # 执行
        if direction == "BUY":
            entry = c; sl = zc.bottom - max(h4_atr * sl_buf, 2.0); tp = entry + (entry - sl) * rr
        else:
            entry = c; sl = zc.top + max(h4_atr * sl_buf, 2.0); tp = entry - (sl - entry) * rr
        
        position = {"side": 1 if direction == "BUY" else -1, "entry": entry, "sl": sl, "tp": tp}
        trades.append({"ot": t, "dir": direction, "en": entry, "sl": sl, "tp": tp,
                       "ct": None, "ex": None, "pr": None, "res": None})
    
    # 平仓
    if position and trades:
        lp = h4["close"].iloc[-1]
        profit = (lp - position["entry"]) * position["side"] * 0.01 * 100
        trades[-1]["ct"], trades[-1]["ex"], trades[-1]["pr"], trades[-1]["res"] = h4["time"].iloc[-1], lp, profit, "W" if profit > 0 else "L"
        balance += profit
    
    closed = [t for t in trades if t.get("pr") is not None]
    if len(closed) < 3: return None
    
    profits = [t["pr"] for t in closed]
    wins = [p for p in profits if p > 0]; losses = [p for p in profits if p < 0]
    wr = len(wins) / len(closed)
    aw = np.mean(wins) if wins else 0; al = abs(np.mean(losses)) if losses else 1
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else 0
    
    peak, dd, eq = 1000, 0, 1000
    for p in profits:
        eq += p
        if eq > peak: peak = eq
        ddp = (peak - eq) / peak * 100
        if ddp > dd: dd = ddp
    
    return {
        "trades": len(closed), "wr": wr * 100, "aw": aw, "al": al,
        "pf": pf, "dd": dd, "np": balance - 1000,
        "score": wr * pf * 100,
    }

# ═══════════ 主程序 ═══════════
if __name__ == "__main__":
    t0 = time.time()
    print("=" * 60)
    print("  SDP v6.2 快速参数优化引擎")
    print(f"  {len(SYMBOLS)}种 × {TOTAL_COMBO}参数组合 = {len(SYMBOLS)*TOTAL_COMBO}次回测")
    print("=" * 60)
    print("\n[*] 正在加载数据 (一次性)...")
    
    all_data = load_data_once()
    if not all_data:
        print("[ERR] 数据加载失败"); sys.exit(1)
    
    print(f"\n[*] 数据加载完成! 开始参数扫描...\n")
    
    all_best = {}
    combo_count = 0
    total_all = len(SYMBOLS) * TOTAL_COMBO
    
    for sym in SYMBOLS:
        data = all_data[sym]
        if data["h4"] is None or len(data["h4"]) < 15:
            print(f"[SKIP] {sym}: 数据不足"); continue
        
        best, best_params = None, None
        
        for sb in PARAM_GRID["sl_buffer"]:
            for rr in PARAM_GRID["rr_ratio"]:
                for adx in PARAM_GRID["adx_min"]:
                    for zs in PARAM_GRID["zone_min_strength"]:
                        combo_count += 1
                        params = {"sl_buffer": sb, "rr_ratio": rr, "adx_min": adx, "zone_min_strength": zs}
                        result = run_backtest(data, params)
                        
                        if result and (best is None or result["score"] > best["score"]):
                            best, best_params = result, params
                        
                        if combo_count % 20 == 0 or combo_count == total_all:
                            pct = combo_count / total_all * 100
                            sys.stdout.write(f"\r  进度: {combo_count}/{total_all} ({pct:.0f}%)")
                            sys.stdout.flush()
        
        if best:
            all_best[sym] = {"params": best_params, "stats": best}
            p = best_params
            s = best
            print(f"\n\n🏆 {sym}: SL={p['sl_buffer']}× RR=1:{p['rr_ratio']} ADX>{p['adx_min']} Z>{p['zone_min_strength']}")
            print(f"   成交{s['trades']}笔 | WR={s['wr']:.0f}% | PF={s['pf']:.1f} | 净利=${s['np']:.0f} | 回撤{s['dd']:.1f}%")
    
    # 汇总
    print(f"\n\n{'='*60}")
    print("📊 全品种最优参数汇总")
    print(f"{'='*60}")
    print(f"{'品种':<10} {'SL×ATR':<10} {'RR':<8} {'ADX>':<8} {'区强>':<8} {'成交':<8} {'胜率':<8} {'净利':<10} {'回撤':<8}")
    print(f"{'-'*70}")
    
    for sym, r in all_best.items():
        p, s = r["params"], r["stats"]
        print(f"{sym:<10} {p['sl_buffer']:<10} 1:{p['rr_ratio']:<6} {p['adx_min']:<8} {p['zone_min_strength']:<8} {s['trades']:<8} {s['wr']:<7.1f}% ${s['np']:<7.0f} {s['dd']:<7.1f}%")
    
    # 更新self_evolve.py
    import re
    se_path = os.path.join(BASE, "self_evolve.py")
    with open(se_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    new_params = "DEFAULT_PARAMS = {\n"
    for sym, r in all_best.items():
        p = r["params"]
        new_params += f'    "{sym}": {{"sl_atr": {p["sl_buffer"]}, "rr_ratio": {p["rr_ratio"]}, "min_adx": {p["adx_min"]}, "min_zone_strength": {p["zone_min_strength"]}, "risk_percent": 1.0}},\n'
    new_params += "}"
    
    content = re.sub(r"DEFAULT_PARAMS = \{[^}]+\}", new_params, content, flags=re.DOTALL)
    with open(se_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\n[OK] self_evolve.py 已更新最优参数!")
    
    elapsed = time.time() - t0
    print(f"\n总用时: {elapsed:.0f}秒 ({elapsed/60:.1f}分钟)")
