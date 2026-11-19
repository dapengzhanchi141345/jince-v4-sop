"""
SDP v6.2 — 策略回测引擎
回测 H4供需区 + H1趋势 + M5确认 的完整决策流

用法:
    python backtest_sdp.py BTCUSD 2026-06-01 2026-07-05
"""
import sys, os, json
import numpy as np, pandas as pd
from datetime import datetime, timedelta
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["MARKET_TYPE"] = "CRYPTO"
BASE = os.path.dirname(os.path.abspath(__file__))

# ─── 引入策略模块 ───
from strategies.supply_demand import SupplyDemandSMC

# ─── 审度司铁律 ───
MAX_LOT = 0.01
RR_RATIO = 2.0
SL_BUFFER_ATR = 0.3

# ─── 工具函数 ───
def ema(arr, period):
    if len(arr) < period: return np.full(len(arr), arr[-1])
    result = np.full(len(arr), np.nan)
    result[period-1] = np.mean(arr[:period])
    for i in range(period, len(arr)):
        result[i] = arr[i] * (2/(period+1)) + result[i-1] * (1 - 2/(period+1))
    return result

def calc_adx(high, low, close, period=14):
    if len(close) < period * 2: return 0
    tr = np.maximum(high[1:] - low[1:], 
                    np.maximum(np.abs(high[1:] - close[:-1]), 
                               np.abs(low[1:] - close[:-1])))
    up = high[1:] - high[:-1]
    dn = low[:-1] - low[1:]
    plus_dm = np.where((up > dn) & (up > 0), up, 0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0)
    atr_s = pd.Series(tr).ewm(span=period).mean().values
    plus_di = 100 * pd.Series(plus_dm).ewm(span=period).mean().values / (atr_s + 1e-10)
    minus_di = 100 * pd.Series(minus_dm).ewm(span=period).mean().values / (atr_s + 1e-10)
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
    return float(pd.Series(dx).ewm(span=period).mean().values[-1])

def calc_atr(high, low, close, period=14):
    if len(high) < period + 1: return 0
    tr = np.maximum(high[1:] - low[1:],
                    np.maximum(np.abs(high[1:] - close[:-1]),
                               np.abs(low[1:] - close[:-1])))
    return float(pd.Series(tr).ewm(span=period).mean().values[-1])

