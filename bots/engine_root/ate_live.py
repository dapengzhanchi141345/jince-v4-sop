"""
A.T.E. v10.5 — 自主交易引擎 LIVE版
连接MT5 → 策略池投票 → 执行交易 → 经验学习 → 进化
"""
import sys, os, json, warnings, copy, random, math, time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
warnings.filterwarnings('ignore')

# 导入MT5
import MetaTrader5 as mt5

BASE = r"E:\GoldstrategyEngine"
ATE_LIVE_DIR = os.path.join(BASE, "data", "ate_live")
os.makedirs(ATE_LIVE_DIR, exist_ok=True)
sys.path.insert(0, BASE)

# ═══ 连接MT5 ═══
def connect_mt5():
    if not mt5.initialize():
        mt5.shutdown()
        if not mt5.initialize():
            return False, f"MT5 Init: {mt5.last_error()}"
    if not mt5.login(60043976, password="", server="TradeMaxGlobal-Demo"):
        return False, f"Login: {mt5.last_error()}"
    acc = mt5.account_info()
    mt5.symbol_select("XAUUSD", True)
    return True, f"Balance ${acc.balance:.2f}"

# ═══ 指标 ═══
def ema(vals, p):
    r = np.full(len(vals), np.nan)
    r[p-1] = np.mean(vals[:p])
    a = 2/(p+1)
    for i in range(p, len(vals)): r[i] = vals[i]*a + r[i-1]*(1-a)
    return r

def atr(h, l, p=14):
    tr = np.maximum(h[1:]-l[1:], np.maximum(np.abs(h[1:]-np.roll(h,1)[1:]), np.abs(l[1:]-np.roll(l,1)[1:])))
    r = np.full(len(h), np.nan); r[p] = np.mean(tr[:p])
    a = 1/p
    for i in range(p+1, len(h)): r[i] = tr[i-1]*a + r[i-1]*(1-a)
    return pd.Series(r).ffill().fillna(np.mean(tr[:p])).values

def adx(h, l, c, p=14):
    if len(c) < p*2: return np.zeros(len(c))
    tr = np.maximum(h[1:]-l[1:], np.maximum(np.abs(h[1:]-c[:-1]), np.abs(l[1:]-c[:-1])))
    u, d = h[1:]-h[:-1], l[:-1]-l[1:]
    pdi = 100*pd.Series(np.where((u>d)&(u>0),u,0)).ewm(span=p).mean()/(pd.Series(tr).ewm(span=p).mean()+1e-10)
    mdi = 100*pd.Series(np.where((d>u)&(d>0),d,0)).ewm(span=p).mean()/(pd.Series(tr).ewm(span=p).mean()+1e-10)
    dx = 100*np.abs(pdi-mdi)/(pdi+mdi+1e-10)
    result = pd.Series(dx).ewm(span=p).mean().values
    return np.concatenate([np.zeros(len(c)-len(result)), result])

# ═══ 供需区 ═══
def find_swing(h, l, lb=3):
    swh, swl = [], []
    for i in range(lb, len(h)-lb):
        if h[i] == max(h[i-lb:i+lb+1]): swh.append((i, h[i]))
        if l[i] == min(l[i-lb:i+lb+1]): swl.append((i, l[i]))
    return swh, swl

