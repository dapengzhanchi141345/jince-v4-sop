# guardian_executor.py — 金策宗师团 · 交易部 · 金刚卫 (guardian-executor)
"""
交易执行: 接 MT5 行情, 用进化出的最佳策略生成实时信号提案 (方向/手数/SL/TP),
并强制送审度司 (risk_auditor) 审计。

安全设计 (金策宗师团 v4.0 铁律):
  1. auto_confirm 默认 False  → 人工确认模式: 只产出提案+审计结论, 不调用 order_send
  2. 即便 auto_confirm=True, 也必须审度司 audit()==PASS 才允许下单
  3. LIVE_TRADING_ENABLED 硬开关默认 False → 即便以上全开, 也不真下单
     (要真下单必须显式将其置 True, 且仅在你明确授权"开实盘"时)

本模块是"执行手", 但永远被"风控脑" (审度司) 掐着咽喉。
"""
import math
import numpy as np
import continuous_evolution_v2 as ce
import symbol_universe as su
from risk_auditor import RiskAuditor
from trade_journal import TradeJournal, AdaptiveSizer

# ══ fail-closed 安全网关 (2026-10-20 P0: 把 config.SAFETY_LIMITS 变成真闸门) ══
# 之前 SAFETY_LIMITS 只在 config.py 里"备着"、无人消费 (workbuddy 诊断坐实的隐患):
# 一旦误开 LIVE_TRADING_ENABLED, 系统会拿着 config 的账号/服务器参数直接下单,
# 但终端若登录了别号/实盘, 代码层完全无感知。这里把它接成下单收敛点前的
# fail-closed 三道墙 (任一道不过 → 拒单, 读不到账户也拒单, 绝不放行):
#   1. 服务器名不含禁词 (Live/Real)   ← 可信锚点, 防连到实盘服务器
#   2. 实际账号 == config.login        ← 可信锚点, 防账号漂移 (终端登了A代码以为是B)
#   3. config.allow_live_trading 总闸  ← 纵深防御, LIVE_TRADING_ENABLED 之外的第二把人工锁
# 注: trade_mode 该券商 demo 也返回 0, 不 fail-closed 卡死, 只记录告警。
try:
    from config import SAFETY_LIMITS, MT5_CONFIG
except Exception:  # config 缺时兜底: 安全网关仍按最严拒绝, 不崩模块
    SAFETY_LIMITS = {"allow_live_trading": False, "expected_trade_mode": 1,
                     "deny_server_keywords": ("-Real", "-Live", "Live", "Real")}
    MT5_CONFIG = {"login": None, "server": ""}

# ══ P0-2 / P0-3 集成层 (2026-08-31 金策宗师团深度优化) ══
# 状态机路由(P0-2, 对冲 CPCV 暴露的 2024 regime 集中亏损) +
# 组合分数 Kelly / 风险平价(P0-3, 对冲 PBO=0.625 策略选择过拟合)。
# 默认关闭 (opt-in, 经环境变量 GSE_REGIME_ROUTER / GSE_PORTFOLIO_KELLY 开启),
# 灰度验证通过后再显式启用 → 不破现有 live 行为。无 sklearn/scipy 依赖。
try:
    from regime_router import (detect_regime, REGIME_PRIORITY,
                                select_strategies as _rr_select)
    from portfolio_alloc import (allocate as _pa_allocate,
                                 fractional_kelly as _pa_kelly)
    _HAVE_P0P1 = True
except Exception:
    _HAVE_P0P1 = False
    detect_regime = REGIME_PRIORITY = _rr_select = None
    _pa_allocate = _pa_kelly = None

# ══ 全局硬开关: 真实下单总闸 ══
# 即便 auto_confirm + audit PASS, 此开关为 False 也绝不调 order_send。
# 仅在用户明确授权"开实盘"时, 由人工将其置 True。
LIVE_TRADING_ENABLED = False

# ══ 本系统固定 magic number (P0-HIGH-3) ══
# 所有本系统开/平/改单统一打此 magic, 供 drift_monitor 按标签过滤本系统成交
# (避免账户里其它手动/其它 EA 的成交污染实盘漂移统计, 造成 RED 伪阳性)。
# 与 drift_monitor.SYSTEM_MAGIC 必须保持一致; 修改需同步两处。
SYSTEM_MAGIC = 20260708


def account_safety_gate(mt5_module):
    """
    fail-closed 账户安全网关 (2026-10-20 P0)。
    下单收敛点调用; 任一道墙不过 → (False, 原因), 绝不放行。
    读不到账户信息也 → (False, ...) (fail-closed, 不误连)。
      墙1 服务器名含禁词 (Live/Real)  → 拒 (防连到实盘服务器)
      墙2 实际 login != config.login   → 拒 (防账号漂移: 终端登了A代码以为是B)
      墙3 config.allow_live_trading 为 False → 拒 (纵深人工总闸, LIVE 开关之外的第二锁)
    注: trade_mode 该券商 demo 也返回 0, 不 fail-closed 卡死, 仅记录。
    """
    try:
        acct = mt5_module.account_info()
    except Exception as e:
        return False, f"safety_gate: 读账户异常({e}) fail-closed 拒单"
    if acct is None:
        return False, "safety_gate: 账户信息不可读 fail-closed 拒单"
    server = str(getattr(acct, "server", "") or "")
    login = getattr(acct, "login", None)
    # 墙1: 服务器禁词
    deny = tuple(SAFETY_LIMITS.get("deny_server_keywords", ("-Real", "-Live", "Live", "Real")))
    hit = [kw for kw in deny if kw.lower() in server.lower()]
    if hit:
        return False, f"safety_gate 墙1: 服务器 '{server}' 命中禁词 {hit} → 疑似实盘, 拒单"
    # 墙2: 账号漂移
    expect_login = MT5_CONFIG.get("login")
    if expect_login is not None and login != expect_login:
        return False, (f"safety_gate 墙2: 终端实际账号 {login} != config 期望 {expect_login} "
                       f"(账号漂移/登错终端) → 拒单")
    # 墙3: 实盘总闸
    if not SAFETY_LIMITS.get("allow_live_trading", False):
        return False, ("safety_gate 墙3: SAFETY_LIMITS.allow_live_trading=False "
                       "(实盘人工总闸未开) → 拒单")
    # trade_mode 记录 (不卡死)
    return True, (f"safety_gate PASS: server={server} login={login} "
                  f"trade_mode={getattr(acct, 'trade_mode', '?')} (demo 该券商可能=0, 仅记录)")

