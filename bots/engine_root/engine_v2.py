"""
金策宗师团 v2.0 — 自进化多智能体交易系统架构
Goldstrategy Guild v2.0 — Self-Evolving Multi-Agent Trading System

核心升级:
  1. 三层多智能体架构 (分析师 → 策略室 → 决策官)
  2. 深度强化学习自进化引擎 (PPO/A2C/DDPG 集成)
  3. 在线学习 + 滚动验证 (每季度自动选最优模型)
  4. 知识蒸馏: MQL5 经验 → Python ML 模型

架构:
  Level 1: 专业分析师 (4个独立智能体)
    ├─ 猎场司: 供需区 + SMC + 技术指标
    ├─ 算天机: 量化风控 + Kelly + Bayesian
    ├─ 观局势: 宏观 + 情绪 + 新闻分析
    └─ 研报员: K线形态 + 图表模式 + 结构

  Level 2: 策略室 (1个整合智能体)
    └─ 策金尊(分析师版本): 整合4位分析师, 行业标准化, 评分聚合

  Level 3: 决策官 (1个最终决策者)
    └─ 策金尊(决策官版本): 综合观点, 风控门禁, 最终下单

  底层引擎:
    └─ DRL自进化层: PPO/A2C/DDPG → 滚动选择最佳代理
"""

import numpy as np
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
import json


# ═══════════════════════════════════════════
# 1. 数据结构定义
# ═══════════════════════════════════════════

