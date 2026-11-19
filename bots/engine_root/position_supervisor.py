# position_supervisor.py — 金策宗师团 · 监军司 (PositionSupervisor)
"""
持仓监督 + 灵活决策引擎。

设计动机 (CIO 2026-07-07):
  原系统只会"开仓 + 等 SL/TP", 持仓与行情背离时完全无能为力,
  必须 CIO 手动介入 (本次 EURUSD 逆风多单即此例)。
  监军司让系统"时刻根据行情灵活决定": 每个周期扫描所有持仓,
  对照实时研判 + ATR 自适应阈值, 决定 HOLD / BREAKEVEN / TRAIL / CLOSE。

铁律 (金策宗师团 v4.0):
  - 任何动作 (平/改SL) 仍经审度司审计, VETO 不可绕过
  - 平仓 = 风险降低 → 审度司 audit_close 默认 PASS
  - 改 SL 仅允许"收紧/持平" → 审度司 audit_modify 放行, 放松即 VETO
  - 不主动开新仓 (那是交易部/金刚卫的职责, 监军司只管已持仓)

决策规则 (按优先级):
  1. 信号反向 (live_bias 与持仓方向相反, 且 ADX 可读) → CLOSE
  2. 趋势崩溃 (ADX < adx_exit) 且浮盈 → CLOSE (保利润)
  3. 浮盈 ≥ 1×ATR 且尚未保本 → BREAKEVEN (SL 移到入场价)
  4. 浮盈 ≥ 2×ATR → TRAIL (SL 追踪到 价-2.5×ATR 宽松距离, 仅收紧; 4×ATR 阶段再收紧至 1.5×ATR 锁利)
  5. 其余 → HOLD

ATR 自适应: 阈值随品种波动率缩放, 高波动放宽、低波动收紧 —— 即"灵活"。
"""
import os
import json
import time
import numpy as np
import MetaTrader5 as mt5
import guardian_executor as ge
import continuous_evolution_v2 as ce
import symbol_universe as su

# [2026-09-02 V3] 向朋友 Godking Apex 学习: 小止损大盈利
#   早保本(SL=开仓价, 模仿朋友实盘 SL=entry) + 吊灯追踪(朋友 backtest PF 3~5),
#   盈利区不主动平仓(让利润奔跑)。False=回退旧逻辑(激进平仓+1×ATR才保本)。
V3_WINNER_RELEASE = True


