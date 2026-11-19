"""
v10.5 — 自主交易引擎 (A.T.E.)
核心: 策略池 + 进化算法 + 经验匹配

架构灵感:
  - Aidyia Holdings 强化学习+完全自主模式
  - Sentient Technologies 进化算法策略竞争
  - 专业交易员的"经验匹配"决策模式

核心机制:
  1. 策略池: 20条"虚拟交易员"并行评估市场
  2. 经验回放: 相似市场状态→类似交易的结果→经验匹配
  3. 进化算法: 优胜劣汰, 交叉变异生成新策略
  4. 动态权重: 每条策略根据近期表现获得话语权
  5. 自适应: 亏损→降权, 盈利→加仓, 连续亏→策略替换

@status: EXPERIMENT — v10.5 自主交易引擎
"""
import sys, os, json, warnings, copy, random, math
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Optional, Tuple
warnings.filterwarnings('ignore')

BASE = r"E:\GoldstrategyEngine"
DATA_DIR = os.path.join(BASE, "data")
ATE_DIR = os.path.join(BASE, "data", "ate")
os.makedirs(ATE_DIR, exist_ok=True)
sys.path.insert(0, BASE)

# ═══════════════════════════════════════════════
# 1. 指标函数
# ═══════════════════════════════════════════════
def ema(vals, p):
    r = np.full(len(vals), np.nan)
    r[p-1] = np.mean(vals[:p])
    a = 2/(p+1)
    for i in range(p, len(vals)): r[i] = vals[i]*a + r[i-1]*(1-a)
    return r

def atr(h, l, p=14):
    tr = np.maximum(h[1:]-l[1:], np.maximum(np.abs(h[1:]-np.roll(h,1)[1:]), np.abs(l[1:]-np.roll(l,1)[1:])))
    r = np.full(len(h), np.nan)
    r[p] = np.mean(tr[:p])
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

# ═══════════════════════════════════════════════
# 2. 供需区检测
# ═══════════════════════════════════════════════
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
        left_high = max(h[max(0,idx-10):idx+1])
        down = left_high - low_val
        if down <= 0: continue
        for j in range(idx+1, min(idx+8, len(c))):
            if c[j] > low_val + down*0.2:
                bh = max(h[idx:j+1]); bl = min(l[idx:j+1])
                ret = (bh-bl)/max(down,1)
                if 0.15 <= ret <= 0.95:
                    zones.append({'type':'D','top':bh,'bottom':max(bl,low_val-(bh-bl)*0.1),
                                 'strength':min(5.0,ret*5+0.5)})
                break
    for idx, high_val in swh:
        if idx < 2 or idx > len(c)-3: continue
        left_low = min(l[max(0,idx-10):idx+1])
        up = high_val - left_low
        if up <= 0: continue
        for j in range(idx+1, min(idx+8, len(c))):
            if c[j] < high_val - up*0.2:
                bh = max(h[idx:j+1]); bl = min(l[idx:j+1])
                ret = (bh-bl)/max(up,1)
                if 0.15 <= ret <= 0.95:
                    zones.append({'type':'S','top':min(bh,high_val+(bh-bl)*0.1),'bottom':bl,
                                 'strength':min(5.0,ret*5+0.5)})
                break
    merged = []
    for z in zones:
        dup = False
        for m in merged:
            if m['type']==z['type'] and abs(m['top']-z['top'])/max(m['top'],1)<0.01 and \
               abs(m['bottom']-z['bottom'])/max(m['bottom'],1)<0.01:
                m['strength'] = max(m['strength'],z['strength']); dup = True; break
        if not dup: merged.append(z)
    return {'demand':[z for z in merged if z['type']=='D'],'supply':[z for z in merged if z['type']=='S']}


# ═══════════════════════════════════════════════
# 3. 策略个体 (一条"虚拟交易员")
# ═══════════════════════════════════════════════
PARAM_BOUNDS = {
    'adx_min': (15, 35),
    'zone_str_min': (0.8, 2.0),
    'sl_mult': (0.8, 2.5),
    'rr_mult': (1.5, 4.0),
    'ema_fast': (5, 20),
    'ema_slow': (15, 40),
    'session_start': (12, 18),
    'd1_filter': (0, 1),
}