# ══ 硬止损美元上限 (A+B+C/C2, 2026-08-18) ══
# 单笔"最小手"对应的止损风险若超过此美元值, order_send 前直接拒单 ——
# 兜底防 USDSEK 类 -1395pip 极端宽 SL 爆亏. 即便 risk_lot 因 allow_min_lot 放行,
# 执行瞬间仍复查; 失败开放(缺字段不阻断). 仅作用于 live 真下单路径.
HARD_STOP_LOSS_USD_CAP = 250.0

# ══ 区间/均值回归模块参数 (P1-B, 震荡市专属通道) ══
# 仅在 market_scanner.RANGE_MODE_ENABLED=True 且检测到低波动区间时调用。
# [P2-A 进化] 2026-07-09 扫描优化(28组有效, 取稳健次优#3, 避过拟合top):
#   BB周期15 / 标准差1.5 / 止损缓冲0.8 — 三品种(XAU/EUR/GBP)全样本 PF>1.1
# [2026-07-11 稳健化] 原判决"非稳健"(触发率<1%)+ 跳过EDGE GATE裸做 fitness=0 品种。
#   修复: ① EDGE 守闸(RANGE_MIN_FITNESS, 镜像 market_scanner.MIN_EDGE_FITNESS=1.0)
#         仅放行有证明优势品种; ② 触发区从 0.2pip 死区放宽到 max(2pip, RANGE_ATR_FRAC×ATR),
#         且改为"K线极值触及/贴近 BB 边界 + 价格在对应半区"才反转(抓边界拒绝),
#         解决空转; ③ 仍守 RR≥2.0 / lot≤0.03 / 全链路 VETO.
RANGE_BB_PERIOD = 15          # Bollinger 周期 (扫描优化: 20→15, 更灵敏的通道)
RANGE_BB_STD = 1.5            # Bollinger 标准差倍数 (扫描优化: 2.0→1.5, 收窄通道增信号)
RANGE_KC_MULT = 1.5           # Keltner ATR 倍数
RANGE_SQUEEZE_THR = 0.9       # BB宽/KC宽 < 此值 = 波动率收缩成区间
RANGE_ENTRY_BUFFER_PIPS = 2.0 # 入场缓冲下限(pip): 与 RANGE_ATR_FRAC 取大 → 放宽触发区
RANGE_ATR_FRAC = 0.15         # 入场区 = max(2pip, 0.15×ATR): 抓 BB 边界拒绝, 告别 0.2pip 死区
RANGE_SL_BUFFER_PIPS = 0.8    # 止损超出区间边界多少 pip (边界外保护)
RANGE_RR_MIN = 2.0            # 区间提案最低盈亏比 (守双铁律)
RANGE_MAX_LOT = 0.03          # 区间单笔上限 (守双铁律)
RANGE_MIN_FITNESS = 1.0       # 区间 EDGE 守闸(镜像 market_scanner.MIN_EDGE_FITNESS):
                              #   fitness<此值(即 EUR/GBP/USDJPY 的 0) → 区间不裸做
# [2026-07-11 回测定案] tools/backtest_range_v2.py 多variant H1回测(6000bars):
#   纯 BB 边界反转(旧) PF 全<1.0(亏); 仅 B_SQUEEZE(波动率收缩后释放+边界触达)
#   在 GBPJPY PF=1.33(204笔) / XAU 1.02(347笔, 边际) 正期望, 且 RR=2.0 下仍稳。
#   决策: 仅白名单品种启用区间模块(控制爆炸半径), 其余趋势-only。GBPJPY 最稳健启用,
#   XAU(1.02 近平)暂关待更多数据。ETH/BTC PF<1 永不开。
# [2026-07-11 回退] 回测铁证(build_range_v3, RR=2.0 部署逻辑, H1 6000bars 样本外):
#   GBPJPY OOS PF=0.555(亏); 原文档 PF=1.33 系 TP=band-mid(RR≈9) 回测, 与 live 强制
#   RR=2.0 代码不匹配 → 验证依据失效. 5 品种 RR=2.0 下 PF 全<1(0.55~0.68, 低于
#   随机基线1.0) → B_SQUEEZE 在 H1 偏突破延续, 紧 RR 接不住. 清空白名单 = 区间模块
#   实际关闭, 待 TP 规则重构(band-mid) + 重 Walk-Forward 验证后再启用.
#   决策铁律: 不裸做 / 不亏钱优先于填空转.
RANGE_ALLOWLIST = set()


