"""
A.T.E. v10.5 — HTTP决策服务器
作为MQL5 EA的"大脑", 接收tick数据, 返回交易决策

架构:
  MQL5 EA (每笔tick) → HTTP POST → Python A.T.E. → 返回决策
                     ← HTTP响应   ←
  Python A.T.E. 持续学习进化 + 策略池 + 经验匹配

启动: python ate_server.py
"""
import sys, os, json, warnings, time, random, threading
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

warnings.filterwarnings('ignore')

BASE = r"E:\GoldstrategyEngine"
ATE_DIR = os.path.join(BASE, "data", "ate_live")
os.makedirs(ATE_DIR, exist_ok=True)
sys.path.insert(0, BASE)

PORT = 8765

# ═══════════════════════════════════════════════
# A.T.E. 核心 — 持续运行, 持续进化
# ═══════════════════════════════════════════════
class ATECore:
    def __init__(self):
        print("[ATE] 初始化自主交易引擎核心...")
        
        # 策略池 (20条虚拟交易员)
        self.agents = []
        for i in range(20):
            self.agents.append({
                'id': i,
                'params': {
                    'adx_min': random.uniform(15, 30),
                    'zone_str': random.uniform(0.8, 1.5),
                    'sl_mult': random.uniform(1.0, 2.0),
                    'rr_mult': random.uniform(2.0, 3.5),
                    'd1_filter': 1 if random.random() > 0.3 else 0,
                },
                'weight': 1.0,
                'pnl': 0.0,
                'wins': 0,
                'losses': 0,
                'trades': [],
            })
        
        # 经验记忆
        self.memory = []
        self.load_state()
        
        # 市场状态
        self.current_state = {}
        self.last_hour = -1
        self.daily_trades = 0
        self.last_day = 0
        
        # 线程锁
        self.lock = threading.Lock()
        
        print(f"[ATE] 就绪: {len(self.agents)}条策略, {len(self.memory)}条经验")
    
    def load_state(self):
        p = os.path.join(ATE_DIR, 'ate_state.json')
        if os.path.exists(p):
            try:
                with open(p,'r') as f: data = json.load(f)
                self.memory = data.get('memory', [])
                for i, a in enumerate(self.agents):
                    sd = data.get('agents', [{}])[i] if i < len(data.get('agents',[])) else {}
                    a['weight'] = sd.get('weight', 1.0)
                    a['pnl'] = sd.get('pnl', 0.0)
                    a['wins'] = sd.get('wins', 0)
                    a['losses'] = sd.get('losses', 0)
                print(f"[ATE] 加载状态: {len(self.memory)}条经验")
            except: pass
    
    def save_state(self):
        with self.lock:
            data = {
                'memory': self.memory[-500:],
                'agents': [{
                    'weight': a['weight'], 'pnl': a['pnl'],
                    'wins': a['wins'], 'losses': a['losses'],
                } for a in self.agents],
                'time': datetime.now().isoformat(),
            }
            with open(os.path.join(ATE_DIR, 'ate_state.json'),'w') as f:
                json.dump(data, f, indent=2)
    
    def on_tick(self, tick_data):
        """每笔tick到达时调用"""
        ask = tick_data.get('ask', 0)
        bid = tick_data.get('bid', 0)
        price = (ask + bid) / 2
        tick_time = tick_data.get('time', 0)
        
        now = datetime.now()
        hour = now.hour
        day = now.day
        
        # 每日重置
        if day != self.last_day:
            self.last_day = day
            self.daily_trades = 0
            # 每日进化: 略微调整策略权重
            self._daily_evolve()
        
        # 检查新H1 K线
        current_h1 = tick_time - (tick_time % 3600)
        is_new_h1 = (current_h1 != self.last_hour)
        if is_new_h1:
            self.last_hour = current_h1
        
        return {
            'price': price,
            'ask': ask,
            'bid': bid,
            'hour': hour,
            'is_new_h1': is_new_h1,
            'is_trade_session': (15 <= hour < 24),
        }
    
    def decide(self, state):
        """基于当前市场状态做决策"""
        price = state['price']
        adx = state.get('adx', 0)
        trend = state.get('trend', 'UP')
        regime = state.get('regime', 'trend')
        atr_val = state.get('atr', 10)
        zone = state.get('zone', '')
        hour = state.get('hour', 0)
        
        # 过滤
        if not (15 <= hour < 24):
            return {'action': 'HOLD', 'reason': '非交易时段'}
        if regime == 'volatile':
            return {'action': 'HOLD', 'reason': '高波动'}
        if adx < 15:
            return {'action': 'HOLD', 'reason': 'ADX太低'}
        if self.daily_trades >= 5:
            return {'action': 'HOLD', 'reason': '日交易上限'}
        
        # 策略池投票
        buy_weight = 0
        sell_weight = 0
        total_weight = 0
        
        for a in self.agents:
            p = a['params']
            w = a['weight']
            
            # 每个策略独立判断
            adx_ok = adx >= p['adx_min']
            if not adx_ok: continue
            
            if trend == 'UP' and zone == 'BUY':
                buy_weight += w
            elif trend == 'DOWN' and zone == 'SELL':
                sell_weight += w
            
            total_weight += w
        
        if total_weight == 0:
            return {'action': 'HOLD', 'reason': '策略池无共识'}
        
        buy_ratio = buy_weight / total_weight
        
        # 经验加持
        similar = self._find_similar(state, 5)
        exp_score = 0
        if similar:
            exp_wr = sum(1 for m in similar if m.get('result',{}).get('profit',0)>0) / len(similar)
            exp_score = (exp_wr - 0.5) * 2
        
        confidence = abs(buy_ratio - 0.5) * 2 + exp_score * 0.3
        confidence = max(0, min(1, confidence))
        
        result = {'action': 'HOLD', 'reason': '共识不足', 'confidence': 0}
        if buy_ratio > 0.65 and confidence > 0.2:
            result = {
                'action': 'BUY',
                'reason': f'策略池{buy_ratio:.0%}看多 | 经验{exp_score:+.1f}',
                'confidence': round(confidence, 2),
                'buy_ratio': round(buy_ratio, 3),
                'sl_mult': 1.5,
                'rr_mult': 2.5,
                'atr': atr_val,
            }
        elif buy_ratio < 0.35 and confidence > 0.2:
            result = {
                'action': 'SELL',
                'reason': f'策略池{(1-buy_ratio):.0%}看空 | 经验{exp_score:+.1f}',
                'confidence': round(confidence, 2),
                'buy_ratio': round(buy_ratio, 3),
                'sl_mult': 1.5,
                'rr_mult': 2.5,
                'atr': atr_val,
            }
        
        # 强趋势调整
        if regime == 'strong_trend':
            if result['action'] == 'BUY':
                result['sl_mult'] = max(1.5*1.2, 1.0)
                result['rr_mult'] = 2.5 * 1.2
            elif result['action'] == 'SELL':
                result['sl_mult'] = max(1.5*1.2, 1.0)
                result['rr_mult'] = 2.5 * 1.2
        
        return result
    
    def on_trade_result(self, trade_data):
        """记录交易结果 → 进化"""
        profit = trade_data.get('profit', 0)
        action = trade_data.get('action', '')
        entry = trade_data.get('entry', 0)
        state = trade_data.get('state', {})
        
        # 记录经验
        self.memory.append({
            'state': state,
            'result': {'profit': profit, 'action': action, 'entry': entry},
            'time': datetime.now().isoformat(),
        })
        
        # 更新策略权重
        with self.lock:
            for a in self.agents:
                a['trades'].append({'profit': profit, 'action': action})
                a['pnl'] += profit
                if profit > 0:
                    a['wins'] += 1
                    a['weight'] = min(2.0, a['weight'] * 1.02)
                else:
                    a['losses'] += 1
                    a['weight'] = max(0.1, a['weight'] * 0.95)
            
            self.daily_trades += 1
        
        # 每10笔交易进化一次
        total = sum(a['wins'] + a['losses'] for a in self.agents)
        if total > 0 and total % 10 == 0:
            self._evolve()
        
        self.save_state()
        
        return {'status': 'recorded'}
    
    def _find_similar(self, state, k=5):
        """找相似历史经验"""
        if not self.memory: return []
        scored = []
        for mem in self.memory[-200:]:
            s = mem.get('state', {})
            score = 0
            if abs(state.get('adx',0)-s.get('adx',0)) < 5: score += 3
            if state.get('regime') == s.get('regime'): score += 3
            if state.get('trend') == s.get('trend'): score += 2
            cur_p = state.get('price',0)
            mem_p = s.get('price',0)
            if cur_p > 0 and mem_p > 0 and max(cur_p,mem_p)/min(cur_p,mem_p) < 1.05:
                score += 2
            scored.append((score, mem))
        scored.sort(key=lambda x: -x[0])
        return [m for s,m in scored[:k] if s > 0]
    
    def _evolve(self):
        """进化: 淘汰最差的20%, 变异生成新的"""
        with self.lock:
            # 按PnL排序
            ranked = sorted(self.agents, key=lambda a: a['pnl'], reverse=True)
            keep = ranked[:16]  # 保留前80%
            # 淘汰后4个 → 从最优变异生成
            for i in range(4):
                parent = random.choice(ranked[:8])
                child = {
                    'id': parent['id'] + 100 + i,
                    'params': dict(parent['params']),
                    'weight': max(0.5, parent['weight'] * random.uniform(0.8, 1.2)),
                    'pnl': 0.0,
                    'wins': 0,
                    'losses': 0,
                    'trades': [],
                }
                # 变异
                for k in child['params']:
                    if random.random() < 0.3:
                        if k == 'adx_min':
                            child['params'][k] = random.uniform(15, 30)
                        elif k == 'zone_str':
                            child['params'][k] = random.uniform(0.8, 1.5)
                        elif k == 'sl_mult':
                            child['params'][k] = random.uniform(1.0, 2.0)
                        elif k == 'rr_mult':
                            child['params'][k] = random.uniform(2.0, 3.5)
                        elif k == 'd1_filter':
                            child['params'][k] = 1 - child['params'][k]
                keep.append(child)
            
            self.agents = keep
            print(f"[EVOLVE] 新一代: 最优PnL=${ranked[0]['pnl']:.2f} 最差=${ranked[-1]['pnl']:.2f}", flush=True)
    
    def _daily_evolve(self):
        """每日微进化: 缓慢调整权重"""
        with self.lock:
            for a in self.agents:
                # 长期不交易或表现差的, 略微恢复权重
                if len(a['trades']) < 5:
                    a['weight'] = min(1.0, a['weight'] * 1.05)


