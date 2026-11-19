"""
金策宗师团 v3.0 — 人工操盘手模拟系统
Goldstrategy Guild v3.0 — Human Trader Simulator

核心设计: 不是机械的指标触发器, 而是一个"有灵魂的操盘手"
像一个真实的人坐在电脑前:
  - 盘前做功课 (扫描市场/经济日历/关键位置)
  - 盘中有纪律 (检查清单/情绪管理/止损纪律)
  - 盘后写日志 (复盘/归因/改进)
  - 连亏停手 / 达目标收工 / 不追涨杀跌

核心区别:
  v1.0: 策略投票机器 (无状态, 每次独立判断)
  v2.0: 多智能体架构 (角色分工, 层级决策)
  v3.0: 人工操盘手 (有意识/有纪律/有反思/有成长)
"""

import numpy as np
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import json
import os
import csv


# ═══════════════════════════════════════════
# 1. 操盘手核心意识层
# ═══════════════════════════════════════════

class TraderMood(Enum):
    """操盘手情绪状态 — 像真的人一样有状态"""
    CALM = "平静"           # 最佳状态
    FOCUSED = "专注"        # 良好
    CAUTIOUS = "谨慎"       # 市场不确定
    FATIGUED = "疲劳"       # 连续盯盘后
    FRUSTRATED = "沮丧"     # 连续亏损后
    OVERCONFIDENT = "自负"  # 连续盈利后

class MarketSession(Enum):
    ASIA = "亚洲盘"
    LONDON_OPEN = "伦敦开盘"
    LONDON_NY_OVERLAP = "伦敦-NY重叠"
    NY_OPEN = "纽约开盘"
    NY_CLOSE = "纽约收盘"
    OFF_HOURS = "非活跃时段"


@dataclass
class TradeJournalEntry:
    """交易日志 — 跟真实交易员的日志一模一样"""
    # 基本信息
    date: date
    time: str
    pair: str = "XAUUSD"
    direction: str = ""      # BUY / SELL
    entry_price: float = 0.0
    exit_price: float = 0.0
    volume: float = 0.0
    profit: float = 0.0      # 实际盈亏
    pips: float = 0.0
    
    # 入场依据 (交易员写的分析)
    entry_reason: str = ""
    setup_type: str = ""      # 供需区 / 订单块 / 趋势回踩 / 突破
    
    # 风险管理
    stop_loss: float = 0.0
    take_profit: float = 0.0
    risk_pct: float = 0.0     # 本笔风险 %
    rr_ratio: float = 0.0
    
    # 心理状态 (跟文章里的交易日志一样)
    pre_trade_mood: str = ""  # 入场前情绪
    post_trade_mood: str = "" # 出场后情绪
    
    # 纪律检查
    followed_plan: bool = True
    rule_violation: str = ""
    
    # 归因分析
    win_reason: str = ""      # 如果赢, 为什么
    loss_reason: str = ""     # 如果亏, 为什么
    lesson: str = ""          # 经验教训
    
    # 市场环境
    market_regime: str = ""
    session: str = ""
    news_impact: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "date": str(self.date), "time": self.time,
            "direction": self.direction, "entry": self.entry_price,
            "exit": self.exit_price, "volume": self.volume,
            "profit": self.profit, "pips": self.pips,
            "setup": self.setup_type, "risk%": self.risk_pct,
            "rr": self.rr_ratio, "pre_mood": self.pre_trade_mood,
            "post_mood": self.post_trade_mood,
            "plan_followed": self.followed_plan,
            "violation": self.rule_violation,
            "lesson": self.lesson, "regime": self.market_regime,
            "session": self.session,
        }


@dataclass
class DailyPlan:
    """盘前计划 — 交易员每天开盘前写的作战计划"""
    date: date
    bias: str = ""               # 日线偏向: 多/空/观望
    key_levels: Dict = field(default_factory=lambda: {
        "support": [], "resistance": [],
        "demand_zones": [], "supply_zones": [],
    })
    trade_setups: List[str] = field(default_factory=list)
    risk_today: float = 0.0      # 今天想冒多少风险
    news_events: List[str] = field(default_factory=list)
    notes: str = ""


# ═══════════════════════════════════════════
# 2. 操盘手日志系统 (跟真实交易员一模一样)
# ═══════════════════════════════════════════