def find_zones(h4_df):
    h = h4_df['high'].values; l = h4_df['low'].values; c = h4_df['close'].values
    zones = []
    swh, swl = find_swing(h, l, 3)
    for idx, low_val in swl:
        if idx < 2 or idx > len(c)-3: continue
        left_high = max(h[max(0,idx-10):idx+1]); down = left_high - low_val
        if down <= 0: continue
        for j in range(idx+1, min(idx+8, len(c))):
            if c[j] > low_val + down*0.2:
                bh = max(h[idx:j+1]); bl = min(l[idx:j+1])
                ret = (bh-bl)/max(down,1)
                if 0.15 <= ret <= 0.95:
                    zones.append({'type':'D','top':bh,'bottom':max(bl,low_val-(bh-bl)*0.1),'strength':min(5.0,ret*5+0.5)})
                break
    for idx, high_val in swh:
        if idx < 2 or idx > len(c)-3: continue
        left_low = min(l[max(0,idx-10):idx+1]); up = high_val - left_low
        if up <= 0: continue
        for j in range(idx+1, min(idx+8, len(c))):
            if c[j] < high_val - up*0.2:
                bh = max(h[idx:j+1]); bl = min(l[idx:j+1])
                ret = (bh-bl)/max(up,1)
                if 0.15 <= ret <= 0.95:
                    zones.append({'type':'S','top':min(bh,high_val+(bh-bl)*0.1),'bottom':bl,'strength':min(5.0,ret*5+0.5)})
                break
    merged = []
    for z in zones:
        dup = any(m['type']==z['type'] and abs(m['top']-z['top'])/max(m['top'],1)<0.01 and abs(m['bottom']-z['bottom'])/max(m['bottom'],1)<0.01 for m in merged)
        if not dup: merged.append(z)
    return {'demand':[z for z in merged if z['type']=='D'],'supply':[z for z in merged if z['type']=='S']}

# ═══ 策略池 (从进化结果加载) ═══
def load_strategy_pool():
    pool_path = os.path.join(BASE, "data", "ate", "strategy_pool.json")
    if os.path.exists(pool_path):
        with open(pool_path,'r') as f:
            data = json.load(f)
        print(f"加载策略池: {len(data['agents'])} 条, 第{data['generation']}代")
        return data['agents']
    else:
        # 从回测最优参数创建默认池
        print("无进化策略池, 使用默认参数")
        return None

# ═══ 经验记忆系统 LIVE版 ═══
class LiveExperience:
    def __init__(self):
        self.memories = []
        self.path = os.path.join(ATE_LIVE_DIR, 'live_memory.json')
        self.load()
    
    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path,'r') as f: self.memories = json.load(f)
            except: pass
        print(f"经验记忆: {len(self.memories)} 条")
    
    def save(self):
        if len(self.memories) > 500: self.memories = self.memories[-500:]
        with open(self.path,'w') as f: json.dump(self.memories, f, indent=2)
    
    def record(self, state, result):
        self.memories.append({'state':state,'result':result,'time':datetime.now().isoformat()})
        self.save()
    
    def find_similar(self, state, top_k=5):
        if not self.memories: return []
        scored = []
        for mem in self.memories[-200:]:
            s = mem['state']; score = 0
            if abs(state.get('adx',0)-s.get('adx',0))<5: score+=3
            elif abs(state.get('adx',0)-s.get('adx',0))<10: score+=1
            if s.get('regime')==state.get('regime'): score+=3
            if s.get('direction')==state.get('direction'): score+=2
            if s.get('trend')==state.get('trend'): score+=1
            cur_p=state.get('price',0); mem_p=s.get('price',0)
            if cur_p>0 and mem_p>0 and max(cur_p,mem_p)/min(cur_p,mem_p)<1.1: score+=2
            scored.append((score,mem))
        scored.sort(key=lambda x:-x[0])
        return [m for s,m in scored[:top_k] if s>0]


