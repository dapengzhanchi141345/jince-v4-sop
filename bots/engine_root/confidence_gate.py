# -*- coding: utf-8 -*-
"""
金策·进化营 - 置信区间审查模块
===============================
Chief裁决：将审查逻辑从"固定样本量"改为"置信区间非负"判定。
要求候选策略的exp_r 95%置信区间下界 > 0，而非单纯看均值。
"""

import os
import sys
import json
import logging
import math
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger('confidence_gate')


@dataclass
class ConfidenceReview:
    """置信区间审查结果"""
    passed: bool
    exp_r_mean: float
    exp_r_ci_lower: float  # 95%置信区间下界
    exp_r_ci_upper: float  # 95%置信区间上界
    sample_size: int
    confidence_level: float = 0.95
    notes: list = None


class ConfidenceGate:
    """置信区间审查闸门（Chief裁决③）"""

    def __init__(self, confidence_level: float = 0.95, min_sample_size: int = 30):
        self.confidence_level = confidence_level
        self.min_sample_size = min_sample_size
        self.review_history = []

    def review(self, fitness: Dict) -> ConfidenceReview:
        """
        执行置信区间审查

        参数：
            fitness: 包含exp_r, wins, losses, sample_size等字段

        返回：
            ConfidenceReview
        """
        notes = []
        exp_r = fitness.get('exp_r', 0.0)
        wins = fitness.get('wins', 0)
        losses = fitness.get('losses', 0)
        sample_size = fitness.get('sample_size', 0)

        # 1. 样本量检查
        if sample_size < self.min_sample_size:
            return ConfidenceReview(
                passed=False,
                exp_r_mean=exp_r,
                exp_r_ci_lower=float('-inf'),
                exp_r_ci_upper=float('inf'),
                sample_size=sample_size,
                notes=[f"❌ 样本不足: {sample_size} < {self.min_sample_size}"]
            )

        # 2. 计算置信区间（使用正态近似）
        # z值 for 95% CI ≈ 1.96
        z = 1.96
        
        # Wilson score interval for binomial proportion
        n = wins + losses
        if n == 0:
            return ConfidenceReview(
                passed=False,
                exp_r_mean=exp_r,
                exp_r_ci_lower=float('-inf'),
                exp_r_ci_upper=float('inf'),
                sample_size=0,
                notes=[f"❌ 无交易样本"]
            )
        
        win_rate = wins / n
        
        # Wilson score interval
        denominator = 1 + z**2 / n
        center = (win_rate + z**2 / (2 * n)) / denominator
        spread = z * math.sqrt(max(0, win_rate * (1 - win_rate) / n + z**2 / (4 * n**2))) / denominator
        
        ci_lower = center - spread
        ci_upper = center + spread
        
        # 转换为exp_r的置信区间（简化线性映射）
        if win_rate > 0:
            exp_r_ci_lower = exp_r * (ci_lower / win_rate)
            exp_r_ci_upper = exp_r * (ci_upper / win_rate)
        else:
            exp_r_ci_lower = exp_r
            exp_r_ci_upper = exp_r

        # 3. 判断是否通过
        passed = exp_r_ci_lower > 0
        
        if not passed:
            notes.append(f"❌ 置信区间下界={exp_r_ci_lower:.4f} ≤ 0（需>0）")
            notes.append(f"   95% CI: [{exp_r_ci_lower:.4f}, {exp_r_ci_upper:.4f}]")
        else:
            notes.append(f"✅ 置信区间下界={exp_r_ci_lower:.4f} > 0")

        # 4. 记录历史
        self.review_history.append({
            'time': datetime.now().isoformat(),
            'passed': passed,
            'exp_r': exp_r,
            'ci_lower': exp_r_ci_lower,
            'ci_upper': exp_r_ci_upper,
            'sample_size': sample_size,
            'notes': notes
        })

        return ConfidenceReview(
            passed=passed,
            exp_r_mean=exp_r,
            exp_r_ci_lower=exp_r_ci_lower,
            exp_r_ci_upper=exp_r_ci_upper,
            sample_size=sample_size,
            notes=notes
        )

    def get_summary(self) -> Dict:
        """获取审查摘要"""
        if not self.review_history:
            return {'total_reviews': 0}

        passed = sum(1 for r in self.review_history if r['passed'])
        
        return {
            'total_reviews': len(self.review_history),
            'passed_count': passed,
            'pass_rate': passed / len(self.review_history) if self.review_history else 0,
            'avg_exp_r': sum([r['exp_r'] for r in self.review_history]) / len(self.review_history) if self.review_history else 0,
            'avg_ci_lower': sum([r['ci_lower'] for r in self.review_history]) / len(self.review_history) if self.review_history else 0,
            'recent_reviews': self.review_history[-5:]
        }


def main():
    import argparse
    parser = argparse.ArgumentParser(description='置信区间审查闸门')
    parser.add_argument('--test', action='store_true', help='测试审查模块')
    args = parser.parse_args()

    if args.test:
        # 测试用例
        gate = ConfidenceGate(confidence_level=0.95, min_sample_size=30)

        # 测试1：高exp_r，大样本（应通过）
        test1 = {'exp_r': 0.3722, 'wins': 364, 'losses': 266, 'sample_size': 630}
        result1 = gate.review(test1)
        print(f"测试1（高exp_r大样本）:")
        print(f"  exp_r={result1.exp_r_mean:.4f}")
        print(f"  95% CI: [{result1.exp_r_ci_lower:.4f}, {result1.exp_r_ci_upper:.4f}]")
        print(f"  通过: {result1.passed}")
        print()

        # 测试2：负exp_r（应失败）
        test2 = {'exp_r': -0.1438, 'wins': 72, 'losses': 120, 'sample_size': 192}
        result2 = gate.review(test2)
        print(f"测试2（负exp_r）:")
        print(f"  exp_r={result2.exp_r_mean:.4f}")
        print(f"  95% CI: [{result2.exp_r_ci_lower:.4f}, {result2.exp_r_ci_upper:.4f}]")
        print(f"  通过: {result2.passed}")
        print()

        # 测试3：小样本（应失败）
        test3 = {'exp_r': 0.5, 'wins': 5, 'losses': 5, 'sample_size': 10}
        result3 = gate.review(test3)
        print(f"测试3（小样本）:")
        print(f"  exp_r={result3.exp_r_mean:.4f}")
        print(f"  通过: {result3.passed}")
        print(f"  备注: {result3.notes}")
        print()

        # 测试4：边缘情况（exp_r略正，样本适中）
        test4 = {'exp_r': 0.05, 'wins': 52, 'losses': 48, 'sample_size': 100}
        result4 = gate.review(test4)
        print(f"测试4（边缘情况）:")
        print(f"  exp_r={result4.exp_r_mean:.4f}")
        print(f"  95% CI: [{result4.exp_r_ci_lower:.4f}, {result4.exp_r_ci_upper:.4f}]")
        print(f"  通过: {result4.passed}")
        print()

        summary = gate.get_summary()
        print(f"统计: 总审查{summary['total_reviews']}次, 通过{summary['passed_count']}次, 通过率{summary['pass_rate']:.1%}")


if __name__ == "__main__":
    main()