class TraderJournal:
    """交易员日志 — 最强的心理改善工具"""
    
    def __init__(self, log_dir: str = "E:/GoldstrategyEngine/logs"):
        self.log_dir = log_dir
        self.journal: List[TradeJournalEntry] = []
        self.daily_plans: Dict[str, DailyPlan] = {}
        self._load_journal()
    
    def _load_journal(self):
        """加载历史日志"""
        path = os.path.join(self.log_dir, "trader_journal.csv")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        entry = TradeJournalEntry(
                            date=date.fromisoformat(row["date"]),
                            time=row["time"],
                            direction=row["direction"],
                            entry_price=float(row.get("entry", 0)),
                            exit_price=float(row.get("exit", 0)),
                            volume=float(row.get("volume", 0)),
                            profit=float(row.get("profit", 0)),
                            pips=float(row.get("pips", 0)),
                            entry_reason=row.get("setup", ""),
                            setup_type=row.get("setup", ""),
                            stop_loss=float(row.get("sl", 0)),
                            take_profit=float(row.get("tp", 0)),
                            risk_pct=float(row.get("risk%", 0)),
                            pre_trade_mood=row.get("pre_mood", ""),
                            followed_plan=row.get("plan_followed", "True") == "True",
                            rule_violation=row.get("violation", ""),
                            lesson=row.get("lesson", ""),
                            market_regime=row.get("regime", ""),
                            session=row.get("session", ""),
                        )
                        self.journal.append(entry)
                print(f"[日志] 加载 {len(self.journal)} 条历史记录")
            except Exception as e:
                print(f"[日志] 加载失败: {e}")
    
    def save_journal(self):
        """保存日志到CSV"""
        os.makedirs(self.log_dir, exist_ok=True)
        path = os.path.join(self.log_dir, "trader_journal.csv")
        
        if not self.journal:
            return
        
        fieldnames = list(TradeJournalEntry().__dict__.keys())
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for entry in self.journal:
                writer.writerow(entry.to_dict())
    
    def add_entry(self, entry: TradeJournalEntry):
        """添加一条日志"""
        self.journal.append(entry)
        self.save_journal()
        print(f"\n📝 日志已记录: {entry.direction} ${entry.entry_price:.1f} → ${entry.exit_price:.1f} (${entry.profit:+.2f})")
    
    def set_daily_plan(self, plan: DailyPlan):
        """写入盘前计划"""
        key = str(plan.date)
        self.daily_plans[key] = plan
        
        path = os.path.join(self.log_dir, f"daily_plan_{key}.txt")
        lines = [
            f"=== 盘前计划 {key} ===",
            f"偏向: {plan.bias}",
            f"关键支撑: {plan.key_levels.get('support', [])}",
            f"关键阻力: {plan.key_levels.get('resistance', [])}",
            f"供需区: {plan.key_levels.get('demand_zones', [])}",
            f"今日风险: {plan.risk_today}%",
            f"新闻: {', '.join(plan.news_events)}",
            f"备注: {plan.notes}",
        ]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    
    def get_statistics(self) -> Dict:
        """生成交易员绩效统计"""
        if not self.journal:
            return {"total_trades": 0}
        
        wins = [e for e in self.journal if e.profit > 0]
        losses = [e for e in self.journal if e.profit <= 0]
        
        total = len(self.journal)
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = win_count / total if total > 0 else 0
        
        total_profit = sum(e.profit for e in wins)
        total_loss = sum(abs(e.profit) for e in losses)
        
        avg_win = total_profit / win_count if win_count > 0 else 0
        avg_loss = total_loss / loss_count if loss_count > 0 else 0
        profit_factor = total_profit / total_loss if total_loss > 0 else 0
        
        # 最大回撤 (简化)
        balance = 10000
        peak = 10000
        max_dd = 0
        for e in self.journal:
            balance += e.profit
            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak
            max_dd = max(max_dd, dd)
        
        return {
            "total_trades": total,
            "wins": win_count,
            "losses": loss_count,
            "win_rate": round(win_rate, 3),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "total_profit": round(total_profit - total_loss, 2),
            "max_drawdown": round(max_dd * 100, 1),
        }


# ═══════════════════════════════════════════
# 3. 操盘手核心 — 有意识的交易者
# ═══════════════════════════════════════════