def load_best_strategy(symbol=None):
    """加载最优策略参数.

    - symbol 给定 → 取该品种独立进化出的最优(best_per_symbol[symbol]);
      缺失时回退到全局 best_strategy, 保证扫描不中断.
    - symbol 为 None → 取全局兜底 best_strategy(向后兼容);
      若仅存在逐品种态则取 fitness 最高者.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, 'data', 'continuous_evolution',
                        'evolution_state.json')
    with open(path, 'r', encoding='utf-8') as f:
        st = json.load(f)
    if symbol is not None:
        bps = st.get('best_per_symbol') or {}
        bs = bps.get(symbol) or st.get('best_strategy') or st.get('best')
    else:
        bs = st.get('best_strategy') or st.get('best')
        if not bs and st.get('best_per_symbol'):
            cand = [v for v in st['best_per_symbol'].values() if v]
            bs = max(cand, key=lambda x: x.get('fitness') or -1e9) if cand else None
    if not bs:
        raise RuntimeError('evolution_state.json 缺少 best_strategy')
    if 'params' not in bs or 'adx_min' not in bs['params']:
        bs.setdefault('params', {})['adx_min'] = 20
    return bs


def load_all_best_strategies():
    """加载全部品种的独立最优策略, 返回 {symbol: best_dict}.

    某品种尚未独立进化时, 回退到全局 best_strategy(若存在),
    保证猎场司对每个品种都有可用参数(逐品种进化是渐进补齐的).
    """
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, 'data', 'continuous_evolution',
                        'evolution_state.json')
    with open(path, 'r', encoding='utf-8') as f:
        st = json.load(f)
    bps = st.get('best_per_symbol') or {}
    fallback = st.get('best_strategy') or st.get('best')
    if not fallback and bps:
        cand = [v for v in bps.values() if v]
        fallback = max(cand, key=lambda x: x.get('fitness') or -1e9) if cand else None
    out = {}
    for sym in ce.SYMBOL_CONFIG:
        bs = bps.get(sym) or fallback
        if bs and ('params' not in bs or 'adx_min' not in bs.get('params', {})):
            bs = dict(bs)
            bs.setdefault('params', {})['adx_min'] = 20
        out[sym] = bs
    return out


class Decision:
    """单笔持仓的监军司决策"""
    def __init__(self, action, ticket, symbol, direction, reason,
                 new_sl=None, floating_pips=0.0, bias='NEUTRAL',
                 bias_reason=''):
        self.action = action          # HOLD / BREAKEVEN / TRAIL / CLOSE
        self.ticket = ticket
        self.symbol = symbol
        self.direction = direction    # BUY / SELL
        self.reason = reason
        self.new_sl = new_sl
        self.floating_pips = floating_pips
        self.bias = bias
        self.bias_reason = bias_reason

    def to_dict(self):
        return {
            'action': self.action, 'ticket': int(self.ticket),
            'symbol': self.symbol, 'direction': self.direction,
            'bias': self.bias, 'bias_reason': self.bias_reason,
            'floating_pips': round(self.floating_pips, 2),
            'new_sl': (round(self.new_sl, 5)
                       if self.new_sl is not None else None),
            'reason': self.reason,
        }


class PositionSupervisor:
    def __init__(self, auto_confirm=False, dry_run=True,
                 adx_exit=18.0, be_mult=1.5, trail_trigger_mult=2.0,
                 trail_dist_mult=2.5,
                 early_be_mult=0.2, trail_lookback=20,
                 trail_atr_mult=2.5, trail_activate_mult=1.5):
        # [2026-08-28 全网前沿重校准 P0]:
        #   保本 1.5×ATR (黄金常回撤1R再继续), 追踪触发 2×ATR, 追踪距离
        #   2.5×ATR (原1.0过紧, 正常波动即触发 → 盈利单过早出场).
        #   MQL5 XAU专家共识: 追踪需 2.5-3.5×ATR, 步进式.
        # [2026-09-02 V3] 向朋友 Apex 学习: 早保本 + 吊灯追踪参数
        #   early_be_mult: 浮盈≥此×ATR 即保本锁至开仓价(模仿朋友 SL=entry).
        #     朋友实盘证实 SL=开仓价(保本锁)从开仓即生效(≈0风险); 0.2×ATR
        #     为兼顾点差/微噪的贴近值(原0.4偏宽, 输单仍吃0.4×ATR).
        #   trail_lookback/trail_atr_mult: 吊灯回看根数/ATR倍数(朋友 backtest)
        #   trail_activate_mult: 浮盈≥此×ATR 才启动吊灯追踪
        self.auto_confirm = auto_confirm
        self.dry_run = dry_run
        self.adx_exit = adx_exit
        self.be_mult = be_mult
        self.trail_trigger_mult = trail_trigger_mult
        self.trail_dist_mult = trail_dist_mult
        self.early_be_mult = early_be_mult
        self.trail_lookback = trail_lookback
        self.trail_atr_mult = trail_atr_mult
        self.trail_activate_mult = trail_activate_mult
        self.strategy = load_best_strategy()
        self.guardian = ge.GuardianExecutor(
            auto_confirm=auto_confirm,
            max_risk_per_trade=0.01,
            max_daily_risk=0.03,
        )
        self.mt5 = None

    # ── 连接 ──────────────────────────────────────────────────
    def connect(self):
        if self.guardian.connect():
            self.mt5 = self.guardian.mt5
            return True
        return False

    # ── 健康检查 (守护进程韧性) ──────────────────────────────
    def healthy(self):
        """MT5 是否仍在线。断线 (account_info 为 None) 即判不健康。
        供 run_supervisor 循环内自动重连使用, 吸收对方守护进程的
        'MT5 断线→重连' 韧性设计。"""
        if self.mt5 is None:
            return False
        try:
            return self.mt5.account_info() is not None
        except Exception:
            return False

    # ── 单笔决策 ──────────────────────────────────────────────
    def _evaluate(self, pos):
        sym = pos.symbol
        direction = ('BUY' if pos.type == mt5.POSITION_TYPE_BUY
                     else 'SELL')
        # [2026-08-28 P4 全网升级] 高影响新闻冻结追踪: HALT级事件期间只
        # 看护不平仓/不收紧 (新闻尖峰会扫SL后反转, 冻结保护盈利单).
        # 数据源: data/event_risk.json (run_trader 维护).
        try:
            _erf = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'data', 'event_risk.json')
            if os.path.exists(_erf):
                with open(_erf, 'r', encoding='utf-8') as f:
                    _est = json.load(f)
                _age = time.time() - float(_est.get('updated', 0))
                if _age < 1800 and _est.get('halt_new_entries'):
                    return Decision('HOLD', pos.ticket, sym, direction,
                                    '高影响新闻窗口, 冻结追踪(防新闻尖峰扫SL)',
                                    floating_pips=0.0)
        except Exception:
            pass
        # pip 取自 canonical 规格 symbol_universe.UNIVERSE (覆盖全部 65 品种);
        # 旧 ce.SYMBOL_CONFIG 仅含 7 个 legacy 品种, 桥接盘(NZDUSD/EURNZD/...)
        # 会 KeyError。主源 UNIVERSE, 回退 legacy 配置(双保险)。
        _spec = su.UNIVERSE.get(sym) or {}
        pip = _spec.get('pip') or ce.SYMBOL_CONFIG.get(sym, {}).get('pip')
        if not pip or pip <= 0:
            return Decision('HOLD', pos.ticket, sym, direction,
                            f'无法解析 {sym} 点值(pip), 保守持有')
        # 实时研判
        bias, bias_reason = self.guardian.live_bias(sym, self.strategy)
        # 行情快照
        mkt = self.guardian.market_state(sym)
        atr = mkt['atr_now']
        adx = mkt['adx_now']
        close_a = mkt.get('close')
        high_a = mkt.get('high')
        low_a = mkt.get('low')
        ii = mkt.get('i')
        sign = 1 if direction == 'BUY' else -1
        floating = (pos.price_current - pos.price_open) * sign  # 价格项
        floating_pips = floating / pip if pip else 0.0

        # 1. 信号反向 → CLOSE
        # [2026-08-24 优化] 反向平仓加浮盈保护: 只有浮盈≥0.5×ATR(利润已锁定)
        # 才反向平仓; 浮亏/小幅浮盈时容忍, 交给追踪止损系统管理.
        # 此前无条件反向平 → 盈利单在 +0.01~+0.69 就被截断 (中位$0.61),
        # 利润跑不足, 盈亏比<1. 0.5×ATR 门槛避免震荡市频繁反转割肉.
        # [2026-08-26 P4-2 融合] 时段偏差保护: 持仓方向与时段统计偏差一致
        # (如USDJPY h8做空) 时, 放宽反向平仓门槛到 1.0×ATR (时段优势加持,
        # 不因短期信号反向过早离场); 反向持仓则维持0.5×ATR更积极离场.
        _sess_bias_ok = False
        try:
            import session_momentum as _sm
            _scfg = _sm.SESSION_STRATEGY_MAP.get(sym)
            if _scfg:
                import datetime as _dtt
                _now_h = _dtt.datetime.fromtimestamp(
                    float(getattr(pos, 'time', 0))).hour if getattr(pos, 'time', 0) else -1
                if _now_h == _scfg['hour'] and direction == _scfg['direction']:
                    _sess_bias_ok = True
        except Exception:
            pass
        if bias != 'NEUTRAL' and bias != direction:
            # [2026-09-02 V3] 盈利区不砍(交给吊灯追踪让利润奔跑);
            #   仅亏损区(未保本)反向才风险平仓(小损≈0, 避免扛 reverse 单到宽SL).
            if floating <= 0:
                return Decision('CLOSE', pos.ticket, sym, direction,
                                f'V3 持仓 {direction} 与信号 {bias} 反向且浮亏 '
                                f'{floating_pips:.1f}pip(未保本), 风险平仓',
                                floating_pips=floating_pips, bias=bias,
                                bias_reason=bias_reason)
            # 盈利区: 容忍反向(让利润奔跑), 交吊灯追踪管理

        # 2. 趋势崩溃且浮亏 → CLOSE (仅亏损区; 盈利区交给吊灯追踪, 不砍赢单)
        if (not np.isnan(adx)) and adx < self.adx_exit and floating <= 0:
            return Decision('CLOSE', pos.ticket, sym, direction,
                            f'ADX {adx:.1f} < {self.adx_exit:.0f} 趋势崩溃且亏损, '
                            f'平仓', floating_pips=floating_pips,
                            bias=bias, bias_reason=bias_reason)

        # 2.5 [P2-1] 趋势衰竭前瞻识别: ADX 斜率转负(趋势衰减) 或 价格极端
        #     偏离 EMA21(超买/超卖) → 趋势动能枯竭, 浮盈持仓提前平仓保利润
        #     (比规则2的 ADX<18 崩溃更前瞻, 减少利润回吐). 异常吞掉不阻断.
        try:
            if None in (close_a, high_a, low_a, ii):
                pass  # 无历史序列(mock/测试环境), 跳过衰竭检测(不阻断主链)
            else:
                _adx_s = ce._adx(high_a, low_a, close_a)
                _ema21 = ce._ema(close_a, 21)
                if (not np.isnan(_adx_s[ii])) and ii >= 5 and (not np.isnan(_ema21[ii])):
                    _slope = _adx_s[ii] - _adx_s[ii - 5]
                    _dev = abs(close_a[ii] - _ema21[ii]) / (atr + 1e-9)
                    if floating <= 0 and (_slope < -8 or _dev > 6):
                        return Decision('CLOSE', pos.ticket, sym, direction,
                                        f'趋势衰竭(ADX斜率{_slope:.1f}/EMA偏离{_dev:.1f}σ)'
                                        f'且亏损, 提前平仓',
                                        floating_pips=floating_pips, bias=bias,
                                        bias_reason=bias_reason)
        except Exception:
            pass

        # ── P0-3 追踪止盈系统接入主链: 无更早退出条件时, 交给追踪决策 ──

        # [2026-08-24 优化] 宽SL主动收紧: 持仓SL距开仓 > 3×ATR 时, 浮盈≥0
        # 立即提到保本(入场价), 浮亏但方向顺应且持仓>12h 也提到 -1×ATR 内,
        # 避免 9.4×ATR 超宽SL长期占用风险预算 (阻塞其他信号如配对).
        try:
            _sl_dist = abs(pos.price_open - pos.sl) if pos.sl else 0
            if _sl_dist > 3.0 * atr:
                if floating >= 0:
                    _new_be = pos.price_open
                    if (direction == 'BUY' and _new_be > pos.sl + 1e-9) or \
                       (direction == 'SELL' and _new_be < pos.sl - 1e-9):
                        return Decision('BREAKEVEN', pos.ticket, sym, direction,
                                        f'宽SL({_sl_dist/atr:.1f}×ATR)收紧至保本, '
                                        f'释放风险预算', new_sl=_new_be,
                                        floating_pips=floating_pips,
                                        bias=bias, bias_reason=bias_reason)
                elif bias != 'NEUTRAL' and bias == direction:
                    # 浮亏但方向顺应: 收紧到 -1×ATR (减少暴露, 不砍顺势单)
                    _tight = (pos.price_open - 1.0 * atr if direction == 'BUY'
                              else pos.price_open + 1.0 * atr)
                    if (direction == 'BUY' and _tight > pos.sl + 1e-9) or \
                       (direction == 'SELL' and _tight < pos.sl - 1e-9):
                        return Decision('BREAKEVEN', pos.ticket, sym, direction,
                                        f'宽SL({_sl_dist/atr:.1f}×ATR)顺势收紧至'
                                        f'-1×ATR, 释放风险预算', new_sl=_tight,
                                        floating_pips=floating_pips,
                                        bias=bias, bias_reason=bias_reason)
        except Exception:
            pass

        # ── V3 [2026-09-02 学朋友Apex: 小止损大盈利] 早保本 + 吊灯追踪 ──
        if V3_WINNER_RELEASE and atr > 0 and pip > 0 \
                and floating >= self.early_be_mult * atr:
            # 已脱离风险区 → 保本锁(模仿朋友 SL=entry), 之后只靠吊灯追踪让利润奔跑
            _be_sl = pos.price_open
            _cur = pos.sl or 0.0
            _need_be = ((direction == 'BUY' and _be_sl > _cur + 1e-9) or
                        (direction == 'SELL' and _be_sl < _cur - 1e-9))
            if _need_be:
                return Decision('BREAKEVEN', pos.ticket, sym, direction,
                                f'V3 浮盈 {floating_pips:.1f}pip≥{self.early_be_mult}×ATR, '
                                f'保本损至开仓价(学Apex SL=entry)',
                                new_sl=_be_sl, floating_pips=floating_pips,
                                bias=bias, bias_reason=bias_reason)
            # 已保本 → 吊灯追踪(激活于 trail_activate_mult×ATR, 锁利下限=开仓价)
            try:
                tr = self._chandelier_trailing(
                    pos, sym, direction, pip, atr, floating,
                    floating_pips, bias, bias_reason,
                    close_a, high_a, low_a, ii)
                if tr is not None:
                    return tr
            except Exception:
                pass
            return Decision('HOLD', pos.ticket, sym, direction,
                            'V3 已保本, 吊灯追踪看护(让利润奔跑)',
                            floating_pips=floating_pips, bias=bias,
                            bias_reason=bias_reason)

        try:
            tr = self._trailing_stop_decision(
                pos, sym, direction, pip, atr, adx,
                floating, floating_pips, bias, bias_reason)
            if tr is not None:
                return tr
        except Exception:
            pass

        # 5. 持有 (兜底: 行情顺应 / 浮盈不足 / 无触发条件)
        return Decision('HOLD', pos.ticket, sym, direction,
                        '行情顺应 / 浮盈不足 / 无触发条件',
                        floating_pips=floating_pips, bias=bias,
                        bias_reason=bias_reason)

    # ── 追踪止盈系统（P0-3增强版 + 2026-08-29 深度修复）──────────────
    # [2026-08-29 修复] 原追踪系统失效根因:
    #   1. 阶段1(保本)SL=开仓±0.5×ATR, 设置后浮盈持续≥1.5×ATR但新SL=旧SL
    #      → _better=False → 后续轮次永不触发 → 追踪停滞
    #   2. 阶段2(追踪)距离2.5×ATR > 初始SL距离1.3×ATR → 永远更宽 → 永不收紧
    #   3. 每轮调用audit_and_modify但新SL=旧SL → retcode=10025(无变化)
    #   → 155笔止损胜率7.1% PnL-94.32 (追踪形同虚设)
    #
    # [修复] 价格追踪式: SL始终=价格±距离, 每次价格创新高/低则收紧, 逻辑清晰无歧义:
    #   - 阶段0: 浮盈≥1×ATR → 保本 (SL=开仓, 仅收紧不回放)
    #   - 阶段1: 浮盈≥2×ATR → 追踪 (SL=价格-2.5×ATR, 每根K线重新计算)
    #   - 阶段2: 浮盈≥4×ATR → 锁利 (SL=价格-1.5×ATR, 更紧锁定利润)
    #   → 价格创新高 → SL自动跟进 → 每次必然变化 → 无10025无效调用

    def _trailing_stop_decision(self, pos, sym, direction, pip, atr, adx,
                                 floating, floating_pips, bias, bias_reason):
        """追踪止盈决策 (价格追踪式, 2026-08-29 修复).
        每轮重新计算 SL=价格±距离, 价格新高则收紧, 无固定值歧义.
        """
        # ── 阶段2: 浮盈≥4×ATR → 锁利 (最紧追踪) ──
        if floating >= 4.0 * atr:
            if direction == 'BUY':
                new_sl = pos.price_current - 1.5 * atr
            else:
                new_sl = pos.price_current + 1.5 * atr
            current_sl = pos.sl or (pos.price_open - (1 if direction=='BUY' else -1) * 100 * pip)
            # 仅收紧，不放宽
            if (direction == 'BUY' and new_sl > current_sl + 1e-9) or \
               (direction == 'SELL' and new_sl < current_sl - 1e-9):
                return Decision('TRAIL', pos.ticket, sym, direction,
                                f'浮盈 {floating_pips:.1f}pip ≥ 4×ATR, 锁利追踪(1.5×ATR)',
                                new_sl=new_sl, floating_pips=floating_pips,
                                bias=bias, bias_reason=bias_reason)

        # ── 阶段1: 浮盈≥2×ATR → 追踪 (宽松距离) ──
        if floating >= 2.0 * atr:
            if direction == 'BUY':
                new_sl = pos.price_current - 2.5 * atr
            else:
                new_sl = pos.price_current + 2.5 * atr
            current_sl = pos.sl or (pos.price_open - (1 if direction=='BUY' else -1) * 100 * pip)
            if (direction == 'BUY' and new_sl > current_sl + 1e-9) or \
               (direction == 'SELL' and new_sl < current_sl - 1e-9):
                return Decision('TRAIL', pos.ticket, sym, direction,
                                f'浮盈 {floating_pips:.1f}pip ≥ 2×ATR, 追踪止损(2.5×ATR)',
                                new_sl=new_sl, floating_pips=floating_pips,
                                bias=bias, bias_reason=bias_reason)

        # ── 阶段0: 浮盈≥1×ATR → 保本 (SL=开仓价, 仅收紧不回放) ──
        if floating >= 1.0 * atr:
            if direction == 'BUY':
                new_sl = pos.price_open
            else:
                new_sl = pos.price_open
            current_sl = pos.sl or 0
            # BUY: 新SL(开仓价) > 当前SL(更紧); SELL: 新SL(开仓价) < 当前SL(更紧)
            if (direction == 'BUY' and new_sl > current_sl + 1e-9) or \
               (direction == 'SELL' and new_sl < current_sl - 1e-9):
                return Decision('BREAKEVEN', pos.ticket, sym, direction,
                                f'浮盈 {floating_pips:.1f}pip ≥ 1×ATR, 保本损至开仓价',
                                new_sl=new_sl,
                                floating_pips=floating_pips, bias=bias,
                                bias_reason=bias_reason)

        return None  # 无需追踪 (浮盈不足)

    # ── 吊灯追踪止损 (V3, 朋友 Apex backtest 模型, XAUUSD PF 3~5) ──
    # [2026-09-02] 朋友 Apex 实盘=SL=entry(保本锁)+TP=0(趋势退出); backtest 用
    #   吊灯追踪模拟退出: 有利移动≥1.5×ATR 启动, 止损=近 L 根极值±2.5×ATR,
    #   仅收紧不回放。此处移植该模型到持仓监督, 让利润奔跑而非过早平仓。
    #   关键: 锁利下限=开仓价(永不回到保本线以下), 避免把赢单锁成亏单。
    def _chandelier_trailing(self, pos, sym, direction, pip, atr, floating,
                             floating_pips, bias, bias_reason,
                             close_a, high_a, low_a, ii):
        """吊灯追踪止损决策 (朋友 Apex 模型).

        激活: 有利移动 ≥ trail_activate_mult×ATR 才启动。
        止损: 近 trail_lookback 根极值 ± trail_atr_mult×ATR, 仅收紧不回放。
          SHORT: 极值=近L根最高, stop=极值+2.5×ATR(随跌下移)
          LONG:  极值=近L根最低, stop=极值-2.5×ATR(随涨上移)
        锁利下限: stop 永不跨过开仓价(保本线), 保证赢单至少平本。
        """
        if high_a is None or low_a is None or ii is None:
            return None
        if floating < self.trail_activate_mult * atr:
            return None  # 未达激活阈值
        L = int(self.trail_lookback)
        i = int(ii)
        lo = max(0, i - L + 1)
        if i - lo < 3:
            return None  # 历史不足, 不追踪
        if direction == 'SELL':
            ext = float(np.max(high_a[lo:i + 1]))
            raw = ext + self.trail_atr_mult * atr
            # 锁利下限=开仓价(永不高于 entry, 即不过保本线)
            trail_stop = min(pos.price_open, raw)
            cur = pos.sl if pos.sl else (pos.price_open + 100.0 * pip)
            if trail_stop < cur - 1e-9 and trail_stop > pos.price_current:
                return Decision('TRAIL', pos.ticket, sym, direction,
                                f'V3 吊灯追踪(空): 浮盈 {floating_pips:.1f}pip≥'
                                f'{self.trail_activate_mult}×ATR, stop={trail_stop:.5f}',
                                new_sl=trail_stop, floating_pips=floating_pips,
                                bias=bias, bias_reason=bias_reason)
        else:
            ext = float(np.min(low_a[lo:i + 1]))
            raw = ext - self.trail_atr_mult * atr
            # 锁利下限=开仓价(永不低于 entry)
            trail_stop = max(pos.price_open, raw)
            cur = pos.sl if pos.sl else (pos.price_open - 100.0 * pip)
            if trail_stop > cur + 1e-9 and trail_stop < pos.price_current:
                return Decision('TRAIL', pos.ticket, sym, direction,
                                f'V3 吊灯追踪(多): 浮盈 {floating_pips:.1f}pip≥'
                                f'{self.trail_activate_mult}×ATR, stop={trail_stop:.5f}',
                                new_sl=trail_stop, floating_pips=floating_pips,
                                bias=bias, bias_reason=bias_reason)
        return None

    # ── 一轮监督 ──────────────────────────────────────────────
    def supervise_once(self):
        if self.mt5 is None:
            self.connect()
        if self.mt5 is None:
            return []
        positions = self.mt5.positions_get() or []
        results = []
        for pos in positions:
            dec = self._evaluate(pos)
            executed = None
            if not self.dry_run and self.auto_confirm \
                    and ge.LIVE_TRADING_ENABLED:
                if dec.action == 'CLOSE':
                    executed = self.guardian.audit_and_close(pos.ticket)
                elif dec.action in ('BREAKEVEN', 'TRAIL'):
                    executed = self.guardian.audit_and_modify(
                        pos.ticket, new_sl=dec.new_sl)
            dec_dict = dec.to_dict()
            dec_dict['executed'] = executed
            dec_dict['dry_run'] = self.dry_run
            results.append(dec_dict)
        return results

    # ── 报告 ──────────────────────────────────────────────────
    def report(self, results):
        lines = []
        mode = 'DRY-RUN(仅报告)' if self.dry_run else 'LIVE(已执行)'
        lines.append(f"[监军司] 监督模式: {mode}  | 持仓数: {len(results)}")
        if not results:
            lines.append("  无持仓, 监军司待命。")
            return "\n".join(lines)
        for r in results:
            act = r['action']
            tag = {'HOLD': '持有', 'BREAKEVEN': '保本损',
                   'TRAIL': '追踪损', 'CLOSE': '平仓'}[act]
            line = (f"  [{tag}] {r['symbol']} {r['direction']} "
                    f"ticket {r['ticket']} | 浮盈 {r['floating_pips']:+.1f}pip "
                    f"| 行情 {r['bias']} ({r['bias_reason']})")
            lines.append(line)
            lines.append(f"        → 决策: {r['reason']}")
            if r.get('new_sl') is not None:
                lines.append(f"        → 新 SL: {r['new_sl']:.5f}")
            if not self.dry_run and r.get('executed'):
                ex = r['executed']
                if act == 'CLOSE':
                    lines.append(f"        → 执行: closed={ex.get('closed')} "
                                 f"deal={ex.get('close', {}).get('deal')} "
                                 f"retcode={ex.get('close', {}).get('retcode')}")
                else:
                    lines.append(f"        → 执行: modified={ex.get('modified')} "
                                 f"retcode={ex.get('modify', {}).get('retcode')}")
        return "\n".join(lines)
