"""
SDP v6.2 — 全品种参数优化引擎

一键回测所有品种，自动寻找最优参数组合
输出: 每品种最佳参数 + 完整统计对比
"""
import sys, os, json, time
import numpy as np, pandas as pd
from datetime import datetime
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
os.environ["MARKET_TYPE"] = "CRYPTO"

# ═══════════════════════════════════════
# 品种配置 (交易所/杠杆/点值不同)
# ═══════════════════════════════════════
SYMBOLS = {
    "XAUUSD": {"type": "FOREX", "tick_val": 0.01, "start": "2026-06-20", "end": "2026-07-05"},
    "EURUSD": {"type": "FOREX", "tick_val": 0.00001, "start": "2026-06-20", "end": "2026-07-05"},
    "GBPUSD": {"type": "FOREX", "tick_val": 0.00001, "start": "2026-06-20", "end": "2026-07-05"},
    "BTCUSD": {"type": "CRYPTO", "tick_val": 0.01, "start": "2026-06-20", "end": "2026-07-05"},
    "ETHUSD": {"type": "CRYPTO", "tick_val": 0.001, "start": "2026-06-20", "end": "2026-07-05"},
}

# ═══════════════════════════════════════
# 参数搜索空间
# ═══════════════════════════════════════
PARAM_GRID = {
    "sl_buffer": [0.3, 0.5, 1.0, 1.5],     # SL = zone + buffer*ATR
    "rr_ratio": [1.5, 2.0, 2.5, 3.0],       # 盈亏比
    "adx_min": [18, 22, 26],                 # ADX过滤
    "zone_min_strength": [1.0, 1.5, 2.0],    # 供需区最小强度
}

# ═══════════════════════════════════════
# 回测引擎 (单次)
# ═══════════════════════════════════════
def load_data(symbol, start, end):
    """从MT5加载多周期数据"""
    import MetaTrader5 as mt5
    MT5_PATH = r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe"
    if not mt5.initialize(path=MT5_PATH):
        return None, None, None
    mt5.login(60043976, password="", server="TradeMaxGlobal-Demo")
    
    utc_from = int(pd.Timestamp(start).timestamp())
    utc_to = int(pd.Timestamp(end).timestamp())
    
    h4 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H4, utc_from, utc_to)
    h1 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, utc_from, utc_to)
    m5 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, utc_from, utc_to)
    
    mt5.shutdown()
    
    def to_df(data):
        if data is None or len(data) == 0: return None
        df = pd.DataFrame(data)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df
    
    return to_df(h4), to_df(h1), to_df(m5)

def ema(arr, period):
    if len(arr) < period: return np.full(len(arr), arr[-1])
    r = np.full(len(arr), np.nan)
    r[period-1] = np.mean(arr[:period])
    for i in range(period, len(arr)):
        r[i] = arr[i] * (2/(period+1)) + r[i-1] * (1 - 2/(period+1))
    return r

def calc_adx(high, low, close):
    if len(close) < 28: return 0
    period = 14
    tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
    up = high[1:] - high[:-1]; dn = low[:-1] - low[1:]
    pdi = 100 * pd.Series(np.where((up > dn) & (up > 0), up, 0)).ewm(span=period).mean() / (pd.Series(tr).ewm(span=period).mean() + 1e-10)
    mdi = 100 * pd.Series(np.where((dn > up) & (dn > 0), dn, 0)).ewm(span=period).mean() / (pd.Series(tr).ewm(span=period).mean() + 1e-10)
    dx = 100 * abs(pdi - mdi) / (pdi + mdi + 1e-10)
    return float(dx.ewm(span=period).mean().iloc[-1])

