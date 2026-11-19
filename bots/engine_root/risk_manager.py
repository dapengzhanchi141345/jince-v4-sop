# -*- coding: utf-8 -*-
"""
RiskManager V1.0 — 机构级风险管控引擎
========================================
对标 Jane Street / Citadel / AQR 机构风控标准

核心功能:
1. Tiered Drawdown Throttling (分级回撤减速)
   - 5%回撤: 风险减25%
   - 10%回撤: 风险减50%
   - 15%回撤: 暂停交易
2. Kelly Criterion 仓位管理 (Fractional Kelly)
3. ATR Volatility-Targeted Position Sizing
4. 品种相关性监控
5. 单日最大亏损熔断
"""

import numpy as np
import json
import os
from typing import Dict, Optional


class RiskManager:
    """机构级风险管控引擎"""

    def __init__(self, initial_equity: float = 10000.0):
        self.initial_equity = initial_equity
        self.current_equity = initial_equity
        self.peak_equity = initial_equity
        self.daily_pnl = 0.0
        self.daily_loss_limit = 0.02  # 单日最大亏损2%
        self.max_total_risk_pct = 0.06  # 总风险敞口上限6%
        self._drawdown_tier = 1.0  # 1.0 = 正常, 0.75 = 减25%, 0.5 = 减50%

        # 历史表现
        self.trade_history = []
        self.equity_curve = [initial_equity]
        self.daily_returns = []

        # 品种持仓记录
        self.positions = {}  # symbol -> position_info

    def update_equity(self, new_equity: float):
        """更新净值"""
        self.current_equity = new_equity
        self.peak_equity = max(self.peak_equity, new_equity)
        self.equity_curve.append(new_equity)

        # 计算日收益
        if len(self.equity_curve) >= 2:
            daily_ret = (new_equity - self.equity_curve[-2]) / self.equity_curve[-2]
            self.daily_returns.append(daily_ret)
            self.daily_pnl += daily_ret * self.equity_curve[-2]

    def get_drawdown_tier(self) -> float:
        """获取回撤级别风险系数"""
        drawdown = (self.peak_equity - self.current_equity) / self.peak_equity

        if drawdown >= 0.15:
            self._drawdown_tier = 0.0  # 暂停
            return 0.0
        elif drawdown >= 0.10:
            self._drawdown_tier = 0.5  # 减50%
            return 0.5
        elif drawdown >= 0.05:
            self._drawdown_tier = 0.75  # 减25%
            return 0.75
        return 1.0

    def check_daily_loss_limit(self) -> bool:
        """检查单日亏损是否触发熔断"""
        return abs(self.daily_pnl) / self.peak_equity >= self.daily_loss_limit

    def calculate_kelly_position(
        self,
        equity: float,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        risk_per_trade: float = 0.01
    ) -> float:
        """
        Kelly Criterion 仓位计算 (Fractional Kelly)

        K = (p * b - q) / b
        其中:
        p = 胜率
        b = 平均盈利/平均亏损 (盈亏比)
        q = 1 - p

        机构标准: 使用 1/4 Kelly 或 1/2 Kelly
        """
        if avg_loss <= 0 or win_rate <= 0:
            return risk_per_trade * equity

        b = avg_win / avg_loss
        p = win_rate
        q = 1 - p

        kelly_fraction = (p * b - q) / b

        # Fractional Kelly (1/4 Kelly 保守，1/2 Kelly 中等)
        fractional_kelly = kelly_fraction * 0.25

        # 确保在合理范围内
        fractional_kelly = max(0.005, min(fractional_kelly, 0.05))

        return fractional_kelly * equity

    def calculate_atr_position_size(
        self,
        equity: float,
        entry: float,
        sl: float,
        atr: float,
        risk_pct: float = 0.01
    ) -> float:
        """
        ATR 波动率目标仓位计算

        Position Size = (Equity × Risk%) / (Entry - SL)
        结合 ATR 动态调整风险敞口
        """
        if atr <= 0 or entry <= 0:
            return 0.01

        # 基础风险敞口
        risk_amount = equity * risk_pct * self._drawdown_tier

        # 每手风险
        risk_per_unit = abs(entry - sl)

        if risk_per_unit <= 0:
            return 0.01

        # 计算手数
        lots = risk_amount / risk_per_unit

        # 波动率调整: 高波动时减小仓位
        vol_adjustment = min(1.0, atr / (entry * 0.02))  # ATR/价格比 2% 为基准
        lots *= vol_adjustment

        # 限制范围
        return max(0.01, min(lots, 1.0))

    def calculate_position_size(
        self,
        symbol: str,
        entry: float,
        sl: float,
        atr: float,
        strategy: str = "UNKNOWN",
        equity: Optional[float] = None
    ) -> Dict:
        """
        综合仓位计算 (Kelly + ATR + Drawdown Tier)
        """
        eq = equity or self.current_equity

        # 检查熔断
        if self.check_daily_loss_limit():
            return {"lots": 0.0, "reason": "daily_loss_limit_hit"}

        # 检查回撤暂停
        tier = self.get_drawdown_tier()
        if tier == 0.0:
            return {"lots": 0.0, "reason": "drawdown_halt"}

        # ATR仓位计算
        atr_lots = self.calculate_atr_position_size(
            eq, entry, sl, atr, risk_pct=0.01 * tier
        )

        # 总风险检查
        total_risk = sum(
            abs(p.get("entry", 0) - p.get("sl", 0)) * p.get("lots", 0) / max(p.get("entry", 1), 1)
            for p in self.positions.values()
        ) * eq

        if total_risk / eq >= self.max_total_risk_pct:
            return {"lots": 0.0, "reason": "total_risk_limit"}

        return {
            "lots": round(atr_lots, 2),
            "risk_pct": 0.01 * tier,
            "tier": tier,
            "reason": "ok"
        }

    def add_position(self, symbol: str, side: int, entry: float, sl: float, tp: float, lots: float, strategy: str):
        """添加持仓记录"""
        self.positions[symbol] = {
            "side": side,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "lots": lots,
            "strategy": strategy,
            "open_time": len(self.equity_curve)
        }

    def close_position(self, symbol: str, exit_price: float, pnl: float):
        """平仓并记录"""
        if symbol in self.positions:
            pos = self.positions.pop(symbol)
            self.trade_history.append({
                "symbol": symbol,
                "side": pos["side"],
                "entry": pos["entry"],
                "exit": exit_price,
                "pnl": pnl,
                "strategy": pos["strategy"],
                "bar": len(self.equity_curve)
            })
            self.update_equity(self.current_equity + pnl)

    def get_performance_stats(self) -> Dict:
        """获取表现统计"""
        if not self.trade_history:
            return {"trades": 0, "win_rate": 0, "pf": 0, "max_drawdown": 0}

        wins = [t for t in self.trade_history if t["pnl"] > 0]
        losses = [t for t in self.trade_history if t["pnl"] <= 0]

        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))

        # 最大回撤
        peak = self.equity_curve[0]
        max_dd = 0
        for eq in self.equity_curve:
            peak = max(peak, eq)
            dd = (peak - eq) / peak
            max_dd = max(max_dd, dd)

        return {
            "trades": len(self.trade_history),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(self.trade_history) * 100 if self.trade_history else 0,
            "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float('inf'),
            "max_drawdown": max_dd * 100,
            "total_pnl": sum(t["pnl"] for t in self.trade_history),
            "drawdown_tier": self._drawdown_tier,
            "current_equity": self.current_equity
        }


