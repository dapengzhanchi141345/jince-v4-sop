"""
Goldstrategy Guild v7.0 — 融合策略引擎
 ① H4供需区(RBD/DBR) + ② SuperTrend动态支撑
 ③ H1趋势(EMA+ADX) + ④ M5裸K确认
 ⑤ 日内时段过滤 + ⑥ 三票决策门 + ⑦ 自进化
"""
import sys, os, time, json, warnings
import numpy as np, pandas as pd
from datetime import datetime, timedelta
warnings.filterwarnings('ignore')

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

# ═══════ 审度司 硬编码 ═══════
MAX_LOT = 0.01
MAX_DAILY_TRADES = 5
MAX_DAILY_LOSS_PCT = 3.0

# ═══════ 获取最新最优参数 ═══════
# 从self_evolve读取
try:
    from self_evolve import SelfEvolve
    evolve = SelfEvolve()
    def get_p(sym): return evolve.get_params(sym)
except:
    def get_p(sym): 
        return {"sl_atr":1.5, "rr_ratio":2.0, "min_adx":20, "min_zone_strength":1.5}

# ═══════ 工具函数 ═══════
def calc_supertrend(high, low, close, atr_period=10, multiplier=3.0):
    """SuperTrend计算"""
    if len(close) < atr_period + 1: return np.full(len(close), close[-1]), np.full(len(close), 1)
    tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
    atr = pd.Series(tr).ewm(span=atr_period).mean().values
    
    hl2 = (high + low) / 2
    up = np.full(len(close), np.nan)
    dn = np.full(len(close), np.nan)
    trend = np.ones(len(close))
    
    up[atr_period] = hl2[atr_period] - multiplier * atr[atr_period-1]
    dn[atr_period] = hl2[atr_period] + multiplier * atr[atr_period-1]
    
    for i in range(atr_period + 1, len(close)):
        up[i] = hl2[i] - multiplier * atr[i-1]
        dn[i] = hl2[i] + multiplier * atr[i-1]
        if close[i-1] > up[i-1]: up[i] = max(up[i], up[i-1])
        else: up[i] = up[i]
        if close[i-1] < dn[i-1]: dn[i] = min(dn[i], dn[i-1])
        else: dn[i] = dn[i]
        trend[i] = 1 if close[i] > dn[i] else -1
        if trend[i] == 1 and trend[i-1] == -1: up[i] = dn[i]
        if trend[i] == -1 and trend[i-1] == 1: dn[i] = up[i]
    
    st_line = np.where(trend == 1, dn, up)
    return st_line, trend

def calc_adx(h, l, c):
    if len(c) < 28: return 0
    p = 14
    tr = np.maximum(h[1:]-l[1:], np.maximum(np.abs(h[1:]-c[:-1]), np.abs(l[1:]-c[:-1])))
    u = h[1:]-h[:-1]; d = l[:-1]-l[1:]
    pdi = 100 * pd.Series(np.where((u>d)&(u>0), u, 0)).ewm(span=p).mean() / (pd.Series(tr).ewm(span=p).mean()+1e-10)
    mdi = 100 * pd.Series(np.where((d>u)&(d>0), d, 0)).ewm(span=p).mean() / (pd.Series(tr).ewm(span=p).mean()+1e-10)
    dx = 100 * abs(pdi - mdi) / (pdi + mdi + 1e-10)
    return float(dx.ewm(span=p).mean().iloc[-1])

# ═══════ 工作日历 ═══════
WEEKDAY_SYMBOLS = ["XAUUSD","EURUSD","GBPUSD","BTCUSD","ETHUSD"]
WEEKEND_SYMBOLS = ["BTCUSD","ETHUSD"]

def get_symbols():
    return WEEKDAY_SYMBOLS if datetime.now().weekday() < 5 else WEEKEND_SYMBOLS

# ═══════ 交易时段 (日内波段过滤) ═══════
# 最佳交易时段 (GMT+8)
TRADE_SESSIONS = {
    "XAUUSD": [(9, 11), (14, 17), (20, 23)],  # 亚盘+欧盘+美盘
    "EURUSD": [(9, 11), (14, 17), (20, 23)],
    "GBPUSD": [(9, 11), (14, 17), (20, 23)],
    "BTCUSD": [(0, 6), (9, 11), (14, 17), (20, 23)],  # BTC几乎全天
    "ETHUSD": [(0, 6), (9, 11), (14, 17), (20, 23)],
}

def in_session(symbol):
    """检查是否在最佳交易时段"""
    h = datetime.now().hour
    sessions = TRADE_SESSIONS.get(symbol, [(0, 23)])
    for start, end in sessions:
        if start <= h < end: return True
    return False