class HumanTrader:
    """
    人工操盘手核心
    
    像一个真实的人:
      1. 有状态 (情绪/疲劳/自信程度)
      2. 有纪律 (检查清单/硬规则)
      3. 有记忆 (历史教训/胜率统计)
      4. 有反思 (盘后复盘/改进)
      5. 有常识 (知道什么时候不该交易)
    """
    
    def __init__(self, name: str = "策金尊", starting_balance: float = 10000):
        self.name = name
        self.balance = starting_balance
        self.peak_balance = starting_balance
        self.mood = TraderMood.CALM
        self.session = MarketSession.OFF_HOURS
        
        # 交易统计 (用于自我认知)
        self.daily_trades = 0
        self.daily_profit = 0.0
        self.consecutive_wins = 0
        self.consecutive_losses = 0
        self.total_trades = 0
        self.monthly_trades = 0
        
        # 硬规则参数 (来自职业交易员研究)
        self.max_daily_trades = 5
        self.max_daily_risk_pct = 3.0
        self.max_consecutive_losses = 3
        self.max_daily_loss_pct = 5.0
        self.daily_profit_target_pct = 3.0
        self.min_cooloff_minutes = 30
        
        # 检查清单
        self.checklist = PreTradeChecklist()
        
        # 日志
        self.journal = TraderJournal()
        
        # 当前持仓
        self.has_position = False
        self.current_position = None
        
        print(f"\n👤 操盘手 {self.name} 就位 | 初始资金 ${self.balance:.0f}")

    # ─── 盘前流程 ─────────────────────────

    def pre_market_routine(self, market_data: Dict) -> DailyPlan:
        """
        盘前仪式 — 每天开盘前必须做的事
        
        真实交易员流程:
          1. 看经济日历
          2. 看日线图定偏向
          3. 标关键水平
          4. 读一遍交易计划
          5. 心理自检
        """
        today = date.today()
        print(f"\n{'='*50}")
        print(f"  📋 盘前准备 — {today}")
        print(f"{'='*50}")
        
        # 1. 经济日历
        news = self._check_economic_calendar(market_data)
        if any("NFP" in n or "FOMC" in n or "CPI" in n for n in news):
            print(f"  ⚠️ 重大数据: {', '.join(news[:3])}")
            print(f"  今日操作: 数据前30分钟不开新仓, 等数据消化")
        
        # 2. 日线偏向 + 关键水平
        bias, levels = self._determine_daily_bias(market_data)
        print(f"  日线偏向: {bias}")
        print(f"  关键支撑: {levels.get('support', [])}")
        print(f"  关键阻力: {levels.get('resistance', [])}")
        
        # 3. 今日风险预算
        risk_budget = self._calc_daily_risk_budget()
        print(f"  今日风险预算: {risk_budget:.1f}%")
        
        # 4. 自检
        self._check_mental_state()
        
        plan = DailyPlan(
            date=today,
            bias=bias,
            key_levels=levels,
            risk_today=risk_budget,
            news_events=news,
            notes=f"情绪状态: {self.mood.value}",
        )
        
        self.journal.set_daily_plan(plan)
        return plan

    def _check_economic_calendar(self, md: Dict) -> List[str]:
        """检查经济日历 — 模拟交易员看新闻"""
        events = md.get("risk_events", [])
        today_str = str(date.today())
        
        # 在真实环境中会从API获取
        # 这里做启发式检测
        weekday = date.today().weekday()
        
        # 周五 → 可能非农
        if weekday == 4:
            events.append("POTENTIAL_NFP_FRIDAY")
        
        return events

    def _determine_daily_bias(self, md: Dict) -> Tuple[str, Dict]:
        """定日线偏向 — 交易员看日图定方向"""
        from strategies.technical import TechnicalStrategies
        ts = TechnicalStrategies()
        
        df_h1 = md.get("df_h1")
        price = md.get("current_price", 0)
        
        bias = "观望"
        levels = {"support": [], "resistance": [], "demand_zones": [], "supply_zones": []}
        
        if df_h1 is not None:
            ema = ts.ema_trend(df_h1, price)
            rsi_data = ts.rsi_signal(df_h1, price)
            
            if ema["direction"] == "BUY":
                bias = "偏多 — 回调做多为主"
            elif ema["direction"] == "SELL":
                bias = "偏空 — 反弹做空为主"
            
            # 找关键水平
            from strategies.technical import SupportResistance
            sr = SupportResistance()
            sr_levels = sr.detect_levels(df_h1, lookback=100)
            levels["support"] = sr_levels.get("support", [])[-3:]
            levels["resistance"] = sr_levels.get("resistance", [])[-3:]
        
        return bias, levels

    def _calc_daily_risk_budget(self) -> float:
        """计算今日风险预算 — 交易员的资金管理"""
        base_risk = self.max_daily_risk_pct
        
        # 连亏后减少风险
        if self.consecutive_losses >= 2:
            base_risk *= 0.5
            print(f"  ⚠️ 连亏{self.consecutive_losses}笔, 今日风险减半")
        
        # 连盈后也不增加风险 (防止自负)
        # (跟业余交易员相反)
        
        return base_risk

    def _check_mental_state(self):
        """心理状态自检"""
        print(f"  当前状态: {self.mood.value}")
        
        if self.mood == TraderMood.FRUSTRATED:
            print(f"  ⛔ 检测到沮丧情绪, 建议休息30分钟再交易")
        elif self.mood == TraderMood.OVERCONFIDENT:
            print(f"  ⚠️ 检测到自负情绪, 提醒自己每笔交易独立")
        elif self.mood == TraderMood.FATIGUED:
            print(f"  ⚠️ 疲劳状态, 考虑减少交易量")

    # ─── 盘中决策流程 ─────────────────────

    def should_trade(self, signal: Dict, market_data: Dict) -> Tuple[bool, str]:
        """
        交易员的核心判断: "这单做不做?"
        
        不是无条件执行信号, 而是像一个真人一样:
          1. 先过心理检查清单
          2. 看今天状态对不对
          3. 看有没有违反硬规则
          4. 问自己"这个位置真的好吗?"
        """
        # 1. 有持仓就不开新仓 (单品种单子)
        if self.has_position:
            return False, "已有持仓, 不开新仓"
        
        # 2. 硬规则检查
        hard_rules_pass, hard_rule_msg = self._check_hard_rules()
        if not hard_rules_pass:
            return False, hard_rule_msg
        
        # 3. 交易前检查清单 (心理层面)
        checklist_pass, checklist_msg = self.checklist.evaluate(signal, market_data)
        if not checklist_pass:
            return False, f"检查清单未通过: {checklist_msg}"
        
        # 4. 交易员经验判断 (编码经验法则)
        exp_pass, exp_msg = self._trader_experience_check(signal, market_data)
        if not exp_pass:
            return False, exp_msg
        
        return True, "全部通过, 可以执行"

    def _check_hard_rules(self) -> Tuple[bool, str]:
        """
        硬规则 — 职业交易员的底线, 任何情况不能违反
        这些就是交易员说的"铁纪律"
        """
        # L1: 日交易次数限制
        if self.daily_trades >= self.max_daily_trades:
            return False, f"达日最大交易次数 ({self.max_daily_trades})"
        
        # L2: 日最大亏损限制
        loss_pct = abs(self.daily_profit) / self.balance * 100
        if self.daily_profit < 0 and loss_pct >= self.max_daily_loss_pct:
            return False, f"达日最大亏损 ({loss_pct:.1f}%), 当日停止交易"
        
        # L3: 日盈利目标达成
        gain_pct = self.daily_profit / self.balance * 100
        if gain_pct >= self.daily_profit_target_pct:
            return False, f"达日盈利目标 ({gain_pct:.1f}%), 收工"
        
        # L4: 连亏停手 (最关键的纪律)
        if self.consecutive_losses >= self.max_consecutive_losses:
            # 检查冷却时间
            if hasattr(self, 'last_trade_time'):
                elapsed = (datetime.now() - self.last_trade_time).total_seconds() / 60
                if elapsed < self.min_cooloff_minutes:
                    return False, f"连亏{self.consecutive_losses}笔, 冷却中 ({elapsed:.0f}/{self.min_cooloff_minutes}分钟)"
                else:
                    # 冷却结束, 重置连亏计数 — 但风险减半
                    self.consecutive_losses = 0
                    print(f"  ✅ 冷却结束, 恢复交易 (风险减半)")
        
        return True, "硬规则通过"

    def _trader_experience_check(self, signal: Dict, md: Dict) -> Tuple[bool, str]:
        """
        交易员经验判断 — 写不进规则但老交易员都知道的东西
        
        这些是我们在网上学习到的职业交易员的隐性知识:
          - "突破后等回踩, 不追"
          - "数据前不进场"
          - "伦敦开盘第一个小时最乱, 等稳定"
          - "不要接飞刀"
          - "强趋势中不逆势"
        """
        price = md.get("current_price", 0)
        direction = signal.get("direction", "NONE")
        vote_score = signal.get("vote_score", 0)
        confidence = signal.get("confidence", 0)
        
        hour = datetime.now().hour
        
        # 经验1: 伦敦开盘第一小时不冲动
        if hour == 8:
            return False, "经验: 伦敦开盘第一小时流动性不稳定, 等09:00后再判断"
        
        # 经验2: 数据前30分钟不进场
        if self._is_near_news_event(md):
            return False, "经验: 数据前30分钟不进场, 等数据消化"
        
        # 经验3: 信号得分不够高时不做
        if direction in ["BUY", "SELL"] and vote_score < 65:
            return False, f"经验: 信号得分{vote_score:.0f}偏低, 等更高确认度"
        
        # 经验4: 不要追涨杀跌 (价格远离均线)
        df_h1 = md.get("df_h1")
        if df_h1 is not None and len(df_h1) > 50:
            ema50 = df_h1["close"].rolling(50).mean().iloc[-1]
            dist_pct = abs(price - ema50) / ema50 * 100
            if dist_pct > 3.0:
                return False, f"经验: 价格远离均线{dist_pct:.1f}%, 等回调再入场"
        
        return True, "经验判断通过"

    def _is_near_news_event(self, md: Dict) -> bool:
        """检查是否临近重大数据"""
        events = md.get("risk_events", [])
        if not events:
            return False
        
        # 简化版: 有风险事件就谨慎
        for e in events:
            if any(kw in e.upper() for kw in ["NFP", "FOMC", "CPI", "FED", "NONFARM", "INTEREST"]):
                return True
        return False

    # ─── 交易执行 ─────────────────────────

    def execute_trade(self, decision: Dict, market_data: Dict) -> Dict:
        """
        执行交易 — 交易员亲自下单
        
        不像EA那样冷冰冰, 交易员会:
          1. 记录入场时的心理状态
          2. 知道自己为什么做这单
          3. 设好止损就不改了
        """
        direction = decision.get("direction", "NONE")
        entry = decision.get("entry_price", 0)
        sl = decision.get("stop_loss", 0)
        tp = decision.get("take_profit", 0)
        volume = decision.get("volume", 0.01)
        
        pre_mood = self.mood.value
        
        print(f"\n📈 {self.name} 执行交易:")
        print(f"  方向: {direction} | 手数: {volume:.2f}")
        print(f"  入场: ${entry:.1f} | SL: ${sl:.1f} | TP: ${tp:.1f}")
        print(f"  情绪: {pre_mood}")
        
        # 记录入场
        self.has_position = True
        self.current_position = {
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "volume": volume,
            "open_time": datetime.now(),
            "entry_reason": decision.get("reasoning", ""),
            "pre_mood": pre_mood,
            "setup_type": decision.get("setup_type", ""),
            "risk_pct": decision.get("risk_pct", 0),
            "rr": decision.get("rr", 0),
            "regime": decision.get("regime", ""),
            "session": self.session.value,
        }
        
        self.daily_trades += 1
        self.total_trades += 1
        
        return self.current_position

    def close_trade(self, exit_price: float, reason: str = "止盈/止损"):
        """
        平仓 — 交易员记录得失
        
        交易员每次平仓都会:
          1. 记录盈亏
          2. 写日志
          3. 归因分析
          4. 更新心态
        """
        if not self.has_position or not self.current_position:
            return None
        
        pos = self.current_position
        direction = pos["direction"]
        entry = pos["entry"]
        volume = pos["volume"]
        
        if direction == "BUY":
            profit = (exit_price - entry) * volume * 100  # 黄金估算
        else:
            profit = (entry - exit_price) * volume * 100
        
        pips = (exit_price - entry) * 10 if direction == "BUY" else (entry - exit_price) * 10
        
        # 更新账户
        self.balance += profit
        if self.balance > self.peak_balance:
            self.peak_balance = self.balance
        
        self.daily_profit += profit
        self.has_position = False
        
        # 更新连胜/连亏
        if profit > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
            self.mood = self._update_mood_after_win()
        else:
            self.consecutive_wins = 0
            self.consecutive_losses += 1
            self.mood = self._update_mood_after_loss()
        
        # 写日志 (交易员最重要的习惯)
        entry_data = TradeJournalEntry(
            date=date.today(),
            time=datetime.now().strftime("%H:%M"),
            direction=direction,
            entry_price=entry,
            exit_price=exit_price,
            volume=volume,
            profit=round(profit, 2),
            pips=round(pips, 1),
            entry_reason=pos.get("entry_reason", ""),
            setup_type=pos.get("setup_type", ""),
            stop_loss=pos.get("sl", 0),
            take_profit=pos.get("tp", 0),
            risk_pct=pos.get("risk_pct", 0),
            rr_ratio=pos.get("rr", 0),
            pre_trade_mood=pos.get("pre_mood", ""),
            post_trade_mood=self.mood.value,
            followed_plan=True,
            market_regime=pos.get("regime", ""),
            session=pos.get("session", ""),
            loss_reason="" if profit > 0 else reason,
            lesson=self._generate_lesson(profit, pos),
        )
        
        self.journal.add_entry(entry_data)
        self.last_trade_time = datetime.now()
        
        print(f"\n{'='*40}")
        print(f"  {'✅' if profit > 0 else '❌'} 平仓 {reason}")
        print(f"  盈亏: ${profit:+.2f} ({pips:.1f}点)")
        print(f"  余额: ${self.balance:.2f}")
        print(f"  情绪: {self.mood.value}")
        print(f"  连亏/连盈: {self.consecutive_losses}/{self.consecutive_wins}")
        print(f"{'='*40}")
        
        # 日目标达标提醒
        gain_pct = self.daily_profit / (self.balance - profit) * 100
        if gain_pct >= self.daily_profit_target_pct:
            print(f"  🎯 已达到日盈利目标 ({gain_pct:.1f}%), 建议收工")
        
        self.current_position = None
        return {"profit": profit, "balance": self.balance}

    def _update_mood_after_win(self) -> TraderMood:
        """盈利后的情绪管理 — 防止自负"""
        if self.consecutive_wins >= 4:
            print(f"  ⚠️ 连盈{self.consecutive_wins}笔, 警惕自负心态")
            return TraderMood.OVERCONFIDENT
        return TraderMood.CALM

    def _update_mood_after_loss(self) -> TraderMood:
        """亏损后的情绪管理 — 防止沮丧"""
        if self.consecutive_losses >= self.max_consecutive_losses:
            print(f"  ⛔ 连亏{self.consecutive_losses}笔, 触发热停机制")
            return TraderMood.FRUSTRATED
        elif self.consecutive_losses >= 2:
            print(f"  ⚠️ 连亏{self.consecutive_losses}笔, 检查是否在按计划交易")
            return TraderMood.CAUTIOUS
        return TraderMood.CALM

    def _generate_lesson(self, profit: float, pos: Dict) -> str:
        """自动生成经验教训 — 交易员的自我反思"""
        if profit > 0:
            return "按计划执行, 纪律性交易"
        else:
            # 根据场景生成不同的教训
            if pos.get("direction") == "BUY" and pos.get("entry", 0) > 0:
                return "入场过早, 应等待更明确的确认信号"
            elif pos.get("setup_type") == "breakout":
                return "突破交易需等回踩确认, 避免追高"
            else:
                return "交易前检查清单未严格遵循"

    # ─── 盘后复盘 ─────────────────────────

    def post_market_review(self):
        """
        盘后复盘 — 交易员每天收盘后最重要的事
        
        跟职业交易员的流程完全一致:
          1. 回顾今天所有交易
          2. 检查是否遵守了计划
          3. 统计今天表现
          4. 写下改进点
        """
        print(f"\n{'='*50}")
        print(f"  📊 盘后复盘 — {date.today()}")
        print(f"{'='*50}")
        
        stats = self.journal.get_statistics()
        
        print(f"  今日交易: {self.daily_trades} 笔")
        print(f"  今日盈亏: ${self.daily_profit:+.2f}")
        print(f"  账户余额: ${self.balance:.2f}")
        print()
        print(f"  历史统计:")
        print(f"    总交易: {stats['total_trades']}")
        print(f"    胜率: {stats['win_rate']:.1%}")
        print(f"    平均盈利: ${stats['avg_win']:.2f}")
        print(f"    平均亏损: ${stats['avg_loss']:.2f}")
        print(f"    盈亏比: {stats['profit_factor']:.2f}")
        print(f"    总利润: ${stats['total_profit']:.2f}")
        print(f"    最大回撤: {stats['max_drawdown']:.1f}%")
        
        # 自我总结
        if self.daily_profit > 0:
            print(f"\n  ✅ 今天做得好的地方:")
            print(f"    - 遵守了交易计划")
        else:
            print(f"\n  📝 今天需要改进:")
            print(f"    - 检查是否在情绪驱动下交易")
        
        # 重置日统计
        self.daily_trades = 0
        self.daily_profit = 0.0