class GuardianExecutor:
    def __init__(self, auto_confirm=False, max_risk_per_trade=0.01,
                 max_daily_risk=0.03, max_lot_per_symbol=None):
        self.auto_confirm = auto_confirm
        self.auditor = RiskAuditor(
            max_risk_per_trade=max_risk_per_trade,
            max_daily_risk=max_daily_risk,
            max_lot_per_symbol=max_lot_per_symbol,
        )
        self.mt5 = None
        self._engine = None  # 延迟创建 BacktestEngine
        # 交易日志 + 自适应仓位 (吸收另一账号 trade_journal→自适应仓位设计)
        self.journal = TradeJournal()
        self.sizer = AdaptiveSizer(self.journal)
        # ── [2026-08-31 P0-2/P0-3] opt-in 开关 (默认关, 灰度验证后开) ──
        import os as _os
        self.use_regime_router = _os.getenv("GSE_REGIME_ROUTER", "0") == "1"
        self.use_portfolio_kelly = _os.getenv("GSE_PORTFOLIO_KELLY", "0") == "1"

    # ── 连接 ──────────────────────────────────────────────────
    def connect(self):
        if ce.ensure_mt5():
            import MetaTrader5 as mt5
            self.mt5 = mt5
            return True
        return False

    def _eng(self):
        if self._engine is None:
            self._engine = ce.BacktestEngine()
        return self._engine

    # ── [2026-08-31] P0-2 / P0-3 辅助层 (opt-in) ──────────────
    _RR_FAMILY_KEYS = ("TREND", "BO", "ICT", "DIV", "MR", "VP", "SDP")

    def _strategy_family(self, strategy):
        """从策略名提取 regime_router 家族键 (TREND/BO/ICT/DIV/MR/VP/SDP)。"""
        name = str(strategy.get("name", "") or "").upper()
        for k in self._RR_FAMILY_KEYS:
            if k in name:
                return k
        return "SDP"

    def _symbol_regime(self, st):
        """由行情快照估算 (vol_state, trend_state)。无数据/无库时回落中性。"""
        if not _HAVE_P0P1:
            return ("mid", "range")
        close = np.asarray(st.get("close"), dtype=float)
        r = np.diff(np.log(close))
        if len(r) < 25:
            return ("mid", "range")
        w = 20
        vol_series = np.array([np.std(r[max(0, i - w):i + 1])
                               for i in range(w - 1, len(r))])
        if len(vol_series) < 3:
            return ("mid", "range")
        vol_now = float(vol_series[-1])
        vol_hist = vol_series[:-1]
        return detect_regime(vol_now, vol_hist, st.get("adx_now", 0.0))

    def _regime_gate(self, symbol, st, strategy):
        """P0-2: 当前 regime 下该策略族被禁用(权重0) → 返回原因(拦截), 否则 None。"""
        vs, ts = self._symbol_regime(st)
        fam = self._strategy_family(strategy)
        pri = REGIME_PRIORITY.get((vs, ts), {})
        w = pri.get(fam, 1)
        if w <= 0:
            return (f"P0-2 状态机禁用: regime=({vs},{ts}) 族={fam} 权重=0 "
                    f"→ 跳过(对冲 regime 集中亏损)")
        return None

    def _portfolio_kelly_factor(self, strategy):
        """P0-3: 用分数 Kelly(0.5)把单笔风险预算按策略族 edge 缩放; 无统计则 1.0。"""
        if not _HAVE_P0P1:
            return 1.0
        fam = self._strategy_family(strategy)
        try:
            stats = self.journal.strategy_stats(fam)
            if stats and stats.get("win_rate") and stats.get("payoff_ratio"):
                k = _pa_kelly(float(stats["win_rate"]),
                              float(stats["payoff_ratio"]), 0.5)
                return float(min(max(k, 0.0), 1.0)) if k > 0 else 1.0
        except Exception:
            pass
        return 1.0

    # ── 行情快照 ──────────────────────────────────────────────
    def market_state(self, symbol):
        """拉最新行情, 算 ADX/ATR, 返回当前 bar 信号判断所需向量"""
        hist, spread = self._eng()._load_history(symbol)
        close, high, low = hist
        n = len(close)
        adx = ce._adx(high, low, close)
        atr = ce._atr(high, low, close)
        i = n - 1  # 最新 bar
        return {
            'symbol': symbol, 'close': close, 'high': high, 'low': low,
            'i': i, 'adx_now': adx[i], 'atr_now': atr[i], 'spread': spread,
            'last_close': float(close[i]),
        }

    # ── 信号生成 (不下单) ─────────────────────────────────────
    def build_signal(self, strategy, symbol, dl_pred=None, tc_bias=None):
        """
        用进化出的最佳策略, 对当前行情生成交易提案。
        复用 walk-forward 的同款入场逻辑 (ADX 门槛 + 方向 + 结构确认 + TC 过滤)。
        返回 (proposal | None, reason)
        """
        st = self.market_state(symbol)
        i = st['i']
        close, high, low = st['close'], st['high'], st['low']
        atr = ce._atr(high, low, close)
        p = strategy['params']

        # [2026-09-03 P0-B] 全局 EDGE 守闸: 任何策略(含 PASD/OTAS/趋势)凡
        #   fitness<阈值一律 SKIP, 堵住"fitness=0 经 PASD/OTAS 绕过门禁实盘交易"
        #   的护栏泄漏 (原仅 build_range_signal 有此闸, 主信号路径缺失 → 占 74% 成交量)。
        #   阈值镜像 RANGE_MIN_FITNESS=1.0 (market_scanner.MIN_EDGE_FITNESS)。
        if isinstance(strategy, dict) and 'fitness' in strategy:
            _fit = float(strategy.get('fitness') or 0)
            if _fit < RANGE_MIN_FITNESS:
                return None, (f'EDGE 守闸(P0-B): fitness={_fit:.2f}'
                              f'<{RANGE_MIN_FITNESS}, {strategy.get("name","?")} SKIP')

        # ── [2026-08-31 P0-2] 状态机路由闸 (opt-in, 默认关) ──
        if self.use_regime_router and _HAVE_P0P1:
            _rg = self._regime_gate(symbol, st, strategy)
            if _rg:
                return None, _rg

        # 1. ADX 趋势门槛
        if np.isnan(st['adx_now']) or st['adx_now'] < p['adx_min']:
            return None, f"ADX {st['adx_now']:.1f} < {p['adx_min']:.1f} (趋势不足)"
        # 2. Momentum 过滤 — P1-F 修复: 阈值必须跟随进化 adx_min, 严禁硬编码架空
        #    (同类 adx_offset bug: 原硬编码 <35 把进化选出的 25-35 盈利带重新否决,
        #     导致 XAU 在 ADX26-30 永远被 momentum 挡死, 零订单). 改为 < adx_min 即
        #     与 #1 一致; 进化已验证该带盈利则放行. 不破任何铁律/安全闸.
        if p.get('momentum_filter') and st['adx_now'] < p['adx_min']:
            return None, f"Momentum 过滤 (ADX<{p['adx_min']:.0f})"
        # 3. 方向 (DL/EMA)
        direction = self._eng()._direction(close, i, dl_pred)
        if direction is None:
            return None, "方向不明确 (DL SIDEWAYS / EMA 无排列)"
        # 4. 结构确认 (供需区 / 突破)
        if not ce._structure_confirm(close, high, low, i, atr):
            return None, "无结构确认 (非供需区/突破)"
        # 5. TC 共识过滤 (实时增强, 可选)
        if tc_bias and direction != tc_bias:
            return None, f"与 TC 共识 {tc_bias} 反向"

        # SL / TP (真实 ATR)
        sl_d = atr[i] * p['sl_multiplier']
        tp_d = atr[i] * p['tp_multiplier']
        entry = st['last_close']
        if direction == 'BUY':
            sl = entry - sl_d
            tp = entry + tp_d
        else:
            sl = entry + sl_d
            tp = entry - tp_d

        cfg = ce.SYMBOL_CONFIG[symbol]
        pip = cfg['pip']
        sl_pts = sl_d / pip
        tp_pts = tp_d / pip
        equity = self._equity()
        # 自适应仓位闸门: 近况期望为负且胜率过低 → 暂停开仓 (信号层不产单)
        pause, pause_reason = self.sizer.should_pause(symbol)
        if pause:
            return None, pause_reason
        # 风险预算: 策略期望与审度司硬上限取小, 确保不突破风控闸门
        # [2026-09-03 P0] 连亏 Tier1: 连亏≥tier1_n 时上限减半 (砍仓止血)
        risk_budget = min(p['risk_per_trade'], self.auditor.effective_max_rpt())
        # ── [2026-08-31 P0-3] 组合分数 Kelly 缩放 (opt-in, 默认关) ──
        if self.use_portfolio_kelly and _HAVE_P0P1:
            risk_budget = risk_budget * self._portfolio_kelly_factor(strategy)
        lot = self._position_size(equity, risk_budget, sl_pts,
                                  cfg['pip_usd_per_lot'], p['position_size'])
        # 自适应仓位乘数: 近况好→加仓(×1.3) / 差→砍仓(×0.5), 不破 cap
        lot_mult = self.sizer.lot_multiplier(symbol)
        lot = min(lot * lot_mult, p['position_size'])
        lot = max(0.01, math.floor(lot * 100) / 100)

        proposal = {
            'symbol': symbol,
            'direction': direction,
            'entry': round(entry, 5),
            'sl': round(sl, 5),
            'tp': round(tp, 5),
            'sl_pts': round(sl_pts, 2),
            'tp_pts': round(tp_pts, 2),
            'lot': lot,
            'pip_usd_per_lot': cfg['pip_usd_per_lot'],
            'spread': st['spread'],
            'strategy': strategy.get('name', 'unknown'),
            'adx': round(float(st['adx_now']), 1),
        }
        return proposal, '信号生成'

    # ── 区间/均值回归信号 (P1-B, 震荡市专属通道) ─────────────
    # 仅在 scan_symbol 的 ADX 硬禁处、RANGE_MODE_ENABLED=True 且检测到低波动
    # 区间(BB 收窄进入 KC)时调用。生成区间边界反转提案, 仍过全链路
    # RF/缠论/审度司VETO/双铁律。默认开关 False → 永不被调用, 零回归。
    def build_range_signal(self, symbol, strategy=None):
        # [2026-07-11 稳健化] 优化点:
        #   1) EDGE 守闸: 仅对"有证明优势"品种开区间通道 —— 直接堵住原
        #      "跳过EDGE GATE在 EUR/GBP/USDJPY/GBPJPY(fitness=0)裸做"的隐患.
        #   2) 触发率提升: 入场区从 0.2pip 死区放宽到 max(2pip, 0.15×ATR),
        #      且改为"本K线极值触及/贴近 BB 边界 + 价格在对应半区"才反转,
        #      抓住区间上下轨的拒绝(wick tag), 解决原 <1% 触发率空转.
        #   3) 仍守双铁律 (RR≥2.0 / lot≤0.03) 与全链路 VETO/RF/缠论 gate.
        #   4) per-symbol 白名单(RANGE_ALLOWLIST): 仅回测 PF≥1 的品种启用,
        #      控制爆炸半径(单品种试点, 不影响其余趋势-only).
        if symbol not in RANGE_ALLOWLIST:
            return None, (f'区间模块未对 {symbol} 开放 '
                          f'(白名单: {sorted(RANGE_ALLOWLIST)})')
        if isinstance(strategy, dict) and 'fitness' in strategy:
            _fit = float(strategy.get('fitness') or 0)
            if _fit < RANGE_MIN_FITNESS:
                return None, (f'区间: 无进化优势 '
                              f'(fitness={_fit:.2f}<{RANGE_MIN_FITNESS}), SKIP')
        st = self.market_state(symbol)
        i = st['i']
        close, high, low = st['close'], st['high'], st['low']
        atr = ce._atr(high, low, close)
        cfg = ce.SYMBOL_CONFIG[symbol]
        pip = cfg['pip']
        period = RANGE_BB_PERIOD
        if i < period + 5 or np.isnan(atr[i]):
            return None, "区间数据不足"
        # ── B_SQUEEZE 均值回归 (经回测验证 GBPJPY PF=1.33/204笔, RR=2.0 下稳) ──
        # 逻辑: 波动率收缩(BB宽/KC宽<0.9)后释放 + 价格贴近 BB 边界 → 边界拒绝反转。
        #   仅当近期出现 squeeze 才交易, 杜绝宽幅震荡裸做(原版 PF<1 主因)。
        ebuf = RANGE_ENTRY_BUFFER_PIPS * pip            # 入场缓冲 = 2pip (与回测一致)
        slbuf = RANGE_SL_BUFFER_PIPS * pip
        price = st['last_close']

        def _bbk(idx):
            w = close[idx - period + 1:idx + 1]
            m = float(np.mean(w)); s = float(np.std(w))
            bu = m + RANGE_BB_STD * s; bd = m - RANGE_BB_STD * s
            ka = float(np.mean(atr[idx - period + 1:idx + 1]))
            ku = m + RANGE_KC_MULT * ka; kd = m - RANGE_KC_MULT * ka
            return bu, bd, ku, kd

        def _sqz(bu, bd, ku, kd):
            bw = bu - bd; kw = ku - kd
            return kw > 0 and (bw / kw) < RANGE_SQUEEZE_THR

        bu_i, bd_i, ku_i, kd_i = _bbk(i)
        squeeze = (_sqz(*_bbk(i - 1)) or _sqz(*_bbk(i - 2)))
        near_lo = bd_i <= price <= bd_i + ebuf
        near_hi = bu_i - ebuf <= price <= bu_i
        if not squeeze:
            return None, "无波动率收缩(BB/KC squeeze), 区间不交易"
        if near_lo:
            direction = 'BUY'
            sl = bd_i - slbuf
            tp = price + 2.0 * (price - sl)          # RR=2.0 强制 (双铁律)
        elif near_hi:
            direction = 'SELL'
            sl = bu_i + slbuf
            tp = price - 2.0 * (sl - price)          # RR=2.0 强制
        else:
            return None, "价格未贴近区间边界 (非反转区)"
        sl_pts = abs(sl - price) / pip
        tp_pts = abs(tp - price) / pip
        # 双铁律 RR≥2.0 硬校验
        if tp_pts / sl_pts < RANGE_RR_MIN - 1e-6:
            return None, f"区间RR不足 ({tp_pts/sl_pts:.2f}<{RANGE_RR_MIN})"
        # 仓位 (复用趋势同款风险预算逻辑, 不破铁律)
        sp = (strategy.get('params', {}) if isinstance(strategy, dict) else {})
        equity = self._equity()
        rb = min(sp.get('risk_per_trade', 0.01), self.auditor.effective_max_rpt())
        lot = self._position_size(equity, rb, sl_pts, cfg['pip_usd_per_lot'],
                                  RANGE_MAX_LOT)
        lot_mult = self.sizer.lot_multiplier(symbol)
        lot = min(lot * lot_mult, RANGE_MAX_LOT)
        lot = max(0.01, math.floor(lot * 100) / 100)
        pause, pause_reason = self.sizer.should_pause(symbol)
        if pause:
            return None, f"区间信号质量门禁: {pause_reason}"
        proposal = {
            'symbol': symbol, 'direction': direction, 'entry': round(price, 5),
            'sl': round(sl, 5), 'tp': round(tp, 5), 'sl_pts': round(sl_pts, 2),
            'tp_pts': round(tp_pts, 2), 'lot': lot,
            'pip_usd_per_lot': cfg['pip_usd_per_lot'], 'spread': st['spread'],
            'strategy': (strategy.get('name', 'range')
                         if isinstance(strategy, dict) else 'range'),
            'adx': round(float(st['adx_now']), 1), 'range_mode': True,
            'range_squeeze': bool(squeeze),
            'range_bb_up': round(bb_up, 5), 'range_bb_dn': round(bb_dn, 5),
        }
        return proposal, '区间反转信号'

    # ── 实时方向研判 (持仓监督用, 不依赖入场门槛) ─────────────
    def live_bias(self, symbol, strategy, dl_pred=None, tc_bias=None):
        """
        返回当前方向性研判 'BUY' / 'SELL' / 'NEUTRAL' 及依据。
        与 build_signal 不同: 不要求结构确认通过才给方向,
        仅用 ADX 可读性 + DL/EMA 方向, 用于"持仓是否还顺应行情"。
        """
        st = self.market_state(symbol)
        i = st['i']
        close = st['close']
        adx = st['adx_now']
        p = strategy['params']
        direction = self._eng()._direction(close, i, dl_pred)
        if direction is None:
            return 'NEUTRAL', 'DL SIDEWAYS / EMA 无排列'
        if np.isnan(adx) or adx < p['adx_min']:
            return 'NEUTRAL', f'ADX {adx:.1f} < {p["adx_min"]:.1f} 趋势不可读'
        if tc_bias and direction != tc_bias:
            return 'NEUTRAL', f'与 TC 共识 {tc_bias} 反向, 不研判'
        return direction.upper(), f'ADX {adx:.1f} 方向 {direction}'

    # ── 审计 + 执行 ───────────────────────────────────────────
    def audit_and_execute(self, proposal):
        """
        审度司审计 → PASS 且 auto 才下单。
        返回 dict: {decision, reasons, proposal, equity, note?, order?}
        """
        if proposal is None:
            return {'decision': 'SKIP', 'reasons': ['无信号'],
                    'proposal': None, 'equity': self._equity()}
        equity = self._equity()
        # [2026-08-24 修复] 实时计算当前持仓 SL 风险总和 (供日累计动态判定,
        # 平仓即释放额度, 不再被历史开仓永久占用). 用 symbol_universe 真实
        # pip/pip_usd 精确估算各持仓风险.
        try:
            import symbol_universe as _su
            _open_risk = 0.0
            for _p in (self.mt5.positions_get() or []):
                _cfg = _su.UNIVERSE.get(_p.symbol) or {}
                _pip = float(_cfg.get('pip', 0.0001) or 0.0001)
                _pipusd = float(_cfg.get('pip_usd', 1.0) or 1.0)
                if _p.sl and _p.price_open:
                    _sl_pts = abs(_p.price_open - _p.sl) / _pip
                    _open_risk += _sl_pts * _p.volume * _pipusd / max(equity, 1.0)
            _open_risk = min(1.0, _open_risk)
        except Exception:
            _open_risk = None
        if _open_risk is not None:
            proposal = dict(proposal)
            proposal['_open_risk'] = _open_risk
        decision, reasons = self.auditor.audit(proposal, equity)

        # 同品种持仓防重硬闸 (资金安全): 避免 _cycle 的 existing 快照异常时
        # Netting 账户重复开仓累加手数。下单前实时查 MT5 持仓, 已有则 VETO。
        try:
            _existing_pos = self.mt5.positions_get(symbol=proposal['symbol'])
        except Exception:
            _existing_pos = None
        if _existing_pos:
            return {'decision': 'VETO',
                    'reasons': [f"已有 {proposal['symbol']} 持仓, 防重复开仓"],
                    'proposal': proposal, 'equity': equity,
                    'note': '未下单 (同品种持仓已存在)'}

        result = {
            'decision': decision,
            'reasons': reasons,
            'proposal': proposal,
            'equity': equity,
        }
        if decision == 'PASS' and self.auto_confirm and LIVE_TRADING_ENABLED:
            ok = self._send_order(proposal)
            result['order'] = ok
            if ok and ok.get('sent'):
                self.auditor.commit(proposal, equity)
                # 度支司记账: 每笔成交落盘, 供自适应仓位与绩效归因
                self.journal.log_fill(
                    symbol=proposal['symbol'],
                    direction=proposal['direction'],
                    lot=ok.get('volume', proposal['lot']),
                    price=ok.get('price'), sl=ok.get('sl'), tp=ok.get('tp'),
                    sl_pts=proposal['sl_pts'], tp_pts=proposal['tp_pts'],
                    adx=proposal.get('adx'), equity=equity,
                    strategy=proposal.get('strategy'),
                    ticket=ok.get('ticket'))
                result['note'] = '已下单 (auto + live)'
            else:
                result['note'] = '下单失败 (见 order 详情)'
        else:
            flags = []
            if decision != 'PASS':
                flags.append('审度司否决')
            if not self.auto_confirm:
                flags.append('人工确认模式')
            if not LIVE_TRADING_ENABLED:
                flags.append('LIVE_TRADING 关闭')
            result['note'] = '未下单 (' + ' / '.join(flags) + ')'
        return result

    # ── 账户 / 仓位 / 下单 ────────────────────────────────────
    def _equity(self):
        if self.mt5 is not None:
            try:
                acc = self.mt5.account_info()
                if acc:
                    return float(acc.equity)
            except Exception:
                pass
        return 10000.0  # 默认 demo 净值 (MT5 未连时)

    def healthy(self):
        """MT5 是否仍在线 (守护进程韧性, 供交易循环断线重连使用)。
        与 PositionSupervisor.healthy() 对称。"""
        if self.mt5 is None:
            return False
        try:
            return self.mt5.account_info() is not None
        except Exception:
            return False

    def _position_size(self, equity, risk_pct, sl_pts, pip_usd, cap):
        """Kelly 分数化保守仓位: 风险预算 / (止损点数 × 每点美元), 封顶 cap。
        向下取整到 0.01 手, 确保实际风险不向上偏出预算。"""
        if sl_pts <= 0 or pip_usd <= 0:
            return 0.01
        lot = (equity * risk_pct) / (sl_pts * pip_usd)
        lot = min(lot, cap)
        lot = max(0.01, math.floor(lot * 100) / 100)
        return lot

    def _send_order(self, proposal):
        """
        真实下单 (仅 auto + live 全开才调用)。
        锚定实时 tick 价格, 按 proposal 的 SL/TP 点数距离重置绝对价位,
        处理 broker 的 min/max 手数 / volume_step / stops_level / digits /
        filling_mode 约束。仍受审度司 VETO 上游控制 (此处只负责执行 PASS 提案)。
        """
        if not LIVE_TRADING_ENABLED:
            return {'sent': False, 'reason': 'LIVE_TRADING disabled'}
        if self.mt5 is None:
            return {'sent': False, 'reason': 'MT5 not connected'}
        mt5 = self.mt5
        # 客户端自动交易开关检测 (否则 order_send 必返 10027)
        try:
            ti = mt5.terminal_info()
            if ti is not None and not getattr(ti, 'trade_allowed', True):
                return {'sent': False,
                        'reason': 'MT5 客户端 AutoTrading 未开启 '
                                  '(terminal trade_allowed=False)'}
        except Exception:
            pass
        # fail-closed 账户安全网关 (2026-10-20 P0): 服务器禁词/账号漂移/实盘总闸 三道墙, 任一不过即拒单
        ok, gate_reason = account_safety_gate(mt5)
        if not ok:
            return {'sent': False, 'reason': gate_reason}
        sym = proposal['symbol']
        info = mt5.symbol_info(sym)
        tick = mt5.symbol_info_tick(sym)
        if info is None or tick is None:
            return {'sent': False, 'reason': f'symbol/tick unavailable: {sym}'}
        # 确保品种在市场观察中可用 (否则某些 broker 拒单)
        try:
            mt5.symbol_select(sym, True)
        except Exception:
            pass

        # 执行端点差摩擦护栏 (双保险, 吸收 Supreme_EA 坑#4: 改基准后护栏被绕过)
        #   与 scanner 预检配合: 即便 scanner 放行, 执行瞬间点差跳变/异常也拦截.
        #   失败开放: atr 缺失(proposal 未带) 或 异常 → 不阻断下单.
        if ce.SPREAD_GUARD_ENABLED:
            try:
                _atr_v = float(proposal.get('atr') or 0.0)
                _ok, _sinfo = ce.spread_friction_ok(sym, _atr_v)
                if not _ok:
                    return {'sent': False, 'reason': _sinfo}
            except Exception:
                pass

        direction = proposal['direction']
        # pip 取自 canonical 规格 symbol_universe.UNIVERSE (覆盖全部 65 品种);
        # 旧 ce.SYMBOL_CONFIG 仅含 7 个 legacy 品种, 桥接盘(NZDUSD/EURNZD/...)
        # 会 KeyError 导致整轮 abort。主源 UNIVERSE, 回退 legacy 配置(双保险)。
        _spec = su.UNIVERSE.get(sym) or {}
        pip = _spec.get('pip') or ce.SYMBOL_CONFIG.get(sym, {}).get('pip')
        if not pip or pip <= 0:
            return {'sent': False, 'reason': f'无法解析 {sym} 点值(pip), 跳过下单'}
        sl_pts = proposal['sl_pts']
        tp_pts = proposal['tp_pts']

        # [2026-08-18 C2] 硬止损$上限: 最小手对应止损风险超上限直接拒单(防爆亏).
        #   pip_usd 取自 proposal(趋势/桥接提案均带), 与 risk_lot 同口径; 失败开放.
        try:
            _pip_usd = float(proposal.get('pip_usd_per_lot') or 0.0)
            _min_lot = float(getattr(info, 'volume_min', 0.01) or 0.01)
            if _pip_usd > 0:
                _sl_risk_min = sl_pts * _pip_usd * _min_lot
                if _sl_risk_min > HARD_STOP_LOSS_USD_CAP:
                    return {'sent': False,
                            'reason': (f'硬止损$上限拦截: 最小手SL风险${_sl_risk_min:.2f}'
                                       f'>{HARD_STOP_LOSS_USD_CAP:.0f} (防爆亏)')}
        except Exception:
            pass
        digits = info.digits
        point = info.point

        # 锚定实时成交价 (BUY 用 ask / SELL 用 bid), 重新计算 SL/TP 绝对价位
        if direction == 'BUY':
            price = tick.ask
            order_type = mt5.ORDER_TYPE_BUY
            sl = price - sl_pts * pip
            tp = price + tp_pts * pip
        else:
            price = tick.bid
            order_type = mt5.ORDER_TYPE_SELL
            sl = price + sl_pts * pip
            tp = price - tp_pts * pip

        # 手数约束: 夹在 [volume_min, volume_max], 按 volume_step 对齐
        lot = max(info.volume_min, min(proposal['lot'], info.volume_max))
        if info.volume_step and info.volume_step > 0:
            lot = math.floor(lot / info.volume_step) * info.volume_step
        lot = round(lot, 2)
        if lot <= 0:
            return {'sent': False, 'reason': 'lot<=0 after clamp'}

        # SL/TP 最小距离 (trade_stops_level, 单位=point; getattr 兜底版本差异)
        sl = round(sl, digits)
        tp = round(tp, digits)
        _slvl = getattr(info, 'trade_stops_level', 0) or 0
        min_stop = _slvl * point if _slvl > 0 else 0
        if min_stop > 0:
            if direction == 'BUY':
                if price - sl < min_stop:
                    sl = round(price - min_stop, digits)
                if tp - price < min_stop:
                    tp = round(price + min_stop, digits)
            else:
                if sl - price < min_stop:
                    sl = round(price + min_stop, digits)
                if price - tp < min_stop:
                    tp = round(price - min_stop, digits)

        # filling mode 自适应: 默认 IOC (本 broker TradeMaxGlobal 实测可用);
        # 仅当 broker 明确支持 FOK 时才改用 FOK。
        # 注: 部分 broker filling_mode 虽报告支持 RETURN, 但 order_send 实际拒 RETURN
        # (retcode=10030 Unsupported filling mode), 故不启用 RETURN 分支。
        filling = mt5.ORDER_FILLING_IOC
        if info.filling_mode & mt5.ORDER_FILLING_FOK:
            filling = mt5.ORDER_FILLING_FOK

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": sym,
            "volume": float(lot),
            "type": order_type,
            "price": float(price),
            "sl": float(sl),
            "tp": float(tp),
            "deviation": 20,
            "magic": SYSTEM_MAGIC,
            # [2026-08-21 优化] comment 携带策略名 → edge_tracker 策略级统计
            # 才能提取到策略名, 策略级 D5 门控才有数据可判 (此前 235/265 笔
            # 成交都是裸 "A.T.E.S07", strategies 统计恒为 0, D5 形同虚设).
            "comment": f"A.T.E.S07.{proposal.get('strategy', 'X')}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }
        result = mt5.order_send(request)
        if result is None:
            return {'sent': False, 'reason': 'order_send returned None',
                    'retcode': None}
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            req = result.request
            return {
                'sent': True,
                'ticket': result.order,
                'retcode': int(result.retcode),
                'price': float(result.price),
                'volume': float(result.volume),
                'sl': float(req.sl) if req is not None else sl,
                'tp': float(req.tp) if req is not None else tp,
            }
        return {
            'sent': False,
            'reason': f'retcode={result.retcode}',
            'retcode': int(result.retcode),
            'comment': str(getattr(result, 'comment', '')),
        }

    # ── 平仓 (按 ticket 反向 DEAL) ─────────────────────────────
    def close_position(self, ticket):
        """
        按 ticket 平仓 (仅 auto + live 全开才真执行)。
        读取持仓 → 反向 DEAL 平仓 → 返回结果 dict。
        平仓只释放风险, 不新增, 故不经单笔/日累计风险占用判断。
        """
        if not LIVE_TRADING_ENABLED:
            return {'closed': False, 'reason': 'LIVE_TRADING disabled'}
        if self.mt5 is None:
            return {'closed': False, 'reason': 'MT5 not connected'}
        mt5 = self.mt5
        # 客户端自动交易开关检测 (否则 order_send 必返 10027)
        try:
            ti = mt5.terminal_info()
            if ti is not None and not getattr(ti, 'trade_allowed', True):
                return {'closed': False,
                        'reason': 'MT5 客户端 AutoTrading 未开启 '
                                  '(terminal trade_allowed=False)'}
        except Exception:
            pass
        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            return {'closed': False, 'reason': f'未找到持仓 ticket={ticket}'}
        p = pos[0]
        sym = p.symbol
        vol = p.volume
        tick = mt5.symbol_info_tick(sym)
        info = mt5.symbol_info(sym)
        if tick is None or info is None:
            return {'closed': False, 'reason': f'symbol/tick unavailable: {sym}'}
        try:
            mt5.symbol_select(sym, True)
        except Exception:
            pass
        if p.type == mt5.POSITION_TYPE_BUY:
            ctype = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            ctype = mt5.ORDER_TYPE_BUY
            price = tick.ask
        # filling: 默认 IOC (本 broker 实测可用), 仅支持 FOK 才用 FOK
        filling = mt5.ORDER_FILLING_IOC
        if info.filling_mode & mt5.ORDER_FILLING_FOK:
            filling = mt5.ORDER_FILLING_FOK
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": sym,
            "volume": float(vol),
            "type": ctype,
            "position": int(ticket),
            "price": float(price),
            "deviation": 20,
            "magic": SYSTEM_MAGIC,
            "comment": "A.T.E.S07.Close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }
        result = mt5.order_send(request)
        if result is None:
            return {'closed': False, 'reason': 'order_send returned None',
                    'retcode': None}
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            return {
                'closed': True,
                'ticket': int(ticket),
                'deal': result.order,
                'retcode': int(result.retcode),
                'price': float(result.price),
                'volume': float(result.volume),
                'symbol': sym,
            }
        return {
            'closed': False,
            'reason': f'retcode={result.retcode}',
            'retcode': int(result.retcode),
            'comment': str(getattr(result, 'comment', '')),
        }

    # ── 平仓盈亏查询 (度支司记账用) ───────────────────────────
    def _close_profit(self, ticket, deal=None):
        """查该持仓平仓后的实现盈亏 (从成交历史聚合)。失败返回 None。"""
        try:
            if self.mt5 is None:
                return None
            deals = self.mt5.history_deals_get(position=ticket)
            if deals:
                return float(sum(float(d.profit) for d in deals))
        except Exception:
            pass
        return None

    # ── 平仓: 审计 + 执行 ─────────────────────────────────────
    def audit_and_close(self, ticket):
        """
        审度司审计平仓 → PASS 才执行。返回 dict。
        """
        if self.mt5 is None:
            self.connect()
        if self.mt5 is None:
            return {'decision': 'SKIP', 'reasons': ['MT5 未连接'],
                    'closed': False}
        pos = self.mt5.positions_get(ticket=ticket)
        if not pos:
            return {'decision': 'SKIP', 'reasons': [f'未找到持仓 {ticket}'],
                    'closed': False}
        p = pos[0]
        decision, reasons = self.auditor.audit_close(p.symbol, p.volume)
        result = {
            'decision': decision,
            'reasons': reasons,
            'symbol': p.symbol,
            'volume': p.volume,
            'ticket': int(ticket),
        }
        if decision == 'PASS' and self.auto_confirm and LIVE_TRADING_ENABLED:
            bal_b = self._equity()
            ok = self.close_position(ticket)
            bal_a = self._equity()
            result['close'] = ok
            result['closed'] = bool(ok and ok.get('closed'))
            if result['closed']:
                # 度支司记账: 平仓盈亏落盘, 供自适应仓位与绩效归因
                profit = self._close_profit(ticket, ok.get('deal'))
                self.journal.log_close(
                    symbol=p.symbol,
                    direction=('BUY' if p.type == self.mt5.POSITION_TYPE_BUY
                               else 'SELL'),
                    profit=profit, reason='supervisor/risk-close',
                    ticket=int(ticket),
                    balance_before=bal_b, balance_after=bal_a)
                # [2026-09-03 P0] 连亏 kill-switch: 登记平仓盈亏 → 更新连亏/滚动期望
                self.auditor.register_close(profit)
                result['note'] = '已平仓 (auto + live)'
            else:
                result['note'] = '平仓失败'
        else:
            flags = []
            if decision != 'PASS':
                flags.append('审度司否决')
            if not self.auto_confirm:
                flags.append('人工确认模式')
            if not LIVE_TRADING_ENABLED:
                flags.append('LIVE_TRADING 关闭')
            result['note'] = '未平仓 (' + ' / '.join(flags) + ')'
            result['closed'] = False
        return result

    # ── 修改持仓 SL/TP ───────────────────────────────────────
    def modify_position(self, ticket, sl=None, tp=None):
        """
        修改持仓的 SL/TP (仅 auto + live 全开才真执行)。
        sl/tp 为绝对价位 (float) 或 None 表示不改。
        注意: 本方法只负责执行"已通过审度司 audit_modify 的收紧类修改",
        调用方必须先经审度司审计, 禁止放松 SL。
        """
        if not LIVE_TRADING_ENABLED:
            return {'modified': False, 'reason': 'LIVE_TRADING disabled'}
        if self.mt5 is None:
            return {'modified': False, 'reason': 'MT5 not connected'}
        mt5 = self.mt5
        try:
            ti = mt5.terminal_info()
            if ti is not None and not getattr(ti, 'trade_allowed', True):
                return {'modified': False,
                        'reason': 'MT5 客户端 AutoTrading 未开启 '
                                  '(terminal trade_allowed=False)'}
        except Exception:
            pass
        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            return {'modified': False, 'reason': f'未找到持仓 ticket={ticket}'}
        p = pos[0]
        sym = p.symbol
        info = mt5.symbol_info(sym)
        if info is None:
            return {'modified': False, 'reason': f'symbol unavailable: {sym}'}
        digits = info.digits
        new_sl = float(sl) if sl is not None else float(p.sl)
        new_tp = float(tp) if tp is not None else float(p.tp)
        # stops_level 最小距离夹紧
        _slvl = getattr(info, 'trade_stops_level', 0) or 0
        min_stop = _slvl * info.point if _slvl > 0 else 0
        tick = mt5.symbol_info_tick(sym)
        if tick is not None and min_stop > 0:
            if p.type == mt5.POSITION_TYPE_BUY:
                # 多单: SL 必须低于 bid, TP 必须高于 ask
                if new_sl > 0 and tick.bid - new_sl < min_stop:
                    new_sl = round(tick.bid - min_stop, digits)
                if new_tp > 0 and new_tp - tick.ask < min_stop:
                    new_tp = round(tick.ask + min_stop, digits)
            else:
                if new_sl > 0 and new_sl - tick.ask < min_stop:
                    new_sl = round(tick.ask + min_stop, digits)
                if new_tp > 0 and tick.bid - new_tp < min_stop:
                    new_tp = round(tick.bid - min_stop, digits)
        new_sl = round(new_sl, digits)
        new_tp = round(new_tp, digits)
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": sym,
            "position": int(ticket),
            "sl": new_sl,
            "tp": new_tp,
            "deviation": 20,
        }
        result = mt5.order_send(request)
        if result is None:
            return {'modified': False, 'reason': 'order_send returned None',
                    'retcode': None}
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            return {
                'modified': True,
                'ticket': int(ticket),
                'retcode': int(result.retcode),
                'sl': new_sl,
                'tp': new_tp,
                'symbol': sym,
            }
        return {
            'modified': False,
            'reason': f'retcode={result.retcode}',
            'retcode': int(result.retcode),
            'comment': str(getattr(result, 'comment', '')),
        }

    # ── SL/TP 修改: 审计 + 执行 ───────────────────────────────
    def audit_and_modify(self, ticket, new_sl=None, new_tp=None):
        """
        审度司审计 SL 修改 → 仅"收紧/持平"才 PASS → 执行 modify_position。
        返回 dict。
        """
        if self.mt5 is None:
            self.connect()
        if self.mt5 is None:
            return {'decision': 'SKIP', 'reasons': ['MT5 未连接']}
        pos = self.mt5.positions_get(ticket=ticket)
        if not pos:
            return {'decision': 'SKIP',
                    'reasons': [f'未找到持仓 {ticket}']}
        p = pos[0]
        equity = self._equity()
        decision, reasons = self.auditor.audit_modify(
            symbol=p.symbol, old_sl=float(p.sl), new_sl=float(new_sl)
            if new_sl is not None else float(p.sl),
            entry=float(p.price_open),
            direction=('BUY' if p.type == self.mt5.POSITION_TYPE_BUY
                       else 'SELL'),
            equity=equity,
        )
        result = {
            'decision': decision,
            'reasons': reasons,
            'ticket': int(ticket),
            'symbol': p.symbol,
        }
        if decision == 'PASS' and self.auto_confirm and LIVE_TRADING_ENABLED:
            ok = self.modify_position(ticket, sl=new_sl, tp=new_tp)
            result['modify'] = ok
            result['modified'] = bool(ok and ok.get('modified'))
            result['note'] = ('已修改 SL/TP (auto + live)'
                              if result['modified'] else '修改失败')
        else:
            flags = []
            if decision != 'PASS':
                flags.append('审度司否决')
            if not self.auto_confirm:
                flags.append('人工确认模式')
            if not LIVE_TRADING_ENABLED:
                flags.append('LIVE_TRADING 关闭')
            result['note'] = '未修改 (' + ' / '.join(flags) + ')'
            result['modified'] = False
        return result
