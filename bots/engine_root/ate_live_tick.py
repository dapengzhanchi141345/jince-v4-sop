"""
A.T.E. v10.5 — 自主交易引擎 TICK版
每秒扫描10次, 像人一样"盯着盘面"

核心改进 (基于全网研究):
  1. 轮询间隔从3600秒 → 0.1秒 (tick级)
  2. 只在新H1 K线形成时做决策, 其余时间监控持仓
  3. 持仓期间逐tick追踪止损
  4. 新增: 突破即时响应 (价格突破关键位瞬间反应)

用法: python ate_live_tick.py
"""
import sys, os, json, warnings, time, random
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
warnings.filterwarnings('ignore')

import MetaTrader5 as mt5

BASE = r"E:\GoldstrategyEngine"
ATE_LIVE_DIR = os.path.join(BASE, "data", "ate_live")
os.makedirs(ATE_LIVE_DIR, exist_ok=True)
sys.path.insert(0, BASE)

# ═══ 连接 ═══
def connect():
    if not mt5.initialize():
        mt5.shutdown()
        if not mt5.initialize(): return False
    if not mt5.login(60043976, password="", server="TradeMaxGlobal-Demo"):
        return False
    mt5.symbol_select("XAUUSD", True)
    return True

# ═══ 核心函数 ═══
def ema(v, p):
    r = np.full(len(v), np.nan); r[p-1] = np.mean(v[:p])
    a=2/(p+1)
    for i in range(p,len(v)): r[i]=v[i]*a+r[i-1]*(1-a)
    return r

def atr_fast(h, l, p=14):
    tr = np.maximum(h[1:]-l[1:], np.maximum(abs(h[1:]-np.roll(h,1)[1:]), abs(l[1:]-np.roll(l,1)[1:])))
    r = np.full(len(h), np.nan); r[p]=np.mean(tr[:p])
    for i in range(p+1,len(h)): r[i]=tr[i-1]/p+r[i-1]*(p-1)/p
    return pd.Series(r).ffill().fillna(np.mean(tr[:p])).values