# ═══ 市场分析器 ═══
class MarketAnalyzer:
    """从MT5获取实时数据并分析"""
    def __init__(self):
        self.h1_cache = None
        self.h4_cache = None
        self.d1_cache = None
        self.last_update = None
    
    def refresh(self):
        """获取最新数据"""
        now = datetime.now()
        h1 = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_H1, 0, 100)
        h4 = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_H4, 0, 60)
        d1 = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_D1, 0, 60)
        
        if h1 is None or len(h1) < 50:
            return False, "H1数据不足"
        
        self.h1_cache = pd.DataFrame(h1)
        self.h4_cache = pd.DataFrame(h4) if h4 is not None else None
        self.d1_cache = pd.DataFrame(d1) if d1 is not None else None
        self.last_update = now
        return True, "OK"
    
    def get_current_state(self):
        """获取当前市场状态"""
        if self.h1_cache is None or len(self.h1_cache) < 60:
            return None
        
        h1 = self.h1_cache
        hc = h1['close'].values; hh = h1['high'].values; hl = h1['low'].values
        
        adx_v = adx(hh, hl, hc)
        atr_v = atr(hh, hl)
        e14 = ema(hc, 14); e28 = ema(hc, 28)
        
        price = hc[-1]
        adx_val = adx_v[-1]
        trend = "UP" if e14[-1] > e28[-1] else "DOWN"
        
        # 市场状态
        regime = "trend"
        if self.h4_cache is not None:
            h4c = self.h4_cache['close'].values
            h4adx = adx(self.h4_cache['high'].values, self.h4_cache['low'].values, h4c)
            if len(h4adx) >= 2:
                hadx = h4adx[-1]
                if hadx < 20 and adx_val < 20: regime = "ranging"
                if hadx > 35: regime = "strong_trend"
        
        atr_hist = atr_v[-30:]
        if len(atr_hist) > 10 and atr_v[-1] > np.mean(atr_hist) * 1.8:
            regime = "volatile"
        
        return {
            'price': round(price, 2),
            'adx': round(adx_val, 1),
            'trend': trend,
            'regime': regime,
            'atr': round(atr_v[-1], 2),
            'time': datetime.now().isoformat(),
        }
    
    def has_h4_zone(self, state):
        """检查当前价格是否有H4供需区"""
        if self.h4_cache is None or len(self.h4_cache) < 30:
            return None
        
        h4 = self.h4_cache
        chunk = h4.iloc[-30:]
        zd = find_zones(chunk)
        price = state['price']
        h4a = atr(h4['high'].values, h4['low'].values)[-1]
        
        direction = None
        for z in zd.get('demand',[]):
            if z['strength']>=1.0 and price>z['top'] and price-z['top']<h4a*3:
                direction = "BUY"; break
        if not direction:
            for z in zd.get('supply',[]):
                if z['strength']>=1.0 and price<z['bottom'] and z['bottom']-price<h4a*3:
                    direction = "SELL"; break
        
        return direction


# ═══ 决策引擎 ═══
class TradingDecider:
    """基于策略池和经验做决策"""
    def __init__(self, agents_config):
        self.agents = agents_config  # list of agent params
        self.experience = LiveExperience()
        self.trade_count = 0
    
    def decide(self, state, zone_dir):
        """做出交易决策"""
        if state is None:
            return {'action':'HOLD','reason':'无市场数据'}
        
        price = state['price']
        adx_val = state['adx']
        regime = state['regime']
        trend = state['trend']
        
        # 过滤: volatile不交易
        if regime == 'volatile':
            return {'action':'HOLD','reason':'高波动市场, 不交易'}
        
        # 时段过滤: 只在15:00-24:00交易
        hour = datetime.now().hour
        if not (15 <= hour < 24):
            return {'action':'HOLD','reason':'非交易时段'}
        
        # ADX过滤: 太低不交易
        if adx_val < 18:
            return {'action':'HOLD','reason':'ADX太低, 市场方向不明'}
        
        # 策略池投票 (简化版: 用agent参数判断)
        buy_votes = 0
        sell_votes = 0
        total_weight = 0
        
        for agent in self.agents:
            p = agent['params']
            # 每个agent用自己的参数判断
            agent_buy = (trend=='UP' and zone_dir=='BUY' and adx_val>=p['adx_min'])
            agent_sell = (trend=='DOWN' and zone_dir=='SELL' and adx_val>=p['adx_min'])
            
            # D1过滤
            if p.get('d1_filter', 1) and self.d1_cache is not None:
                dc = self.d1_cache['close'].values
                de9 = ema(dc, 9); de21 = ema(dc, 21)
                if len(de9) >= 21:
                    d1_up = de9[-1] > de21[-1]
                    if d1_up:
                        agent_buy = agent_buy and zone_dir=='BUY'
                        agent_sell = False
                    else:
                        agent_sell = agent_sell and zone_dir=='SELL'
                        agent_buy = False
            
            # 经验加持
            similar = self.experience.find_similar(state, 3)
            exp_bonus = 0
            if similar:
                wr = sum(1 for m in similar if m['result'].get('profit',0)>0) / len(similar)
                exp_bonus = (wr - 0.5) * 2
            
            weight = max(0.1, agent.get('fitness', 10))
            if agent_buy:
                buy_votes += weight * (1 + exp_bonus)
            if agent_sell:
                sell_votes += weight * (1 + exp_bonus)
            total_weight += weight
        
        # 决策
        total = buy_votes + sell_votes
        if total == 0:
            return {'action':'HOLD','reason':'策略池无共识'}
        
        buy_ratio = buy_votes / total
        confidence = abs(buy_ratio - 0.5) * 2
        
        action = 'HOLD'
        reason = '共识不足'
        if buy_ratio > 0.65 and confidence > 0.2:
            action = 'BUY'
            reason = f'策略池{buy_votes/total_weight*100:.0f}%看多+{zone_dir}'
        elif buy_ratio < 0.35 and confidence > 0.2:
            action = 'SELL'
            reason = f'策略池{sell_votes/total_weight*100:.0f}%看空+{zone_dir}'
        
        return {
            'action': action,
            'confidence': round(confidence, 2),
            'buy_ratio': round(buy_ratio, 3),
            'reason': reason,
            'agents_agree': round(max(buy_ratio, 1-buy_ratio)*100, 1),
        }