# ═══════════════════════════════════════════════
# HTTP服务器 — MQL5通过WebRequest调用
# ═══════════════════════════════════════════════
ate = ATECore()

class ATEHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        path = urlparse(self.path).path
        content_len = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_len).decode('utf-8') if content_len > 0 else '{}'
        
        try:
            data = json.loads(body)
        except:
            data = {}
        
        response = {'status': 'error', 'message': 'unknown'}
        
        if path == '/tick':
            # MQL5每笔tick发送过来
            tick_info = ate.on_tick(data)
            response = {
                'status': 'ok',
                'session': tick_info['is_trade_session'],
                'new_h1': tick_info['is_new_h1'],
                'price': tick_info['price'],
            }
        
        elif path == '/analyze':
            # MQL5在新H1时请求分析
            state = data.get('state', {})
            decision = ate.decide(state)
            response = {
                'status': 'ok',
                'decision': decision,
            }
        
        elif path == '/result':
            # MQL5报告交易结果
            result = ate.on_trade_result(data)
            response = {
                'status': 'ok',
                'result': result,
            }
        
        elif path == '/status':
            # 查询引擎状态
            with ate.lock:
                agents_summary = [{
                    'id': a['id'],
                    'weight': round(a['weight'], 2),
                    'pnl': round(a['pnl'], 2),
                    'wins': a['wins'],
                    'losses': a['losses'],
                    'params': a['params'],
                } for a in ate.agents[:5]]  # 只返回前5条
            response = {
                'status': 'ok',
                'agents': len(ate.agents),
                'memory': len(ate.memory),
                'top_agents': agents_summary,
                'daily_trades': ate.daily_trades,
            }
        
        else:
            response = {'status': 'error', 'message': f'unknown path: {path}'}
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))
    
    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            html = f"""<!DOCTYPE html>
<html><head><title>A.T.E. v10.5</title>
<meta charset="utf-8">
<style>
body {{ font-family: monospace; background: #1a1a2e; color: #fff; padding: 20px; }}
h1 {{ color: #e94560; }}
.card {{ background: #16213e; padding: 15px; margin: 10px 0; border-radius: 8px; }}
.green {{ color: #4ecca3; }}
.red {{ color: #e94560; }}
.blue {{ color: #87ceeb; }}
</style></head><body>
<h1>A.T.E. v10.5 — 自主交易引擎</h1>
<div class="card">
<p>状态: <span class="green">运行中</span></p>
<p>策略池: <span class="blue">{len(ate.agents)}</span> 条</p>
<p>经验记忆: <span class="blue">{len(ate.memory)}</span> 条</p>
<p>本日交易: <span class="blue">{ate.daily_trades}</span> 笔</p>
</div>
<div class="card">
<h3>TOP 3 策略</h3>
<ol>"""
            with ate.lock:
                ranked = sorted(ate.agents, key=lambda a: a['pnl'], reverse=True)
                for a in ranked[:3]:
                    html += f'<li>PnL=${a["pnl"]:.2f} | W:{a["wins"]} L:{a["losses"]} | 权重:{a["weight"]:.2f}</li>'
            html += """</ol></div>
<div class="card">
<p>API端点:</p>
<p><code>POST /tick</code> — 发送tick数据</p>
<p><code>POST /analyze</code> — 请求交易决策</p>
<p><code>POST /result</code> — 报告交易结果</p>
<p><code>GET /status</code> — 查询引擎状态</p>
</div>
</body></html>"""
            self.wfile.write(html.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # 静默日志

def run_server():
    server = HTTPServer(('0.0.0.0', PORT), ATEHandler)
    print(f"[HTTP] A.T.E. 服务器启动: http://localhost:{PORT}", flush=True)
    print(f"[HTTP] MQL5 EA 连接地址: http://127.0.0.1:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[HTTP] 服务器停止", flush=True)
        server.shutdown()

if __name__ == '__main__':
    print("="*60, flush=True)
    print("  A.T.E. v10.5 — HTTP决策服务器", flush=True)
    print("  架构: MQL5 EA (手) ↔ HTTP ↔ Python A.T.E. (大脑)", flush=True)
    print("="*60, flush=True)
    run_server()