# ═══════════════════════════════════════════
# 4. 交易前检查清单
# ═══════════════════════════════════════════

class PreTradeChecklist:
    """
    交易前检查清单 — 交易员的最后一道防线
    
    来自职业交易员研究的"入场前的5个YES":
      1. 这个信号在我的交易计划内吗?
      2. 风险回报比至少是1:1.5吗?
      3. 我这次的风险在1%或以下吗?
      4. 我的止损设在结构性位置吗?
      5. 我现在情绪是中立的吗?
    """
    
    def __init__(self):
        self.items = [
            ChecklistItem("信号在计划内", "这个信号符合今天的交易计划吗?"),
            ChecklistItem("盈亏比达标", "R:R ≥ 1:1.5?"),
            ChecklistItem("风险合规", "单笔风险 ≤ 1%?"),
            ChecklistItem("止损有逻辑", "止损设在结构位外?"),
            ChecklistItem("情绪中立", "现在的情绪适合交易吗?"),
            ChecklistItem("不追涨", "价格没有远离合理区间?"),
            ChecklistItem("方向一致", "与日线偏向一致?"),
        ]
    
    def evaluate(self, signal: Dict, market_data: Dict) -> Tuple[bool, str]:
        """运行检查清单, 全部YES才通过"""
        for item in self.items:
            passed, msg = item.check(signal, market_data)
            if not passed:
                return False, f"{item.name}: {msg}"
        return True, "全部通过"

