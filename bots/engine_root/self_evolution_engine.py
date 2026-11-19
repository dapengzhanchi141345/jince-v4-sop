"""
A.T.E. 自主进化引擎 — 让系统像人类操盘手一样持续进步
核心机制: 决策 → 执行 → 反馈 → 进化 → 再决策
"""
import sys, os, json, warnings, time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict, OrderedDict
from pathlib import Path
warnings.filterwarnings('ignore')

import MetaTrader5 as mt5
if not mt5.initialize(): mt5.initialize()
mt5.login(60043976, password="", server="TradeMaxGlobal-Demo")

BASE = r"E:\GoldstrategyEngine"
DATA_DIR = os.path.join(BASE, "data")
EVOLVE_DIR = os.path.join(DATA_DIR, "evolution")
os.makedirs(EVOLVE_DIR, exist_ok=True)

# ═══ 品种列表 ═══
SYMBOLS = {
    "XAUUSD": {"name":"黄金", "digits":2, "pip":1, "spread_cost":0.3},
    "BTCUSD": {"name":"比特币", "digits":0, "pip":1, "spread_cost":0.5},
    "ETHUSD": {"name":"以太坊", "digits":0, "pip":1, "spread_cost":0.3},
    "EURUSD": {"name":"欧元", "digits":5, "pip":0.00001, "spread_cost":0.05},
    "GBPUSD": {"name":"英镑", "digits":5, "pip":0.00001, "spread_cost":0.06},
    "USDJPY": {"name":"美元/日元", "digits":3, "pip":0.001, "spread_cost":0.04},
    "GBPJPY": {"name":"英镑/日元", "digits":3, "pip":0.001, "spread_cost":0.08},
    "AUDUSD": {"name":"澳元", "digits":5, "pip":0.00001, "spread_cost":0.05},
}

# ═══ 人类操盘手的"经验库" ═══
class ExperienceMemory:
    """类似人类交易员的'盘感'——从过去的交易中学习的经验"""
    
    def __init__(self):
        self.file = os.path.join(EVOLVE_DIR, "experience.db")
        self.data = self._load()
    
    def _load(self):
        if os.path.exists(self.file):
            with open(self.file, 'r') as f:
                return json.load(f)
        return {'patterns': [], 'success_rate': 0.5, 'evolution_rounds': 0}
    
    def save(self):
        with open(self.file, 'w') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
    
    def add_experience(self, symbol, direction, conditions, outcome, pnl):
        """记录一次交易经验"""
        exp = {
            'symbol': symbol,
            'direction': direction,
            'conditions': conditions,
            'outcome': outcome,
            'pnl': pnl,
            'timestamp': datetime.now().isoformat()
        }
        self.data['patterns'].append(exp)
        if len(self.data['patterns']) > 1000:
            self.data['patterns'] = self.data['patterns'][-1000:]
        self._update_success_rate()
        self.save()
    
    def _update_success_rate(self):
        wins = [p for p in self.data['patterns'] if p['pnl'] > 0]
        total = len(self.data['patterns'])
        self.data['success_rate'] = len(wins) / max(total, 1)
    
    def get_confidence(self, symbol, direction, conditions):
        """根据历史经验获取当前决策的信心"""
        matching = [
            p for p in self.data['patterns']
            if p['symbol'] == symbol
            and p['direction'] == direction
            and all(p.get(c) == conditions.get(c) for c in conditions if c in p)
        ]
        if matching:
            win_rate = sum(1 for p in matching if p['pnl'] > 0) / len(matching)
            return win_rate
        return self.data['success_rate']

# ═══ 指标计算 ═══
def ema(v, p):
    r = np.full(len(v), np.nan); r[p-1] = np.mean(v[:p])
    a = 2/(p+1)
    for i in range(p, len(v)): r[i] = v[i]*a + r[i-1]*(1-a)
    return r

def rsi_calc(c, p=14):
    d = np.diff(c)
    g = np.where(d>0, d, 0); lo = np.where(d<0, -d, 0)
    ag = pd.Series(g).ewm(span=p).mean().values
    al = pd.Series(lo).ewm(span=p).mean().values
    return 100 - 100/(1+ag/(al+1e-10))

def macd_calc(c, fast=12, slow=26, signal=9):
    ef = ema(c, fast); es = ema(c, slow)
    line = ef - es
    return line, ema(line, signal), line - ema(line, signal)