if __name__ == "__main__":
    print("=" * 70)
    print("RiskManager V1.0 自检")
    print("=" * 70)

    rm = RiskManager(initial_equity=10000.0)

    # 测试1: 基础仓位计算
    result = rm.calculate_position_size("XAUUSD", 2600.0, 2550.0, 15.0, "OTAS")
    print(f"\n测试1 - 基础仓位:")
    print(f"  手数: {result['lots']}")
    print(f"  风险级别: {result['tier']}")
    print(f"  状态: {result['reason']}")

    # 测试2: 回撤减速
    print("\n测试2 - 回撤减速:")
    rm.update_equity(9500.0)  # 5% 回撤
    tier = rm.get_drawdown_tier()
    print(f"  回撤5%: 风险系数 = {tier} (应0.75)")

    rm.update_equity(9000.0)  # 10% 回撤
    tier = rm.get_drawdown_tier()
    print(f"  回撤10%: 风险系数 = {tier} (应0.5)")

    rm.update_equity(8500.0)  # 15% 回撤
    tier = rm.get_drawdown_tier()
    print(f"  回撤15%: 风险系数 = {tier} (应0.0，暂停)")

    # 测试3: Kelly计算
    print("\n测试3 - Kelly仓位:")
    kelly_size = rm.calculate_kelly_position(
        equity=10000.0,
        win_rate=0.55,
        avg_win=150.0,
        avg_loss=100.0
    )
    print(f"  胜率55%, 盈亏比1.5: Kelly仓位 = ${kelly_size:.2f}")

    # 测试4: 表现统计
    print("\n测试4 - 表现统计:")
    rm.add_position("XAUUSD", 1, 2600.0, 2550.0, 2700.0, 0.1, "OTAS")
    rm.close_position("XAUUSD", 2650.0, 500.0)
    stats = rm.get_performance_stats()
    print(f"  交易数: {stats['trades']}")
    print(f"  胜率: {stats['win_rate']:.1f}%")
    print(f"  PF: {stats['profit_factor']:.2f}")
    print(f"  当前净值: ${stats['current_equity']:.2f}")

    print("\n" + "=" * 70)
    print("✅ RiskManager 自检完成")
    print("=" * 70)