def run_single_backtest(symbol, start, end, params):
    """单次回测"""
    from strategies.supply_demand import SupplyDemandSMC
    
    sl_buf = params["sl_buffer"]
    rr = params["rr_ratio"]
    adx_min = params["adx_min"]
    zone_min = params["zone_min_strength"]
    
    h4, h1, m5 = load_data(symbol, start, end)
    if h4 is None or len(h4) < 15:
        return None
    
    sd = SupplyDemandSMC({
        "swing_lookback": 20, "base_min_bars": 1, "base_max_bars": 5,
        "retracement_min": 0.20, "retracement_max": 0.90,
    })
    
    # H1指标
    h1["ema20"] = ema(h1["close"].values, 20)
    h1["ema50"] = ema(h1["close"].values, 50)
    
    trades = []
    position = None
    balance = 1000
    init_balance = 1000
    equity_curve = [1000]
    
    for i in range(5, len(h4)):
        h4_bar = h4.iloc[i]
        h4_time = h4_bar["time"]
        h4_close = h4_bar["close"]
        h4_high = h4_bar["high"]
        h4_low = h4_bar["low"]
        
        # ─── SL/TP检查 ───
        if position:
            hit = None
            if position["side"] == 1:  # BUY
                if h4_low <= position["sl"]: hit = "SL"
                elif h4_high >= position["tp"]: hit = "TP"
            else:  # SELL
                if h4_high >= position["sl"]: hit = "SL"
                elif h4_low <= position["tp"]: hit = "TP"
            
            if hit:
                close_price = position["sl"] if hit == "SL" else position["tp"]
                profit = (close_price - position["entry"]) * position["side"] * 0.01 * 100
                trades[-1]["close_time"] = h4_time
                trades[-1]["exit"] = close_price
                trades[-1]["profit"] = round(profit, 2)
                trades[-1]["result"] = "WIN" if profit > 0 else "LOSS"
                trades[-1]["close_reason"] = hit
                balance += profit
                position = None
                equity_curve.append(balance)
                continue
        
        # ─── 1. 供需区检测 ───
        chunk = h4.iloc[max(0,i-60):i+1]
        zones = sd.detect_zones(chunk)
        
        # 4H ATR
        tr = np.maximum(h4.iloc[i-14:i+1]["high"].values[1:] - h4.iloc[i-14:i+1]["low"].values[1:],
                        np.maximum(np.abs(h4.iloc[i-14:i+1]["high"].values[1:] - h4.iloc[i-14:i+1]["close"].values[:-1]),
                                   np.abs(h4.iloc[i-14:i+1]["low"].values[1:] - h4.iloc[i-14:i+1]["close"].values[:-1])))
        h4_atr = float(np.mean(tr)) if len(tr) > 0 else 50
        
        has_zone = False
        zone_candidate = None
        zone_type = None
        
        for z in zones.get("demand", []):
            if z.strength < zone_min: continue
            if h4_close > z.top and h4_close - z.top < h4_atr * 2:
                has_zone = True
                zone_candidate = z
                zone_type = "DEMAND"
                break
        
        if not has_zone:
            for z in zones.get("supply", []):
                if z.strength < zone_min: continue
                if h4_close < z.bottom and z.bottom - h4_close < h4_atr * 2:
                    has_zone = True
                    zone_candidate = z
                    zone_type = "SUPPLY"
                    break
        
        if not has_zone: continue
        
        # ─── 2. H1趋势 ───
        h1_bars = h1[h1["time"] <= h4_time]
        if len(h1_bars) < 28: continue
        
        h1_last = h1_bars.iloc[-1]
        price = h1_last["close"]
        ema20_v = h1_last["ema20"]
        ema50_v = h1_last["ema50"]
        
        # 计算ADX
        chunk_h1 = h1_bars.iloc[-30:]
        adx_val = calc_adx(chunk_h1["high"].values, chunk_h1["low"].values, chunk_h1["close"].values)
        
        trend = "RANGING"
        if adx_val < adx_min:
            trend = "RANGING"
        elif price > ema50_v:
            trend = "BULLISH"
        elif price < ema50_v:
            trend = "BEARISH"
        
        # 方向匹配
        direction = None
        if trend == "BULLISH" and zone_type == "DEMAND":
            direction = "BUY"
        elif trend == "BEARISH" and zone_type == "SUPPLY":
            direction = "SELL"
        
        if not direction: continue
        
        # ─── 3. M5确认 ───
        if m5 is not None:
            m5_bars = m5[(m5["time"] > h4_time - pd.Timedelta(hours=4)) & (m5["time"] <= h4_time)]
            if len(m5_bars) >= 5:
                confirmed = False
                for k in range(3, len(m5_bars)):
                    c = m5_bars.iloc[k]
                    cp = m5_bars.iloc[k-1]
                    body = abs(c["close"] - c["open"])
                    body_p = abs(cp["close"] - cp["open"])
                    low_w = min(c["close"], c["open"]) - c["low"]
                    high_w = c["high"] - max(c["close"], c["open"])
                    
                    if direction == "BUY":
                        if low_w > body * 2 and c["close"] > c["open"]: confirmed = True
                        elif body > body_p * 1.5 and c["close"] > c["open"] and cp["close"] < cp["open"]: confirmed = True
                    else:
                        if high_w > body * 2 and c["close"] < c["open"]: confirmed = True
                        elif body > body_p * 1.5 and c["close"] < c["open"] and cp["close"] > cp["open"]: confirmed = True
                if not confirmed: continue
        
        # ─── 执行 ───
        atr_val = h4_atr
        if direction == "BUY":
            entry = h4_close
            sl = zone_candidate.bottom - max(atr_val * sl_buf, 2.0)
            tp = entry + (entry - sl) * rr
        else:
            entry = h4_close
            sl = zone_candidate.top + max(atr_val * sl_buf, 2.0)
            tp = entry - (sl - entry) * rr
        
        position = {"side": 1 if direction == "BUY" else -1, "entry": entry, "sl": sl, "tp": tp}
        trades.append({
            "open_time": h4_time, "direction": direction, "entry": entry,
            "sl": sl, "tp": tp, "trend": trend, "adx": round(adx_val, 1),
            "close_time": None, "exit": None, "profit": None, "result": None
        })
    
    # 最终平仓
    if position and len(trades) > 0:
        last_price = h4["close"].iloc[-1]
        profit = (last_price - position["entry"]) * position["side"] * 0.01 * 100
        trades[-1]["close_time"] = h4["time"].iloc[-1]
        trades[-1]["exit"] = last_price
        trades[-1]["profit"] = round(profit, 2)
        trades[-1]["result"] = "WIN" if profit > 0 else "LOSS"
        balance += profit
    
    # ─── 统计 ───
    closed = [t for t in trades if t.get("profit") is not None]
    if len(closed) < 3:
        return None
    
    profits = [t["profit"] for t in closed]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    win_rate = len(wins) / len(closed) if closed else 0
    avg_win = np.mean(wins) if wins else 0
    avg_loss = abs(np.mean(losses)) if losses else 1
    
    # 最大回撤
    peak = init_balance
    max_dd = 0
    eq = init_balance
    for p in profits:
        eq += p
        if eq > peak: peak = eq
        dd = (peak - eq) / peak * 100
        if dd > max_dd: max_dd = dd
    
    return {
        "total_return": (balance / init_balance - 1) * 100,
        "trades": len(closed),
        "win_rate": win_rate * 100,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else 0,
        "max_drawdown": max_dd,
        "net_profit": balance - init_balance,
        "score": win_rate * (sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else 0) * 100,
    }