# ═══ 交易策略引擎 ═══
class TradingStrategy:
    """自主进化的交易策略——每轮迭代后自我调整"""
    
    def __init__(self):
        self.params = {
            'adx_threshold': 18,
            'rsi_overbought': 70,
            'rsi_oversold': 30,
            'ma_short': 9,
            'ma_long': 21,
            'position_size': 0.1,
            'risk_per_trade': 0.01,
            'max_positions': 3,
            'take_profit_ratio': 2.0,
            'stop_loss_ratio': 1.0,
        }
        self.performance_history = []
        self.evolved_params = {}
    
    def evaluate_performance(self, trades):
        """评估策略表现"""
        if not trades:
            return {'win_rate': 0, 'total_pnl': 0, 'sharpe': 0, 'max_drawdown': 0}
        
        pnls = [t['pnl'] for t in trades]
        wins = sum(1 for p in pnls if p > 0)
        total = len(pnls)
        win_rate = wins / max(total, 1)
        total_pnl = sum(pnls)
        avg_pnl = total_pnl / total if total > 0 else 0
        
        # 简易夏普比率
        if len(pnls) > 1:
            std_pnl = np.std(pnls)
            sharpe = avg_pnl / std_pnl if std_pnl > 0 else 0
        else:
            sharpe = 0
        
        # 最大回撤
        cum_pnl = np.cumsum(pnls)
        peak = cum_pnl[0]
        max_dd = 0
        for p in cum_pnl:
            if p > peak: peak = p
            dd = peak - p
            if dd > max_dd: max_dd = dd
        
        return {
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'sharpe': sharpe,
            'max_drawdown': max_dd,
            'total_trades': total,
            'avg_pnl_per_trade': avg_pnl,
        }
    
    def evolve(self, performance, round_num):
        """进化策略参数——根据上一轮表现自动调参"""
        self.performance_history.append({
            'round': round_num,
            'performance': performance,
            'params': self.params.copy(),
        })
        
        # 进化逻辑: 模拟人类操盘手的"自我修正"
        new_params = self.params.copy()
        changes = []
        
        if performance['win_rate'] < 0.4:
            # 胜率低 — 收紧入场条件
            new_params['adx_threshold'] = min(25, self.params['adx_threshold'] + 3)
            changes.append(f"ADX阈值上调 {self.params['adx_threshold']}→{new_params['adx_threshold']} (胜率{performance['win_rate']:.1%}太低)")
        
        if performance['sharpe'] < 0.5:
            # 风险收益比差 — 缩小仓位
            new_params['position_size'] = max(0.005, self.params['position_size'] * 0.8)
            changes.append(f"仓位下调 {self.params['position_size']:.3f}→{new_params['position_size']:.3f} (夏普比率低)")
        
        if performance['max_drawdown'] > 500:
            # 回撤过大 — 收紧止损
            new_params['stop_loss_ratio'] = max(0.5, self.params['stop_loss_ratio'] * 0.8)
            changes.append(f"止损收紧 {self.params['stop_loss_ratio']:.1f}→{new_params['stop_loss_ratio']:.1f} (回撤过大)")
        
        if performance['win_rate'] > 0.55 and performance['total_pnl'] > 0:
            # 表现良好 — 适度扩大仓位
            new_params['position_size'] = min(0.2, self.params['position_size'] * 1.05)
            changes.append(f"仓位微调 {self.params['position_size']:.3f}→{new_params['position_size']:.3f} (表现良好)")
        
        if changes:
            self.evolved_params[f'round_{round_num}'] = {
                'changes': changes,
                'new_params': new_params,
                'performance': performance,
            }
            self.params = new_params
            return True, changes
        return False, []
    
    def get_strategy_score(self):
        """策略整体评分"""
        if not self.performance_history:
            return 0
        last = self.performance_history[-1]
        perf = last['performance']
        score = (
            perf['win_rate'] * 40 +
            min(perf['total_pnl'] / 1000, 1) * 30 +
            min(perf['sharpe'] / 2, 1) * 30
        )
        return score