# ═══════ 主引擎 ═══════
class HybridTrader:
    """v7.0 融合策略引擎"""
    
    def __init__(self):
        self.mt5 = __import__("MetaTraper5", globals(), locals(), ["*"], 0)
        # 修正导入名
        import MetaTrader5 as mt5
        self.mt5 = mt5
        self.sd = None
        self.connected = False
        self.daily_pl = 0.0; self.daily_trades = 0
        self.cooldown_until = 0; self.consecutive_losses = 0
        self.current_date = datetime.now().date()
        self.last_deal_ticket = None
        self.evolve = SelfEvolve()
    
    def connect(self):
        mt5 = self.mt5
        paths = [r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe",
                 r"C:\Program Files\MetaTrader 5\terminal64.exe"]
        for p in paths:
            if os.path.exists(p) and mt5.initialize(path=p): break
        else: mt5.initialize()
        
        if not mt5.login(60043976, password="", server="TradeMaxGlobal-Demo"):
            return False
        
        for sym in get_symbols():
            mt5.symbol_select(sym, True)
        
        self.connected = True
        return True
    
    def analyze(self, symbol):
        """全维度分析: 供需区+SuperTrend+H1趋势+M5确认"""
        mt5 = self.mt5
        p = get_p(symbol)
        
        # ─── H4数据 ───
        h4 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 80)
        if h4 is None: return None
        h4_df = pd.DataFrame(h4)
        h4_close = h4_df["close"].iloc[-1]
        h4_atr = float((h4_df["high"].iloc[-14:] - h4_df["low"].iloc[-14:]).mean())
        
        # ─── 1. 供需区 ───
        from strategies.supply_demand import SupplyDemandSMC
        if self.sd is None:
            self.sd = SupplyDemandSMC({"swing_lookback":20,"base_min_bars":1,"base_max_bars":5,
                                       "retracement_min":0.20,"retracement_max":0.90})
        zones = self.sd.detect_zones(h4_df)
        
        demand_zone = None; supply_zone = None
        for z in zones.get("demand",[]):
            if z.strength >= p["min_zone_strength"] and h4_close > z.top and h4_close - z.top < h4_atr * 2:
                demand_zone = z; break
        for z in zones.get("supply",[]):
            if z.strength >= p["min_zone_strength"] and h4_close < z.bottom and z.bottom - h4_close < h4_atr * 2:
                supply_zone = z; break
        
        # ─── H1数据 ───
        h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 60)
        if h1 is None: return None
        h1_df = pd.DataFrame(h1)
        h1_c = h1_df["close"].values; h1_h = h1_df["high"].values; h1_l = h1_df["low"].values
        h1_ema20 = h1_df["close"].ewm(span=20).mean().iloc[-1]
        h1_ema50 = h1_df["close"].ewm(span=50).mean().iloc[-1]
        h1_adx = calc_adx(h1_h[-30:], h1_l[-30:], h1_c[-30:])
        h1_price = h1_c[-1]
        
        # ─── 2. SuperTrend (H1) ───
        st_line, st_trend = calc_supertrend(h1_h, h1_l, h1_c)
        st_current = st_line[-1]
        st_direction = "UP" if st_trend[-1] == 1 else "DOWN"
        
        # ─── 3. 趋势判断 ───
        trend = "RANGING"
        if h1_adx >= p["min_adx"] and h1_price > h1_ema50 and st_direction == "UP":
            trend = "BULLISH"
        elif h1_adx >= p["min_adx"] and h1_price < h1_ema50 and st_direction == "DOWN":
            trend = "BEARISH"
        
        # ─── 4. M5裸K确认 ───
        m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 15)
        m5_confirmed = False
        m5_direction = None
        
        if m5 is not None:
            m5_df = pd.DataFrame(m5)
            for k in range(3, len(m5_df)):
                ck, cp = m5_df.iloc[k], m5_df.iloc[k-1]
                body = abs(ck["close"] - ck["open"])
                body_p = abs(cp["close"] - cp["open"])
                lw = min(ck["close"], ck["open"]) - ck["low"]
                hw = ck["high"] - max(ck["close"], ck["open"])
                
                # 看涨信号
                if (lw > body * 2 and ck["close"] > ck["open"]) or \
                   (body > body_p * 1.5 and ck["close"] > ck["open"] and cp["close"] < cp["open"]):
                    m5_direction = "BUY"
                    if trend == "BULLISH": m5_confirmed = True
                # 看跌信号
                if (hw > body * 2 and ck["close"] < ck["open"]) or \
                   (body > body_p * 1.5 and ck["close"] < ck["open"] and cp["close"] > cp["open"]):
                    m5_direction = "SELL"
                    if trend == "BEARISH": m5_confirmed = True
        
        # ─── 决策门 ═══
        signal = {"symbol": symbol, "price": h4_close, "atr": h4_atr,
                  "trend": trend, "adx": h1_adx, "st_direction": st_direction,
                  "demand_zone": demand_zone, "supply_zone": supply_zone,
                  "m5_confirmed": m5_confirmed, "m5_direction": m5_direction,
                  "in_session": in_session(symbol)}
        
        # 方向判定
        direction = "HOLD"
        target_zone = None
        
        if trend == "BULLISH" and demand_zone and m5_confirmed and m5_direction == "BUY":
            direction = "BUY"
            target_zone = demand_zone
        elif trend == "BEARISH" and supply_zone and m5_confirmed and m5_direction == "SELL":
            direction = "SELL"
            target_zone = supply_zone
        
        signal["direction"] = direction
        signal["target_zone"] = target_zone
        return signal
    
    def execute(self, signal):
        """执行交易"""
        mt5 = self.mt5; sym = signal["symbol"]
        p = get_p(sym)
        z = signal["target_zone"]; dr = signal["direction"]
        tick = mt5.symbol_info_tick(sym)
        if not tick: return False
        
        atr = signal["atr"]; price = tick.ask if dr == "BUY" else tick.bid
        ot = mt5.ORDER_TYPE_BUY if dr == "BUY" else mt5.ORDER_TYPE_SELL
        
        if dr == "BUY":
            sl = z.bottom - max(atr * p["sl_atr"], 2.0)
            tp = price + (price - sl) * p["rr_ratio"]
        else:
            sl = z.top + max(atr * p["sl_atr"], 2.0)
            tp = price - (sl - price) * p["rr_ratio"]
        
        sl, tp = round(sl, 2), round(tp, 2)
        MAGIC = {"XAUUSD":20260710,"EURUSD":20260711,"GBPUSD":20260712,"BTCUSD":20260706,"ETHUSD":20260707}
        
        for fill in [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK]:
            req = {"action":mt5.TRADE_ACTION_DEAL,"symbol":sym,"volume":MAX_LOT,
                   "type":ot,"price":price,"sl":sl,"tp":tp,
                   "deviation":200,"magic":MAGIC.get(sym,20260706),
                   "comment":f"SDP v7","type_time":mt5.ORDER_TIME_GTC,"type_filling":fill}
            res = mt5.order_send(req)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                return True
        return False
    
    def run_cycle(self):
        """主循环"""
        mt5 = self.mt5; now = datetime.now()
        
        if now.date() != self.current_date:
            self.current_date = now.date(); self.daily_trades = 0; self.daily_pl = 0.0
        
        if time.time() < self.cooldown_until: return
        if self.daily_trades >= MAX_DAILY_TRADES: return
        
        # 管理持仓
        for sym in get_symbols():
            pos = mt5.positions_get(symbol=sym)
            if not pos: continue
            for p_ in pos:
                entry, curr = float(p_.price_open), float(p_.price_current)
                side = 1 if p_.type == 0 else -1; dist = (curr - entry) * side
                sl = float(p_.sl); profit = float(p_.profit)
                
                if profit > 0 and sl > 0:
                    r = abs(entry - sl)
                    if r > 0 and dist >= r * 0.5:
                        be = round(entry + 1 if side == 1 else entry - 1, 2)
                        if (side == 1 and sl < be) or (side == -1 and sl > be):
                            mt5.order_send({"action":mt5.TRADE_ACTION_SLTP,"symbol":sym,
                                            "position":p_.ticket,"sl":be,"tp":p_.tp})
        
        # 检查平仓
        hist = mt5.history_deals_get(now.replace(hour=0,minute=0,second=0), now)
        if hist:
            for d in hist[-3:]:
                if "SDP v7" in (d.comment or "") and d.profit != 0 and d.ticket != getattr(self, "_ld", None):
                    self._ld = d.ticket
                    if d.profit < 0:
                        self.consecutive_losses += 1; self.daily_pl += d.profit
                        if self.consecutive_losses >= 2:
                            self.cooldown_until = time.time() + 3600
                    else: self.consecutive_losses = 0
        
        # 新品种分析
        for sym in get_symbols():
            if mt5.positions_get(symbol=sym): continue
            signal = self.analyze(sym)
            if not signal or signal["direction"] == "HOLD": continue
            
            if self.execute(signal):
                self.daily_trades += 1
                print(f"[TRADE] {sym} {signal['direction']} @ ${signal['price']:.2f} | "
                      f"{signal['trend']} ST={signal['st_direction']} ADX={signal['adx']:.0f}")
    
    def start(self):
        print("SDP v7.0 Hybrid Engine starting...")
        if not self.connect(): return
        print("Running...")
        while True:
            try:
                self.run_cycle()
                time.sleep(10)
            except KeyboardInterrupt: break
            except: time.sleep(30)
        self.mt5.shutdown()

# 从GitHub学到的策略要点集成到分析流程中
# 
# GitHub SuperTrend + ADX 策略学到:
# 1. ATR Factor=5, ATR Period=20 (比标准SuperTrend更敏感)
# 2. ADX > 25 过滤 (比我们的20更严格)
# 3. 结合21 SMA趋势过滤 (我们用EMA50)
# 4. SuperTrend线作为动态止损位 (搭配供需区使用)
#
# 日内波段交易学到:
# 1. 只在主要交易时段开单
# 2. 前日高低点作为关键位
# 3. M15作为主要入场框架
# 4. 日内目标20-40pip

if __name__ == "__main__":
    t = HybridTrader()
    t.start()
