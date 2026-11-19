# risk_auditor.py — 金策宗师团 · 风控部 · 审度司 (risk-auditor)
"""
独立风险审计: 对每一笔交易提案做合规/风险核算, 拥有对交易的一票否决权。
CIO / 交易部 / 金刚卫 均不得绕过本模块的结论。

风控铁律 (金策宗师团 v4.0):
  - 单笔风险 ≤ 1% 账户净值
  - 日累计风险 ≤ 3% 账户净值
  - 单品种手数 ≤ 上限
  - 审度司 VETO 优先级最高, 任何角色不可推翻

注意: 本模块只做"审计 + 风险登记", 不触任何下单接口。
"""
import json
import os
import datetime


# ── 组合相关性分组 (优化2: 组合风控) ──
#   同组品种在统计上高度相关(如 USDJPY/GBPJPY 同为日元系),
#   同时同方向开仓会放大相关性风险. 此处用"分组成员"近似相关系数,
#   零外部数据依赖; 如需更精细可日后接历史收益率相关矩阵.
#   组内默认相关系数 (简化, 用于降权/拒开判定).
CORRELATION_GROUPS = {
    'JPY': ['USDJPY', 'GBPJPY'],          # 日元系: 高度同向
    'USD_MAJORS': ['EURUSD', 'GBPUSD'],  # 美元直盘: 中度同向
}
GROUP_CORR = 0.8