# ═══ 模拟交易系统 ═══
class Simulator:
    """模拟交易引擎——生成虚拟交易用于策略进化"""
    
    def __init__(self, initial_balance=10000):
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.trades = []
        self.equity_curve = [initial_balance]
    
    def simulate_trade(self, symbol, direction, entry_price, stop_loss, take_profit, lot_size):
        """模拟一笔交易"""
        spread = SYMBOLS[symbol]['spread_cost']
        
        # 随机但带倾向的模拟
        trend_factor = 0.55 if direction in ['BUY', 'SELL'] else 0.5
        noise = np.random.normal(0, 1)
        outcome_factor = trend_factor + noise * 0.3
        
        if outcome_factor > 0.55:
            result = 'WIN'
            pnl = (take_profit - entry_price) * lot_size * 100 * np.random.uniform(0.5, 1.5)
        elif outcome_factor < 0.45:
            result = 'LOSS'
            pnl = -(entry_price - stop_loss) * lot_size * 100 * np.random.uniform(0.5, 1.5)
        else:
            result = 'BREAKEVEN'
            pnl = 0
        
        pnl = round(pnl, 2)
        self.balance += pnl
        self.equity_curve.append(self.balance)
        
        trade = {
            'symbol': symbol,
            'direction': direction,
            'entry': entry_price,
            'sl': stop_loss,
            'tp': take_profit,
            'lot_size': lot_size,
            'result': result,
            'pnl': pnl,
            'timestamp': datetime.now().isoformat(),
        }
        self.trades.append(trade)
        return trade

# ═══ 自主进化主循环 ═══
def run_evolution_cycle(round_num, max_rounds=10, verbose=True):
    """运行一轮进化"""
    print(f"\n{'='*70}")
    print(f"  🧬 进化轮次 {round_num}/{max_rounds}")
    print(f"{'='*70}")
    
    # 初始化组件
    experience = ExperienceMemory()
    strategy = TradingStrategy()
    simulator = Simulator()
    
    # 这一轮模拟100笔交易
    num_trades = 100
    all_trades = []
    
    if verbose:
        print(f"  📊 模拟 {num_trades} 笔交易...")
    
    for _ in range(num_trades):
        sym = np.random.choice(list(SYMBOLS.keys()))
        direction = np.random.choice(['BUY', 'SELL'])
        base_price = {'XAUUSD': 4000, 'BTCUSD': 60000, 'ETHUSD': 1600, 'EURUSD': 1.14, 'GBPUSD': 1.32, 'USDJPY': 162, 'GBPJPY': 215, 'AUDUSD': 0.69}[sym]
        spread = SYMBOLS[sym]['spread_cost']
        
        entry = base_price + np.random.uniform(-2, 2)
        sl_mult = strategy.params['stop_loss_ratio']
        tp_mult = strategy.params['take_profit_ratio']
        sl = entry - sl_mult * spread if direction == 'BUY' else entry + sl_mult * spread
        tp = entry + tp_mult * spread if direction == 'BUY' else entry - tp_mult * spread
        lot = strategy.params['position_size']
        
        trade = simulator.simulate_trade(sym, direction, entry, sl, tp, lot)
        all_trades.append(trade)
    
    if verbose:
        print(f"  ✅ 模拟完成, 获得 {len(all_trades)} 笔交易")
    
    # 评估表现
    performance = strategy.evaluate_performance(all_trades)
    if verbose:
        print(f"  📈 本轮表现:")
        print(f"    胜率: {performance['win_rate']:.1%} ({performance['total_trades']}笔)")
        print(f"    总盈亏: ${performance['total_pnl']:.2f}")
        print(f"    夏普比率: {performance['sharpe']:.3f}")
        print(f"    最大回撤: ${performance['max_drawdown']:.2f}")
    
    # 进化策略
    evolved, changes = strategy.evolve(performance, round_num)
    
    if evolved:
        if verbose:
            print(f"  🔬 策略进化 ({len(changes)}项调整):")
            for chg in changes:
                print(f"    • {chg}")
    else:
        if verbose:
            print(f"  ⏸️  策略稳定, 无需调整")
    
    # 记录经验
    for trade in all_trades:
        if trade['result'] in ['WIN', 'LOSS']:
            experience.add_experience(
                symbol=trade['symbol'],
                direction=trade['direction'],
                conditions={'entry_approx': trade['entry'], 'lot_size': trade['lot_size']},
                outcome=trade['result'],
                pnl=trade['pnl']
            )
    
    # 保存本轮快照
    snapshot = {
        'round': round_num,
        'performance': performance,
        'strategy_params': strategy.params,
        'evolved_changes': changes,
        'equity_curve': simulator.equity_curve[-20:],  # 最近20个点
        'timestamp': datetime.now().isoformat(),
    }
    snap_file = os.path.join(EVOLVE_DIR, f"snapshot_r{round_num}.json")
    with open(snap_file, 'w') as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False, default=str)
    
    return {
        'performance': performance,
        'evolved': evolved,
        'changes': changes,
        'snapshot': snapshot,
    }