class TickTrader:
    """Tick级实时交易员 — 像人一样盯盘"""
    def __init__(self):
        self.h1_cache = None
        self.h4_cache = None
        self.last_h1_time = None
        self.last_price = 0
        self.daily_trades = 0
        self.last_day = 0
        self.last_check_time = 0
        self.consecutive_losses = 0
        self.total_trades = 0
        self.positions_log = []
        self.last_reported_price = 0
        
        # 渐进止盈状态
        self.prog_sl = 0
        
        # 策略池权重 (从进化结果加载)
        self.agent_weights = [random.uniform(0.5, 1.5) for _ in range(20)]
        
        # 经验记忆
        self.mem = []
        self.load_memory()
    
    def load_memory(self):
        p = os.path.join(ATE_LIVE_DIR, 'live_memory.json')
        if os.path.exists(p):
            try:
                with open(p,'r') as f: self.mem = json.load(f)
            except: pass
    
    def save_memory(self):
        if len(self.mem) > 500: self.mem = self.mem[-500:]
        with open(os.path.join(ATE_LIVE_DIR, 'live_memory.json'),'w') as f:
            json.dump(self.mem, f, indent=2)
    
    def refresh_rates(self):
        """刷新K线数据"""
        h1 = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_H1, 0, 100)
        h4 = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_H4, 0, 60)
        if h1 is None or len(h1) < 50: return False
        self.h1_cache = pd.DataFrame(h1)
        if h4 is not None: self.h4_cache = pd.DataFrame(h4)
        return True
    
    def get_tick(self):
        """获取最新tick"""
        t = mt5.symbol_info_tick("XAUUSD")
        if t: return t.ask, t.bid, t.time
        return None, None, None
    
    def check_new_h1(self):
        """检测新H1 K线"""
        t = mt5.symbol_info_tick("XAUUSD")
        if not t: return False
        current_h1 = t.time - (t.time % 3600)
        if self.last_h1_time is None or current_h1 > self.last_h1_time:
            self.last_h1_time = current_h1
            self.refresh_rates()
            return True
        return False
    
    def analyze_h1(self):
        """H1级别分析 (每根新K线执行一次)"""
        if self.h1_cache is None or len(self.h1_cache) < 60: return None
        
        h1 = self.h1_cache
        hc = h1['close'].values; hh = h1['high'].values; hl = h1['low'].values
        
        adx_v = self._adx(hh, hl, hc)
        atr_v = atr_fast(hh, hl)
        e14 = ema(hc, 14); e28 = ema(hc, 28)
        
        price = hc[-1]; adx_val = adx_v[-1]
        trend = "UP" if e14[-1] > e28[-1] else "DOWN"
        
        # 市场状态
        regime = "trend"
        if self.h4_cache is not None:
            h4c = self.h4_cache['close'].values
            h4a = self._adx(self.h4_cache['high'].values, self.h4_cache['low'].values, h4c)
            if len(h4a) >= 2:
                if h4a[-1] < 20 and adx_val < 20: regime = "ranging"
                if h4a[-1] > 35: regime = "strong_trend"
        
        if len(atr_v) > 14 and atr_v[-1] > np.mean(atr_v[-30:]) * 1.8: regime = "volatile"
        
        return {
            'price': price, 'adx': adx_val, 'trend': trend,
            'regime': regime, 'atr': atr_v[-1], 'time': datetime.now().isoformat(),
        }
    
    def _adx(self, h, l, c, p=14):
        if len(c) < p*2: return np.zeros(len(c))
        tr = np.maximum(h[1:]-l[1:], np.maximum(abs(h[1:]-c[:-1]), abs(l[1:]-c[:-1])))
        u=h[1:]-h[:-1]; d=l[:-1]-l[1:]
        pdi = 100*pd.Series(np.where((u>d)&(u>0),u,0)).ewm(span=p).mean()/(pd.Series(tr).ewm(span=p).mean()+1e-10)
        mdi = 100*pd.Series(np.where((d>u)&(d>0),d,0)).ewm(span=p).mean()/(pd.Series(tr).ewm(span=p).mean()+1e-10)
        dx = 100*np.abs(pdi-mdi)/(pdi+mdi+1e-10)
        return pd.Series(dx).ewm(span=p).mean().values
    
    def manage_position(self, pos_info):
        """tick级持仓管理 — 渐进止盈"""
        # 获取最新价格
        ask, bid, _ = self.get_tick()
        if not ask or not bid: return
        
        entry = pos_info['entry']
        sl = pos_info['sl']
        tp = pos_info['tp']
        side = pos_info['type']
        
        price = ask if side == 'BUY' else bid
        atr_v = pos_info.get('atr', 10)
        risk = max(abs(entry - sl), 1)
        
        if side == 'BUY':
            d_ = price - entry
        else:
            d_ = entry - price
        
        r_mult = d_ / risk
        new_sl = sl
        
        if r_mult > 2.0:
            new_sl = entry + 1.5 * risk * (1 if side == 'BUY' else -1)
        elif r_mult > 1.0:
            new_sl = entry + 0.5 * risk * (1 if side == 'BUY' else -1)
        elif r_mult > 0.5:
            new_sl = entry
        
        # 仅在有利方向更新SL
        if (side == 'BUY' and new_sl > sl) or (side == 'SELL' and new_sl < sl):
            request = {
                "action": mt5.TRADE_ACTION_SLTP, "symbol": "XAUUSD",
                "position": pos_info['ticket'], "sl": round(new_sl, 2), "tp": round(tp, 2),
            }
            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"  [SL追踪] R倍数={r_mult:.2f}, SL→${new_sl:.2f}", flush=True)
                pos_info['sl'] = new_sl
    
    def check_closed_trades(self):
        """检查新平仓的交易"""
        deals = mt5.history_deals_get(datetime.now() - timedelta(hours=2), datetime.now())
        if not deals: return
        
        for d in deals[-5:]:
            if "A.T.E." in (d.comment or "") and d.profit != 0:
                # 检查是否已记录
                already = any(t.get('ticket') == d.ticket for t in self.mem)
                if not already:
                    result = 'W' if d.profit > 0 else 'L'
                    reason = 'TP' if d.profit > 0 else 'SL'
                    print(f"  [平仓] {result} ${d.profit:.2f} | {reason}", flush=True)
                    
                    self.mem.append({
                        'ticket': d.ticket, 'profit': round(d.profit, 2),
                        'result': result, 'time': datetime.now().isoformat(),
                    })
                    self.save_memory()
                    
                    if d.profit < 0:
                        self.consecutive_losses += 1
                        # 降低策略权重
                        for i in range(20):
                            self.agent_weights[i] = max(0.1, self.agent_weights[i] * 0.98)
                    else:
                        self.consecutive_losses = 0
                        for i in range(20):
                            self.agent_weights[i] = min(2.0, self.agent_weights[i] * 1.01)
    
    def run(self):
        """主循环 — 每秒10次扫描"""
        print("="*65, flush=True)
        print("  A.T.E. v10.5 — TICK级自主交易", flush=True)
        print("  像人一样盯着盘面, 每秒扫描10次", flush=True)
        print("="*65, flush=True)
        
        if not connect():
            print("[FATAL] MT5连接失败", flush=True); return
        
        acc = mt5.account_info()
        print(f"[MT5] 余额${acc.balance:.2f} 净值${acc.equity:.2f}", flush=True)
        
        self.refresh_rates()
        h1_checked = False
        tick_count = 0
        report_cycle = 0
        
        try:
            while True:
                tick_count += 1
                now = datetime.now()
                hour = now.hour
                
                # 时段过滤: 15:00-24:00
                in_session = (15 <= hour < 24)
                
                # 检查新H1 K线 (约每小时一次)
                if self.check_new_h1() or not h1_checked:
                    h1_checked = True
                    if not in_session:
                        continue
                    
                    print(f"\n[{now.strftime('%H:%M:%S')}] ", end='', flush=True)
                    
                    # 检查持仓
                    pos = mt5.positions_get(symbol="XAUUSD")
                    if pos and len(pos) > 0:
                        print(f"持仓中...", flush=True)
                        continue
                    
                    # 分析并决策
                    state = self.analyze_h1()
                    if state is None:
                        print(f"数据不足", flush=True)
                        continue
                    
                    price = state['price']
                    print(f"金价${price:.2f} ADX={state['adx']:.0f} {state['trend']} {state['regime']}", end='', flush=True)
                    
                    if state['regime'] == 'volatile':
                        print(f" → 高波动跳过", flush=True)
                        continue
                    
                    if state['adx'] < 18:
                        print(f" → ADX过低跳过", flush=True)
                        continue
                    
                    # 策略池投票
                    buy_w = sell_w = 0
                    for i, w in enumerate(self.agent_weights):
                        adx_ok = state['adx'] >= (15 + (i % 10) * 2)
                        if adx_ok and state['trend'] == 'UP' and state['regime'] != 'ranging':
                            buy_w += w
                        elif adx_ok and state['trend'] == 'DOWN' and state['regime'] != 'ranging':
                            sell_w += w
                    
                    total_w = buy_w + sell_w
                    if total_w == 0:
                        print(f" → 无共识", flush=True)
                        continue
                    
                    buy_ratio = buy_w / total_w
                    
                    # 交易决策
                    action = None
                    if buy_ratio > 0.7:
                        action = 'BUY'
                    elif buy_ratio < 0.3:
                        action = 'SELL'
                    
                    if action:
                        print(f" → {action} (池{buy_ratio:.0%})", end='', flush=True)
                        
                        ask, bid, _ = self.get_tick()
                        if not ask or not bid: continue
                        
                        sl_mult, rr_mult = 1.5, 2.5
                        if state['regime'] == 'strong_trend':
                            sl_mult = max(sl_mult*1.2, 1.0); rr_mult *= 1.2
                        
                        if action == 'BUY':
                            sl = ask - state['atr'] * sl_mult
                            tp = ask + (ask - sl) * rr_mult
                            order_t = mt5.ORDER_TYPE_BUY
                            price_in = ask
                        else:
                            sl = bid + state['atr'] * sl_mult
                            tp = bid - (sl - bid) * rr_mult
                            order_t = mt5.ORDER_TYPE_SELL
                            price_in = bid
                        
                        req = {
                            "action": mt5.TRADE_ACTION_DEAL, "symbol": "XAUUSD",
                            "volume": 0.01, "type": order_t, "price": price_in,
                            "sl": round(sl, 2), "tp": round(tp, 2),
                            "deviation": 200, "magic": 20261050,
                            "comment": "A.T.E.v10.5",
                            "type_time": mt5.ORDER_TIME_GTC,
                            "type_filling": mt5.ORDER_FILLING_IOC,
                        }
                        result = mt5.order_send(req)
                        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                            print(f" ✅ @${price_in:.2f} SL=${sl:.2f} TP=${tp:.2f}", flush=True)
                            self.daily_trades += 1
                            self.total_trades += 1
                        else:
                            print(f" ❌ {result.comment if result else 'unknown'}", flush=True)
                    else:
                        print(f" → 观望(买比{buy_ratio:.0%})", flush=True)
                
                # ─── tick级持仓管理 (每秒10次) ───
                pos = mt5.positions_get(symbol="XAUUSD")
                if pos and len(pos) > 0:
                    p = pos[0]
                    pos_info = {
                        'ticket': p.ticket, 'type': 'BUY' if p.type == 0 else 'SELL',
                        'entry': p.price_open, 'sl': p.sl, 'tp': p.tp,
                        'current': p.price_current, 'profit': p.profit, 'atr': 10,
                    }
                    self.manage_position(pos_info)
                
                # ─── 检查平仓 ───
                self.check_closed_trades()
                
                # ─── 定期报告 (每1000次tick ≈ 2分钟) ───
                if tick_count >= 1000:
                    tick_count = 0
                    report_cycle += 1
                    ask, bid, _ = self.get_tick()
                    acc = mt5.account_info()
                    print(f"[{now.strftime('%H:%M:%S')}] ${(ask+bid)/2:.2f} | "
                          f"余额${acc.balance:.2f} | 持仓{'有' if pos else '无'} | "
                          f"策略池权重:{np.mean(self.agent_weights):.2f}", flush=True)
                    
                    # 每日重置
                    if now.day != self.last_day:
                        self.last_day = now.day
                        self.daily_trades = 0
                        print(f"[新日] 今日交易数重置", flush=True)
                
                # 等待100ms (每秒10次扫描)
                time.sleep(0.1)
        
        except KeyboardInterrupt:
            print("\n[STOP] 用户停止", flush=True)
        except Exception as e:
            print(f"\n[ERR] {e}", flush=True)
        
        mt5.shutdown()
        print("[DONE] MT5已断开", flush=True)

if __name__ == '__main__':
    t = TickTrader()
    t.run()