# ═══ 执行器 ═══
class TradeExecutor:
    """执行交易 — 开仓/止损/止盈"""
    def __init__(self):
        self.last_ticket = None
        self.last_entry = None
        self.last_sl = None
        self.last_tp = None
    
    def execute(self, decision, price, atr_val, lot=0.01):
        """执行交易"""
        if decision['action'] == 'HOLD':
            return {'executed': False, 'reason': decision['reason']}
        
        # SL/TP
        sl_mult, rr_mult = 1.5, 2.5
        if decision['action'] == 'BUY':
            sl = price - atr_val * sl_mult
            tp = price + (price - sl) * rr_mult
            order_type = mt5.ORDER_TYPE_BUY
        else:
            sl = price + atr_val * sl_mult
            tp = price - (sl - price) * rr_mult
            order_type = mt5.ORDER_TYPE_SELL
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": "XAUUSD",
            "volume": lot,
            "type": order_type,
            "price": price,
            "sl": round(sl, 2),
            "tp": round(tp, 2),
            "deviation": 200,
            "magic": 20261050,
            "comment": "A.T.E.v10.5",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            self.last_ticket = result.order
            self.last_entry = price
            self.last_sl = sl
            self.last_tp = tp
            return {
                'executed': True,
                'ticket': result.order,
                'action': decision['action'],
                'entry': round(price, 2),
                'sl': round(sl, 2),
                'tp': round(tp, 2),
                'reason': decision['reason'],
            }
        else:
            return {'executed': False, 'reason': f"下单失败: {result.comment if result else 'unknown'}"}
    
    def check_position(self):
        """检查当前持仓"""
        pos = mt5.positions_get(symbol="XAUUSD")
        if pos and len(pos) > 0:
            p = pos[0]
            return {
                'has_position': True,
                'ticket': p.ticket,
                'type': 'BUY' if p.type == 0 else 'SELL',
                'entry': p.price_open,
                'current': p.price_current,
                'profit': p.profit,
                'sl': p.sl,
                'tp': p.tp,
            }
        return {'has_position': False}


