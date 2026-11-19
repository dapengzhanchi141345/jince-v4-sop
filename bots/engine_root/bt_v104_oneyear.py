"""
XAUUSD 真实数据下载 + v10.4 策略回测
1年: 2025-07-01 ~ 2026-07-01
修正: 使用真实 SupplyDemandSMC 模块
"""
import sys, os, json, warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict

warnings.filterwarnings('ignore')
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
DATA_DIR = os.path.join(BASE, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# 引入真实供需区检测模块
from strategies.supply_demand import SupplyDemandSMC


# ═══════════════════════════════════════════════
# Phase 1: 从MT5下载真实数据
# ═══════════════════════════════════════════════
def download_data():
    """下载1年 XAUUSD H1/H4/D1 数据"""
    import MetaTrader5 as mt5
    
    # 连接MT5
    MT5_PATH = r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe"
    if not mt5.initialize(path=MT5_PATH):
        print(f"[ERR] MT5 初始化失败: {mt5.last_error()}")
        # Try auto
        mt5.shutdown()
        if not mt5.initialize():
            print(f"[ERR] MT5 自动初始化失败: {mt5.last_error()}")
            return False
    
    if not mt5.login(60043976, password="", server="TradeMaxGlobal-Demo"):
        print(f"[ERR] MT5 登录失败: {mt5.last_error()}")
        mt5.shutdown()
        return False
    
    print("[OK] MT5 连接成功")
    
    sym = "XAUUSD"
    end = datetime(2026, 7, 1)
    start = datetime(2025, 7, 1)
    
    utc_from = int(start.timestamp())
    utc_to = int(end.timestamp())
    
    print(f"下载 {sym} 数据: {start.date()} ~ {end.date()}")
    
    # H1
    h1 = mt5.copy_rates_range(sym, mt5.TIMEFRAME_H1, utc_from, utc_to)
    if h1 is None or len(h1) < 100:
        print(f"[ERR] H1 数据不足: {len(h1) if h1 is not None else 0}")
        mt5.shutdown()
        return False
    h1d = pd.DataFrame(h1)
    h1d["time"] = pd.to_datetime(h1d["time"], unit="s")
    h1d.to_csv(os.path.join(DATA_DIR, "XAUUSD_H1.csv"), index=False)
    print(f"[OK] H1: {len(h1d)} bars ({h1d['time'].iloc[0].date()} ~ {h1d['time'].iloc[-1].date()})")
    
    # H4
    h4 = mt5.copy_rates_range(sym, mt5.TIMEFRAME_H4, utc_from, utc_to)
    if h4 is not None and len(h4) > 20:
        h4d = pd.DataFrame(h4)
        h4d["time"] = pd.to_datetime(h4d["time"], unit="s")
        h4d.to_csv(os.path.join(DATA_DIR, "XAUUSD_H4.csv"), index=False)
        print(f"[OK] H4: {len(h4d)} bars")
    
    # D1
    d1 = mt5.copy_rates_range(sym, mt5.TIMEFRAME_D1, utc_from, utc_to)
    if d1 is not None and len(d1) > 20:
        d1d = pd.DataFrame(d1)
        d1d["time"] = pd.to_datetime(d1d["time"], unit="s")
        d1d.to_csv(os.path.join(DATA_DIR, "XAUUSD_D1.csv"), index=False)
        print(f"[OK] D1: {len(d1d)} bars")
    
    mt5.shutdown()
    return True


# ═══════════════════════════════════════════════
# Phase 2: 技术指标
# ═══════════════════════════════════════════════
def calc_ema(values, period):
    if len(values) < period:
        return np.full(len(values), values[-1] if len(values) > 0 else 0)
    result = np.full(len(values), np.nan)
    result[period-1] = np.mean(values[:period])
    alpha = 2 / (period + 1)
    for i in range(period, len(values)):
        result[i] = values[i] * alpha + result[i-1] * (1 - alpha)
    return result

def calc_atr(high, low, close, period=14):
    if len(close) < period + 1:
        return np.full(len(close), np.mean(high[-5:] - low[-5:]) if len(high) >= 5 else 1.0)
    tr = np.maximum(high[1:] - low[1:],
                    np.maximum(np.abs(high[1:] - close[:-1]),
                               np.abs(low[1:] - close[:-1])))
    result = np.full(len(close), np.nan)
    result[period] = np.mean(tr[:period])
    alpha = 1 / period
    for i in range(period + 1, len(close)):
        result[i] = tr[i-1] * alpha + result[i-1] * (1 - alpha)
    return pd.Series(result).ffill().fillna(np.mean(tr[:period]) if len(tr) > period else 1.0).values

def calc_adx(high, low, close, period=14):
    if len(close) < period * 2:
        return np.zeros(len(close))
    tr = np.maximum(high[1:] - low[1:],
                    np.maximum(np.abs(high[1:] - close[:-1]),
                               np.abs(low[1:] - close[:-1])))
    up = high[1:] - high[:-1]
    dn = low[:-1] - low[1:]
    plus_dm = np.where((up > dn) & (up > 0), up, 0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0)
    atr_s = pd.Series(tr).ewm(span=period).mean().values
    pdi = 100 * pd.Series(plus_dm).ewm(span=period).mean().values / (atr_s + 1e-10)
    mdi = 100 * pd.Series(minus_dm).ewm(span=period).mean().values / (atr_s + 1e-10)
    dx = 100 * np.abs(pdi - mdi) / (pdi + mdi + 1e-10)
    result = pd.Series(dx).ewm(span=period).mean().values
    return np.concatenate([np.zeros(len(close) - len(result)), result])


# ═══════════════════════════════════════════════
# Phase 3: 供需区检测 (使用真实 SupplyDemandSMC)
# ═══════════════════════════════════════════════
SD_ENGINE = None  # 全局单例

def get_sd_engine():
    global SD_ENGINE
    if SD_ENGINE is None:
        SD_ENGINE = SupplyDemandSMC({
            "slb": 15, "bmb": 2, "bmx": 10, "rmn": 0.20, "rmx": 0.85
        })
    return SD_ENGINE

def detect_zones_real(h4_df_slice):
    """使用真实 SupplyDemandSMC 检测供需区"""
    sd = get_sd_engine()
    return sd.detect_zones(h4_df_slice)


# ═══════════════════════════════════════════════
# Phase 4: 回测引擎
# ═══════════════════════════════════════════════
def run_backtest(h1_df, h4_df, d1_df, initial_balance=10000, max_lot=0.01):
    """v10.4 策略回测"""
    # 准备数据
    h1 = h1_df.copy()
    h4 = h4_df.copy()
    
    h1_close = h1["close"].values
    h1_high = h1["high"].values
    h1_low = h1["low"].values
    h1_time = h1["time"].values
    
    # 计算指标
    adx_values = calc_adx(h1_high, h1_low, h1_close)
    atr_values = calc_atr(h1_high, h1_low, h1_close)
    ema14 = calc_ema(h1_close, 14)
    ema28 = calc_ema(h1_close, 28)
    
    # H4 数据对齐到H1
    h4_close = h4["close"].values
    h4_high = h4["high"].values
    h4_low = h4["low"].values
    h4_time = h4["time"].values
    h4_adx_values = calc_adx(h4_high, h4_low, h4_close)
    
    # D1
    d1_close = d1_df["close"].values
    d1_ema9 = calc_ema(d1_close, 9)
    d1_ema21 = calc_ema(d1_close, 21)
    
    # 交易记录
    trades = []
    position = None  # {side, entry, sl, tp, open_idx, zone, regime}
    balance = initial_balance
    equity_curve = [balance]
    daily_trades = 0
    last_date = None
    consecutive_losses = 0
    cooldown_until = None
    progressive_sl = None
    
    for i in range(60, len(h1)):
        bar_time = pd.Timestamp(h1_time[i])
        price = h1_close[i]
        bar_high = h1_high[i]
        bar_low = h1_low[i]
        
        # 日重置
        current_date = bar_time.date()
        if last_date != current_date:
            daily_trades = 0
            last_date = current_date
        
        # 冷却检查
        if cooldown_until and bar_time < cooldown_until:
            equity_curve.append(balance)
            continue
        
        # 检查持仓
        if position:
            hit_sl = False
            hit_tp = False
            reason = ""
            
            effective_sl = progressive_sl if progressive_sl is not None else position["sl"]
            
            if position["side"] == 1:  # BUY
                if bar_low <= min(effective_sl, position["sl"]):
                    hit_sl = True
                    reason = "SL"
                elif bar_high >= position["tp"]:
                    hit_tp = True
                    reason = "TP"
            else:  # SELL
                if bar_high >= max(effective_sl, position["sl"]):
                    hit_sl = True
                    reason = "SL"
                elif bar_low <= position["tp"]:
                    hit_tp = True
                    reason = "TP"
            
            if hit_sl:
                profit = (position["sl"] - position["entry"]) * position["side"] * max_lot * 100
                close_price = position["sl"]
            elif hit_tp:
                profit = (position["tp"] - position["entry"]) * position["side"] * max_lot * 100
                close_price = position["tp"]
            else:
                # 渐进止盈
                r_ = abs(position["entry"] - position["sl"])
                if r_ > 0:
                    if position["side"] == 1:
                        d_ = price - position["entry"]
                    else:
                        d_ = position["entry"] - price
                    mult = d_ / r_
                    if mult > 2.0 and progressive_sl is None:
                        new_sl = position["entry"] + 1.5 * r_ if position["side"] == 1 else position["entry"] - 1.5 * r_
                        progressive_sl = new_sl
                    elif mult > 1.0 and progressive_sl is None:
                        new_sl = position["entry"] + 0.5 * r_ if position["side"] == 1 else position["entry"] - 0.5 * r_
                        progressive_sl = new_sl
                    elif mult > 0.5 and progressive_sl is None:
                        progressive_sl = position["entry"]
                
                equity_curve.append(balance)
                continue
            
            # 记录平仓
            trades.append({
                "open_time": position["open_time"].strftime("%Y-%m-%d %H:%M"),
                "close_time": bar_time.strftime("%Y-%m-%d %H:%M"),
                "direction": "BUY" if position["side"] == 1 else "SELL",
                "entry": round(position["entry"], 2),
                "exit": round(close_price, 2),
                "sl": round(position["sl"], 2),
                "tp": round(position["tp"], 2),
                "profit": round(profit, 2),
                "result": "WIN" if profit > 0 else "LOSS",
                "reason": reason,
                "regime": position.get("regime", ""),
                "zone_type": position.get("zone", ""),
                "r_mult": round(abs(close_price - position["entry"]) / max(abs(position["entry"] - position["sl"]), 0.01), 2),
            })
            
            balance += profit
            
            if profit < 0:
                consecutive_losses += 1
                if consecutive_losses >= 5:
                    cooldown_until = bar_time + timedelta(hours=24)
                elif consecutive_losses >= 3:
                    cooldown_until = bar_time + timedelta(hours=4)
                elif consecutive_losses >= 2:
                    cooldown_until = bar_time + timedelta(minutes=30)
            else:
                consecutive_losses = 0
            
            position = None
            progressive_sl = None
            equity_curve.append(balance)
            continue
        
        # 开新仓判断
        if daily_trades >= 8:
            equity_curve.append(balance)
            continue
        
        # 时段限制 (XAUUSD: 15-00)
        if not (15 <= bar_time.hour < 24):
            equity_curve.append(balance)
            continue
        
        # ADX filter
        if adx_values[i] < 22:
            equity_curve.append(balance)
            continue
        
        # Market regime
        h4_idx = min(i // 4, len(h4_adx_values) - 1)
        h4_adx = h4_adx_values[max(0, h4_idx)]
        adx = adx_values[i]
        
        regime = "trend"
        if h4_adx < 20 and adx < 20:
            regime = "ranging"
        if h4_adx > 35:
            regime = "strong_trend"
        atr_hist = atr_values[max(0, i-30):i+1]
        if len(atr_hist) > 10 and atr_values[i] > np.mean(atr_hist) * 1.8:
            regime = "volatile"
        if regime == "volatile":
            equity_curve.append(balance)
            continue
        
        # EMA trend
        if np.isnan(ema14[i]) or np.isnan(ema28[i]):
            equity_curve.append(balance)
            continue
        trend = "UP" if ema14[i] > ema28[i] else "DOWN"
        
        # H4供需区 (使用真实 SupplyDemandSMC)
        h4_idx_full = i // 4
        h4_start = max(0, h4_idx_full - 30)
        h4_chunk = h4.iloc[h4_start:min(h4_idx_full+1, len(h4))]
        if len(h4_chunk) < 15:
            equity_curve.append(balance)
            continue
        zones = detect_zones_real(h4_chunk)
        zone_dict = zones  # SupplyDemandSMC 已返回 {"demand": [], "supply": []}
        
        h4a = np.mean(atr_values[max(0, i-20):i+1]) * 4  # approximate H4 ATR
        zm = 1.2
        
        zc = None
        zt = None
        flip = False
        
        for z in zone_dict.get("demand", []):
            if z.strength >= zm and price > z.top and price - z.top < h4a * 3:
                zc, zt = z, "D"
                break
        if not zc:
            for z in zone_dict.get("supply", []):
                if z.strength >= zm and price < z.bottom and z.bottom - price < h4a * 3:
                    zc, zt = z, "S"
                    break
        if not zc:
            for z in zone_dict.get("supply", []):
                if price > z.top:
                    zc, zt = z, "D"
                    flip = True
                    break
        if not zc:
            for z in zone_dict.get("demand", []):
                if price < z.bottom:
                    zc, zt = z, "S"
                    flip = True
                    break
        if not zc:
            equity_curve.append(balance)
            continue
        
        # D1方向过滤
        d1_day = i // 24
        d1_day = min(d1_day, len(d1_close) - 1)
        if d1_day >= 21 and not np.isnan(d1_ema9[d1_day]) and not np.isnan(d1_ema21[d1_day]):
            d1_dir = "UP" if d1_ema9[d1_day] > d1_ema21[d1_day] else "DOWN"
            direction = "BUY" if d1_dir == "UP" and zt == "D" else "SELL" if d1_dir == "DOWN" and zt == "S" else None
        else:
            direction = "BUY" if trend == "UP" and zt == "D" else "SELL" if trend == "DOWN" and zt == "S" else None
        
        if not direction:
            equity_curve.append(balance)
            continue
        
        # SL/TP: 结构止损
        atr = atr_values[i]
        sl_mult = 1.5
        rr_mult = 2.5
        if regime == "ranging":
            sl_mult = min(sl_mult * 0.7, 0.8)
            rr_mult = max(rr_mult * 0.8, 1.5)
        elif regime == "strong_trend":
            sl_mult = max(sl_mult * 1.2, 1.0)
            rr_mult = rr_mult * 1.2
        
        buf = max(h4a * 0.1, 0.5)
        if direction == "BUY":
            sl = zc.bottom - buf
            tp = price + (price - sl) * rr_mult
        else:
            sl = zc.top + buf
            tp = price - (sl - price) * rr_mult
        
        # 开仓
        position = {
            "side": 1 if direction == "BUY" else -1,
            "entry": price,
            "sl": sl,
            "tp": tp,
            "open_time": bar_time,
            "regime": regime,
            "zone": ("F" if flip else zt) + "G",
        }
        daily_trades += 1
        
        zone_tag = ("F" if flip else zt) + "G"
        action = f"[TRADE] XAUUSD {direction} @ ${price:.2f} | V{regime[0].upper()}{zone_tag}"
        # Print trade in real-time
        if len(trades) % 5 == 0 or True:
            pass  # silent mode
        
        equity_curve.append(balance)
    
    # 平掉最后一笔
    if position:
        profit = (h1_close[-1] - position["entry"]) * position["side"] * max_lot * 100
        trades.append({
            "open_time": position["open_time"].strftime("%Y-%m-%d %H:%M"),
            "close_time": pd.Timestamp(h1_time[-1]).strftime("%Y-%m-%d %H:%M"),
            "direction": "BUY" if position["side"] == 1 else "SELL",
            "entry": round(position["entry"], 2),
            "exit": round(h1_close[-1], 2),
            "sl": round(position["sl"], 2),
            "tp": round(position["tp"], 2),
            "profit": round(profit, 2),
            "result": "WIN" if profit > 0 else "LOSS",
            "reason": "回测结束",
            "regime": position.get("regime", ""),
            "zone_type": position.get("zone", ""),
            "r_mult": round(abs(h1_close[-1] - position["entry"]) / max(abs(position["entry"] - position["sl"]), 0.01), 2),
        })
        balance += profit
    
    return trades, balance, np.array(equity_curve)


# ═══════════════════════════════════════════════
# 绩效报告
# ═══════════════════════════════════════════════
def generate_report(trades, balance, equity, initial_balance):
    closed = [t for t in trades if t["result"] != "OPEN"]
    if not closed:
        return {"error": "无交易"}
    
    wins = [t for t in closed if t["profit"] > 0]
    losses = [t for t in closed if t["profit"] < 0]
    total_pnl = sum(t["profit"] for t in closed)
    
    win_rate = len(wins) / len(closed) * 100 if closed else 0
    avg_win = np.mean([t["profit"] for t in wins]) if wins else 0
    avg_loss = abs(np.mean([t["profit"] for t in losses])) if losses else 0
    
    gross_profit = sum(t["profit"] for t in wins) if wins else 0
    gross_loss = abs(sum(t["profit"] for t in losses)) if losses else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    # Max drawdown
    peak = initial_balance
    max_dd = 0
    max_dd_pct = 0
    for e in equity:
        if e > peak:
            peak = e
        dd = peak - e
        dd_pct = (peak - e) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = dd_pct
    
    # Sharpe
    returns = np.diff(equity) / (equity[:-1] + 1e-10)
    sharpe = 0
    if len(returns) > 1 and np.std(returns) > 0:
        sharpe = np.mean(returns) / np.std(returns) * np.sqrt(365 * 24)
    
    # Calmar
    return_pct = total_pnl / initial_balance * 100
    calmar = return_pct / max_dd_pct if max_dd_pct > 0 else 0
    
    # Max consecutive
    max_consec_wins = 0
    max_consec_losses = 0
    cur_w = 0
    cur_l = 0
    for t in closed:
        if t["profit"] > 0:
            cur_w += 1
            cur_l = 0
        else:
            cur_l += 1
            cur_w = 0
        max_consec_wins = max(max_consec_wins, cur_w)
        max_consec_losses = max(max_consec_losses, cur_l)
    
    # Regime breakdown
    regime_stats = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0})
    for t in closed:
        r = t.get("regime", "unknown")
        regime_stats[r]["trades"] += 1
        regime_stats[r]["pnl"] += t["profit"]
        if t["profit"] > 0:
            regime_stats[r]["wins"] += 1
    
    # Monthly breakdown
    monthly = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0})
    for t in closed:
        m = t["close_time"][:7]
        monthly[m]["trades"] += 1
        monthly[m]["pnl"] += t["profit"]
        if t["profit"] > 0:
            monthly[m]["wins"] += 1
    
    # Avg R multiple
    avg_r = np.mean([t.get("r_mult", 0) for t in closed]) if closed else 0
    
    return {
        "period": f"{closed[0]['open_time'][:10]} ~ {closed[-1]['close_time'][:10]}" if closed else "N/A",
        "total_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "sharpe_ratio": round(sharpe, 2),
        "calmar_ratio": round(calmar, 2),
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "max_consec_wins": max_consec_wins,
        "max_consec_losses": max_consec_losses,
        "final_balance": round(initial_balance + total_pnl, 2),
        "return_pct": round(return_pct, 2),
        "avg_r_multiple": round(avg_r, 2),
        "regime_stats": {k: {
            "trades": v["trades"],
            "wr": round(v["wins"] / v["trades"] * 100, 1) if v["trades"] > 0 else 0,
            "pnl": round(v["pnl"], 2),
        } for k, v in regime_stats.items()},
        "monthly_stats": dict(sorted(monthly.items())),
    }