def optimize_symbol(symbol, cfg):
    """对单个品种做参数扫描"""
    print(f"\n{'='*60}")
    print(f"优化: {symbol} ({cfg['type']})")
    print(f"期间: {cfg['start']} ~ {cfg['end']}")
    print(f"{'='*60}")
    
    best = None
    best_params = None
    results = []
    
    total = (len(PARAM_GRID["sl_buffer"]) * len(PARAM_GRID["rr_ratio"]) * 
             len(PARAM_GRID["adx_min"]) * len(PARAM_GRID["zone_min_strength"]))
    count = 0
    
    for sb in PARAM_GRID["sl_buffer"]:
        for rr in PARAM_GRID["rr_ratio"]:
            for adx in PARAM_GRID["adx_min"]:
                for zs in PARAM_GRID["zone_min_strength"]:
                    count += 1
                    params = {"sl_buffer": sb, "rr_ratio": rr, "adx_min": adx, "zone_min_strength": zs}
                    
                    result = run_single_backtest(symbol, cfg["start"], cfg["end"], params)
                    if result is None: continue
                    
                    results.append((params, result))
                    
                    if best is None or result["score"] > best["score"]:
                        best = result
                        best_params = params
                    
                    sys.stdout.write(f"\r  [{count}/{total}] SL={sb} RR={rr} ADX>{adx} Z>{zs} → "
                                   f"${result['net_profit']:.0f} WR={result['win_rate']:.0f}% PF={result['profit_factor']:.1f}")
                    sys.stdout.flush()
    
    print(f"\n")
    
    # 输出最优
    if best:
        print(f"\n🏆 {symbol} 最优参数:")
        print(f"  SL缓冲区: {best_params['sl_buffer']}×ATR")
        print(f"  盈亏比:  1:{best_params['rr_ratio']}")
        print(f"  ADX门槛: >{best_params['adx_min']}")
        print(f"  区最小强度: >{best_params['zone_min_strength']}")
        print(f"━━━━━━━━━━━━━━━━━━━━━")
        print(f"  总成交:  {best['trades']} 笔")
        print(f"  胜率:    {best['win_rate']:.1f}%")
        print(f"  净利润:  ${best['net_profit']:.2f}")
        print(f"  盈亏比:  {best['profit_factor']:.2f}")
        print(f"  最大回撤: {best['max_drawdown']:.1f}%")
        print(f"  得分:    {best['score']:.0f}")
        
        # 保存最优参数
        return {
            "symbol": symbol,
            "best_params": best_params,
            "stats": best,
            "all_results": sorted(results, key=lambda x: x[1]["score"], reverse=True)[:10],
        }
    return None

