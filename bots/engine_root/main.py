# ============================================================================
# [2026-11-02 金策·御史 审计] 旧单引擎 —— 已停止维护，勿用于实盘
# 现状: (1) from strategies.supply_demand import SupplyDemandSMC 实跑 ImportError
#       (2) 本文件调用 ema_trend/adx_analysis/macd_signal/rsi_signal/bollinger_signal/
#           candle_pattern，而 TechnicalStrategies 只提供 analyze()
#       (3) supply_demand.py 含 3 处未来函数 (i+1 / i+3)
# 生产链: multi_agent/ (30min 全链)。修活本文件需重写适配层并过五验。
# 审计报告: E:\AgentCommons\yushi\reports\2026-11-02\审计报告_v1.md
# ============================================================================
"""
金策宗师团 — MT5 量化交易引擎 主入口
Goldstrategy Guild v1.0.0 — Main Entry Point

用法:
    python main.py              # 单次运行 (信号分析)
    python main.py --monitor    # 持续监控模式
    python main.py --backtest   # 回测模式

运行前必须在 config.py 中填写 MT5 账号信息!
"""

import sys
import os
import time
import json
import argparse
from datetime import datetime
from typing import Optional, Dict

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import TRADING_CONFIG, DATA_CONFIG, ENGINE_MODE, PATHS, RISK_CONFIG
from mt5_connector import MT5Connector
from strategies.supply_demand import SupplyDemandSMC
from strategies.technical import TechnicalStrategies, SupportResistance
from engine.hmm_regime import HMMRegimeDetector
from engine.voting import VotingEngine
from risk.risk_manager import RiskManager
from execution.order_manager import OrderExecutor, PositionManager, TradeLogger