def print_report(report):
    print("\n" + "=" * 65)
    print(f"  XAUUSD v10.4 实盘回测报告")
    print(f"  期间: {report.get('period', 'N/A')}")
    print(f"  本金: $10,000")
    print("=" * 65)
    
    print(f"\n{'指标':<25} {'值':<15}")
    print("-" * 40)
    
    metrics = [
        ("总交易数", f"{report['total_trades']} 笔"),
        ("盈利", f"{report['wins']} 笔"),
        ("亏损", f"{report['losses']} 笔"),
        ("胜率", f"{report['win_rate']}%"),
        ("总盈亏", f"${report['total_pnl']:.2f}"),
        ("收益率", f"{report['return_pct']:+.2f}%"),
        ("平均盈利", f"${report['avg_win']:.2f}"),
        ("平均亏损", f"${report['avg_loss']:.2f}"),
        ("盈亏比(PF)", f"{report['profit_factor']:.2f}"),
        ("夏普比率", f"{report['sharpe_ratio']:.2f}"),
        ("卡尔玛比率", f"{report['calmar_ratio']:.2f}"),
        ("最大回撤", f"${report['max_drawdown']:.2f} ({report['max_drawdown_pct']:.2f}%)"),
        ("最大连赢", f"{report['max_consec_wins']} 笔"),
        ("最大连亏", f"{report['max_consec_losses']} 笔"),
        ("平均R倍数", f"{report['avg_r_multiple']:.2f}R"),
        ("期末余额", f"${report['final_balance']:.2f}"),
    ]
    
    for label, value in metrics:
        print(f"{label:<25} {value:<15}")
    
    print("\n" + "-" * 65)
    print("■ 市场状态分解")
    print("-" * 65)
    print(f"{'状态':<15} {'笔数':<10} {'胜率':<10} {'PnL':<10}")
    print("-" * 40)
    for regime, stats in report.get("regime_stats", {}).items():
        print(f"{regime:<15} {stats['trades']:<10} {stats['wr']:<9.1f}% ${stats['pnl']:<8.2f}")
    
    print("\n" + "-" * 65)
    print("■ 月度分解")
    print("-" * 65)
    print(f"{'月份':<10} {'笔数':<8} {'胜率':<8} {'PnL':<10}")
    print("-" * 35)
    for month, stats in report.get("monthly_stats", {}).items():
        print(f"{month:<10} {stats['trades']:<8} {stats['wr']:<7.1f}% ${stats['pnl']:<8.2f}")
    
    print("-" * 65)
    
    # 评估
    pf = report["profit_factor"]
    sharpe = report["sharpe_ratio"]
    dd = report["max_drawdown_pct"]
    wr = report["win_rate"]
    total = report["total_pnl"]
    
    print(f"\n▶ 评估结论:")
    if total > 0 and pf > 1.5 and sharpe > 1.0:
        print("  ✅ v10.4 策略整体表现优秀，可部署实盘")
    elif total > 0 and pf > 1.0:
        print("  ✅ v10.4 盈利，但风控还需观察")
    elif total < 0:
        print("  ❌ v10.4 当期亏损，需分析原因")
    
    if wr > 40:
        print(f"  • 胜率 {wr}% - 良好")
    elif wr > 30:
        print(f"  • 胜率 {wr}% - 可接受")
    else:
        print(f"  • 胜率 {wr}% - 偏低，但若盈亏比高可弥补")
    
    if pf > 2.0:
        print(f"  • 盈亏比 {pf} - 优秀")
    elif pf > 1.5:
        print(f"  • 盈亏比 {pf} - 良好")
    elif pf > 1.0:
        print(f"  • 盈亏比 {pf} - 及格")
    else:
        print(f"  • 盈亏比 {pf} - 亏损")
    
    if dd < 10:
        print(f"  • 最大回撤 {dd}% - 风险可控")
    elif dd < 20:
        print(f"  • 最大回撤 {dd}% - 注意风险")
    else:
        print(f"  • 最大回撤 {dd}% - 风险偏高")
    
    print("=" * 65)