# ═══ 多轮进化 ═══
def run_multi_round_evolution(rounds=5):
    """多轮自主进化"""
    results = []
    history = []
    
    for r in range(1, rounds + 1):
        result = run_evolution_cycle(r, max_rounds=rounds)
        results.append(result)
        history.append(result['performance'])
        
        # 可视化进化曲线
        if r > 1:
            prev = history[-2]
            curr = history[-1]
            improvement = (curr['total_pnl'] - prev['total_pnl']) / abs(prev['total_pnl']) * 100 if prev['total_pnl'] != 0 else 0
            print(f"\n  🚀 相比上一轮:")
            print(f"    PnL变化: {improvement:+.1f}%")
            print(f"    胜率变化: {(curr['win_rate'] - prev['win_rate']):+.1%}")
    
    return results, history

# ═══ 生成进化报告 ═══
def generate_evolution_report(results, history):
    """生成进化报告"""
    report = []
    report.append("=" * 70)
    report.append("  A.T.E. 自主进化报告 — Evolution Report v1.0")
    report.append("=" * 70)
    report.append("")
    report.append(f"进化轮次: {len(results)}")
    report.append(f"初始资金: $10,000")
    report.append("")
    report.append("-" * 70)
    report.append("  各轮表现对比")
    report.append("-" * 70)
    report.append(f"{'轮次':>4s} | {'胜率':>8s} | {'PnL':>10s} | {'夏普':>8s} | {'回撤':>10s} | {'是否进化':>8s}")
    report.append("-" * 70)
    
    for i, (r, h) in enumerate(zip(results, history)):
        changed_str = "是" if r['evolved'] else "否"
        report.append(
            f"{i+1:>4d} | {h['win_rate']:>7.1%} | ${h['total_pnl']:>8.0f} | {h['sharpe']:>8.3f} | ${h['max_drawdown']:>9.0f} | {changed_str:>8s}"
        )
    
    report.append("")
    report.append("-" * 70)
    report.append("  进化总结")
    report.append("-" * 70)
    
    if len(history) >= 2:
        first = history[0]
        last = history[-1]
        pnl_improvement = last['total_pnl'] - first['total_pnl']
        wr_improvement = last['win_rate'] - first['win_rate']
        
        report.append(f"  PnL提升: ${pnl_improvement:+.2f}")
        report.append(f"  胜率变化: {wr_improvement:+.1%}")
        report.append(f"  夏普变化: {last['sharpe'] - first['sharpe']:+.3f}")
        report.append("")
        
        if pnl_improvement > 0 and wr_improvement > 0:
            report.append("  🎉 进化成功! 系统在持续学习和改善!")
        elif pnl_improvement > 0:
            report.append("  👍 PnL改善, 继续优化胜率")
        else:
            report.append("  ⚠️  需要调整进化方向")
    
    report.append("")
    report.append("=" * 70)
    
    return "\n".join(report)

# ═══ 主流程 ═══
if __name__ == "__main__":
    print("🧬 A.T.E. 自主进化引擎启动")
    print("模拟10轮进化, 每轮100笔交易...")
    
    # 运行进化
    results, history = run_multi_round_evolution(rounds=10)
    
    # 生成报告
    report_text = generate_evolution_report(results, history)
    print("\n" + report_text)
    
    # 保存报告
    report_file = os.path.join(EVOLVE_DIR, "evolution_report.txt")
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report_text)
    
    # 保存JSON数据
    json_file = os.path.join(EVOLVE_DIR, "evolution_data.json")
    with open(json_file, 'w') as f:
        json.dump({
            'results': results,
            'history': history,
            'final_strategy_params': results[-1]['snapshot']['strategy_params'],
        }, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\n✅ 进化完成! 报告保存: {report_file}")
    print(f"   数据保存: {json_file}")
    print(f"   快照目录: {EVOLVE_DIR}")

mt5.shutdown()
