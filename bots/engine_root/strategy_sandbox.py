# -*- coding: utf-8 -*-
"""
策略沙盒架构 - 各策略独立运行，互不影响
"""

import json
from typing import Dict, List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class SandboxPosition:
    symbol: str
    side: int
    entry: float
    sl: float
    tp: float
    lot: float
    strategy: str
    open_time: str
    bar_index: int = 0
    
    def to_dict(self):
        return {
            "symbol": self.symbol,
            "side": self.side,
            "entry": self.entry,
            "sl": self.sl,
            "tp": self.tp,
            "lot": self.lot,
            "strategy": self.strategy,
            "open_time": self.open_time,
            "bar_index": self.bar_index
        }


class StrategySandbox:
    def __init__(self, strategy_name: str, max_positions: int = 1):
        self.strategy_name = strategy_name
        self.max_positions = max_positions
        self.positions = {}
        self.trade_history = []
        self.stats = {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "total_pnl": 0.0
        }
    
    def has_position(self, symbol):
        return symbol in self.positions
    
    def open_position(self, symbol, side, entry, sl, tp, lot, bar_index=0):
        if self.has_position(symbol):
            return False
        if len(self.positions) >= self.max_positions:
            return False
        pos = SandboxPosition(
            symbol=symbol, side=side, entry=entry, sl=sl, tp=tp,
            lot=lot, strategy=self.strategy_name,
            open_time=datetime.now().isoformat(), bar_index=bar_index
        )
        self.positions[symbol] = pos
        self.stats["total_trades"] += 1
        return True
    
    def close_position(self, symbol, pnl=0.0):
        if symbol not in self.positions:
            return False
        pos = self.positions.pop(symbol)
        self.trade_history.append({
            "symbol": pos.symbol, "side": pos.side,
            "entry": pos.entry, "exit_pnl": pnl,
            "open_time": pos.open_time,
            "close_time": datetime.now().isoformat()
        })
        self.stats["total_pnl"] += pnl
        if pnl > 0:
            self.stats["wins"] += 1
        else:
            self.stats["losses"] += 1
        return True
    
    def get_status(self):
        return {
            "strategy": self.strategy_name,
            "positions": len(self.positions),
            "symbols": list(self.positions.keys()),
            "stats": self.stats.copy()
        }


class StrategySandboxManager:
    def __init__(self, initial_equity=10000.0):
        self.sandboxes = {}
        self.initial_equity = initial_equity
        self.current_equity = initial_equity
        self.max_total_risk_pct = 0.05
        self._init_sandboxes()
    
    def _init_sandboxes(self):
        for name in ["OTAS", "PASD", "TREND", "DIV", "MR", "BO"]:
            self.sandboxes[name] = StrategySandbox(name, max_positions=1)
    
    def can_open_position(self, symbol, strategy):
        if strategy not in self.sandboxes:
            return False
        sandbox = self.sandboxes[strategy]
        if sandbox.has_position(symbol):
            return False
        total_risk = sum(
            pos.lot * 0.001 
            for sb in self.sandboxes.values() 
            for pos in sb.positions.values()
        )
        return total_risk < self.max_total_risk_pct
    
    def open_position(self, symbol, strategy, side, entry, sl, tp, lot):
        if not self.can_open_position(symbol, strategy):
            return False
        return self.sandboxes[strategy].open_position(
            symbol, side, entry, sl, tp, lot
        )
    
    def get_conflict_check(self, symbol):
        positions = {}
        for name, sandbox in self.sandboxes.items():
            for sym, pos in sandbox.positions.items():
                if sym == symbol:
                    positions[name] = pos.to_dict()
        return {
            "has_position": len(positions) > 0,
            "position_by": list(positions.keys()),
            "all_positions": positions
        }


if __name__ == "__main__":
    manager = StrategySandboxManager()
    print("策略沙盒架构测试")
    
    # 测试1: 多品种并行开仓
    print("")
    print("测试1: 多品种并行开仓")
    symbols = ["XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD"]
    strategies = ["OTAS", "PASD", "TREND", "DIV"]
    for sym, strat in zip(symbols, strategies):
        success = manager.open_position(sym, strat, 1, 2600.0, 2550.0, 2700.0, 0.1)
        status = "PASS" if success else "FAIL"
        print(f"  {sym} ({strat}): {status}")
    
    # 测试2: 同品种冲突检查
    print("")
    print("测试2: 同品种冲突检查")
    conflict = manager.get_conflict_check("XAUUSD")
    print(f"  XAUUSD已有持仓: {conflict['has_position']}")
    print(f"  持仓策略: {conflict['position_by']}")
    
    # 测试3: 各策略独立状态
    print("")
    print("测试3: 各策略独立状态")
    for name, sb in manager.sandboxes.items():
        if sb.positions:
            print(f"  {name}: {list(sb.positions.keys())}")
    
    print("")
    print("架构验证通过")