class SDPBacktest:
    """SDP策略回测引擎"""
    
    def __init__(self, symbol, start_date, end_date, initial_balance=1000):
        self.symbol = symbol
        self.start = pd.to_datetime(start_date)
        self.end = pd.to_datetime(end_date)
        self.balance = initial_balance
        self.equity = initial_balance
        self.initial_balance = initial_balance
        
        # 供需区引擎
        self.sd = SupplyDemandSMC({
            "swing_lookback": 20, "base_min_bars": 1, "base_max_bars": 5,
            "retracement_min": 0.20, "retracement_max": 0.90,
        })
        
        # 交易记录
        self.trades = []
        self.equity_curve = []
        
        # 状态
        self.position = None  # {"side": 1/-1, "entry": price, "sl": , "tp": }
        self.daily_trades = 0
        self.cooldown_until = None
        
        # 从MT5拉数据
        self._load_data()
    
    def _load_data(self):
        """加载H4/H1/M5历史数据"""
        import MetaTrader5 as mt5
        
        MT5_PATH = r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe"
        if not mt5.initialize(path=MT5_PATH):
            print("[ERR] MT5初始化失败")
            sys.exit(1)
        
        # 登录演示账号
        mt5.login(60043976, password="", server="TradeMaxGlobal-Demo")
        
        # 转换日期为MT5 timestamp
        utc_from = int(self.start.timestamp())
        utc_to = int(self.end.timestamp())
        
        print(f"[*] 加载 {self.symbol} 数据...")
        
        # H4数据 (供需区识别)
        h4 = mt5.copy_rates_range(self.symbol, mt5.TIMEFRAME_H4, utc_from, utc_to)
        if h4 is None or len(h4) < 20:
            print(f"[ERR] H4数据不足: {len(h4) if h4 else 0}")
            mt5.shutdown()
            sys.exit(1)
        self.h4 = pd.DataFrame(h4)
        self.h4["time"] = pd.to_datetime(self.h4["time"], unit="s")
        print(f"[OK] H4: {len(self.h4)} 根K线 ({self.h4['time'].iloc[0].strftime('%Y-%m-%d')} ~ {self.h4['time'].iloc[-1].strftime('%Y-%m-%d')})")
        
        # H1数据 (趋势+ADX)
        h1 = mt5.copy_rates_range(self.symbol, mt5.TIMEFRAME_H1, utc_from, utc_to)
        if h1 is None or len(h1) < 50:
            print(f"[ERR] H1数据不足: {len(h1) if h1 else 0}")
            mt5.shutdown()
            sys.exit(1)
        self.h1 = pd.DataFrame(h1)
        self.h1["time"] = pd.to_datetime(self.h1["time"], unit="s")
        print(f"[OK] H1: {len(self.h1)} 根K线")
        
        # M5数据 (入场确认) — 只需部分加载用于模拟
        m5 = mt5.copy_rates_range(self.symbol, mt5.TIMEFRAME_M5, utc_from, utc_to)
        if m5 is not None and len(m5) > 0:
            self.m5 = pd.DataFrame(m5)
            self.m5["time"] = pd.to_datetime(self.m5["time"], unit="s")
            print(f"[OK] M5: {len(self.m5)} 根K线")
        else:
            self.m5 = None
            print("[!] M5数据不可用，使用H1 close模拟")
        
        mt5.shutdown()
        self._preprocess()
    
    def _preprocess(self):
        """数据预处理: 计算技术指标"""
        h1 = self.h1
        h1["ema20"] = ema(h1["close"].values, 20)
        h1["ema50"] = ema(h1["close"].values, 50)
        
        # 逐根计算ADX和ATR
        adx_vals, atr_vals = [], []
        for i in range(len(h1)):
            s = max(0, i-30)
            adx_vals.append(calc_adx(h1["high"].values[s:i+1], h1["low"].values[s:i+1], h1["close"].values[s:i+1]))
            atr_vals.append(calc_atr(h1["high"].values[s:i+1], h1["low"].values[s:i+1], h1["close"].values[s:i+1]))
        h1["adx"] = adx_vals
        h1["atr"] = atr_vals
    
    def run(self):
        """运行回测"""
        print(f"\n{'='*60}")
        print(f"回测: {self.symbol}")
        print(f"期间: {self.start.date()} ~ {self.end.date()}")
        print(f"本金: ${self.initial_balance:.2f}")
        print(f"{'='*60}\n")
        
        h4 = self.h4
        h1 = self.h1
        
        # 每根H4 K线检查一次
        zone_cache = {}  # H4时间→供需区
        
        for i in range(5, len(h4)):
            h4_bar = h4.iloc[i]
            h4_time = h4_bar["time"]
            h4_close = h4_bar["close"]
            
            # ─── 1. 检测供需区 ───
            chunk = h4.iloc[max(0,i-60):i+1]
            zones = self.sd.detect_zones(chunk)
            
            # 找当前价格附近的供需区
            demand = [z for z in zones.get("demand", []) if z.strength >= 1.5 and 
                      h4_close > z.top * 0.98 and h4_close - z.top < self._get_h4_atr(i) * 2]
            supply = [z for z in zones.get("supply", []) if z.strength >= 1.5 and
                      h4_close < z.bottom * 1.02 and z.bottom - h4_close < self._get_h4_atr(i) * 2]
            
            has_demand = len(demand) > 0
            has_supply = len(supply) > 0
            
            # ─── 2. 看H1趋势 ───
            h1_bars = h1[h1["time"] <= h4_time]
            if len(h1_bars) < 30: continue
            
            h1_last = h1_bars.iloc[-1]
            price = h1_last["close"]
            
            # EMA方向
            ema20_v = h1_last["ema20"]
            ema50_v = h1_last["ema50"]
            
            # 市场结构
            swing_highs, swing_lows = [], []
            for j in range(max(0, len(h1_bars)-40), len(h1_bars)):
                if j < 5 or j >= len(h1_bars)-5: continue
                ch = h1_bars.iloc[j]
                if ch["high"] > max(h1_bars.iloc[j-5:j+5]["high"]) and ch["high"] > max(h1_bars.iloc[max(0,j-3):j+3]["high"]):
                    swing_highs.append(ch["high"])
                if ch["low"] < min(h1_bars.iloc[j-5:j+5]["low"]) and ch["low"] < min(h1_bars.iloc[max(0,j-3):j+3]["low"]):
                    swing_lows.append(ch["low"])
            
            # 趋势分类
            adx_val = h1_last["adx"]
            trend = "RANGING"
            if adx_val < 20: trend = "RANGING"
            elif price > ema50_v and (len(swing_highs)<2 or swing_highs[-1] > swing_highs[-2]) and \
                 (len(swing_lows)<2 or swing_lows[-1] > swing_lows[-2]):
                trend = "BULLISH"
            elif price < ema50_v and (len(swing_highs)<2 or swing_highs[-1] < swing_highs[-2]) and \
                 (len(swing_lows)<2 or swing_lows[-1] < swing_lows[-2]):
                trend = "BEARISH"
            
            # ─── 决策门: 三票一致 ───
            h4_vote = None
            if trend == "BULLISH" and has_demand:
                h4_vote = ("BUY", demand[0])
            elif trend == "BEARISH" and has_supply:
                h4_vote = ("SELL", supply[0])
            
            if not h4_vote: continue
            
            direction, zone = h4_vote
            atr_val = h1_last["atr"]
            
            # ─── 3. M5确认(模拟) ───
            if self.m5 is not None:
                m5_bars = self.m5[(self.m5["time"] > h4_time - timedelta(hours=4)) & 
                                   (self.m5["time"] <= h4_time)]
                if len(m5_bars) < 5: continue
                
                confirmed = False
                for k in range(3, len(m5_bars)):
                    m5_chunk = m5_bars.iloc[k-3:k+1]
                    body = abs(m5_chunk["close"].iloc[-1] - m5_chunk["open"].iloc[-1])
                    body_p = abs(m5_chunk["close"].iloc[-2] - m5_chunk["open"].iloc[-2])
                    low_w = min(m5_chunk["close"].iloc[-1], m5_chunk["open"].iloc[-1]) - m5_chunk["low"].iloc[-1]
                    high_w = m5_chunk["high"].iloc[-1] - max(m5_chunk["close"].iloc[-1], m5_chunk["open"].iloc[-1])
                    
                    if direction == "BUY":
                        if low_w > body * 2 and m5_chunk["close"].iloc[-1] > m5_chunk["open"].iloc[-1]:
                            confirmed = True
                        elif body > body_p * 1.5 and m5_chunk["close"].iloc[-1] > m5_chunk["open"].iloc[-1] and \
                             m5_chunk["close"].iloc[-2] < m5_chunk["open"].iloc[-2]:
                            confirmed = True
                    else:
                        if high_w > body * 2 and m5_chunk["close"].iloc[-1] < m5_chunk["open"].iloc[-1]:
                            confirmed = True
                        elif body > body_p * 1.5 and m5_chunk["close"].iloc[-1] < m5_chunk["open"].iloc[-1] and \
                             m5_chunk["close"].iloc[-2] > m5_chunk["open"].iloc[-2]:
                            confirmed = True
                
                if not confirmed: continue
            
            # ─── 如果有持仓先平仓 ───
            self._close_position(h4_close, h4_time, "信号反向" if self.position else "")
            
            # ─── 执行开仓 ───
            if direction == "BUY":
                entry = h4_close
                sl = zone.bottom - max(atr_val * SL_BUFFER_ATR, 2.0)
                tp = entry + (entry - sl) * RR_RATIO
            else:
                entry = h4_close
                sl = zone.top + max(atr_val * SL_BUFFER_ATR, 2.0)
                tp = entry - (sl - entry) * RR_RATIO
            
            self.position = {
                "side": 1 if direction == "BUY" else -1,
                "entry": entry, "sl": sl, "tp": tp,
                "open_time": h4_time, "volume": MAX_LOT,
                "zone_type": zone.type, "zone_str": f'{zone.bottom:.0f}-{zone.top:.0f}',
            }
            
            # 记录开仓
            self.trades.append({
                "open_time": h4_time, "direction": direction, "volume": MAX_LOT,
                "entry": entry, "sl": sl, "tp": tp,
                "zone": f'{zone.bottom:.0f}-{zone.top:.0f}',
                "trend": trend, "adx": round(adx_val, 1),
                "close_time": None, "exit": None, "profit": None, "result": None,
            })
            
            print(f"  [{h4_time.strftime('%m-%d %H:%M')}] OPEN {direction} {MAX_LOT} @ ${entry:.2f} "
                  f"SL=${sl:.2f} TP=${tp:.2f} | {zone.type} {zone.bottom:.0f}-{zone.top:.0f} | {trend} ADX={adx_val:.0f}")
        
        # 最终平仓
        if self.position:
            self._close_position(h4["close"].iloc[-1], h4["time"].iloc[-1], "回测结束")
        
        self._report()
    
    def _close_position(self, price, time, reason=""):
        """平仓"""
        if not self.position:
            return
        
        p = self.position
        profit = (price - p["entry"]) * p["side"] * p["volume"] * 100
        
        # 更新最后一笔trade
        if self.trades:
            last_trade = self.trades[-1]
            last_trade["close_time"] = time
            last_trade["exit"] = price
            last_trade["profit"] = round(profit, 2)
            last_trade["result"] = "WIN" if profit > 0 else "LOSS"
            last_trade["close_reason"] = reason
        
        self.balance += profit
        self.position = None
    
    def _check_sl_tp(self, h4_bar):
        """检查是否触发了SL/TP（在H4 K线范围内检查高低点）"""
        if not self.position: return None
        p = self.position
        high, low = h4_bar["high"], h4_bar["low"]
        
        if p["side"] == 1:  # BUY
            if low <= p["sl"]: return "SL"
            if high >= p["tp"]: return "TP"
        else:
            if high >= p["sl"]: return "SL"
            if low <= p["tp"]: return "TP"
        return None
    
    def _get_h4_atr(self, idx):
        """获取H4的ATR"""
        s = max(0, idx-14)
        h4_chunk = self.h4.iloc[s:idx+1]
        if len(h4_chunk) < 2: return 50
        tr = np.maximum(h4_chunk["high"].values[1:] - h4_chunk["low"].values[1:],
                        np.maximum(np.abs(h4_chunk["high"].values[1:] - h4_chunk["close"].values[:-1]),
                                   np.abs(h4_chunk["low"].values[1:] - h4_chunk["close"].values[:-1])))
        return float(np.mean(tr))
    
    def _report(self):
        """输出回测报告"""
        if not self.trades:
            print("\n[!] 无交易")
            return
        
        df = pd.DataFrame(self.trades)
        closed = df[df["profit"].notna()]
        
        if len(closed) == 0:
            print("\n[!] 无平仓交易")
            return
        
        wins = closed[closed["profit"] > 0]
        losses = closed[closed["profit"] < 0]
        total_pnl = closed["profit"].sum()
        
        print(f"\n{'='*60}")
        print(f"📊 回测报告: {self.symbol}")
        print(f"{'='*60}")
        print(f"  交易期间:  {self.start.date()} ~ {self.end.date()}")
        print(f"  总成交:    {len(closed)} 笔")
        print(f"  盈利:      {len(wins)} 笔")
        print(f"  亏损:      {len(losses)} 笔")
        print(f"  胜率:      {len(wins)/(len(wins)+len(losses))*100:.1f}%" if len(wins)+len(losses) > 0 else "  胜率:  N/A")
        print(f"  总盈亏:    ${total_pnl:.2f}")
        print(f"  最大盈利:  ${wins['profit'].max():.2f}" if len(wins) > 0 else "")
        print(f"  最大亏损:  ${losses['profit'].min():.2f}" if len(losses) > 0 else "")
        print(f"  盈亏比:    {abs(wins['profit'].mean() / losses['profit'].mean()):.2f}" if len(losses) > 0 and losses['profit'].mean() != 0 else "  盈亏比:  N/A")
        print(f"  期初余额:  ${self.initial_balance:.2f}")
        print(f"  期末余额:  ${self.balance:.2f}")
        print(f"  收益率:    {(self.balance/self.initial_balance-1)*100:+.2f}%")
        
        # 逐笔明细
        print(f"\n  逐笔明细:")
        print(f"  {'开仓':<18} {'方向':<6} {'入场':<10} {'出场':<10} {'盈亏':<10} {'结果':<6} {'条件'}")
        print(f"  {'-'*70}")
        for _, t in closed.iterrows():
            ot = pd.to_datetime(t["open_time"]).strftime("%m-%d %H:%M")
            ct = pd.to_datetime(t["close_time"]).strftime("%m-%d %H:%M") if pd.notna(t["close_time"]) else "--"
            print(f"  {ot:<18} {t['direction']:<6} ${t['entry']:<7.2f} ${t['exit']:<7.2f} ${t['profit']:<7.2f} {t['result']:<6} {t['trend']}")
        
        # 保存结果
        result_path = os.path.join(BASE, "logs", f"backtest_{self.symbol}_{self.start.date()}_{self.end.date()}.csv")
        closed.to_csv(result_path, index=False)
        print(f"\n  明细已保存: {result_path}")

if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSD"
    start = sys.argv[2] if len(sys.argv) > 2 else "2026-06-20"
    end = sys.argv[3] if len(sys.argv) > 3 else "2026-07-05"
    
    bt = SDPBacktest(symbol, start, end)
    bt.run()
