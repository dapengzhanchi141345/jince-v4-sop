# -*- coding: utf-8 -*-
"""
金策·进化营 - Risk-Officer独立风控审查模块
===========================================
chief裁决⑤：在进化结果进入"候选区"前，必须经过独立风控审查。
重点审查：最大回撤(MDD)和夏普比率(Sharpe)，而非仅看期望R。
风控模块拥有"否决权"。
"""

import os
import sys
import json
import logging
import math
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger('risk_officer')


@dataclass
class RiskReview:
    """风控审查结果"""
    passed: bool
    mdd: float
    sharpe: float
    exp_r: float
    max_consecutive_losses: int
    drawdown_duration: int
    notes: list


class RiskOfficer:
    """独立风控审查官"""

    # 风控阈值
    MAX_MDD = 0.15  # 最大回撤15%
    MIN_SHARPE = 0.5  # 最小夏普比率0.5
    MAX_CONSECUTIVE_LOSSES = 5  # 最大连续亏损5笔
    MAX_DRAWDOWN_DURATION = 30  # 最大回撤持续30根

    def __init__(self):
        self.review_history = []

    def review(self, genome: Any, fitness: Dict) -> RiskReview:
        """
        执行独立风控审查

        参数：
            genome: 待审查的基因组
            fitness: 背测结果

        返回：
            RiskReview
        """
        notes = []

        # 1. 最大回撤审查
        mdd = self._calc_mdd(fitness)
        mdd_pass = mdd <= self.MAX_MDD
        if not mdd_pass:
            notes.append(f"❌ MDD={mdd:.2%} > {self.MAX_MDD:.0%}阈值")

        # 2. 夏普比率审查
        sharpe = self._calc_sharpe(fitness)
        sharpe_pass = sharpe >= self.MIN_SHARPE
        if not sharpe_pass:
            notes.append(f"❌ Sharpe={sharpe:.2f} < {self.MIN_SHARPE:.2f}阈值")

        # 3. 期望R审查（chief关注）
        exp_r = fitness.get('exp_r', 0.0)
        exp_r_pass = exp_r > 0.0
        if not exp_r_pass:
            notes.append(f"❌ exp_r={exp_r:.4f} < 0（负期望）")

        # 4. 连续亏损审查
        max_consec_losses = self._calc_max_consecutive_losses(fitness)
        consec_pass = max_consec_losses <= self.MAX_CONSECUTIVE_LOSSES
        if not consec_pass:
            notes.append(f"❌ 连续亏损{max_consec_losses}笔 > {self.MAX_CONSECUTIVE_LOSSES}笔")

        # 5. 回撤持续审查
        dd_duration = self._calc_drawdown_duration(fitness)
        duration_pass = dd_duration <= self.MAX_DRAWDOWN_DURATION
        if not duration_pass:
            notes.append(f"❌ 回撤持续{dd_duration}根 > {self.MAX_DRAWDOWN_DURATION}根")

        # 综合裁决
        all_pass = mdd_pass and sharpe_pass and exp_r_pass and consec_pass and duration_pass

        review = RiskReview(
            passed=all_pass,
            mdd=mdd,
            sharpe=sharpe,
            exp_r=exp_r,
            max_consecutive_losses=max_consec_losses,
            drawdown_duration=dd_duration,
            notes=notes
        )

        # 记录历史
        self.review_history.append({
            'time': __import__('datetime').datetime.now().isoformat(),
            'passed': all_pass,
            'mdd': mdd,
            'sharpe': sharpe,
            'exp_r': exp_r,
            'notes': notes
        })

        # 日志
        if all_pass:
            logger.info(f"✅ 风控审查通过 | MDD={mdd:.2%} | Sharpe={sharpe:.2f} | exp_r={exp_r:.4f}")
        else:
            logger.warning(f"❌ 风控审查驳回 | {'; '.join(notes)}")

        return review

    def _calc_mdd(self, fitness: Dict) -> float:
        """计算最大回撤（简化版）"""
        # TODO: 实际应从交易日志计算
        exp_r = fitness.get('exp_r', 0.0)
        win_rate = fitness.get('win_rate', 0.5)
        # 简化公式：MDD与负期望成正比
        return max(0.05, abs(exp_r) * 0.5) if exp_r < 0 else 0.05

    def _calc_sharpe(self, fitness: Dict, risk_free_rate: float = 0.0) -> float:
        """计算夏普比率"""
        exp_r = fitness.get('exp_r', 0.0)
        win_rate = fitness.get('win_rate', 0.5)
        variance = win_rate * (1 - win_rate)
        if variance > 0:
            return exp_r / math.sqrt(variance)
        return 0.0

    def _calc_max_consecutive_losses(self, fitness: Dict) -> int:
        """计算最大连续亏损笔数（简化）"""
        # TODO: 实际应从交易日志计算
        return max(1, int(fitness.get('losses', 0) / 10))

    def _calc_drawdown_duration(self, fitness: Dict) -> int:
        """计算最大回撤持续根数（简化）"""
        # TODO: 实际应从交易日志计算
        return max(10, int(fitness.get('sample_size', 0) * 0.1))

    def get_summary(self) -> Dict:
        """获取风控审查摘要"""
        if not self.review_history:
            return {'total_reviews': 0}

        passed = sum(1 for r in self.review_history if r['passed'])
        n = len(self.review_history)
        avg_mdd = sum(r['mdd'] for r in self.review_history) / n
        avg_sharpe = sum(r['sharpe'] for r in self.review_history) / n
        avg_exp_r = sum(r['exp_r'] for r in self.review_history) / n

        return {
            'total_reviews': len(self.review_history),
            'passed_count': passed,
            'pass_rate': passed / len(self.review_history),
            'avg_mdd': avg_mdd,
            'avg_sharpe': avg_sharpe,
            'avg_exp_r': avg_exp_r,
            'recent_reviews': self.review_history[-5:]
        }


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Risk-Officer独立风控审查')
    parser.add_argument('--test', action='store_true', help='测试风控模块')
    args = parser.parse_args()

    if args.test:
        # 测试风控模块
        officer = RiskOfficer()

        # 模拟审查
        test_fitness = {
            'exp_r': 0.3722,
            'win_rate': 0.59,
            'sample_size': 312,
            'wins': 184,
            'losses': 128
        }

        review = officer.review(None, test_fitness)
        print(f"✅ 风控审查完成")
        print(f"   通过: {review.passed}")
        print(f"   MDD: {review.mdd:.2%}")
        print(f"   Sharpe: {review.sharpe:.2f}")
        print(f"   exp_r: {review.exp_r:.4f}")
        if review.notes:
            print(f"   备注: {review.notes}")

        summary = officer.get_summary()
        print(f"\n📊 风控统计:")
        print(f"   总审查次数: {summary['total_reviews']}")
        print(f"   通过率: {summary['pass_rate']:.1%}")
        print(f"   平均MDD: {summary['avg_mdd']:.2%}")
        print(f"   平均Sharpe: {summary['avg_sharpe']:.2f}")


if __name__ == "__main__":
    main()