class GoldstrategyEngine:
    """
    金策宗师团主引擎
    集成: 策略层 → 引擎层 → 风控层 → 执行层
    """

    def __init__(self):
        self.connector = MT5Connector()
        self.sd_strategy = SupplyDemandSMC(DATA_CONFIG)
        self.tech_strategy = TechnicalStrategies()
        self.sr_strategy = SupportResistance()
        self.regime_detector = HMMRegimeDetector({
            "n_regimes": 4,
            "lookback_days": 90,
            "retrain_interval": 24,
        })
        self.voting = VotingEngine()
        self.risk = RiskManager()
        self.executor = None
        self.position_mgr = None
        self.logger = TradeLogger()

        # 状态
        self.current_regime = "RANGING"
        self.consecutive_wins = 0
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self.bayesian = {"mean_winrate": 0.5, "conservative_winrate": 0.3}

    # ─── 初始化 ─────────────────────────

    def initialize(self) -> bool:
        """初始化引擎 (连接MT5)"""
        print("=" * 50)
        print("  金策宗师团 — Goldstrategy Guild v1.0.0")
        print(f"  模式: {ENGINE_MODE}")
        print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 50)

        if not self.connector.connect():
            print("[ENGINE] ❌ MT5 连接失败")
            print("[ENGINE] 请在 config.py 中填写正确的账号信息后重试")
            return False

        self.executor = OrderExecutor(self.connector)
        self.position_mgr = PositionManager(self.executor)
        print(f"[ENGINE] ✅ 引擎初始化完成 | 品种: {TRADING_CONFIG['symbol']}")
        return True

    def shutdown(self):
        """关闭引擎"""
        self.connector.disconnect()
        print("[ENGINE] 引擎已关闭")

    # ─── 主运行循环 ─────────────────────

    def run_once(self) -> dict:
        """单次运行: 分析市场 + 决策 + 执行"""
        result = {
            "timestamp": datetime.now().isoformat(),
            "status": "OK",
            "regime": "UNKNOWN",
            "signal": "NONE",
            "trade": None,
        }

        # 1. 获取数据
        df_h1 = self.connector.get_rates("H1", 200)
        df_m15 = self.connector.get_rates("M15", 200)
        df_m5 = self.connector.get_rates("M5", 100)
        tick = self.connector.get_tick()

        if tick is None or df_h1 is None:
            result["status"] = "NO_DATA"
            return result

        current_price = (tick["bid"] + tick["ask"]) / 2
        account = self.connector.get_account_info()

        print(f"\n{'='*50}")
        print(f"  当前价格: ${current_price:.1f} | 余额: ${account.get('balance',0):.0f}")
        print(f"{'='*50}")

        # 2. 市场状态检测
        self.current_regime = self.regime_detector.detect_regime(df_h1)
        regime_params = self.regime_detector.get_regime_params(self.current_regime)
        result["regime"] = self.current_regime
        print(f"\n📊 市场状态: {self.current_regime}")
        print(f"   {regime_params['description']}")
        print(f"   策略阈值: {regime_params['vote_threshold']} | Kelly: {regime_params['kelly_fraction']}")

        # 3. 执行所有策略
        signals = {}
        supplier = self.connector.get_symbol_info()
        spread = tick["spread"] / (supplier.get("point", 0.001) or 0.001)

        # 3a. 供需SMC
        sd_signal = self.sd_strategy.generate_signal(df_h1, current_price, self.current_regime)
        signals["supply_demand"] = sd_signal
        signals["order_block_smc"] = {"direction": sd_signal["direction"], "score": sd_signal["score"] * 0.5, "reasoning": "SMC汇合"}
        signals["fvg"] = {"direction": "NONE", "score": 0, "reasoning": ""}

        # 3b. 技术指标
        signals["trend_ema"] = self.tech_strategy.ema_trend(df_h1, current_price)
        signals["trend_adx"] = self.tech_strategy.adx_analysis(df_h1)
        signals["macd"] = self.tech_strategy.macd_signal(df_h1)
        signals["rsi_mean_reversion"] = self.tech_strategy.rsi_signal(df_h1, current_price)

        # 3c. 布林带
        signals["bollinger"] = self.tech_strategy.bollinger_signal(df_h1, current_price)

        # 3d. K线形态
        signals["candle_pattern"] = self.tech_strategy.candle_pattern(df_h1)

        # 3e. 支撑阻力
        sr_levels = self.sr_strategy.detect_levels(df_h1)
        signals["support_resistance"] = self.sr_strategy.generate_signal(sr_levels, current_price)

        # 4. 加权投票
        vote_result = self.voting.evaluate(signals, self.current_regime)
        result["signal"] = vote_result

        # 打印投票结果
        print(f"\n🗳️  策略投票结果:")
        print(f"   买入得分: {vote_result['buy_score']:.1f} | 卖出得分: {vote_result['sell_score']:.1f}")
        print(f"   净得分: {vote_result['net_score']:.1f} | 阈值: {vote_result['threshold']}")
        print(f"   决策: {vote_result['direction']} (置信度: {vote_result['confidence']:.1%})")
        print(f"   活跃策略: {vote_result['active_strategies']}")
        for r in vote_result["reasons"][:5]:
            print(f"     {r}")

        # 记录信号
        self.logger.log_signal(vote_result, self.current_regime)

        # 5. 如果信号有效 → 执行
        if vote_result["direction"] != "NONE" and ENGINE_MODE == "DEMO":
            print(f"\n🔶 DEMO模式: 信号已生成, 但不执行真实交易")

        if vote_result["direction"] != "NONE" and ENGINE_MODE == "LIVE":
            self._execute_trade(vote_result, current_price, account, spread, regime_params)

        # 6. 管理现有持仓
        positions = self.connector.get_positions()
        if positions:
            atr = self._calc_atr(df_h1)
            self.position_mgr.manage_positions(positions, atr)

        return result

    # ─── 执行交易 ───────────────────────

    def _execute_trade(self, vote_result: dict, price: float,
                       account: dict, spread: float, regime_params: dict):
        """执行交易 (LIVE模式)"""
        if self.executor is None:
            return

        direction = vote_result["direction"]

        # 获取最佳的入场价格
        best_signal = None
        best_entry = 0
        best_sl = 0
        best_tp = 0

        for name, sig in vote_result["raw_signals"].items():
            if sig["direction"] == direction and sig.get("entry", 0) > 0:
                if best_signal is None or sig.get("score", 0) > best_signal.get("score", 0):
                    best_signal = sig
                    best_entry = sig["entry"]
                    best_sl = sig["sl"]
                    best_tp = sig["tp"]

        if best_entry == 0:
            # 使用当前价格
            best_entry = price
            atr = self._calc_atr_from_connector()
            if direction == "BUY":
                best_sl = price - atr * 1.5
                best_tp = price + atr * 3.0
            else:
                best_sl = price + atr * 1.5
                best_tp = price - atr * 3.0

        # 风控检查
        context = {
            "balance": account.get("balance", 10000),
            "equity": account.get("equity", 10000),
            "atr": self._calc_atr_from_connector(),
            "current_price": price,
            "spread": spread,
            "entry": best_entry,
            "sl": best_sl,
            "tp": best_tp,
            "direction": direction,
            "current_hour": datetime.now().hour,
        }

        risk_check = self.risk.check_all(context)
        if not risk_check["all_pass"]:
            print(f"\n❌ 风控拒绝交易:")
            for check, passed in risk_check["checks"].items():
                if not passed:
                    print(f"   {check}: ❌")
            return

        # Kelly 仓位
        kelly_pct = self.risk.calc_kelly(
            self.bayesian["conservative_winrate"],
            abs(best_tp - best_entry),
            abs(best_entry - best_sl),
        )

        # 反马丁格尔
        am_mult = self.risk.calc_anti_martingale(self.consecutive_wins)
        final_risk_pct = kelly_pct * am_mult

        # 计算手数
        risk_amount = account.get("balance", 10000) * min(final_risk_pct, 0.01)
        sl_distance = abs(best_entry - best_sl)
        lot_size = self.executor.calc_lot_size(risk_amount, sl_distance)

        if lot_size <= 0:
            print("[TRADE] 手数计算为0, 跳过")
            return

        # 执行
        print(f"\n📈 执行交易:")
        print(f"   方向: {direction} | 手数: {lot_size:.2f}")
        print(f"   入场: ${best_entry:.1f} | SL: ${best_sl:.1f} | TP: ${best_tp:.1f}")
        print(f"   风险: ${risk_amount:.2f} ({final_risk_pct*100:.2f}%)")

        trade_result = self.executor.market_order(
            direction, lot_size, best_sl, best_tp
        )

        if trade_result["status"] == "EXECUTED":
            self.total_trades += 1
            self.logger.log_trade(trade_result, {
                "winrate": self.bayesian["mean_winrate"],
                "kelly": kelly_pct,
                "vote_score": vote_result["net_score"],
            }, self.current_regime)

    def _calc_atr(self, df, period=14) -> float:
        """计算ATR"""
        if df is None or len(df) < period:
            return 1.0

        high = df["high"].values[-period:]
        low = df["low"].values[-period:]
        close = df["close"].values[-period - 1:-1]

        tr_values = []
        for i in range(len(high)):
            hl = high[i] - low[i]
            hc = abs(high[i] - close[i]) if i < len(close) else 0
            lc = abs(low[i] - close[i]) if i < len(close) else 0
            tr_values.append(max(hl, hc, lc))

        return np.mean(tr_values) if tr_values else 1.0

    def _calc_atr_from_connector(self) -> float:
        """从连接器获取ATR"""
        df = self.connector.get_rates("H1", 20)
        return self._calc_atr(df)

    # ─── 持续监控 ───────────────────────

    def run_monitor(self, interval_seconds=300):
        """持续监控模式"""
        print(f"\n🔄 持续监控模式 | 每{interval_seconds}s检查一次")

        while True:
            try:
                if not self.connector.is_connected():
                    self.connector.reconnect()

                self.run_once()

                print(f"\n⏳ 等待 {interval_seconds}s 后下次检查...")
                print("-" * 50)
                time.sleep(interval_seconds)

            except KeyboardInterrupt:
                print("\n[ENGINE] 用户终止")
                break
            except Exception as e:
                print(f"\n[ENGINE] 错误: {e}")
                time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="金策宗师团 MT5 交易引擎")
    parser.add_argument("--monitor", action="store_true", help="持续监控模式")
    parser.add_argument("--interval", type=int, default=300, help="监控间隔(秒)")
    args = parser.parse_args()

    engine = GoldstrategyEngine()

    if not engine.initialize():
        sys.exit(1)

    try:
        if args.monitor:
            engine.run_monitor(args.interval)
        else:
            engine.run_once()
    finally:
        engine.shutdown()


if __name__ == "__main__":
    # 为了在Python 3.13+中兼容, 使用numpy导入
    import numpy as np
    main()