@dataclass
class ChecklistItem:
    name: str
    question: str
    
    def check(self, signal: Dict, md: Dict) -> Tuple[bool, str]:
        """每个检查项的具体逻辑"""
        price = md.get("current_price", 0)
        entry = signal.get("entry_price", 0)
        sl = signal.get("stop_loss", 0)
        tp = signal.get("take_profit", 0)
        direction = signal.get("direction", "NONE")
        vote_score = signal.get("vote_score", 0)
        
        if self.name == "盈亏比达标":
            if direction == "BUY":
                risk = entry - sl if entry > sl else 0
                reward = tp - entry if tp > entry else 0
            elif direction == "SELL":
                risk = sl - entry if sl > entry else 0
                reward = entry - tp if entry > tp else 0
            else:
                return False, "无方向"
            
            if risk <= 0:
                return False, "止损距离为0"
            rr = reward / risk
            return rr >= 1.5, f"当前R:R={rr:.2f}"
        
        elif self.name == "风险合规":
            risk_pct = signal.get("risk_pct", 0)
            return risk_pct <= 1.0, f"风险{risk_pct:.2f}%"
        
        elif self.name == "情绪中立":
            mood = signal.get("trader_mood", "CALM")
            bad_moods = ["FRUSTRATED", "OVERCONFIDENT", "FATIGUED"]
            return mood not in bad_moods, f"当前情绪: {mood}"
        
        elif self.name == "不追涨":
            # 价格距离ema50不超过3%
            df_h1 = md.get("df_h1")
            if df_h1 is not None and len(df_h1) > 50:
                ema50 = df_h1["close"].rolling(50).mean().iloc[-1]
                dist = abs(price - ema50) / ema50 * 100
                return dist <= 3.0, f"距均线{dist:.1f}%"
            return True, "无数据, 跳过"
        
        elif self.name == "方向一致":
            bias = md.get("daily_bias", "观望")
            if bias == "观望":
                return True, "无明确偏向"
            if direction == "BUY" and "多" in bias:
                return True, "一致"
            if direction == "SELL" and "空" in bias:
                return True, "一致"
            return False, f"方向({direction})与偏向({bias})不一致"
        
        return True, "通过"