# ═══ MAIN ═══
if __name__ == "__main__":
    print("=" * 65)
    print("XAUUSD v10.4  一年实盘回测")
    print("=" * 65)
    
    # Phase 1: 下载数据
    print("\n[Phase 1] 下载真实数据...")
    h1_csv = os.path.join(DATA_DIR, "XAUUSD_H1.csv")
    h4_csv = os.path.join(DATA_DIR, "XAUUSD_H4.csv")
    d1_csv = os.path.join(DATA_DIR, "XAUUSD_D1.csv")
    
    if not all(os.path.exists(f) for f in [h1_csv, h4_csv, d1_csv]):
        if download_data():
            print("数据下载完成")
        else:
            print("[ERR] 数据下载失败，退出")
            sys.exit(1)
    else:
        print("数据已缓存")
    
    h1 = pd.read_csv(h1_csv, parse_dates=["time"])
    h4 = pd.read_csv(h4_csv, parse_dates=["time"])
    d1 = pd.read_csv(d1_csv, parse_dates=["time"])
    
    print(f"H1: {len(h1)} bars ({str(h1['time'].iloc[0])[:10]} ~ {str(h1['time'].iloc[-1])[:10]})")
    print(f"H4: {len(h4)} bars")
    print(f"D1: {len(d1)} bars")
    
    # Phase 2: 回测
    print("\n[Phase 2] 运行回测...")
    trades, final_balance, equity = run_backtest(h1, h4, d1, 10000, 0.01)
    print(f"完成: {len([t for t in trades if t['result'] != 'OPEN'])} 笔交易, 期末余额 ${final_balance:.2f}")
    
    # Phase 3: 报告
    print("\n[Phase 3] 生成报告...")
    report = generate_report(trades, final_balance, equity, 10000)
    print_report(report)
    
    # 保存
    out_path = os.path.join(DATA_DIR, "backtest_v104_report.json")
    with open(out_path, "w", encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n报告已保存: {out_path}")
    
    trades_out = os.path.join(DATA_DIR, "backtest_v104_trades.csv")
    if trades:
        pd.DataFrame(trades).to_csv(trades_out, index=False)
        print(f"交易明细: {trades_out}")