class TraderAgent:
    """一条虚拟交易员 — 有自己的性格参数和交易历史"""
    def __init__(self, agent_id, params=None, parent=None):
        self.id = agent_id
        self.generation = parent.generation + 1 if parent else 0
        self.parent_id = parent.id if parent else None
        self.birth_time = datetime.now().isoformat()
        
        # 参数: 随机初始化或继承
        if params:
            self.p = dict(params)
        else:
            self.p = {}
            for k, (lo, hi) in PARAM_BOUNDS.items():
                if k == 'd1_filter':
                    self.p[k] = 1 if random.random() > 0.3 else 0
                else:
                    self.p[k] = round(random.uniform(lo, hi), 1)
        
        # 交易历史和绩效
        self.trades: List[Dict] = []
        self.wins = 0
        self.losses = 0
        self.total_pnl = 0.0
        self.total_risk = 0.0  # sum of risk (entry-SL) in $
        self.equity_curve: List[float] = [10000.0]
        
        # 状态
        self.fitness = 0.0
        self.last_pnl = 0.0  # last 20 trades PnL for WFER
        self.wfer = 1.0      # Walk-Forward Efficiency Ratio
        
        # 自适应状态
        self.regime_pnl = defaultdict(float)  # regime -> PnL
        self.recent_wins = 0
        self.recent_losses = 0
        self.consec_wins = 0
        self.consec_losses = 0
    
    def mutate(self, rate=0.3):
        """变异: 参数微调"""
        for k, (lo, hi) in PARAM_BOUNDS.items():
            if random.random() < rate:
                if k == 'd1_filter':
                    self.p[k] = 1 - self.p[k]
                else:
                    delta = random.uniform(-0.3, 0.3) * (hi - lo)
                    self.p[k] = round(max(lo, min(hi, self.p[k] + delta)), 1)
    
    def clone(self, new_id):
        """克隆自己 (用于生成下一代)"""
        child = TraderAgent(new_id, params=self.p, parent=self)
        child.mutate()
        return child
    
    def record_trade(self, trade):
        """记录一笔交易, 更新内部状态"""
        self.trades.append(trade)
        profit = trade['profit']
        risk = abs(trade['entry'] - trade['sl']) * 0.01  # approximate risk in $
        
        self.total_pnl += profit
        self.total_risk += risk
        
        if profit > 0:
            self.wins += 1
            self.recent_wins += 1
            self.recent_losses = 0
            self.consec_wins = max(self.consec_wins, self.recent_wins)
        else:
            self.losses += 1
            self.recent_losses += 1
            self.recent_wins = 0
            self.consec_losses = max(self.consec_losses, self.recent_losses)
        
        # 市场状态跟踪
        regime = trade.get('regime', '?')
        self.regime_pnl[regime] += profit
        
        # 更新最近20笔的WFER
        recent = [t for t in self.trades[-30:] if t.get('result','') in ('WIN','LOSS')]
        if len(recent) >= 10:
            first10 = recent[:len(recent)//2]
            last10 = recent[len(recent)//2:]
            pnl_f = sum(t['profit'] for t in first10) / max(len(first10), 1)
            pnl_l = sum(t['profit'] for t in last10) / max(len(last10), 1)
            # WFER: forward efficiency ratio
            total_risk_last10 = sum(abs(t['entry']-t['sl']) for t in last10) * 0.01
            self.wfer = pnl_l / max(total_risk_last10/len(last10), 0.1)
            self.wfer = max(-1, min(3, self.wfer))  # clip
        
        self.last_pnl = profit
    
    def get_fitness(self):
        """综合适��度评分"""
        n = len([t for t in self.trades if t.get('result','') in ('WIN','LOSS')])
        if n == 0: return -999
        
        wins = [t for t in self.trades if t['profit']>0]
        losses = [t for t in self.trades if t['profit']<0]
        wr = len(wins)/n if n > 0 else 0
        pf = sum(t['profit'] for t in wins) / max(abs(sum(t['profit'] for t in losses)), 1)
        
        # 夏普近似
        returns = [t['profit'] for t in self.trades if t.get('result','') in ('WIN','LOSS')]
        sharpe = np.mean(returns)/max(np.std(returns), 0.01)/100 if returns else 0
        
        # 综合得分: 越高越好
        score = self.total_pnl * 0.01 + wr * 2 + pf * 5 + sharpe * 10
        
        # 惩罚连亏
        if self.consec_losses >= 5:
            score *= 0.5
        
        # 惩罚过度交易
        if n < 5:
            score -= 50  # 数据不足的惩罚
        
        self.fitness = round(score, 1)
        return self.fitness


# ═══════════════════════════════════════════════
# 4. 经验记忆系统
# ═══════════════════════════════════════════════
class ExperienceMemory:
    """经验记忆: 记录市场状态+交易结果, 支持相似匹配"""
    def __init__(self):
        self.memories = []  # [{state, trade_result, ...}]
        self.load()
    
    def load(self):
        path = os.path.join(ATE_DIR, 'experience_memory.json')
        if os.path.exists(path):
            try:
                with open(path,'r') as f: self.memories = json.load(f)
            except: self.memories = []
    
    def save(self):
        os.makedirs(ATE_DIR, exist_ok=True)
        path = os.path.join(ATE_DIR, 'experience_memory.json')
        # 只保留最近500条
        if len(self.memories) > 500:
            self.memories = self.memories[-500:]
        with open(path,'w') as f: json.dump(self.memories, f, indent=2)
    
    def record(self, state: Dict, trade_result: Dict):
        """记录一次经验"""
        self.memories.append({
            'state': state,
            'result': trade_result,
            'time': datetime.now().isoformat(),
        })
        self.save()
    
    def find_similar(self, current_state: Dict, top_k=10) -> List[Dict]:
        """找到最相似的过去经验"""
        if not self.memories:
            return []
        
        scored = []
        for mem in self.memories[-200:]:  # 最近200条
            s = mem['state']
            score = 0
            # ADX相似度
            cur_adx = current_state.get('adx', 0)
            mem_adx = s.get('adx', 0)
            if abs(cur_adx - mem_adx) < 5: score += 3
            elif abs(cur_adx - mem_adx) < 10: score += 1
            
            # 市场状态匹配
            if s.get('regime') == current_state.get('regime'): score += 3
            
            # 方向匹配
            if s.get('direction') == current_state.get('direction'): score += 2
            
            # 趋势匹配
            if s.get('trend') == current_state.get('trend'): score += 1
            
            # 价格水平相似
            cur_price = current_state.get('price', 0)
            mem_price = s.get('price', 0)
            if cur_price > 0 and mem_price > 0:
                price_ratio = max(cur_price, mem_price) / min(cur_price, mem_price)
                if price_ratio < 1.1: score += 2
                elif price_ratio < 1.2: score += 1
            
            scored.append((score, mem))
        
        scored.sort(key=lambda x: -x[0])
        return [m for s, m in scored[:top_k] if s > 0]


# ═══════════════════════════════════════════════
# 5. 策略池 + 进化引擎
# ═══════════════════════════════════════════════
class EvolutionEngine:
    """进化引擎: 管理策略池、评估、选择、进化"""
    def __init__(self, pool_size=20):
        self.pool_size = pool_size
        self.agents: List[TraderAgent] = []
        self.generation = 0
        self.best_agent = None
        self.experience = ExperienceMemory()
        self.evolution_log = []
        self.load_pool()
    
    def load_pool(self):
        """加载或初始化策略池"""
        path = os.path.join(ATE_DIR, 'strategy_pool.json')
        if os.path.exists(path):
            try:
                with open(path,'r') as f:
                    data = json.load(f)
                self.generation = data.get('generation', 0)
                for ad in data.get('agents', []):
                    agent = TraderAgent(ad['id'], params=ad['params'])
                    agent.generation = ad.get('generation', 0)
                    agent.total_pnl = ad.get('total_pnl', 0)
                    agent.wins = ad.get('wins', 0)
                    agent.losses = ad.get('losses', 0)
                    agent.fitness = ad.get('fitness', 0)
                    agent.wfer = ad.get('wfer', 1.0)
                    self.agents.append(agent)
                print(f"加载策略池: {len(self.agents)} 条, 第{self.generation}代")
            except: pass
        
        if not self.agents:
            self.init_pool()
    
    def init_pool(self):
        """初始化策略池"""
        for i in range(self.pool_size):
            agent = TraderAgent(f"agent_{i:03d}")
            self.agents.append(agent)
        print(f"初始化策略池: {self.pool_size} 条随机策略")
    
    def save_pool(self):
        """保存策略池"""
        data = {
            'generation': self.generation,
            'agents': [{
                'id': a.id, 'generation': a.generation, 'parent_id': a.parent_id,
                'params': a.p, 'total_pnl': a.total_pnl,
                'wins': a.wins, 'losses': a.losses,
                'fitness': a.fitness, 'wfer': a.wfer,
            } for a in self.agents],
        }
        with open(os.path.join(ATE_DIR, 'strategy_pool.json'), 'w') as f:
            json.dump(data, f, indent=2)
    
    def evaluate_all(self, h1_df, h4_df, d1_df):
        """对所有策略进行回测评估"""
        print(f"\n评估 {len(self.agents)} 条策略...")
        for i, agent in enumerate(self.agents):
            if i % 5 == 0: print(f"  Agent {i+1}/{len(self.agents)}...", end='', flush=True)
            trades, pnl = self._backtest_agent(agent, h1_df, h4_df, d1_df)
            agent.trades = trades
            # 重置并重新记录
            agent.total_pnl = 0
            agent.wins = 0
            agent.losses = 0
            for t in trades:
                if t.get('result','') in ('WIN','LOSS'):
                    agent.total_pnl += t['profit']
                    if t['profit'] > 0: agent.wins += 1
                    else: agent.losses += 1
            agent.get_fitness()
        print("\n评估完成")
    
    def _backtest_agent(self, agent, h1_df, h4_df, d1_df) -> Tuple[List, float]:
        """用agent的参数跑回测"""
        p = agent.p
        h1 = h1_df.copy(); h4 = h4_df.copy()
        hc = h1['close'].values; hh = h1['high'].values; hl = h1['low'].values; ht = h1['time'].values
        
        adx_v = adx(hh, hl, hc); atr_v = atr(hh, hl)
        e_fast = ema(hc, int(p['ema_fast']))
        e_slow = ema(hc, int(p['ema_slow']))
        
        h4c = h4['close'].values; h4adx = adx(h4['high'].values, h4['low'].values, h4c)
        dc = d1_df['close'].values
        de9 = ema(dc, 9) if p['d1_filter'] else None
        de21 = ema(dc, 21) if p['d1_filter'] else None
        
        trades = []; pos = None; bal = 10000.0
        
        for i in range(100, len(h1)):
            bt = pd.Timestamp(ht[i]); price = hc[i]; bh = hh[i]; bl = hl[i]
            
            # 冷却+限交易
            # (简化: 不实现冷却, 用止损和参数控制频率)
            
            if pos:
                hit_sl = (pos['side']==1 and bl<=pos['sl']) or (pos['side']==-1 and bh>=pos['sl'])
                hit_tp = (pos['side']==1 and bh>=pos['tp']) or (pos['side']==-1 and bl<=pos['tp'])
                if hit_sl or hit_tp:
                    ep = pos['sl'] if hit_sl else pos['tp']
                    profit = (ep-pos['entry'])*pos['side']*0.01*100
                    trades.append({'open_time':pos['ot'],'close_time':str(bt)[:16],
                        'direction':'BUY' if pos['side']==1 else 'SELL',
                        'entry':round(pos['entry'],2),'exit':round(ep,2),'profit':round(profit,2),
                        'result':'WIN' if profit>0 else 'LOSS','regime':pos.get('regime',''),
                        'adx_at_entry':round(pos.get('adx',0),1),'trend_at_entry':pos.get('trend','')})
                    bal += profit; pos = None; continue
                else: continue
            
            if not (int(p['session_start']) <= bt.hour < 24): continue
            if np.isnan(adx_v[i]) or adx_v[i] < p['adx_min']: continue
            
            # 市场状态
            h4i = min(i//4, len(h4c)-1)
            hadx = h4adx[max(0,h4i)]
            regime = 'trend'
            if hadx < 20 and adx_v[i] < 20: regime = 'ranging'
            if hadx > 35: regime = 'strong_trend'
            atr_h = atr_v[max(0,i-30):i+1]
            if len(atr_h)>10 and atr_v[i] > np.mean(atr_h)*1.8: regime = 'volatile'
            if regime == 'volatile': continue
            
            if np.isnan(e_fast[i]) or np.isnan(e_slow[i]): continue
            trend = 'UP' if e_fast[i] > e_slow[i] else 'DOWN'
            
            # 供需区
            chunk = h4.iloc[max(0,h4i-30):h4i+1]
            if len(chunk) < 15: continue
            zd = find_zones(chunk)
            h4a_val = atr_v[max(0,i)] * 4
            
            zc = None; zt = None; flip = False
            for z in zd.get('demand',[]):
                if z['strength']>=p['zone_str_min'] and price>z['top'] and price-z['top']<h4a_val*3:
                    zc,zt=z,'D'; break
            if not zc:
                for z in zd.get('supply',[]):
                    if z['strength']>=p['zone_str_min'] and price<z['bottom'] and z['bottom']-price<h4a_val*3:
                        zc,zt=z,'S'; break
            if not zc:
                for z in zd.get('supply',[]):
                    if price>z['top']: zc,zt=z,'D'; flip=True; break
            if not zc:
                for z in zd.get('demand',[]):
                    if price<z['bottom']: zc,zt=z,'S'; flip=True; break
            if not zc: continue
            
            # D1方向
            if p['d1_filter'] and de9 is not None:
                d1i = min(i//24, len(dc)-1)
                if d1i >= 21:
                    d1_dir = 'UP' if de9[d1i] > de21[d1i] else 'DOWN'
                    direction = 'BUY' if d1_dir=='UP' and zt=='D' else 'SELL' if d1_dir=='DOWN' and zt=='S' else None
                else: direction = 'BUY' if trend=='UP' and zt=='D' else 'SELL' if trend=='DOWN' and zt=='S' else None
            else:
                direction = 'BUY' if trend=='UP' and zt=='D' else 'SELL' if trend=='DOWN' and zt=='S' else None
            if not direction: continue
            
            sm = p['sl_mult']; rm = p['rr_mult']
            if regime == 'ranging': sm = min(sm*0.7, 0.8); rm = max(rm*0.8, 1.5)
            elif regime == 'strong_trend': sm = max(sm*1.2, 1.0); rm *= 1.2
            
            buf = max(h4a_val*0.1, 0.5)
            if direction == 'BUY': sl = zc['bottom'] - buf; tp = price + (price-sl)*rm
            else: sl = zc['top'] + buf; tp = price - (sl-price)*rm
            
            pos = {'side':1 if direction=='BUY' else -1,'entry':price,'sl':sl,'tp':tp,
                   'ot':str(bt)[:16],'regime':regime,'adx':adx_v[i],'trend':trend}
        
        return trades, bal
    
    def select_and_evolve(self):
        """选择最优策略 → 进化生成下一代"""
        self.generation += 1
        
        # 按适应度排序
        ranked = sorted(self.agents, key=lambda a: a.get_fitness(), reverse=True)
        
        # 保留前20% (精英保留)
        elite_count = max(3, self.pool_size // 5)
        elite = ranked[:elite_count]
        
        # 淘汰后40%
        survivors = elite.copy()
        
        # 从精英中交叉变异生成新策略
        while len(survivors) < self.pool_size:
            parent = random.choice(elite)
            child = parent.clone(f"agent_{len(survivors):03d}_g{self.generation}")
            survivors.append(child)
        
        self.agents = survivors
        self.best_agent = elite[0]
        
        # 记录进化日志
        log_entry = {
            'generation': self.generation,
            'best_fitness': elite[0].fitness,
            'best_pnl': elite[0].total_pnl,
            'best_params': elite[0].p,
            'pool_avg_fitness': np.mean([a.fitness for a in self.agents]),
            'pool_avg_pnl': np.mean([a.total_pnl for a in self.agents]),
            'time': datetime.now().isoformat(),
        }
        self.evolution_log.append(log_entry)
        self.save_pool()
        
        return log_entry
    
    def get_consensus_signal(self, current_state: Dict, h1_df, h4_df, d1_df):
        """策略池投票: 每条策略给出信号, 加权投票"""
        signals = []
        for agent in self.agents:
            p = agent.p
            # 每个agent自己判断 (简化版)
            # 这里用agent的参数+经验记忆做决策
            exp_matches = self.experience.find_similar(current_state, top_k=5)
            
            agent_vote = 0
            agent_confidence = 0
            
            # 从经验中学习: 相似的过去经验决定当前判断
            if exp_matches:
                win_rate = sum(1 for m in exp_matches if m['result'].get('profit',0)>0) / len(exp_matches)
                avg_pnl = np.mean([m['result'].get('profit',0) for m in exp_matches])
                agent_vote = 1 if win_rate > 0.5 else -1
                agent_confidence = abs(win_rate - 0.5) * 2  # 0~1
            else:
                # 没有经验匹配 → 用agent自身的参数判断
                agent_confidence = 0.3  # 低置信度
            
            weight = agent.get_fitness() + 50  # 避免负数
            weight = max(0, weight)
            
            signals.append({
                'agent_id': agent.id,
                'vote': agent_vote,
                'confidence': agent_confidence,
                'weight': weight,
                'fitness': agent.fitness,
                'pnl': agent.total_pnl,
            })
        
        # 加权聚合
        buy_weight = sum(s['weight']*s['confidence'] for s in signals if s['vote']==1)
        sell_weight = sum(s['weight']*s['confidence'] for s in signals if s['vote']==-1)
        total_weight = buy_weight + sell_weight
        
        if total_weight == 0:
            return {'signal': 'HOLD', 'confidence': 0, 'buy_ratio': 0.5}
        
        buy_ratio = buy_weight / total_weight
        if buy_ratio > 0.65:
            signal = 'BUY'
            confidence = (buy_ratio - 0.5) * 2
        elif buy_ratio < 0.35:
            signal = 'SELL'
            confidence = (0.5 - buy_ratio) * 2
        else:
            signal = 'HOLD'
            confidence = 0
        
        return {
            'signal': signal,
            'confidence': round(confidence, 2),
            'buy_ratio': round(buy_ratio, 3),
            'agents_voting': len(signals),
            'buy_votes': sum(1 for s in signals if s['vote']==1),
            'sell_votes': sum(1 for s in signals if s['vote']==-1),
        }


# ═══════════════════════════════════════════════
# 6. 主回测
# ═══════════════════════════════════════════════
def full_backtest(evolution_rounds=3):
    """完整自进化回测"""
    h1 = pd.read_csv(os.path.join(DATA_DIR,'XAUUSD_H1.csv'), parse_dates=['time'])
    h4 = pd.read_csv(os.path.join(DATA_DIR,'XAUUSD_H4.csv'), parse_dates=['time'])
    d1 = pd.read_csv(os.path.join(DATA_DIR,'XAUUSD_D1.csv'), parse_dates=['time'])
    print(f'数据: H1={len(h1)} H4={len(h4)} D1={len(d1)}')
    
    ate = EvolutionEngine(pool_size=20)
    
    for rnd in range(1, evolution_rounds+1):
        print(f'\n{"="*60}')
        print(f'  第 {rnd} 代 进化')
        print(f'{"="*60}')
        
        ate.evaluate_all(h1, h4, d1)
        log = ate.select_and_evolve()
        
        print(f'  最优适应度: {log["best_fitness"]}')
        print(f'  最优PnL: ${log["best_pnl"]:.2f}')
        print(f'  最优参数: ADX≥{log["best_params"]["adx_min"]} ZS≥{log["best_params"]["zone_str_min"]} '
              f'SLx{log["best_params"]["sl_mult"]} RRx{log["best_params"]["rr_mult"]}')
        print(f'  池平均适应度: {log["pool_avg_fitness"]:.1f} 平均PnL: ${log["pool_avg_pnl"]:.2f}')
        
        # 保存中间进化日志
        with open(os.path.join(ATE_DIR, f'evolution_log_g{log["generation"]}.json'), 'w') as f:
            json.dump(log, f, indent=2)
    
    # 最终结果
    best = ate.best_agent
    print(f'\n{"="*60}')
    print(f'  ★ A.T.E. 最终进化结果')
    print(f'{"="*60}')
    print(f'  第 {ate.generation} 代 | 策略池: {len(ate.agents)} 条')
    print(f'')
    print(f'  最优策略参数:')
    for k, v in best.p.items():
        print(f'    {k}: {v}')
    print(f'')
    print(f'  最优策略绩效:')
    print(f'    总交易: {len([t for t in best.trades if t.get("result","") in ("WIN","LOSS")])} 笔')
    print(f'    总PnL: ${best.total_pnl:.2f}')
    print(f'    胜率: {best.wins/max(best.wins+best.losses,1)*100:.1f}%')
    print(f'    适应度: {best.fitness}')
    
    # 保存最终策略池
    ate.save_pool()
    print(f'\n策略池已保存: {os.path.join(ATE_DIR, "strategy_pool.json")}')
    
    return ate

if __name__ == '__main__':
    print('='*65)
    print('  A.T.E. v10.5 — 自主交易引擎')
    print('  基于: 策略池(20条) + 进化算法 + 经验匹配')
    print('='*65)
    ate = full_backtest(evolution_rounds=5)