class SignalDirection(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NONE = "NONE"


class MarketRegime(Enum):
    STRONG_TREND = "STRONG_TREND"
    WEAK_TREND = "WEAK_TREND" 
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    RANGING = "RANGING"


@dataclass
class AnalystReport:
    """分析师报告 — 统一格式"""
    agent_id: str
    agent_name: str
    score: float                # 0-100 吸引力评分
    direction: SignalDirection
    confidence: float           # 0-1
    reasoning: str
    signals: Dict[str, Any]    # 原始信号数据
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class TradeDecision:
    """最终交易决策"""
    direction: SignalDirection
    entry_price: float
    stop_loss: float
    take_profit: float
    volume: float
    confidence: float
    vote_score: float
    regime: MarketRegime
    kelly_fraction: float
    risk_checks: Dict[str, bool]
    analyst_scores: Dict[str, float]
    reasoning: str


# ═══════════════════════════════════════════
# 2. Level 1: 专业分析师团队
# ═══════════════════════════════════════════

class BaseAnalyst:
    """分析师基类"""
    
    def __init__(self, agent_id: str, name: str):
        self.agent_id = agent_id
        self.name = name
        self.history: List[AnalystReport] = []
        self.performance: Dict = {
            "total_signals": 0,
            "correct_signals": 0,
            "avg_score": 50.0,
            "reliability": 0.5,  # 历史可靠性权重
        }

    def analyze(self, market_data: Dict) -> AnalystReport:
        """分析市场并生成报告 (子类实现)"""
        raise NotImplementedError

    def update_performance(self, was_correct: bool):
        """更新历史表现"""
        self.performance["total_signals"] += 1
        if was_correct:
            self.performance["correct_signals"] += 1
        
        total = self.performance["total_signals"]
        correct = self.performance["correct_signals"]
        self.performance["reliability"] = correct / total if total > 0 else 0.5


class MarketAnalyst(BaseAnalyst):
    """猎场司 — 市场分析专家
    负责: 供需区/SMC/FVG/EMA/MACD/ADX/RSI/布林带/K线形态
    """
    
    def __init__(self):
        super().__init__("market-hunter-v2", "猎场司")
        
    def analyze(self, md: Dict) -> AnalystReport:
        """执行全维度市场分析"""
        price = md.get("current_price", 0)
        df_h1 = md.get("df_h1")
        df_m15 = md.get("df_m15")
        
        score = 50  # 中性起点
        signals = {}
        reasons = []
        direction = SignalDirection.NONE
        confidence = 0.0
        
        # 1. 供需区分析
        zones = self._analyze_zones(df_h1, price)
        if zones:
            signals["supply_demand"] = zones
            score += zones.get("score", 0)
            if zones.get("direction") == "BUY":
                direction = SignalDirection.BUY
                reasons.append(f"供需区{zones.get('zone_type','')} @ ${zones.get('zone_price',0):.1f}")
            elif zones.get("direction") == "SELL":
                direction = SignalDirection.SELL
                reasons.append(f"供给区{zones.get('zone_type','')} @ ${zones.get('zone_price',0):.1f}")
        
        # 2. 技术指标综合
        tech = self._analyze_technicals(df_h1, price)
        if tech:
            signals["technicals"] = tech
            score += tech.get("score", 0)
            reasons.append(tech.get("reasoning", ""))
            if tech.get("direction") != "NONE":
                direction = tech["direction"]
        
        # 3. K线形态
        patterns = self._analyze_patterns(df_h1)
        if patterns:
            signals["patterns"] = patterns
            score += patterns.get("score", 0)
            if patterns.get("direction") != "NONE":
                reasons.append(patterns.get("reasoning", ""))
        
        # 4. 多时间框架汇合
        confluence = self._check_confluence(df_h1, df_m15, price)
        signals["confluence"] = confluence
        if confluence.get("confirmed", False):
            score += 10
            reasons.append(f"多TF汇合: {confluence.get('ratio', 0):.0%}")
        
        # 分数归一化 0-100
        score = max(0, min(100, score))
        confidence = abs(score - 50) / 50
        
        return AnalystReport(
            agent_id=self.agent_id,
            agent_name=self.name,
            score=score,
            direction=direction,
            confidence=confidence,
            reasoning=" | ".join(reasons),
            signals=signals,
        )

    def _analyze_zones(self, df, price):
        """供需区分析 (调用 SDP 引擎)"""
        from strategies.supply_demand import SupplyDemandSMC
        from config import DATA_CONFIG
        
        sd = SupplyDemandSMC(DATA_CONFIG)
        result = sd.generate_signal(df, price, "UNKNOWN")
        return {
            "direction": result["direction"],
            "score": result["score"],
            "zone_type": "DBR" if result.get("zones",{}).get("demand") else "RBD",
            "zone_price": result.get("entry", 0),
            "strength": result.get("score", 0),
        }

    def _analyze_technicals(self, df, price):
        """技术指标综合"""
        from strategies.technical import TechnicalStrategies
        ts = TechnicalStrategies()
        
        total_score = 0
        buy_votes = 0
        sell_votes = 0
        
        for name, func in [
            ("ema", ts.ema_trend), ("macd", ts.macd_signal),
            ("rsi", ts.rsi_signal), ("bb", ts.bollinger_signal),
        ]:
            try:
                sig = func(df, price) if name in ["ema", "rsi", "bb"] else func(df)
                if sig["direction"] == "BUY":
                    buy_votes += 1
                    total_score += sig["score"]
                elif sig["direction"] == "SELL":
                    sell_votes += 1
                    total_score -= sig["score"]
            except Exception:
                pass
        
        net = buy_votes - sell_votes
        direction = SignalDirection.BUY if net > 1 else (SignalDirection.SELL if net < -1 else SignalDirection.NONE)
        
        return {
            "direction": direction,
            "score": total_score * 5,
            "buy_votes": buy_votes,
            "sell_votes": sell_votes,
            "reasoning": f"技术指标: {buy_votes}多/{sell_votes}空",
        }

    def _analyze_patterns(self, df):
        """K线形态分析"""
        from strategies.technical import TechnicalStrategies
        ts = TechnicalStrategies()
        
        try:
            result = ts.candle_pattern(df)
            return {
                "direction": SignalDirection[result["direction"]] if result["direction"] != "NONE" else SignalDirection.NONE,
                "score": result["score"] * 5,
                "reasoning": result["reasoning"],
            }
        except Exception:
            return {"direction": SignalDirection.NONE, "score": 0, "reasoning": ""}

    def _check_confluence(self, df_h1, df_m15, price):
        """多时间框架汇合检查"""
        if df_h1 is None or df_m15 is None:
            return {"confirmed": False, "ratio": 0}
        
        from strategies.technical import TechnicalStrategies
        ts = TechnicalStrategies()
        
        h1_trend = ts.ema_trend(df_h1, price)
        m15_trend = ts.ema_trend(df_m15, price)
        
        confirmed = h1_trend["direction"] == m15_trend["direction"] and h1_trend["direction"] != "NONE"
        return {"confirmed": confirmed, "ratio": 1.0 if confirmed else 0.0}


class RiskAnalyst(BaseAnalyst):
    """算天机 v2 — 量化风控分析专家"""
    
    def __init__(self):
        super().__init__("quant-oracle-v2", "算天机")
        self.wins = 0
        self.losses = 0

    def analyze(self, md: Dict) -> AnalystReport:
        from risk.risk_manager import RiskManager
        rm = RiskManager()
        
        score = 50
        signals = {}
        reasons = []
        direction = SignalDirection.NONE

        # 1. Bayesian 胜率更新
        bayes = rm.update_bayesian(self.wins, self.losses)
        signals["bayesian"] = bayes
        reasons.append(f"Bayesian胜率: {bayes['conservative_winrate']:.0%}")
        
        # 2. Kelly 仓位计算
        avg_win = md.get("avg_win", 200)
        avg_loss = md.get("avg_loss", 100)
        kelly = rm.calc_kelly(bayes["conservative_winrate"], avg_win, avg_loss)
        signals["kelly"] = kelly
        
        # 3. 波动率评估
        atr = md.get("atr", 0)
        price = md.get("current_price", 0)
        if atr > 0 and price > 0:
            vol_ratio = atr / price * 100
            if vol_ratio > 2.0:
                score -= 20
                reasons.append(f"高波动率: {vol_ratio:.1f}%")
            elif vol_ratio < 0.3:
                score -= 10
                reasons.append(f"低波动率: {vol_ratio:.1f}%")
        
        # 4. 连续亏损检查
        consecutive_losses = md.get("consecutive_losses", 0)
        if consecutive_losses >= 3:
            score -= 25
            direction = SignalDirection.HOLD
            reasons.append(f"连亏{consecutive_losses}笔, 建议暂停")
        
        score = max(0, min(100, score))
        return AnalystReport(
            agent_id=self.agent_id,
            agent_name=self.name,
            score=score,
            direction=direction,
            confidence=abs(score - 50) / 50,
            reasoning=" | ".join(reasons),
            signals=signals,
        )


class MacroAnalyst(BaseAnalyst):
    """观局势 — 宏观 + 市场情绪分析"""
    
    def __init__(self):
        super().__init__("macro-observer-v2", "观局势")

    def analyze(self, md: Dict) -> AnalystReport:
        score = 50
        signals = {}
        reasons = []
        direction = SignalDirection.NONE
        
        # 1. 交易时段
        hour = md.get("current_hour", 12)
        if 8 <= hour <= 10:  # 伦敦开盘
            score += 10
            reasons.append("伦敦盘活跃期")
        elif 13 <= hour <= 15:  # 伦敦-NY重叠
            score += 15
            reasons.append("伦敦-NY重叠, 高波动期")
        elif 22 <= hour or hour <= 2:
            score -= 10
            reasons.append("非活跃时段")
        
        # 2. 季节性/日历
        date = md.get("current_date", datetime.now())
        if date.weekday() >= 5:
            score -= 10
            reasons.append("周末流动性低")
        
        # 3. 风险事件
        risk_events = md.get("risk_events", [])
        if "NFP" in str(risk_events):
            score -= 20
            reasons.append("非农数据前, 谨慎")
            direction = SignalDirection.HOLD
        
        score = max(0, min(100, score))
        return AnalystReport(
            agent_id=self.agent_id,
            agent_name=self.name,
            score=score,
            direction=direction,
            confidence=abs(score - 50) / 50,
            reasoning=" | ".join(reasons),
            signals=signals,
        )


# ═══════════════════════════════════════════
# 3. Level 2: 策略室 (Sector Room)
# ═══════════════════════════════════════════

class StrategyRoom:
    """
    策略室 — 整合Level 1所有分析师报告
    对标: 论文中的行业智能体
    
    负责:
      1. 收集4位分析师报告
      2. 按历史可靠性加权
      3. 行业标准化评分
      4. 输出综合投资论点
    """
    
    def __init__(self):
        self.analysts: Dict[str, BaseAnalyst] = {}
        
    def register_analyst(self, analyst: BaseAnalyst):
        self.analysts[analyst.agent_id] = analyst
    
    def synthesize(self, reports: List[AnalystReport], regime: MarketRegime) -> AnalystReport:
        """
        综合所有分析师报告, 生成统一评分
        加权规则:
          - 基础权重: 分析师历史可靠性
          - 市场状态调节: 不同regime下权重不同
          - 共识增强: 多位分析师一致时加分
        """
        if not reports:
            return AnalystReport("strategy-room", "策略室", 50, SignalDirection.NONE, 0, "无报告", {})
        
        total_weight = 0
        weighted_score = 0
        directions = []
        confidences = []
        all_reasons = []
        all_signals = {}
        
        # Regime 权重调节
        regime_weights = {
            MarketRegime.STRONG_TREND: {
                "market-hunter-v2": 1.3,  # 趋势中技术分析更重要
                "quant-oracle-v2": 0.8,
                "macro-observer-v2": 0.9,
            },
            MarketRegime.HIGH_VOLATILITY: {
                "market-hunter-v2": 0.7,
                "quant-oracle-v2": 1.5,  # 高波动中风控最重要
                "macro-observer-v2": 1.2,
            },
            MarketRegime.RANGING: {
                "market-hunter-v2": 1.0,
                "quant-oracle-v2": 1.0,
                "macro-observer-v2": 1.0,
            },
            MarketRegime.WEAK_TREND: {
                "market-hunter-v2": 1.1,
                "quant-oracle-v2": 0.9,
                "macro-observer-v2": 1.0,
            },
        }
        
        regime_w = regime_weights.get(regime, regime_weights[MarketRegime.RANGING])
        
        for report in reports:
            reliability = self.analysts.get(report.agent_id, BaseAnalyst(report.agent_id, "")).performance["reliability"]
            regime_adjust = regime_w.get(report.agent_id, 1.0)
            weight = reliability * regime_adjust
            
            weighted_score += report.score * weight
            total_weight += weight
            directions.append(report.direction)
            confidences.append(report.confidence)
            all_reasons.append(f"[{report.agent_name}] {report.reasoning}")
            all_signals[report.agent_id] = report.signals
        
        # 最终评分
        final_score = weighted_score / total_weight if total_weight > 0 else 50
        
        # 方向: 取大多数
        buy_count = directions.count(SignalDirection.BUY)
        sell_count = directions.count(SignalDirection.SELL)
        hold_count = directions.count(SignalDirection.HOLD)
        
        if buy_count > sell_count and buy_count > hold_count:
            final_direction = SignalDirection.BUY
        elif sell_count > buy_count and sell_count > hold_count:
            final_direction = SignalDirection.SELL
        else:
            final_direction = SignalDirection.NONE
        
        # 置信度: 方向一致程度
        max_count = max(buy_count, sell_count, hold_count)
        confidence = max_count / len(directions) if directions else 0
        
        return AnalystReport(
            agent_id="strategy-room",
            agent_name="策略室",
            score=round(final_score, 1),
            direction=final_direction,
            confidence=confidence,
            reasoning="\n".join(all_reasons),
            signals=all_signals,
        )


# ═══════════════════════════════════════════
# 4. Level 3: 决策官 (Portfolio Manager)
# ═══════════════════════════════════════════

class PortfolioManager:
    """
    决策官 — 最终决策者
    对标: 论文中的PM智能体 + 自进化DRL引擎
    
    负责:
      1. 接收策略室报告 + 宏观分析
      2. DRL自进化引擎: PPO/A2C/DDPG 滚动选择
      3. 12层风控门禁
      4. 最终下单决策
    """
    
    def __init__(self, engine_mode="DEMO"):
        self.mode = engine_mode
        self.regime = MarketRegime.RANGING
        self.drl_agents = {}  # PPO, A2C, DDPG
        self.active_agent = None  # 当前选中的最佳DRL代理
        self.rolling_window = 90  # 3个月滚动窗口
        self.validation_window = 90  # 3个月验证窗口
        
        # 历史决策记录 (用于DRL训练)
        self.decision_history: List[TradeDecision] = []
        
        # 风险状态
        self.consecutive_losses = 0
        self.peak_balance = 10000
        self.current_balance = 10000
        self.wins = 0
        self.losses = 0
        
    def decide(self, strategy_report: AnalystReport, 
               macro_report: Optional[AnalystReport],
               market_data: Dict) -> TradeDecision:
        """
        做出最终交易决策
        
        流程:
          1. 综合策略室 + 宏观报告
          2. 运行DRL自进化引擎 (P+1步选择)
          3. 计算Kelly仓位
          4. 12层风控检查
          5. 输出TradeDecision
        """
        from risk.risk_manager import RiskManager
        self.rm = RiskManager()
        
        price = market_data.get("current_price", 0)
        balance = market_data.get("balance", 10000)
        
        # 1. 综合评分
        final_score = strategy_report.score
        if macro_report:
            final_score = final_score * 0.7 + macro_report.score * 0.3
        
        direction = strategy_report.direction
        
        # 2. DRL自进化引擎 (自动选择最佳策略)
        drl_signal = self._run_drl_engine(market_data)
        if drl_signal:
            # DRL信号与分析师信号融合
            if drl_signal["direction"] == direction.value:
                final_score += 10  # 一致加分
            else:
                final_score -= 15  # 分歧减分
        
        # 3. 计算入场/止损/止盈
        atr = market_data.get("atr", 1.0)
        if direction == SignalDirection.BUY:
            entry = price
            sl = price - atr * 1.5
            tp = price + atr * 3.0
        elif direction == SignalDirection.SELL:
            entry = price
            sl = price + atr * 1.5
            tp = price - atr * 3.0
        else:
            entry = sl = tp = 0
        
        # 4. Kelly仓位
        bayes = self.rm.update_bayesian(self.wins, self.losses)
        kelly_pct = self.rm.calc_kelly(
            bayes["conservative_winrate"],
            abs(tp - entry) if tp > entry else 100,
            abs(entry - sl) if entry > sl else 100,
        )
        
        # 5. 风控检查
        context = {
            "balance": balance,
            "equity": balance,
            "atr": atr,
            "current_price": price,
            "spread": market_data.get("spread", 10),
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "direction": direction.value if direction != SignalDirection.NONE else "NONE",
            "current_hour": market_data.get("current_hour", 12),
        }
        
        risk_check = self.rm.check_all(context)
        
        # 6. 最终决定
        should_trade = (
            direction != SignalDirection.NONE
            and direction != SignalDirection.HOLD
            and final_score > 60  # 评分 > 60 才交易
            and risk_check["all_pass"]
        )
        
        if not should_trade:
            direction = SignalDirection.NONE
        
        return TradeDecision(
            direction=direction,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            volume=0.01 if should_trade else 0,
            confidence=strategy_report.confidence,
            vote_score=final_score,
            regime=self.regime,
            kelly_fraction=kelly_pct,
            risk_checks=risk_check["checks"],
            analyst_scores={
                "strategy_room": strategy_report.score,
                "macro": macro_report.score if macro_report else 50,
            },
            reasoning=strategy_report.reasoning,
        )
    
    def _run_drl_engine(self, market_data: Dict) -> Optional[Dict]:
        """
        DRL自进化引擎核心
        
        实现:
          1. 3个DRL代理 (PPO/A2C/DDPG)
          2. 滚动训练窗口 (3个月)
          3. 滚动验证窗口 (3个月) 
          4. 选择夏普比率最高的代理
          5. 在线学习: 每次交易后更新
        """
        # 这里在实际部署时会调用外部DRL模型
        # 当前返回启发式信号作为占位
        
        if not self.decision_history:
            return None
        
        # 基于各分析师历史表现加权
        # 在完整版中会使用sklearn或PyTorch训练
        if self.regime == MarketRegime.STRONG_TREND:
            return {"direction": SignalDirection.BUY, "confidence": 0.7}
        elif self.regime == MarketRegime.HIGH_VOLATILITY:
            return {"direction": SignalDirection.HOLD, "confidence": 0.6}
        
        return None
    
    def update_training(self, decision: TradeDecision, actual_result: float):
        """
        在线学习更新
        
        actual_result: 交易实际盈亏 (正=盈利, 负=亏损)
        """
        self.decision_history.append(decision)
        
        if actual_result > 0:
            self.wins += 1
            self.consecutive_losses = 0
        else:
            self.losses += 1
            self.consecutive_losses += 1
        
        # 更新分析师可靠性
        for agent_id, score in decision.analyst_scores.items():
            # 简化版: score > 60 且盈利 = 正确
            was_correct = (score > 60 and actual_result > 0) or (score < 40 and actual_result < 0)
            # 这里应该更新对应分析师的performance
        
        print(f"[DRL] 学习更新: 结果=${actual_result:.2f} | 胜率={self.wins}/{self.wins+self.losses}")


# ═══════════════════════════════════════════
# 5. 编排器 (主引擎 v2)
# ═══════════════════════════════════════════

class GoldstrategyEngineV2:
    """
    金策宗师团 v2 主引擎
    
    SOP工作流:
      Phase 1: Level 1 分析师并行分析
      Phase 2: 策略室整合 + 宏观分析
      Phase 3: DRL自进化引擎运行
      Phase 4: 决策官最终决策
      Phase 5: 执行/风控/学习
    """
    
    def __init__(self, mode="DEMO"):
        self.mode = mode
        
        # Level 1: 分析师
        self.analysts = {
            "market-hunter-v2": MarketAnalyst(),
            "quant-oracle-v2": RiskAnalyst(),
            "macro-observer-v2": MacroAnalyst(),
        }
        
        # Level 2: 策略室
        self.strategy_room = StrategyRoom()
        for aid, analyst in self.analysts.items():
            self.strategy_room.register_analyst(analyst)
        
        # Level 3: 决策官
        self.pm = PortfolioManager(mode)
        
        # DRL引擎状态
        self.drl_ready = False
        self.last_regime_switch = datetime.now()
        
    def run_analysis_cycle(self, market_data: Dict) -> TradeDecision:
        """
        运行一个完整的分析周期
        
        Args:
            market_data: 包含所有市场数据的字典
        
        Returns:
            TradeDecision: 最终交易决策
        """
        print("\n" + "="*60)
        print("  金策宗师团 v2.0 — 分析周期开始")
        print("="*60)
        
        # Phase 1: Level 1 分析
        print("\n▶ Phase 1: 分析师团队")
        reports = []
        for aid, analyst in self.analysts.items():
            try:
                report = analyst.analyze(market_data)
                reports.append(report)
                print(f"  [{analyst.name:12s}] 评分={report.score:.0f} | 方向={report.direction.value:4s} | 置信={report.confidence:.0%}")
            except Exception as e:
                print(f"  [{analyst.name:12s}] 分析失败: {e}")
        
        # Phase 2: 策略室
        print("\n▶ Phase 2: 策略室整合")
        regime = MarketRegime(market_data.get("regime", "RANGING"))
        strategy_report = self.strategy_room.synthesize(reports, regime)
        print(f"  [策略室] 综合评分={strategy_report.score:.0f} | 方向={strategy_report.direction.value}")
        
        # 宏观分析
        macro_report = None
        if "macro-observer-v2" in self.analysts:
            macro_report = self.analysts["macro-observer-v2"].analyze(market_data)
            print(f"  [观局势] 宏观评分={macro_report.score:.0f}")
        
        # Phase 3: DRL引擎 (简版)
        print("\n▶ Phase 3: DRL自进化引擎")
        drl_signal = self.pm._run_drl_engine(market_data)
        if drl_signal:
            print(f"  [DRL] 信号={drl_signal['direction'].value}")
        else:
            print(f"  [DRL] 训练数据不足, 使用分析师信号")
        
        # Phase 4: 最终决策
        print("\n▶ Phase 4: 决策官裁决")
        decision = self.pm.decide(strategy_report, macro_report, market_data)
        print(f"  [决策] {decision.direction.value} | 评分={decision.vote_score:.0f}")
        print(f"  入场=${decision.entry_price:.1f} SL=${decision.stop_loss:.1f} TP=${decision.take_profit:.1f}")
        print(f"  Kelly={decision.kelly_fraction:.2%} | 置信={decision.confidence:.0%}")
        
        # Phase 5: 风控结果
        failed_checks = [k for k, v in decision.risk_checks.items() if not v]
        if failed_checks:
            print(f"  ⚠️ 风控拦截: {', '.join(failed_checks)}")
        
        print(f"\n{'='*60}")
        return decision
    
    def record_trade_result(self, decision: TradeDecision, profit: float):
        """记录交易结果并触发在线学习"""
        self.pm.update_training(decision, profit)
        
        # 更新分析师表现
        for aid, analyst in self.analysts.items():
            score = decision.analyst_scores.get(aid, 50)
            was_correct = (score > 60 and profit > 0) or (score < 40 and profit < 0)
            analyst.update_performance(was_correct)


# ═══════════════════════════════════════════
# 6. 自进化DRL训练器 (待实现)
# ═══════════════════════════════════════════

class DRLTrainer:
    """
    深度强化学习训练器
    
    待实现组件:
      1. PPO代理 — 稳定策略梯度
      2. A2C代理 — 风险规避
      3. DDPG代理 — 连续动作优化
    
    训练流程:
      1. 每季度滚动窗口
      2. 3个月训练 + 3个月验证
      3. 按夏普比率选最佳代理
      4. 在线持续更新
    
    状态空间: 181维 (价格+指标+持仓+余额)
    动作空间: [-1, 1] 连续 (卖出→持有→买入)
    奖励函数: 组合价值变化 - 交易成本
    """
    
    def __init__(self):
        self.agents = {}  # PPO, A2C, DDPG
        self.active_agent = None
        self.replay_buffer = []
        
    def train(self, historical_data: np.ndarray, labels: np.ndarray):
        """训练DRL代理"""
        pass
    
    def predict(self, state: np.ndarray) -> Tuple[float, float]:
        """预测动作和置信度"""
        return (0.0, 0.5)  # (action, confidence)
    
    def select_best_agent(self, validation_results: Dict) -> str:
        """按夏普比率选最佳代理"""
        best = max(validation_results, key=lambda k: validation_results[k]["sharpe"])
        return best


# ═══════════════════════════════════════════
# 7. 启动脚本
# ═══════════════════════════════════════════

def main():
    """演示: 单次分析周期"""
    import time
    
    engine = GoldstrategyEngineV2(mode="DEMO")
    
    # 模拟市场数据
    mock_data = {
        "current_price": 2335.50,
        "current_hour": datetime.now().hour,
        "current_date": datetime.now(),
        "balance": 10000.0,
        "equity": 10050.0,
        "atr": 12.5,
        "spread": 15,
        "regime": "WEAK_TREND",
        "avg_win": 180,
        "avg_loss": 85,
        "consecutive_losses": 0,
        "risk_events": [],
        "df_h1": None,  # 实际运行时需要填充
        "df_m15": None,
    }
    
    decision = engine.run_analysis_cycle(mock_data)
    
    if decision.direction != SignalDirection.NONE:
        print(f"\n✅ 建议执行: {decision.direction.value} ${decision.entry_price:.1f}")
    else:
        print(f"\n⏸️  当前无合适交易机会")
    
    return engine


if __name__ == "__main__":
    engine = main()
