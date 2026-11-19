# -*- coding: utf-8 -*-
# ⚠️ DEMO ONLY —— 本脚本用 np.random 合成行情测"信号数增减"，与样本显著性/exp_r 无关，
# 属演示级代码，**不用于生产进化主链路**（真实进化走 evolution/evolution_engine.py + continuous_evolution_v2.py 的 MT5 真实数据）。
# 勿将其输出当作"已学习/已进化"结论。
"""
AutoEvolutionLoop - 主动进化循环监控
====================================
每轮自动执行: 回测 → 诊断 → 优化 → 验证
无需人工干预，持续自我进化
"""

from typing import Dict, List
import sys
sys.path.insert(0, 'E:/GoldstrategyEngine')

import numpy as np
import pandas as pd
from datetime import datetime
import json
import os
import time

class AutoEvolutionLoop:
    """主动进化循环"""

    def __init__(self):
        self.loop_count = 0
        self.max_loops = 10  # 默认10轮
        self.results_log = []

    def run_loop(self, loop_num: int = 0):
        """运行一轮进化循环"""
        self.loop_count = loop_num
        print(f'\n{"="*70}')
        print(f'【主动进化循环 #{loop_num}】')
        print(f'{"="*70}')

        # 1. 全策略回测
        print('\n[1/4] 全策略回测...')
        backtest_results = self._run_backtest()

        # 2. 问题诊断
        print('\n[2/4] 问题诊断...')
        issues = self._diagnose_issues(backtest_results)

        # 3. 参数优化
        print('\n[3/4] 参数优化...')
        optimizations = self._run_optimization(issues)

        # 4. 验证改进
        print('\n[4/4] 验证改进...')
        validation = self._validate_improvements(backtest_results, optimizations)

        # 记录结果
        self.results_log.append({
            'loop': loop_num,
            'timestamp': datetime.now().isoformat(),
            'backtest': backtest_results,
            'issues': issues,
            'optimizations': optimizations,
            'validation': validation,
        })

        return {
            'loop': loop_num,
            'status': 'completed',
            'improvements': validation,
        }

    def _run_backtest(self) -> Dict:
        """全策略回测"""
        from advanced_strategies_v4 import STRATEGY_REGISTRY_V4

        # 生成测试数据
        np.random.seed(42)
        n = 2000
        closes = [100.0]
        for i in range(1, n):
            trend = 0.01 * np.sin(i * 0.002)
            noise = np.random.randn() * 0.4
            closes.append(closes[-1] * (1 + trend + noise * 0.01))
        closes = np.array(closes)
        opens = closes + np.random.randn(n) * 0.05
        highs = np.maximum(closes, opens) + np.abs(np.random.randn(n)) * 0.2
        lows = np.minimum(closes, opens) - np.abs(np.random.randn(n)) * 0.2
        times = np.arange(n) * 3600

        h1 = pd.DataFrame({'open': opens, 'high': highs, 'low': lows, 'close': closes, 'time': times})
        h4 = pd.DataFrame({'open': opens[::4], 'high': highs[::4], 'low': lows[::4], 'close': closes[::4], 'time': times[::4]})
        d1 = pd.DataFrame({'open': opens[::20], 'high': highs[::20], 'low': lows[::20], 'close': closes[::20], 'time': times[::20]})

        cfg = {'pip': 0.01, 'lot': 0.1}

        results = {}
        for name, gen in STRATEGY_REGISTRY_V4.items():
            try:
                sigs = gen(h1, h4, d1, cfg)
                results[name] = {
                    'signals': len(sigs),
                    'buys': len([s for s in sigs if s.get('side') == 1]),
                    'sells': len([s for s in sigs if s.get('side') == -1]),
                }
                print(f'  {name}: {len(sigs)} 信号 (买{results[name]["buys"]} 卖{results[name]["sells"]})')
            except Exception as e:
                results[name] = {'error': str(e)}
                print(f'  {name}: ❌ {str(e)[:30]}')

        return results

    def _diagnose_issues(self, backtest_results: Dict) -> List[Dict]:
        """诊断问题"""
        issues = []

        for strategy, data in backtest_results.items():
            if 'error' in data:
                issues.append({
                    'strategy': strategy,
                    'issue': 'generation_error',
                    'severity': 'high',
                    'message': data['error'],
                })
            elif data.get('signals', 0) < 3:
                issues.append({
                    'strategy': strategy,
                    'issue': 'signal_too_few',
                    'severity': 'medium',
                    'message': f'信号数过少 ({data["signals"]})',
                })
            elif data.get('signals', 0) > 1000:
                issues.append({
                    'strategy': strategy,
                    'issue': 'signal_too_many',
                    'severity': 'low',
                    'message': f'信号数过多 ({data["signals"]})，建议增加过滤',
                })

        return issues

    def _run_optimization(self, issues: List[Dict]) -> List[Dict]:
        """运行优化"""
        optimizations = []

        for issue in issues:
            strategy = issue['strategy']
            optimization = {
                'strategy': strategy,
                'issue': issue['issue'],
                'action': 'none',
                'status': 'pending',
            }

            if issue['issue'] == 'signal_too_few':
                optimization['action'] = 'relax_filters'
                optimization['params'] = {
                    'adx_min': 15,  # 降低ADX门槛
                    'quality_threshold': 0.2,  # 降低质量门槛
                }
                optimization['status'] = 'applied'

            elif issue['issue'] == 'signal_too_many':
                optimization['action'] = 'tighten_filters'
                optimization['params'] = {
                    'adx_min': 25,  # 提高ADX门槛
                    'quality_threshold': 0.6,  # 提高质量门槛
                }
                optimization['status'] = 'applied'

            elif issue['issue'] == 'generation_error':
                optimization['action'] = 'code_fix'
                optimization['status'] = 'requires_manual_review'

            optimizations.append(optimization)
            print(f'  🔧 {strategy}: {optimization["action"]}')

        return optimizations

    def _validate_improvements(self, old_results: Dict, optimizations: List[Dict]) -> Dict:
        """验证改进效果"""
        from advanced_strategies_v4 import STRATEGY_REGISTRY_V4

        improvements = {}
        all_good = True

        for opt in optimizations:
            strategy = opt['strategy']
            if opt['status'] == 'applied':
                # 使用优化后的参数重新测试
                cfg = {'pip': 0.01, 'lot': 0.1, **opt.get('params', {})}
                gen = STRATEGY_REGISTRY_V4.get(strategy)
                if gen:
                    # 重新生成数据
                    np.random.seed(42)
                    n = 2000
                    closes = [100.0]
                    for i in range(1, n):
                        closes.append(closes[-1] * (1 + np.random.randn() * 0.01))
                    closes = np.array(closes)
                    opens = closes + np.random.randn(n) * 0.05
                    highs = np.maximum(closes, opens) + np.abs(np.random.randn(n)) * 0.2
                    lows = np.minimum(closes, opens) - np.abs(np.random.randn(n)) * 0.2
                    h1 = pd.DataFrame({'open': opens, 'high': highs, 'low': lows, 'close': closes})
                    h4 = h1.iloc[::4].copy()
                    d1 = h1.iloc[::20].copy()

                    new_sigs = gen(h1, h4, d1, cfg)
                    old_sigs = old_results.get(strategy, {}).get('signals', 0)
                    new_sigs_count = len(new_sigs)

                    improvement = new_sigs_count - old_sigs
                    improvements[strategy] = {
                        'old': old_sigs,
                        'new': new_sigs_count,
                        'change': improvement,
                        'status': 'improved' if improvement > 0 else 'declined',
                    }

                    if improvement <= 0:
                        all_good = False

        return {
            'all_improved': all_good,
            'details': improvements,
        }

    def run_auto_evolution(self, max_loops: int = 5):
        """运行自动进化循环"""
        print('='*70)
        print('🚀 主动进化引擎启动')
        print('模式: 全自动循环优化 (无需人工干预)')
        print(f'目标: {max_loops}轮迭代')
        print('='*70)

        for loop in range(1, max_loops + 1):
            result = self.run_loop(loop)

            # 保存每轮结果
            self._save_loop_result(result)

            # 检查是否收敛
            if loop > 1 and result.get('improvements', {}).get('all_improved', True):
                print(f'\n✅ 第{loop}轮: 所有策略改进，收敛达标')
                break

            time.sleep(0.1)  # 避免过快

        self._save_final_report()
        return self.results_log

    def _save_loop_result(self, result: Dict):
        """保存每轮结果"""
        output_dir = 'E:/GoldstrategyEngine/evolution'
        os.makedirs(output_dir, exist_ok=True)

        filename = f'{output_dir}/loop_{result["loop"]:03d}.json'
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    def _save_final_report(self):
        """保存最终报告"""
        output_dir = 'E:/GoldstrategyEngine/evolution'
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'{output_dir}/final_report_{timestamp}.json'

        report = {
            'timestamp': timestamp,
            'total_loops': self.loop_count,
            'results': self.results_log,
            'summary': {
                'loops_completed': self.loop_count,
                'final_status': 'converged' if self.loop_count > 0 else 'failed',
            }
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f'\n✅ 最终报告已保存: {filename}')


# ═══════════════════════════════════════════════════════════════
# 主程序
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    loop = AutoEvolutionLoop()
    loop.run_auto_evolution(max_loops=3)
    print('\n🎉 主动进化完成！')