# ═══ 主循环 ═══
def live_loop(interval_seconds=3600):
    """自主交易主循环 — 每小时检查一次"""
    print("="*65)
    print("  A.T.E. v10.5 — 自主交易引擎 LIVE")
    print("="*65)
    
    # 连接
    ok, msg = connect_mt5()
    if not ok:
        print(f"[FATAL] {msg}")
        return
    print(f"[MT5] {msg}")
    
    # 加载策略池
    agents_config = load_strategy_pool()
    if agents_config is None:
        # 默认池
        agents_config = [{'params':{'adx_min':20,'zone_str_min':1.0,'d1_filter':1},'fitness':20}]
    
    analyzer = MarketAnalyzer()
    experience = LiveExperience()
    executor = TradeExecutor()
    
    # 第一次刷新数据
    ok, msg = analyzer.refresh()
    if not ok:
        print(f"[ERR] {msg}")
        mt5.shutdown()
        return
    
    print(f"\n[START] 自主交易已启动, 每{interval_seconds//60}分钟检查一次")
    print(f"[TIME] {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    cycle = 0
    while True:
        try:
            cycle += 1
            now = datetime.now()
            
            # 获取市场状态
            ok, _ = analyzer.refresh()
            if not ok:
                print(f"[{now.strftime('%H:%M')}] [WARN] 数据刷新失败, 重试中...")
                time.sleep(60)
                continue
            
            state = analyzer.get_current_state()
            if state is None:
                time.sleep(60)
                continue
            
            zone_dir = analyzer.has_h4_zone(state)
            price = state['price']
            regime = state['regime']
            
            print(f"\n[{now.strftime('%H:%M')}] 金价=${price:.2f} | ADX={state['adx']} | {regime} | Zone={zone_dir or '无'}")
            
            # 检查现有持仓
            pos = executor.check_position()
            if pos['has_position']:
                print(f"  持仓: {pos['type']} @ ${pos['entry']:.2f} | 浮动: ${pos['profit']:.2f}")
                # 不重复开仓
                time.sleep(interval_seconds)
                continue
            
            # 决策
            decider = TradingDecider(agents_config)
            decider.experience = experience
            decider.d1_cache = analyzer.d1_cache
            
            decision = decider.decide(state, zone_dir)
            print(f"  决策: {decision['action']} (置信度{decision['confidence']}) | {decision['reason']}")
            
            # 执行
            if decision['action'] != 'HOLD' and decision['confidence'] > 0.2:
                result = executor.execute(decision, price, state['atr'], lot=0.01)
                if result['executed']:
                    print(f"  ✅ 开仓: {result['action']} @ ${result['entry']:.2f} | SL=${result['sl']:.2f} TP=${result['tp']:.2f}")
                    experience.record(state, {'action':decision['action'],'entry':result['entry'],'profit':0})
                else:
                    print(f"  ❌ 开仓失败: {result['reason']}")
            else:
                print(f"  ⏸ 等待: {decision['reason']}")
            
            # 每60分钟检查一次
            for _ in range(interval_seconds // 60):
                # 检查持仓盈亏
                pos = executor.check_position()
                if pos['has_position']:
                    # 检查是否有新增平仓交易
                    deals = mt5.history_deals_get(now - timedelta(hours=1), datetime.now())
                    if deals:
                        for d in deals[-5:]:
                            if d.comment == "A.T.E.v10.5" and d.profit != 0:
                                # 记录交易
                                experience.record(state, {
                                    'action': 'CLOSE',
                                    'entry': d.price,
                                    'profit': d.profit,
                                    'reason': 'TP' if d.profit > 0 else 'SL',
                                })
                                print(f"  [CLOSE] 平仓 {'W' if d.profit>0 else 'L'} ${d.profit:.2f}")
                    
                    if cycle % 10 == 0:
                        print(f"  持仓: {pos['type']} @ ${pos['entry']:.2f} 浮动=${pos['profit']:.2f}")
                time.sleep(60)
            
            # 每10轮报告一次
            if cycle % 10 == 0:
                acc = mt5.account_info()
                print(f"\n  [STATUS] 余额${acc.balance:.2f} 净值${acc.equity:.2f} 浮盈${acc.profit:.2f}")
        
        except KeyboardInterrupt:
            print("\n[STOP] 用户停止")
            break
        except Exception as e:
            print(f"[ERR] {e}")
            time.sleep(60)
    
    mt5.shutdown()
    print("[DONE] MT5已断开")


# ═══ 首次运行: 连接测试 + 启动 ═══
if __name__ == '__main__':
    # 先测试连接
    ok, msg = connect_mt5()
    if ok:
        print(f"[OK] {msg}")
        mt5.shutdown()
        
        # 启动
        print("\n启动自主交易? (按Ctrl+C停止)")
        live_loop(interval_seconds=3600)  # 每小时检查一次
    else:
        print(f"[ERR] {msg}")