# ═══════════════════════════════════════
# 主程序
# ═══════════════════════════════════════
if __name__ == "__main__":
    t0 = time.time()
    
    print("=" * 60)
    print("  SDP v6.2 全品种参数优化引擎")
    print(f"  {len(SYMBOLS)}个品种 × {len(PARAM_GRID['sl_buffer'])*len(PARAM_GRID['rr_ratio'])*len(PARAM_GRID['adx_min'])*len(PARAM_GRID['zone_min_strength'])}个参数组合")
    print("=" * 60)
    
    all_best = {}
    for sym, cfg in SYMBOLS.items():
        result = optimize_symbol(sym, cfg)
        if result:
            all_best[sym] = result
    
    # 汇总报告
    print(f"\n\n{'='*60}")
    print("📊 全品种最优参数汇总")
    print(f"{'='*60}")
    print(f"{'品种':<10} {'SL×ATR':<10} {'RR':<8} {'ADX>':<8} {'区强>':<8} {'成交':<8} {'胜率':<8} {'净利':<10} {'回撤':<8}")
    print(f"{'-'*70}")
    
    for sym, r in all_best.items():
        p = r["best_params"]
        s = r["stats"]
        print(f"{sym:<10} {p['sl_buffer']:<10} 1:{p['rr_ratio']:<6} {p['adx_min']:<8} {p['zone_min_strength']:<8} {s['trades']:<8} {s['win_rate']:<7.1f}% ${s['net_profit']:<7.2f} {s['max_drawdown']:<7.1f}%")
    
    # 更新self_evolve默认参数
    print(f"\n{'='*60}")
    print("写入最优参数到 self_evolve.py...")
    
    updates = {}
    for sym, r in all_best.items():
        p = r["best_params"]
        updates[sym] = {
            "sl_atr": p["sl_buffer"],
            "rr_ratio": p["rr_ratio"],
            "min_adx": p["adx_min"],
            "min_zone_strength": p["zone_min_strength"],
        }
    
    # 更新self_evolve.py
    import re
    se_path = os.path.join(BASE, "self_evolve.py")
    with open(se_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 替换DEFAULT_PARAMS部分
    new_params = "DEFAULT_PARAMS = {\n"
    for sym, up in updates.items():
        new_params += f'    "{sym}": {{"sl_atr": {up["sl_atr"]}, "rr_ratio": {up["rr_ratio"]}, '
        new_params += f'"min_adx": {up["min_adx"]}, "min_zone_strength": {up["min_zone_strength"]}, "risk_percent": 1.0}},\n'
    new_params += "}"
    
    # 找到并替换DEFAULT_PARAMS块
    pattern = r"DEFAULT_PARAMS = \{[^}]+\}"
    new_content = re.sub(pattern, new_params, content, flags=re.DOTALL)
    
    with open(se_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    
    print("[OK] self_evolve.py 已更新!")
    
    # 保存完整报告
    report_path = os.path.join(BASE, "logs", "optimization_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(all_best, f, indent=2, default=str)
    print(f"[OK] 报告已保存: {report_path}")
    
    elapsed = time.time() - t0
    print(f"\n总用时: {elapsed:.0f}秒 ({elapsed/60:.1f}分钟)")