class RiskAuditor:
    def __init__(self, max_risk_per_trade=0.01, max_daily_risk=0.03,
                 max_lot_per_symbol=None,
                 state_file=None):
        self.max_rpt = max_risk_per_trade      # 单笔风险上限 (净值占比)
        self.max_dr = max_daily_risk           # 日累计风险上限
        self.max_lot = max_lot_per_symbol or {}  # {symbol: 手数上限}
        # [2026-09-03 P0 连亏 kill-switch] 死亡螺旋防护 (08-18 单日787平仓/-347元凶):
        #   连亏≥tier1_n(默认3)→单笔/日险上限减半 (Tier1 防御, 砍仓止血);
        #   连亏≥kill_switch_n(默认5)→硬暂停新开仓 (kill-switch), 直到一笔盈利重置;
        #   近 rolling_n(默认10)笔滚动期望 < rolling_halt_r(默认-0.3R)→暂停 (权益曲线保护, 切SIM).
        self.kill_switch_n = 5
        self.tier1_n = 3
        self.rolling_n = 10
        self.rolling_halt_r = -0.3
        # [2026-08-28 P3 全网升级] 账户回撤熔断 (Ernest Chan: Hard Stops on
        # total equity 防黑天鹅): 回撤>10%降半仓, >15%暂停新开.
        self.dd_halt_pct = 0.15
        self.dd_half_pct = 0.10
        self.peak_equity = None   # 启动时初始化
        self._dd_pct = 0.0
        if state_file is None:
            state_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      'data', 'continuous_evolution', 'risk_state.json')
        self.state_file = state_file
        self.state = self._load()

    def set_peak_equity(self, equity):
        """记录账户峰值 (每轮调用, 用于回撤计算)."""
        if equity <= 0:
            return
        if self.peak_equity is None or equity > self.peak_equity:
            self.peak_equity = equity
        if self.peak_equity > 0:
            self._dd_pct = max(0.0, (self.peak_equity - equity) / self.peak_equity)

    def drawdown_pct(self):
        """当前账户回撤比例 (0..1)."""
        return self._dd_pct

    def drawdown_scale(self):
        """回撤风险缩放: 1.0正常 / 0.5回撤>10% / 0.0回撤>15%暂停."""
        if self._dd_pct >= self.dd_halt_pct:
            return 0.0
        if self._dd_pct >= self.dd_half_pct:
            return 0.5
        return 1.0

    # ── 状态持久化 ──────────────────────────────────────────────
    def _load(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass  # 损坏则重建, 不崩溃
        return self._fresh()

    def _fresh(self):
        return {'date': datetime.date.today().isoformat(),
                'daily_risk_used': 0.0, 'trades_today': 0,
                'consecutive_losses': 0, 'recent_r': []}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except Exception:
            pass  # 持久化失败不阻断交易审计

    def _rollover(self):
        """跨日自动重置日风险计数"""
        today = datetime.date.today().isoformat()
        if self.state.get('date') != today:
            self.state = self._fresh()
            self._save()

    # ── 核心审计 ────────────────────────────────────────────────
    def audit(self, proposal, equity):
        """
        proposal: dict {
            'symbol', 'direction', 'lot',
            'sl_pts' (止损点数, 以pip计), 'tp_pts', 'pip_usd_per_lot'
        }
        equity: 账户净值 (float)
        返回 (decision, reasons)
            decision ∈ {'PASS', 'VETO'}
            reasons: list[str]
        """
        self._rollover()
        reasons = []
        sym = proposal['symbol']

        # [2026-08-28 P3] 账户回撤熔断: 回撤>15% 暂停新开 (黑天鹅保护)
        if self._dd_pct >= self.dd_halt_pct:
            return 'VETO', [f"账户回撤 {self._dd_pct*100:.0f}% ≥ "
                            f"{self.dd_halt_pct*100:.0f}%, 熔断暂停新开仓"]

        # [2026-09-03 P0 连亏 kill-switch] 死亡螺旋防护 (净亏根因)
        cl = int(self.state.get('consecutive_losses', 0))
        if cl >= self.kill_switch_n:
            return 'VETO', [f"连亏 {cl} 笔 ≥ {self.kill_switch_n}, "
                            f"kill-switch 暂停新开仓 (出现盈利重置)"]
        # 连亏≥tier1_n → 单笔/日险上限减半 (Tier1 防御, 砍仓止血)
        _scale = 0.5 if cl >= self.tier1_n else 1.0
        # 近 rolling_n 笔滚动期望 < rolling_halt_r → 权益曲线保护暂停
        _recent = self.state.get('recent_r', [])[-self.rolling_n:]
        if len(_recent) >= self.rolling_n and (sum(_recent) / len(_recent)) < self.rolling_halt_r:
            return 'VETO', [f"近{self.rolling_n}笔滚动期望 "
                            f"{sum(_recent)/len(_recent):.2f}R < {self.rolling_halt_r}R, "
                            f"权益曲线保护暂停新开仓"]
        _max_rpt = self.max_rpt * _scale
        _max_dr = self.max_dr * _scale

        # 1. 手数上限
        cap = self.max_lot.get(sym)
        if cap is not None and proposal['lot'] > cap + 1e-9:
            reasons.append(f"手数 {proposal['lot']:.2f} 超 {sym} 上限 {cap:.2f}")

        # 2. 单笔风险
        # [2026-08-24 优化] 配对交易 (pair_ref 存在) 双腿对冲: 单腿风险按
        # 半计 (另一腿反向抵消, 净风险≈价差而非单腿方向), 否则 XAU/XAG
        # 等宽波动品种的配对腿会被 2.5% 单笔上限误杀. 非配对维持原逻辑.
        risk_amt = proposal['lot'] * proposal['sl_pts'] * proposal['pip_usd_per_lot']
        risk_pct = (risk_amt / equity) if equity > 0 else 1.0
        if proposal.get('pair_ref'):
            risk_pct *= 0.5   # 配对腿风险减半 (对冲)
        if risk_pct > _max_rpt + 1e-9:
            reasons.append(
                f"单笔风险 {risk_pct*100:.2f}% 超上限 {_max_rpt*100:.1f}%"
                + (" (连亏Tier1减半)" if _scale < 1.0 else ""))

        # 3. 日累计风险
        # [2026-08-24 修复] 原逻辑 daily_risk_used 只增不减 (commit累加, 平仓不
        # 释放) → 当天开过几笔后额度永久占用, 后续优质信号(如配对)被永久卡死.
        # 改为动态计算: 当前持仓实际SL风险总和(平仓自动释放) + 本提案风险.
        # 传入的 open_risk 由调用方(guardian)实时统计; 缺失时回退历史累计.
        open_risk = proposal.get('_open_risk', None)
        if open_risk is None:
            open_risk = self.state['daily_risk_used']
        if open_risk + risk_pct > _max_dr + 1e-9:
            reasons.append(
                f"日累计风险将达 {(open_risk+risk_pct)*100:.2f}% "
                f"超上限 {_max_dr*100:.1f}% (当前持仓 {open_risk*100:.2f}%)"
                + (" (连亏Tier1减半)" if _scale < 1.0 else ""))

        if reasons:
            return 'VETO', reasons
        return 'PASS', ['风险合规']

    # ── 组合相关性风控 (优化2) ─────────────────────────────────
    def assess_portfolio_correlation(self, symbol, direction, open_dirs):
        """评估新提案与现有持仓的组合相关性风险 (默认仅报告, 不拦截).

        参数:
          symbol    : 新提案品种
          direction : 'BUY' / 'SELL' (新提案方向)
          open_dirs : dict {symbol: 'BUY'/'SELL'} 当前已开仓品种及其方向
        返回 dict:
          {action, correlated_with, corr, note}
            action ∈ {'OK', 'DOWNWEIGHT', 'REJECT'}
              OK         — 无同组持仓, 无相关性风险
              DOWNWEIGHT— 同组但有反向持仓(天然对冲), 建议降权
              REJECT    — 同组且同方向持仓(相关性高), 建议拒开
        纯函数: 不修改任何状态; 是否真正拦截由调用方按 PORTFOLIO_CORR_ENFORCE 决定.
        不破三安全闸 / VETO / ADX硬禁 / 双铁律.
        """
        grp = next((g for g, ms in CORRELATION_GROUPS.items()
                    if symbol in ms), None)
        if grp is None:
            return {'action': 'OK', 'correlated_with': [], 'corr': 0.0,
                    'note': f'{symbol} 不在任何相关分组, 无组合相关性风险'}
        same_dir = [(m, open_dirs[m]) for m in CORRELATION_GROUPS[grp]
                    if m != symbol and m in open_dirs
                    and open_dirs[m] == direction]
        if same_dir:
            return {'action': 'REJECT', 'correlated_with': same_dir,
                    'corr': GROUP_CORR,
                    'note': (f'{symbol} 与 {same_dir} 同属 {grp} 分组且同方向, '
                             f'相关系数≈{GROUP_CORR}, 相关性风险高')}
        opp_dir = [(m, open_dirs[m]) for m in CORRELATION_GROUPS[grp]
                   if m != symbol and m in open_dirs
                   and open_dirs[m] != direction]
        if opp_dir:
            return {'action': 'DOWNWEIGHT', 'correlated_with': opp_dir,
                    'corr': GROUP_CORR,
                    'note': (f'{symbol} 与 {opp_dir} 同属 {grp} 分组但反向(对冲), '
                             f'建议降权')}
        return {'action': 'OK', 'correlated_with': [], 'corr': 0.0,
                'note': f'{symbol} 所属 {grp} 分组当前无持仓, 无组合相关性风险'}

    def daily_risk_log(self, open_positions=None):
        """日累计风险强化日志: 返回当前日风险占用/上限/笔数 + 持仓数,
        供组合风控(优化2)记录. 纯读, 不修改状态."""
        self._rollover()
        return {
            'date': self.state['date'],
            'daily_risk_used_pct': round(self.state['daily_risk_used'] * 100, 2),
            'max_daily_risk_pct': round(self.max_dr * 100, 2),
            'trades_today': self.state['trades_today'],
            'open_positions': len(open_positions) if open_positions else 0,
            'single_risk_cap_pct': round(self.max_rpt * 100, 2),
        }

    # ── 风险登记 (成交后调用) ──────────────────────────────────
    def commit(self, proposal, equity):
        """审计通过后登记风险占用, 计入日累计"""
        risk_pct = (proposal['lot'] * proposal['sl_pts'] * proposal['pip_usd_per_lot']
                    / equity) if equity > 0 else 0.0
        self.state['daily_risk_used'] += risk_pct
        self.state['trades_today'] += 1
        self._save()

    # ── 连亏 kill-switch: 平仓后登记盈亏 ──────────────────────
    def register_close(self, profit, risk_r=None):
        """平仓后登记实现盈亏 → 更新连亏计数与滚动期望窗口.
        profit: 实现盈亏(float); None 表示无法判定(如查询失败)→ 不更新计数防误触发.
        risk_r: 该笔 R 倍数(可选, 用于滚动期望)."""
        if profit is None:
            return
        cl = int(self.state.get('consecutive_losses', 0))
        cl = 0 if profit > 0 else cl + 1
        self.state['consecutive_losses'] = cl
        if risk_r is not None:
            _r = self.state.setdefault('recent_r', [])
            _r.append(float(risk_r))
            if len(_r) > self.rolling_n:
                _r[:] = _r[-self.rolling_n:]
        self._save()

    def effective_max_rpt(self):
        """连亏 Tier1 防御: 连亏≥tier1_n 时单笔下注上限减半 (供 guardian 仓位计算)."""
        cl = int(self.state.get('consecutive_losses', 0))
        return self.max_rpt * (0.5 if cl >= self.tier1_n else 1.0)

    # ── 平仓审计 ────────────────────────────────────────────────
    def audit_close(self, symbol, volume):
        """
        平仓审计: 平仓只降低风险暴露, 不新增任何风险, 审度司默认放行。
        不计入日风险占用 (close 释放额度而非占用), 仅记录操作日志。
        注意: 平仓不做 VETO —— VETO 的设计目的是阻止"新增坏风险",
        而平仓是减仓, 与风控目标同向。
        """
        self._rollover()
        return 'PASS', [f'平仓 {symbol} {volume} → 风险暴露降低, 审度司放行']

    # ── SL/TP 修改审计 ────────────────────────────────────────
    def audit_modify(self, symbol, old_sl, new_sl, entry, direction, equity):
        """
        SL 修改审计: 仅允许"收紧/持平"风险的修改
        (SL 向入场价靠拢 / 移到 BE / trailing), 拒绝"放松"风险
        (SL 远离入场价 → 放大潜在亏损)。
        这是监军司做保本损/追踪止损的安全闸门: 永远不能把止损挪远。
        direction: 'BUY' / 'SELL'
        """
        self._rollover()
        if direction == 'BUY':
            old_risk = (entry - old_sl) if old_sl and old_sl > 0 else 0.0
            new_risk = (entry - new_sl) if new_sl and new_sl > 0 else 0.0
        else:
            old_risk = (old_sl - entry) if old_sl and old_sl > 0 else 0.0
            new_risk = (new_sl - entry) if new_sl and new_sl > 0 else 0.0
        if new_risk > old_risk + 1e-9:
            return 'VETO', [
                f'SL 修改将放大风险 (旧 {old_risk:.5f} → 新 {new_risk:.5f}), '
                f'审度司否决 (禁止放松止损)']
        return 'PASS', ['SL 收紧/持平, 风险降低或不变, 审度司放行']

    def daily_risk_used(self):
        self._rollover()
        return self.state['daily_risk_used']

    def summary(self):
        self._rollover()
        return {
            'date': self.state['date'],
            'daily_risk_used_pct': round(self.state['daily_risk_used'] * 100, 2),
            'max_daily_risk_pct': round(self.max_dr * 100, 2),
            'trades_today': self.state['trades_today'],
            'single_risk_cap_pct': round(self.max_rpt * 100, 2),
        }