# ═══════════════════════════════════════════
# 5. 完整操盘手系统
# ═══════════════════════════════════════════

class GoldstrategyHumanTrader:
    """
    金策宗师团 — 人工操盘手模拟系统 v3.0
    
    完整工作流:
      ┌─────────────────────────────────────────┐
      │  盘前 08:00                              │
      │  1. 看经济日历                           │
      │  2. 定日线偏向                           │
      │  3. 标关键水平                           │
      │  4. 心理自检                              │
      ├─────────────────────────────────────────┤
      │  盘中 09:00-22:00                        │
      │  1. 等待信号                             │
      │  2. 运行检查清单                         │
      │  3. 硬规则检查 (连亏/日风险/日目标)       │
      │  4. 交易员经验判断                        │
      │  5. 通过 → 执行 / 不通过 → 等下一机会    │
      │  6. 持仓中不盯盘 (每30分钟检查一次)       │
      ├─────────────────────────────────────────┤
      │  盘后 22:00                              │
      │  1. 复盘今天交易                         │
      │  2. 写日志                               │
      │  3. 统计表现                             │
      │  4. 写下改进点                           │
      └─────────────────────────────────────────┘
    """
    
    def __init__(self, mode="DEMO"):
        self.mode = mode
        self.trader = HumanTrader()
        self.market_data = {}
        self.engine_v2 = None  # 引用v2引擎获取技术信号
        
        print(f"🕴️ 金策宗师团 v3.0 — 人工操盘手模拟系统")
        print(f"   模式: {mode}")
        print(f"   \"交易员的80% success来自心理纪律, 20%来自策略\"")
    
    def full_trading_day(self, market_data: Dict):
        """
        模拟一个完整的交易日 — 跟真实交易员一样
        
        运行顺序:
          盘前 → 盘中循环 → 盘后
        """
        self.market_data = market_data
        
        # 1. 盘前
        plan = self.trader.pre_market_routine(market_data)
        market_data["daily_bias"] = plan.bias
        
        # 2. 模拟盘中 (简化版)
        print(f"\n{'='*50}")
        print(f"  🎯 盘中交易时段")
        print(f"{'='*50}")
        
        # 从v2引擎获取信号
        from engine_v2 import GoldstrategyEngineV2, SignalDirection
        self.engine_v2 = GoldstrategyEngineV2(self.mode)
        decision = self.engine_v2.run_analysis_cycle(market_data)
        
        # 3. 交易员判断是否执行
        signal_dict = {
            "direction": decision.direction.value if hasattr(decision.direction, 'value') else "NONE",
            "entry_price": decision.entry_price,
            "stop_loss": decision.stop_loss,
            "take_profit": decision.take_profit,
            "vote_score": decision.vote_score,
            "confidence": decision.confidence,
            "regime": decision.regime.value if hasattr(decision.regime, 'value') else "RANGING",
            "trader_mood": self.trader.mood.name,
            "risk_pct": decision.kelly_fraction,
            "rr": abs(decision.take_profit - decision.entry_price) / abs(decision.stop_loss - decision.entry_price) if abs(decision.stop_loss - decision.entry_price) > 0 else 0,
            "reasoning": decision.reasoning,
            "setup_type": "多策略融合",
            "risk_checks": decision.risk_checks,
        }
        
        # 只检查风控和逻辑, 不检查心理 (因为这是AI)
        can_trade = True
        block_reasons = []
        
        # 风控拦截
        failed_checks = [k for k, v in decision.risk_checks.items() if not v]
        if failed_checks:
            can_trade = False
            block_reasons.append(f"风控: {', '.join(failed_checks)}")
        
        # 方向无效
        if decision.direction == SignalDirection.NONE:
            can_trade = False
            block_reasons.append("无明确信号方向")
        
        # 硬规则 (连亏/日交易数)
        hard_pass, hard_msg = self.trader._check_hard_rules()
        if not hard_pass:
            can_trade = False
            block_reasons.append(f"纪律: {hard_msg}")
        
        # 交易员经验
        if can_trade:
            exp_pass, exp_msg = self.trader._trader_experience_check(signal_dict, market_data)
            if not exp_pass:
                can_trade = False
                block_reasons.append(f"经验: {exp_msg}")
        
        # 4. 执行或放弃
        if can_trade and self.mode == "DEMO":
            print(f"\n🔶 DEMO模式: 信号已通过所有检查, 但不执行真实交易")
            print(f"   方向: {decision.direction.value} ${decision.entry_price:.1f}")
            print(f"   SL: ${decision.stop_loss:.1f} TP: ${decision.take_profit:.1f}")
            print(f"   Kelly: {decision.kelly_fraction:.2%}")
        
        elif can_trade and self.mode == "LIVE":
            result = self.trader.execute_trade(signal_dict, market_data)
            # 模拟持仓结束后平仓
            exit_price = decision.take_profit if decision.direction == SignalDirection.BUY else decision.stop_loss
            self.trader.close_trade(exit_price, "模拟平仓")
        
        else:
            print(f"\n⏸️  未执行交易:")
            for reason in block_reasons:
                print(f"   - {reason}")
            if self.trader.mood.value != "平静":
                print(f"   - 情绪状态: {self.trader.mood.value}")
        
        # 5. 盘后复盘
        self.trader.post_market_review()


def demo():
    """演示: 模拟操盘手一天"""
    from datetime import datetime
    
    trader_system = GoldstrategyHumanTrader(mode="DEMO")
    
    mock_data = {
        "current_price": 2335.50,
        "current_hour": 14,
        "current_date": datetime.now(),
        "balance": 10000.0,
        "equity": 10050.0,
        "atr": 12.5,
        "spread": 15,
        "regime": "WEAK_TREND",
        "avg_win": 180,
        "avg_loss": 85,
        "consecutive_losses": 0,
        "risk_events": ["CPI_DATA_THURSDAY"],
        "df_h1": None,
        "df_m15": None,
    }
    
    trader_system.full_trading_day(mock_data)
    
    print(f"\n{'='*50}")
    print(f"  📋 最终状态")
    print(f"  余额: ${trader_system.trader.balance:.2f}")
    print(f"  总交易: {trader_system.trader.total_trades}")
    print(f"  日志条数: {len(trader_system.trader.journal.journal)}")
    print(f"  情绪: {trader_system.trader.mood.value}")


if __name__ == "__main__":
    demo()
