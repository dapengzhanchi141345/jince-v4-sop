# market_scanner.py — 金策宗师团 · 交易部 · 猎场司 (market-hunter)
"""
自动扫盘开仓器 (猎场司):
  扫描全部配置品种的多周期行情 (H1 入场 + W1/D1/H4 趋势背景 + 15M 精准层),
  生成经多层过滤的入场提案。

升级点 (吸收另一账号 "多周期冲突跳过" + SDP 多周期共振理念 + 用户多周期体系):
  - 多周期共振 (P1+P2+P3): W1 战略牛熊锁(反向硬拒) + D1/H4 分层加权评分 +
    15M 精准入场确认与缩止损提盈亏比; 由二元 SKIP 升级为分层评分(顺向加分/
    逆势扣分/W1硬拒/评分越高仓位越满, 仅缩小不放大, 守双铁律).
  - ADX 趋势门槛 / 结构确认 / 自适应暂停闸门: 由 GuardianExecutor.build_signal 负责
  - 最终下单仍须 audit_and_execute → 审度司 VETO + LIVE 硬开关
  - 进化优势门禁 (EDGE GATE, 默认开): 逐品种 walk-forward 后, 仅放行
    best_fitness≥MIN_EDGE_FITNESS 且回测 pf≥MIN_BASELINE_PF 的品种;
    无优势/负优势品种一律 SKIP(承认模型非全品种通吃, 不在裸做品种上交易).

注意: 本模块只"生产提案", 不下单。下单由 run_trader / GuardianExecutor 完成。
"""
import math
import numpy as np
import continuous_evolution_v2 as ce
from guardian_executor import GuardianExecutor
import chanlun_analyzer as cl     # 缠论结构几何层 (P0+P1: 形态学+背驰+买卖点)
import regime_detector as rd      # 研策师 Regime 检测层 (HMM + 简化状态机 fallback)
import symbol_universe as su     # 全品种宇宙 + DATA_COLLECTION_MODE 收集模式开关

# MT5 周期常量 (与 ENUM_TIMEFRAMES 一致)
TF = {'M15': 15, 'M30': 30, 'H1': 16385, 'H4': 16388, 'D1': 16408, 'W1': 16416}
ENTRY_TF = 'H1'
# P1: 多周期共振层级升为战略锁 — W1(周线)战略牛熊最高权威 + D1(日线)定大方向 + H4(四小时)趋势背景
CTX_TFS = ['W1', 'D1', 'H4']     # 趋势背景周期(与入场 H1 共振); W1 反向→硬拒
HIST_N = 400
_TREND_BAND = 0.001            # 趋势显著性容差 (EMA21-EMA200 分离度 / 价格 ≥ 0.1% 才算有趋势)
ADX_HARD_FLOOR = 20             # 趋势通道全局硬底(历史安全经验锚点); 实际由
                              # evolved adx_min(>=38) 把守, 本常量仅作语义保留
RANGE_ADX_CEIL = 35             # 区间/均值回归模块覆盖带上限 (P2-A2 拓宽):
                              # 从原 ADX<20 拓宽到 ADX<35, 填补 20<ADX<35 死亡
                              # 真空带. 回测(moderate ADX<35)证: XAU PF1.219/379笔,
                              # ETH PF1.069/547笔, 无品种 PF<1.0 → 安全.

# ── 多周期共振分层评分 (P1 战略锁 + P3 评分化) ──
#   P1: W1 为最高权威, 与入场方向反向 → 强 SKIP(比 H4/D1 更硬)
#   P3: 把"二元SKIP"升级为分层加权评分 — W1/H4/D1/H1/M15 各赋方向权重,
#       顺向累积加分、逆势分级扣分; 总分 ≥ MTF_SCORE_THRESHOLD 才允许开仓;
#       评分越高 → 在双铁律(仓位≤0.03)内微调放大仓位(仅放大到 cap, 不破铁律)
_MTF_WEIGHTS = {'W1': 3, 'D1': 2, 'H4': 2, 'H1': 2, 'M15': 1}  # 日内波段: 强化 H4/H1 摆动结构权重(需H4/H1共振才达阈值)
MTF_SCORE_THRESHOLD = 3        # 分层评分阈值(总分), 低于则 SKIP
# 15M 精准入场层 (P2): H1 出信号后, 用 15M 做"入场确认 + 缩止损提盈亏比"
#   15M 顺向且出现拐点/破位才真正进场; 止损从 H1 ATR 级缩到 15M 结构级(仍守 RR≥2)
M15_CONFIRM_REQUIRED = True    # M15 出现明确反向趋势 → SKIP(噪音过滤); 中性/同向 → 放行
M15_SL_TIGHT_MULT   = 2.0      # 缩止损 = 15M ATR × 该倍数(结构级止损, 比H1 ATR更紧, 日内波段取向)
M15_RR_MIN          = 2.0      # 缩止损后最低盈亏比(守双铁律 RR≥2.0 不可破)

# 进化优势门禁 (EDGE GATE, 默认开启)
#   问题背景: 逐品种 walk-forward 进化后, 部分品种(如 EURUSD/GBPUSD/USDJPY)
#   始终找不到正期望策略 (best_fitness≈0, 回测 pf<1), 其 params 仅是进化没动过
#   的随机种子值. 若仍放行交易, 等于在"无优势/负优势"品种上裸做 —— 正是
#   最初"镑美亏大钱"的 misfit 根源. 此门禁只放行"有证明优势"的品种, 其余 SKIP.
#   与 ADX硬禁/审度司VETO 同级的安全闸, 默认开启不可绕.
# [P2-A 止血修复 2026-07-09] 重新启用 EDGE 门禁 (修掉 null-baseline 误杀 bug 后):
#   原 07-08 因 "(_bl.get('pf') or 0) < 1.0" 对 baseline=null 的品种(如 XAU)误杀而关掉;
#   现改为 null-safe (baseline 缺失不拦), 仅拦 fitness<1.0(无优势) 或 baseline.pf<1.0(真负优势).
#   数据说话: 近3日 EUR/GBP/USDJPY/GBPJPY 无优势品种净亏 -$8.50, 门禁恢复可止血且不误伤有edge品种.
EDGE_GATE_ENABLED   = True    # 仅放行"有证明优势"品种 (fitness≥1.0 且 baseline.pf≥1.0 或缺失); 修复 null-baseline 陷阱后安全启用

# 区间/均值回归模块开关 (P1-B, 震荡市专属通道)
#   False (默认) → 扫描行为与改动前 100% 一致 (ADX<20 硬禁 SKIP, 零回归).
#   True  → H1 ADX<RANGE_ADX_CEIL(35) 时走区间反转分支
#           (guardian.build_range_signal), 生成提案后跳过趋势专属的 EDGE GATE
#           + build_signal, 但仍过 RF 门禁/缠论gate/审度司VETO/双铁律.
#           覆盖带已从原 ADX<20 拓宽到 ADX<35, 填补 20<ADX<35 死亡真空带
#           (趋势通道 adx_min>=38 本就不点火). 这是给中等/低波动区开专属低风险
#           通道 (紧止损+RR≥2.0), 不破铁律精神. 回测证安全(见 RANGE_ADX_CEIL).
RANGE_MODE_ENABLED = True   # [2026-07-11 重启用] B_SQUEEZE 区间模块经 tools/backtest_range_v2.py
                           # 回测证 PF≥1 (GBPJPY PF=1.33/204笔最稳); guardian_executor 内
                           # 仅 RANGE_ALLOWLIST={GBPJPY} 启用, 其余品种趋势-only.
MIN_EDGE_FITNESS    = 1.0       # 品种自身 best_fitness 下限(XAUUSD40/BTC12/ETH24过; 无优势0/0.65不过)
MIN_BASELINE_PF     = 1.0       # 回测 pf 下限(pf<1=负期望, 即使fitness凑够也拒)

# P2 中枢动态止损覆盖开关 (默认关闭)
#   True  → 猎场司在 1.5 缠论 gate 通过后, 用中枢 ZG/ZD 生成的结构性 SL
#           覆盖 build_signal 的 ATR SL (保持原 RR 重算 TP)。更贴合缠论结构,
#           但中枢在小周期可能频繁变化 → 默认不启用, 仅 DRY-RUN 验证后由 CIO 拍板。
#   False → 仅把中枢信息写入 proposal['chanlun'] 供复盘/监军司参考, 不覆盖开仓 SL。
CHANLUN_SL_OVERRIDE = False

# RF 质量增强门禁开关 (默认关闭)
#   True  → 猎场司在 1.5 缠论 gate 之前(信号方向已知后)调用 RFAlpha.score()
#           评估该方向未来 N 根概率, 若 < RF_GATE_THRESHOLD 则 SKIP。
#           仅增强 signal_quality, 不替代 should_pause / ADX<20 硬禁 /
#           缠论 gate / 审度司 VETO; 永远在 VETO 下游。
#   False → 不启用(默认), RF 永不参与决策链 (与 CHANLUN_SL_OVERRIDE 同模式)。
RF_QUALITY_GATE = False
RF_GATE_THRESHOLD = 0.5          # 历史基准 (P1-C 前, 有 edge 品种用)
RF_GATE_THRESHOLD_EDGE = 0.65    # P1-C: 有 edge 品种提升门槛 (证据: XAU pf1.06→1.424, BTC0.955→1.523, 笔数仍≥300充足)

# ── Regime 检测层 (HMM / 简化状态机 fallback) — 研策师自进化 v4.0 升级项 ──
#   识别 H1 市场状态 {trend, range, volatile}, 与现有 Walk-Forward + WFER
#   退化检测互补(不替代、不破铁律).
#   REGIME_ADAPTIVE=False (默认) = 整层不执行 → 扫描行为与改动前 100% 一致 (零回归).
#
#   优化1 (深度整体优化, CIO 已授权): REGIME_ADAPTIVE=True 时进入"第二阶段" —
#   检测 regime 并经 REGIME_SWITCH_COOLDOWN 防抖后, 用 REGIME_PRESETS 覆盖
#   扫描参数(adx_min/sl_mult/tp_mult/position_size), 在 ADX硬禁 之后、RF gate
#   之前应用; 切参后仍走全链路(VETO/双铁律/ADX硬禁/缠论gate/多周期共振 不可绕过).
#   默认 False → 零影响. 绝不破三安全闸.
REGIME_ADAPTIVE = True

# Regime → 参数预设 (仅数据结构; REGIME_ADAPTIVE=True 时才套用).
#   优化: 由"绝对 adx_min/sl/tp"改为**相对偏移** (P0-HIGH-1 修复审计事实#1):
#     - adx_offset 是相对进化选出 adx_min 的偏移量 (非绝对覆盖),
#       应用后 effective_adx = clamp(evolved_adx_min + offset, 20, 60)
#       (下限 20 保 ADX 地板精神; 上限 60 防极端).
#     - sl_mult / tp_mult 为绝对倍率, 直接覆盖 sl_multiplier / tp_multiplier;
#       三档预设均为 RR=2.0 (trend 2.5/5.0, range 1.5/3.0, volatile 4.0/8.0),
#       应用后**立即重过双铁律** _ensure_rr (RR>=2 不可破) 与 _ensure_risk_cap
#       (仓位<=0.03 且缩仓后夹 [0.01,0.03]).
#   切参不得破坏: 三安全闸(VETO 单笔≤1%/日≤3%) / ADX硬禁(<20) / 双铁律(RR≥2+仓位≤0.03).
REGIME_PRESETS = {
    'trend':    {'adx_offset': -8, 'sl_mult': 2.5, 'tp_mult': 5.0},
    'range':    {'adx_offset': 0,  'sl_mult': 1.5, 'tp_mult': 3.0},
    'volatile': {'adx_offset': +8, 'sl_mult': 4.0, 'tp_mult': 8.0},
}

# Regime 切换冷却 (单位: H1 根): regime 需连续稳定 N 根才真正切换, 防抖动.
#   默认 6 根 (≈ 一个交易日内 H1 扫描周期量). 仅 REGIME_ADAPTIVE=True 时生效.
REGIME_SWITCH_COOLDOWN = 6

# ── 信号质量动态化 (优化2, 默认关闭) ──
#   RF 质量门禁阈值由固定 0.5 改为随 Regime 动态调节:
#   trend 放宽(更易过)、volatile 收紧(更难过). 仅 DYNAMIC_SIGNAL_THRESHOLD=True
#   且 REGIME_ADAPTIVE=True(已知 regime) 时生效. 默认 False → 沿用 RF_GATE_THRESHOLD.
#   不破 ADX硬禁 / VETO / 双铁律.
DYNAMIC_SIGNAL_THRESHOLD = True
REGIME_GATE_THRESHOLD = {'trend': 0.45, 'range': 0.50, 'volatile': 0.50}

# ── 组合相关性风控 (优化2, 审度司, 默认关闭) ──
#   PORTFOLIO_CORR_CHECK=True 时, 对新提案做"同组同方向持仓"相关性评估:
#   默认仅记录(portfolio_corr)不拦截; 仅当 PORTFOLIO_CORR_ENFORCE=True 才拒开.
#   日累计风险强化日志一并输出. 默认 False → 零影响、不破任何铁律.
PORTFOLIO_CORR_CHECK = True
PORTFOLIO_CORR_ENFORCE = True

_BASE_PX = {'XAUUSD': 4000, 'BTCUSD': 58000, 'ETHUSD': 1600,
            'EURUSD': 1.14, 'GBPUSD': 1.32, 'USDJPY': 162, 'GBPJPY': 215}


def _ensure_mt5():
    if ce.ensure_mt5():
        return ce._MT5_OBJ
    return None


def _aggregate_d1_to_weekly(d1_rates, target_weeks=200):
    """用 D1 真数据聚合等价周线 (5 D1≈1 周). 物理等价于 W1 趋势背景:
    不依赖 broker 提供 W1 API 权限 (实测 TMGM 终端 copy_rates W1 全 None),
    也不制造假随机数据. 这是'补全最优'而非妥协降级 —— 周线战略维度由
    真·D1 历史派生, 满足 _trend_bias 的 len>=200 阈值."""
    try:
        n = len(d1_rates)
        if n < 30:
            return None
        need = min(n, target_weeks * 5)
        seg = d1_rates[n - need:] if need < n else d1_rates
        closes, highs, lows = [], [], []
        for w in range(0, need, 5):
            chunk = seg[w:w + 5]
            m = len(chunk)
            if m == 0:
                continue
            closes.append(float(chunk['close'][m - 1]))
            highs.append(float(chunk['high'].max()))
            lows.append(float(chunk['low'].min()))
        if len(closes) < 60:   # 至少约1.2年周线, 保证 EMA200 有意义
            return None
        return (np.array(closes, float), np.array(highs, float), np.array(lows, float))
    except Exception:
        return None


def _load_tf(symbol, tf, n=HIST_N, allow_synthetic=True):
    """拉指定周期历史 OHLC (清洗缓存). 分级降级 (2026-07-11 修复 W1 假数据污染):

      - MT5 已连接但某周期数据不足:
          * W1 专属补全 (2026-07-11 升级): 直接拉 W1 失败 → 用 D1 真数据
            聚合等价周线 (5 D1≈1 周), 物理等价于 W1 趋势背景. 这是补全
            最优而非降级, 周线战略维度由真数据派生, 不制造假随机.
          * 其余周期确实缺失 → 返回 None, 上层标记 NEUTRAL, 干净退化为
            其余周期共振, 杜绝随机数据污染多周期共振评分.
      - 完全无 MT5 (_ensure_mt5() is None, 开发/回归环境) → allow_synthetic=True
        时合成数据兜底, 保证无 MT5 也能跑测试。
    """
    try:
        mt5 = _ensure_mt5()
        if mt5 is not None:
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, n)
            if rates is not None and len(rates) > 120:
                import pandas as pd
                df = pd.DataFrame(rates)
                close = ce._clean_close_arr(df['close'])
                high = ce._clean_close_arr(df['high'])
                low = ce._clean_close_arr(df['low'])
                return close, high, low
            # W1 拉不到 → D1 真数据聚合等价周线 (补全最优, 非随机)
            if tf == TF['W1']:
                d1 = mt5.copy_rates_from_pos(symbol, TF['D1'], 0, max(n, 1000))
                if d1 is not None and len(d1) >= 30:
                    wk = _aggregate_d1_to_weekly(d1)
                    if wk is not None:
                        return wk
            # 其余周期确实缺失 → 返回 None (上层 NEUTRAL 干净退化, 不污染)
            return None
    except Exception:
        pass
    if not allow_synthetic:
        return None
    # 合成降级 (仅完全无 MT5 的开发/回归环境使用)
    cfg = ce.SYMBOL_CONFIG[symbol]
    base = _BASE_PX.get(symbol, 100)
    sigma = min(cfg['volatility'] * 1e-4, 0.004)
    rets = np.random.normal(0, sigma, n)
    close = base * np.cumprod(1.0 + rets)
    bn = np.clip(np.abs(np.random.normal(0, sigma * 2.0, n)), 0, 0.01)
    high = np.maximum(close, close * (1 + bn))
    low = np.minimum(close, close * (1 - bn))
    return close, high, low


def _trend_bias(close):
    """EMA21/50/200 周期趋势方向: 多头排列→BUY, 空头排列→SELL, 否则 NEUTRAL.
       与 build_signal 的 _direction 回退规则同口径, 保证入场与背景一致.

       趋势显著性容差带 _TREND_BAND: 仅当 EMA21 与 EMA200 分离度超过价格
       的 0.1% 才认定"有明确趋势"; 否则判 NEUTRAL。这避免近平直/震荡的
       大周期被噪声误判为 BUY/SELL 从而误杀有效入场 (契合"大周期无明确
       趋势=NEUTRAL 放行"的设计意图)。"""
    if len(close) < 200:
        return 'NEUTRAL'
    e21 = ce._ema(close, 21)
    e50 = ce._ema(close, 50)
    e200 = ce._ema(close, 200)
    c = close[-1]
    base = abs(e200[-1]) + 1e-9
    if abs((e21[-1] - e200[-1]) / base) < _TREND_BAND:
        return 'NEUTRAL'
    if c > e21[-1] > e50[-1] > e200[-1]:
        return 'BUY'
    if c < e21[-1] < e50[-1] < e200[-1]:
        return 'SELL'
    return 'NEUTRAL'


def _mtf_resonance_score(ctx, direction):
    """多周期共振分层评分 (P1 战略锁 + P3 评分化).
    入参 ctx: {tf: bias} 至少含 W1/D1/H4; direction: 入场方向.
    返回 (score, hard_reject, all_neutral, lot_scale):
      - score: 各 TF 顺向 +weight / 逆势 -weight / NEUTRAL 0 之和
      - hard_reject: W1 反向(非 NEUTRAL 且与方向不符) → True (战略牛熊锁)
      - all_neutral: W1/D1/H4 三者全 NEUTRAL
      - lot_scale: [0.5,1.0] 评分越高仓位越满(仅缩小, 守双铁律仓位≤0.03)
    """
    score = 0
    for tf, w in _MTF_WEIGHTS.items():
        if tf not in ctx:
            continue
        b = ctx[tf]
        if b == 'NEUTRAL':
            continue
        score += w if b == direction else -w
    w1 = ctx.get('W1', 'NEUTRAL')
    hard_reject = (w1 != 'NEUTRAL' and w1 != direction)
    all_neutral = all(ctx.get(t, 'NEUTRAL') == 'NEUTRAL'
                      for t in ('W1', 'D1', 'H4'))
    if all_neutral:
        lot_scale = 0.5
    else:
        hi = sum(_MTF_WEIGHTS.get(t, 0) for t in ('W1', 'D1', 'H4'))
        lo = MTF_SCORE_THRESHOLD
        frac = (score - lo) / max(hi - lo, 1e-9)
        lot_scale = max(0.5, min(1.0, 0.5 + frac * 0.5))
    return score, hard_reject, all_neutral, lot_scale


class MarketHunter:
    def __init__(self, strategy=None, strategies=None, guardian=None, rf_alpha=None):
        # 逐品种独立策略: strategies={symbol: best_dict} 优先;
        # 兼容旧调用: 仅传单一 strategy 时, 复制到全部品种(共享, 向后兼容).
        self.strategies = dict(strategies) if strategies else (
            {s: strategy for s in ce.SYMBOL_CONFIG} if strategy is not None else {})
        # 保留 self.strategy 兼容引用(取首个品种, 或 None)
        self.strategy = strategy or (
            next(iter(self.strategies.values())) if self.strategies else None)
        self.guardian = guardian or GuardianExecutor()
        self._cache = {}
        self._cache_ts = {}        # 行情缓存时间戳(配合 _HIST_CACHE_TTL 定时刷新)
        self._rf_trained_at = {}   # RF 模型训练时间戳(配合 _RF_RETRAIN_TTL 定期重训)
        # RF 质量增强: 可选注入预训练模型; 否则 RF_QUALITY_GATE 开时按品种懒训练
        self._rf_injected = rf_alpha
        self._rf_models = {}
        # Regime 检测层: 懒创建单例检测器 (仅 REGIME_ADAPTIVE=True 时使用)
        self._regime_det = None
        # Regime 冷却防抖状态: symbol -> {'applied','candidate','stable'}
        #   applied   = 当前生效(regime 切参用的)状态
        #   candidate = 最新检测到的状态
        #   stable    = candidate 连续命中的次数(根); 达 REGIME_SWITCH_COOLDOWN 才切换
        self._regime_state = {}

    # 行情缓存 TTL(秒): 修复"整进程永不刷新 → 喂给 ADX/MTF/RF 的是陈旧快照"瑕疵.
    # 超过 TTL 重拉 MT5, 保证指标基于实时行情而非启动快照.
    _HIST_CACHE_TTL = 300

    def _hist(self, symbol, tf):
        key = (symbol, tf)
        import time as _t
        now = _t.time()
        if key not in self._cache or \
                (now - self._cache_ts.get(key, now)) > self._HIST_CACHE_TTL:
            data = _load_tf(symbol, tf)
            # 数据缺失周期(如 W1) -> sentinel (None,None,None), 上层按 NEUTRAL 退化
            self._cache[key] = (None, None, None) if data is None else data
            self._cache_ts[key] = now
        return self._cache[key]

    # RF 模型重训周期(秒): 修复"首扫训练一次后永不重训 → 模型随市场漂移过时"瑕疵.
    # 超过 TTL 丢弃旧模型, 下次扫描用刷新后的行情(_HIST_CACHE_TTL)重训.
    _RF_RETRAIN_TTL = 3600

    def _rf_ensure(self, symbol):
        """懒训练/取用 RF 质量模型 (仅 RF_QUALITY_GATE=True 时生效)。

        - 若注入预训练模型且已训练 → 直接复用
        - 否则用该品种 H1 历史训练一个 RFAlpha (缓存到 _rf_models, 避免重复训练)
        - 训练失败/样本不足 → 返回 None (门禁放行, 不阻断交易链)
        绝不依赖 MT5: 历史缺失时 _hist 自动合成降级(仅 DRY-RUN/开发用)。
        """
        if not RF_QUALITY_GATE:
            return None
        if self._rf_injected is not None and getattr(self._rf_injected,
                                                     'is_trained', False):
            return self._rf_injected
        import time as _t
        now = _t.time()
        mdl = self._rf_models.get(symbol)
        if mdl is not None:
            # 定期重训: 超期则丢弃, 用刷新后的行情重训(避免模型漂移过时)
            if (now - self._rf_trained_at.get(symbol, 0)) > self._RF_RETRAIN_TTL:
                mdl = None
                self._rf_models[symbol] = None
            else:
                return mdl
        if mdl is None:
            try:
                from rf_alpha import RFAlpha
                c, h, l = self._hist(symbol, TF[ENTRY_TF])
                model = RFAlpha()
                if model.fit((c, h, l)):
                    self._rf_models[symbol] = model
                    self._rf_trained_at[symbol] = now
                    return model
                self._rf_models[symbol] = None  # 标记已尝试但失败, 避免反复训练
                return None
            except Exception:
                self._rf_models[symbol] = None
                return None
        return None

    # ── Regime 冷却防抖 + 切参逻辑 (优化1) ──────────────────────────
    def _step_regime(self, symbol, h1_h, h1_l, h1_c):
        """检测 H1 regime + 冷却防抖: 连续稳定 REGIME_SWITCH_COOLDOWN 根才切换.

        返回 (applied_regime, rdet_dict). 异常 → 返回 (None, {regime:None, error}).
        状态按 symbol 独立维护于 self._regime_state, 避免跨品种相互重置。
        """
        if self._regime_det is None:
            self._regime_det = rd.RegimeDetector()
        try:
            rdet = self._regime_det.detect(symbol, h1_h, h1_l, h1_c)
        except Exception as e:
            return None, {'regime': None, 'regime_error': str(e)}
        regime = rdet.get('regime')
        st = self._regime_state.get(
            symbol, {'applied': None, 'candidate': None, 'stable': 0})
        if st['candidate'] is None or st['candidate'] != regime:
            st['candidate'] = regime
            st['stable'] = 1                      # 状态变化 → 重新计数
        else:
            st['stable'] += 1                     # 连续稳定 +1
        if st['applied'] is None:
            st['applied'] = regime                # 首次检测立即生效
        elif st['stable'] >= REGIME_SWITCH_COOLDOWN:
            st['applied'] = st['candidate']       # 稳定 N 根后切换
        self._regime_state[symbol] = st
        return st['applied'], rdet

    @staticmethod
    def _apply_regime_preset(strategy_params, regime):
        """把 REGIME_PRESETS 的**相对偏移**覆盖到策略参数 (P0-HIGH-1 修复).

        应用逻辑:
          1. effective_adx = clamp(evolved_adx_min + adx_offset, 20, 60)
             (相对偏移, 不再整体架空进化选出的 adx_min; 下限20保ADX地板,
              上限60防极端)
          2. sl_mult / tp_mult 以绝对倍率覆盖 sl_multiplier / tp_multiplier
             (三档预设均 RR=2.0)
          3. volatility_scalar **全 regime** 生效 (继承策略仓位后 ×scalar, 仍夹
             [0.01,0.03]) —— 修复审计事实#4 (原仅 volatile 分支, 且≈1.0形同虚设)
          4. 覆盖后**立即重过双铁律**: _ensure_rr(RR>=2 不可破) +
             _ensure_risk_cap(仓位<=0.03, 缩仓后仍夹 [0.01,0.03])
        返回 (merged_params, info_dict); info 供提案/扫描日志透明标注
        (P1-MEDIUM-2: regime / effective_adx_min / 是否缩仓).
        绝不破坏三安全闸(VETO) / ADX硬禁(<20) / 缠论gate / 多周期共振.
        """
        preset = REGIME_PRESETS.get(regime)
        merged = dict(strategy_params)
        evolved_adx = float(merged.get('adx_min', 20))
        vol_scalar = float(merged.get('volatility_scalar', 1.0))
        effective_adx = evolved_adx
        scaled = False
        if preset:
            # 1. adx_offset 已废止 (P0 进化, 2026-07-09): regime 检测不稳会
            #    把进化的 adx_min 错误偏移, 架空逐品种进化优势 (EUR 误判 volatile
            #    抬到53卡死). 进化选出的 adx_min 直接生效; 真实风控由
            #    volatility_scalar 全 regime 缩仓承担. 不破双铁律/VETO/ADX硬禁.
            effective_adx = evolved_adx
            merged['adx_min'] = effective_adx
            # 2. 绝对倍率覆盖 sl/tp
            if 'sl_mult' in preset:
                merged['sl_multiplier'] = preset['sl_mult']
            if 'tp_mult' in preset:
                merged['tp_multiplier'] = preset['tp_mult']
        # 3. volatility_scalar 全 regime 缩仓 (继承仓位 × scalar)
        if 'volatility_scalar' in merged:
            new_pos = merged['position_size'] * vol_scalar
            if new_pos < merged['position_size']:
                scaled = True
            merged['position_size'] = new_pos
        # 4. 双铁律把关
        merged = ce._ensure_rr(merged)        # 双铁律①: RR>=2 不可破
        merged = ce._ensure_risk_cap(merged)  # 双铁律②: 仓位<=0.03, 缩仓后仍夹[0.01,0.03]
        info = {
            'regime': regime,
            'regime_preset': preset,
            'evolved_adx_min': round(evolved_adx, 2),
            'effective_adx_min': round(effective_adx, 2),
            'position_scaled': bool(scaled),
            'volatility_scalar': round(vol_scalar, 4),
        }
        return merged, info

    def scan_symbol(self, symbol, dl_pred=None, tc_bias=None,
                    existing_symbols=None, open_dirs=None):
        """对一个品种产出入场提案 (经全部前置过滤) 或 (None, 原因).
        existing_symbols: 当前已有持仓的品种集合, 命中则跳过 (防重复开仓)."""
        if existing_symbols and symbol in existing_symbols:
            return None, (f'已有 {symbol} 持仓, 猎场司不重复开仓 '
                          f'(交由监军司看护)')
        proposal = None  # 区间模式专属: 中等/低波动带可能提前接管生成提案
        # [2026-07-11 深度优化] 无趋势 edge 且非区间白名单品种 → 早退,
        # 避免每轮空跑全套扫描/门禁计算(终会 EDGE GATE SKIP, 提前返回省算力与日志).
        # 区间白名单品种仍正常进入区间接管分支; 后续回测通过扩白名单即自动放行.
        _so = self.strategies.get(symbol)
        # [2026-07-11 修复] 区间白名单取 guardian 权威定义(单一来源), 避免本模块
        #   重复定义导致与 guardian_executor.RANGE_ALLOWLIST 漂移 / NameError.
        #   区间开放品种(fitness 低但允许区间兜底)应放行至区间接管分支, 不早退.
        _range_allow = getattr(self.guardian, 'RANGE_ALLOWLIST', set())
        # [全品种收集模式] DATA_COLLECTION_MODE=True 时跳过 fitness 早退,
        # 允许无进化优势品种进入扫描(收集实盘数据, 待筛选). 其他安全闸不受影响.
        if (not su.DATA_COLLECTION_MODE
                and _so is not None and isinstance(_so, dict)
                and float(_so.get('fitness') or 0) < MIN_EDGE_FITNESS
                and symbol not in _range_allow):
            return None, (f'{symbol} 无进化优势(fitness=0)且非区间品种, SKIP')
        # [P0-修复 2026-07-10] 顶层初始化 regime_apply_info, 防区间模式
        #   (REGIME_ADAPTIVE=True 时生成 _range_mode 提案) 跳过下方趋势段(L462
        #   if 块, 含 L481 的 None 初始化), 但 L502 regime 写入块在 L462 之外仍
        #   执行, 到 L516 访问未绑定变量 → UnboundLocalError 拖垮整轮扫描.
        #   顶层绑定后任意路径均安全(区间模式 regime_apply_info=None→L516 跳过).
        regime_apply_info = None
        # 0) 区间/均值回归模块接管上限 = 该品种进化 adx_min (封顶 RANGE_ADX_CEIL=35).
        #    P2-A2 路由修正: 趋势通道已进化到低 adx_min(黄金25/币25/以太18),
        #    中等波动带(adx_min≤ADX<35)本就有趋势 edge, 不应被区间模块劫持;
        #    仅当 H1 ADX < adx_min(趋势无法交易) 才交区间模块兜底反转.
        #    → 恢复"趋势优先、区间兜底", 直接提资金利用率(原零订单主因).
        #    adx_min 缺失时回退 RANGE_ADX_CEIL(35) 保持旧行为; 上限封顶35避免
        #    高 adx_min 品种(EUR45/GBP42)区间活动被不当扩大.
        h1_c, h1_h, h1_l = self._hist(symbol, TF[ENTRY_TF])
        h1_adx = ce._adx(h1_h, h1_l, h1_c)
        # 0.2) 点差摩擦护栏 (吸收 Supreme_EA 知识包 InpMaxSpreadATR=0.40 / 坑#3#4)
        #   当前点差 > SPREAD_ATR_RATIO × ATR → 流动性/摩擦过大, 拒开新单.
        #   失败开放(与 RF/缠论 gate 一致): mt5 不可用/tick 缺失/atr<=0 → 放行.
        #   注意: 本系统 SL/TP 与护栏共用同一 ATR 基准(无 D1/H1 分裂), 护栏
        #         不会被"改基准"无声绕过 —— Supreme_EA 坑#4 的反面教材, 天然免疫.
        atr_now = ce._atr(h1_h, h1_l, h1_c)
        atr_now = float(atr_now[-1]) if len(atr_now) > 0 else 0.0
        if ce.SPREAD_GUARD_ENABLED:
            _ok, _sinfo = ce.spread_friction_ok(symbol, atr_now)
            if not _ok:
                return None, _sinfo
        _ceil_src = self.strategies.get(symbol)
        _ceiling = RANGE_ADX_CEIL
        if isinstance(_ceil_src, dict) and isinstance(_ceil_src.get('params'), dict):
            _am = _ceil_src['params'].get('adx_min')
            if isinstance(_am, (int, float)):
                _ceiling = min(float(_am), RANGE_ADX_CEIL)
        if len(h1_adx) > 0 and not np.isnan(h1_adx[-1]) \
                and h1_adx[-1] < _ceiling:
            # 趋势阈值未达(adx_min): 区间模块开专属通道兜底
            if RANGE_MODE_ENABLED:
                try:
                    rng_prop, rng_reason = self.guardian.build_range_signal(
                        symbol, self.strategies.get(symbol))
                    if rng_prop is not None:
                        # 区间提案接管: 跳过下方趋势专属 EDGE GATE + build_signal,
                        # 但仍走 RF 门禁/缠论gate/审度司VETO/双铁律 (全链路保护).
                        proposal = rng_prop
                        proposal['_range_mode'] = True
                    else:
                        return None, (f'H1 ADX {h1_adx[-1]:.1f} < '
                                      f'{_ceiling:.0f} (中等波动; 区间: {rng_reason})')
                except Exception as e:
                    return None, f'区间模块异常: {e}'
            else:
                return None, (f'H1 ADX {h1_adx[-1]:.1f} < {_ceiling:.0f} '
                              f'(硬禁新开)')
        # 0.5) 信号质量门禁: 该品种近期表现差 → 直接 SKIP (早于信号计算)
        sizer = getattr(self.guardian, 'sizer', None)
        if sizer is not None:
            paused, preason = sizer.should_pause(symbol)
            if paused:
                return None, f'信号质量门禁: {preason}'
        # 0.45) Regime 自适应切参 (第二阶段, 默认 REGIME_ADAPTIVE=False 整层跳过)
        #       定位: ADX硬禁(0) 之后, 信号生成(1) 之前.
        #       切参逻辑: detect regime → 经 REGIME_SWITCH_COOLDOWN 防抖后,
        #       从 REGIME_PRESETS 取 adx_min/sl_mult/tp_mult/position_size 覆盖
        #       当前扫描参数(仍走全链路: VETO/双铁律/ADX硬禁不可绕过).
        #       默认 False → 不检测、不切参, 行为 100% 不变(零回归).
        eff_regime = None
        rdet = None
        if REGIME_ADAPTIVE:
            try:
                eff_regime, rdet = self._step_regime(symbol, h1_h, h1_l, h1_c)
            except Exception as e:
                rdet = {'regime': None, 'regime_error': str(e)}

        # 1) H1 入场信号 (含 ADX 门槛 / 结构确认 / 自适应暂停闸门)
        #    Regime 切参: 若 eff_regime 命中预设, 用覆盖后的 params 调 build_signal
        #    逐品种: 从 self.strategies 取该品种独立进化参数(不再共享一套)
        strat_obj = self.strategies.get(symbol)
        # 区间模式(proposal 已生成)即使 strat_obj 缺失也继续走后续 gate;
        # 仅趋势模式(未生成 proposal) 且缺策略参数才 return.
        if proposal is None and strat_obj is None:
            return None, f'无 {symbol} 的品种策略参数(逐品种进化尚未覆盖)'
        # 0.6) 趋势专属段: EDGE GATE + Regime 切参 + build_signal
        #   区间模式(_range_mode)已自行生成提案, 跳过此段 (但仍过下方
        #   RF/缠论/审度司 全链路). 趋势模式正常走.
        if proposal is None or not proposal.get('_range_mode'):
        # 0.6) 进化优势门禁 (EDGE GATE): 只交易有证明优势的品种
        #   无优势(fitness≈0)/负优势(pf<1) → 直接 SKIP, 不在"裸做"品种上交易.
        #   这是"安全且诚实"哲学的最后一道闸: 承认模型并非全品种通吃.
        #   仅在策略 dict 确实带 'fitness' 键时生效(即生产从 evolution_state
        #   加载的真实逐品种策略); 合成/空测试策略(无该键)放行, 交其他闸判断.
            # [全品种收集模式] 收集模式开启时整体放开 EDGE GATE(含 fitness/pf 双判),
            # 全品种均可交易(仍守 ADX硬禁/点差护栏/双铁律/审度司VETO). 默认关闭.
            if (EDGE_GATE_ENABLED and not su.DATA_COLLECTION_MODE
                    and 'fitness' in strat_obj):
                _fit = float(strat_obj.get('fitness') or 0)
                if _fit < MIN_EDGE_FITNESS:
                    return None, (f'{symbol} 无进化优势 '
                                  f'(fitness={_fit:.2f} < {MIN_EDGE_FITNESS}), SKIP')
                # [P2-A 修复] baseline 缺失(null) 不误杀: 仅当 baseline 存在且
                #   pf 为数值且 < MIN_BASELINE_PF 才拦 (旧逻辑 `or 0` 会把 null 当 0 误拦 XAU 等).
                _bl = strat_obj.get('baseline')
                _blpf = _bl.get('pf') if isinstance(_bl, dict) else None
                if isinstance(_blpf, (int, float)) and _blpf < MIN_BASELINE_PF:
                    return None, (f'{symbol} 回测负优势 '
                                  f'(pf={_blpf:.2f} < {MIN_BASELINE_PF}), SKIP')
            strat = strat_obj
            regime_apply_info = None
            if REGIME_ADAPTIVE and eff_regime is not None:
                try:
                    ov, rinfo = self._apply_regime_preset(
                        strat_obj['params'], eff_regime)
                    strat = dict(strat_obj)
                    strat['params'] = ov
                    regime_apply_info = rinfo
                except Exception:
                    strat = strat_obj
            proposal, reason = self.guardian.build_signal(
                strat, symbol, dl_pred, tc_bias)
            if proposal is None:
                return None, reason
        # 1.45) Regime 检测层 (HMM / 简化状态机 fallback) — DRY-RUN 仅记录
        #       定位: ADX硬禁(0) 之后, RF gate(1.4) 之前. 默认 REGIME_ADAPTIVE=False
        #       → 整块跳过, 扫描行为与改动前 100% 一致(零回归). 开 True 时进入
        #       第二阶段: 0.45 已检测 regime 并切参, 此处仅把 regime 信息写入
        #       proposal 供复盘/监军司参考, 不阻断过滤链. 异常/数据不足/超时 → 放行
        #       不阻断(与 RF/缠论 gate 一致). 切参已激活, 仍绝不触碰三安全闸/
        #       VETO/ADX硬禁/双铁律.
        if REGIME_ADAPTIVE:
            # 切参已在 0.45/1 完成; 此处仅把 regime 信息写入提案供复盘/监军司参考,
            # 不阻断过滤链. 异常/数据不足/超时已在 0.45 捕获并放行.
            proposal['regime'] = eff_regime
            if rdet is not None:
                proposal['regime_confidence'] = rdet.get('confidence')
                proposal['regime_method'] = rdet.get('method')
                if rdet.get('regime_error'):
                    proposal['regime_error'] = rdet.get('regime_error')
            proposal['regime_applied'] = eff_regime
            proposal['regime_preset'] = REGIME_PRESETS.get(eff_regime)
            # P1-MEDIUM-2 透明标注: 实盘生效的 regime 依赖参数 (含 effective_adx)
            #   —— evolution_state 的 best 标签仍标 Strategy_07 (不动),
            #      但此处明确"实盘生效=regime依赖参数", 避免标签误导(审计事实#5).
            if regime_apply_info is not None:
                proposal['regime_effective_adx_min'] = \
                    regime_apply_info['effective_adx_min']
                proposal['regime_evolved_adx_min'] = \
                    regime_apply_info['evolved_adx_min']
                proposal['regime_position_scaled'] = \
                    regime_apply_info['position_scaled']
                proposal['regime_volatility_scalar'] = \
                    regime_apply_info['volatility_scalar']
                proposal['regime_live_params'] = (
                    f"实盘生效=regime依赖参数(effective_adx="
                    f"{regime_apply_info['effective_adx_min']}"
                    f"{', 已缩仓' if regime_apply_info['position_scaled'] else ''})")
        # 1.4) RF 质量增强门禁 (增强非替代, 默认关闭 RF_QUALITY_GATE)
        #      定位: 在 1.5 缠论 gate 之前、信号方向已知后, 用 RFAlpha.score()
        #      评估该方向未来 N 根概率, 不足阈值则 SKIP。
        #      不替换 should_pause(0.5) / ADX<20 硬禁(0) / 缠论 gate / 审度司 VETO。
        #      异常或模型不可用 → 放行, 绝不阻断交易链。
        if RF_QUALITY_GATE:
            direction = proposal['direction']
            rfp = self._rf_ensure(symbol)
            if rfp is not None:
                try:
                    sc = rfp.score(h1_c, h1_h, h1_l)
                    if sc is not None:
                        # 信号质量动态化: 阈值随 Regime 调节 (仅 DYNAMIC_SIGNAL_THRESHOLD
                        # + REGIME_ADAPTIVE 同时开启时); 默认沿用 RF_GATE_THRESHOLD(0.5).
                        # trend 放宽 / volatile 收紧, 不破 ADX硬禁/VETO/双铁律.
                        # 阈值确定 (P1-C 重构, 2026-07-09):
                        #   有真实 edge 品种(fitness>0 & baseline 非空) → 提升至 0.65
                        #     (P1-C 回测证据: XAUUSD pf 1.06→1.424 / wr 0.52→0.567 / n 仍314;
                        #      BTCUSD pf 0.955→1.523 从亏转盈; 笔数均≥300 充足不过度减笔).
                        #     不随 regime 波动 (比依赖不稳的 regime 检测更可靠).
                        #   无 edge 品种(fitness<=0 | baseline 空) → 护栏 0.65 (智能风控, 非禁止).
                        #   注: 旧 DYNAMIC_SIGNAL_THRESHOLD+REGIME_ADAPTIVE 动态调节已弃用
                        #     (regime 检测不稳会架空进化参数, 同 adx_offset 教训).
                        thr = RF_GATE_THRESHOLD_EDGE
                        _strat = self.strategies.get(symbol)
                        if _strat is not None:
                            _fit = float(_strat.get('fitness', 0) or 0)
                            _base = _strat.get('baseline')
                            if _fit <= 0 or _base is None:
                                thr = 0.65
                                proposal['unproven_edge'] = True
                        proposal['signal_threshold_base'] = RF_GATE_THRESHOLD
                        proposal['signal_threshold_dynamic'] = thr
                        p_dir = sc['UP'] if direction == 'BUY' else sc['DOWN']
                        p_opp = sc['DOWN'] if direction == 'BUY' else sc['UP']
                        opp = 'SELL' if direction == 'BUY' else 'BUY'
                        # 双方向择优: 提案方向不达标, 但反方向概率更高且≥阈值
                        # → 翻转入场 (利用 RF 的 UP/DOWN 全信息, 克服 _direction 单边偏见)
                        if p_dir < thr and p_opp >= thr and p_opp > p_dir:
                            entry = proposal['entry']
                            _pip = ce.SYMBOL_CONFIG[symbol]['pip']
                            if opp == 'BUY':
                                _new_sl = entry - proposal['sl_pts'] * _pip
                                _new_tp = entry + proposal['tp_pts'] * _pip
                            else:
                                _new_sl = entry + proposal['sl_pts'] * _pip
                                _new_tp = entry - proposal['tp_pts'] * _pip
                            proposal['direction'] = opp
                            proposal['sl'] = round(_new_sl, 5)
                            proposal['tp'] = round(_new_tp, 5)
                            proposal['rf_flipped'] = True
                            proposal['rf'] = sc
                            print(f"  [RF择优翻转] {symbol} {direction}→{opp} "
                                  f"P({opp})={p_opp:.2f} (UP={sc['UP']:.2f}/"
                                  f"DOWN={sc['DOWN']:.2f}) thr={thr:.2f}")
                        elif p_dir >= thr:
                            proposal['rf'] = sc
                            print(f"  [RF门禁] {symbol} {direction} "
                                  f"P({direction})={p_dir:.2f} (thr={thr:.2f}) "
                                  f"(UP={sc['UP']:.2f}/DOWN={sc['DOWN']:.2f})")
                        else:
                            return None, (f'RF质量门禁: 双方向均<{thr:.2f} '
                                          f'(UP={sc["UP"]:.2f}/DOWN={sc["DOWN"]:.2f})')
                except Exception as e:
                    proposal.setdefault('rf', {})['error'] = str(e)
        # 1.5) 缠论结构 gate (P0+P1 形态学 + 背驰 + 一/二类买卖点)
        #      接入定位: 增强信号源, 非替代 — 只禁反向 + 确认, 中性放行
        #      - BUY 遇顶背驰/卖点 → SKIP
        #      - SELL 遇底背驰/买点 → SKIP
        #      - 同向背驰/买卖点   → BULLISH/BEARISH_CONFIRM (写入提案)
        #      - 中性/无结构       → 放行 (不强制要求买卖点, 避免漏单)
        #      异常降级: 分析失败时绝不阻断交易链, 放行并记录
        direction = proposal['direction']
        try:
            cl_res = cl.analyze(h1_c, h1_h, h1_l)
            allowed, tag, note = cl.gate_signal(cl_res, direction)
            zs = cl_res.get('zhongshu')   # (ZD, ZG) or None
            sl_sug = cl.chanlun_stop(direction, zs)
            proposal['chanlun'] = {
                'tag': tag,
                'note': note,
                'trend': cl_res.get('trend_type'),
                'divergence': cl_res.get('divergence'),
                'bsp': cl_res.get('latest_bsp'),
                'bi_count': cl_res.get('bi_count'),
                'zhongshu': zs,
                'sl_suggestion': sl_sug,
            }
            if not allowed:
                # P1-H: 缠论反向否决降级 — 当 RF 质量门禁已高置信通过(方向概率
                #   ≥RF_GATE_THRESHOLD_EDGE)时, 缠论反向仅作参考记录, 不硬拒。
                #   修复"缠论 gate 违反系统铁律(中性即放行, 不单独否决交易) 且
                #   震荡市假背驰系统性否决 XAU 趋势 edge"的问题。仅在 RF 已守质量
                #   前提下放行, 不破双铁律/审度司VETO/ADX硬禁。RF 未通过或不存在
                #   时(测试桩/质量不足)维持原 SKIP 行为, 零回归。
                _rf = proposal.get('rf')
                if _rf is not None:
                    _rdir = proposal['direction']
                    _rp = _rf.get('DOWN') if _rdir == 'SELL' else _rf.get('UP')
                    if _rp is not None and _rp >= RF_GATE_THRESHOLD_EDGE:
                        proposal['chanlun']['tag'] = 'REVERSE_OVERRIDE_BY_RF'
                        proposal['chanlun']['note'] = f'缠论反向但RF高置信放行: {note}'
                    else:
                        return None, f'缠论 gate: {note}'
                else:
                    return None, f'缠论 gate: {note}'
            # 1.5b) 中枢动态止损覆盖 (P2, 默认关闭, 由 CHANLUN_SL_OVERRIDE 控制)
            if CHANLUN_SL_OVERRIDE and sl_sug is not None:
                self._apply_chanlun_sl(proposal, sl_sug, symbol)
        except Exception as e:
            proposal.setdefault('chanlun', {})['tag'] = 'ERROR_SKIP'
            proposal['chanlun']['note'] = f'chanlun error: {e}'
        # 1.55) 组合相关性风控 (审度司, 默认 PORTFOLIO_CORR_CHECK=False → 仅记录不拦截)
        #       若新提案品种与现有持仓同组且同方向(相关性高), 记录降权/拒开建议;
        #       仅当 PORTFOLIO_CORR_ENFORCE=True 才真正拒开(默认 DRY-RUN 不强制).
        #       日累计风险强化日志一并写入提案. 不破三安全闸/VETO/ADX硬禁/双铁律.
        if PORTFOLIO_CORR_CHECK and open_dirs:
            try:
                pc = self.guardian.auditor.assess_portfolio_correlation(
                    symbol, proposal['direction'], open_dirs)
                proposal['portfolio_corr'] = pc
                # 日累计风险强化日志 (DRY-RUN 记录, 不强制拦截)
                proposal['daily_risk'] = self.guardian.auditor.daily_risk_log(
                    list(open_dirs.keys()))
                if PORTFOLIO_CORR_ENFORCE and pc['action'] == 'REJECT':
                    return None, f'组合相关性拒开: {pc["note"]}'
            except Exception as e:
                proposal['portfolio_corr_error'] = str(e)
        # 2) 多周期共振分层评分 (P1 战略锁 W1 + P3 评分化)
        #    - W1 反向(非 NEUTRAL 且与方向不符) → 硬拒(战略牛熊锁)
        #    - 其余 [W1,D1,H4] 顺向加分/逆势扣分, 总分 < 阈值 且 非全中性 → SKIP
        #    - 全中性(无大周期背书) → 放行但半仓试单
        direction = proposal['direction']
        ctx = {}
        for tf in CTX_TFS:
            c = self._hist(symbol, TF[tf])[0]
            # W1/D1/H4 任一周数据缺失(如 W1 拉不到) → NEUTRAL 干净退化, 不污染共振
            bias = _trend_bias(c) if c is not None else 'NEUTRAL'
            ctx[tf] = bias
        mtf_score, mtf_hard_reject, mtf_all_neutral, mtf_lot_scale = \
            _mtf_resonance_score(ctx, direction)
        if mtf_hard_reject:
            return None, (f'W1 趋势 {ctx.get("W1")} 与入场 {direction} 反向 '
                          f'(战略牛熊锁硬拒, SKIP)')
        if (not mtf_all_neutral) and mtf_score < MTF_SCORE_THRESHOLD:
            return None, (f'多周期共振不足 (score={mtf_score} < '
                          f'{MTF_SCORE_THRESHOLD}, W1/D1/H4={ctx.get("W1")}/'
                          f'{ctx.get("D1")}/{ctx.get("H4")}, SKIP)')
        proposal['mtf'] = ctx
        proposal['mtf_score'] = mtf_score
        proposal['mtf_lot_scale'] = mtf_lot_scale

        # 2.5) P2: 15M 精准入场确认 + 缩止损提盈亏比
        m15_c, m15_h, m15_l = self._hist(symbol, TF['M15'])
        # M15 数据缺失(极端断线) → NEUTRAL, 不误拒; 正常时已是真实 M15(已修值15)
        m15_bias = _trend_bias(m15_c) if m15_c is not None else 'NEUTRAL'
        if M15_CONFIRM_REQUIRED and m15_bias != 'NEUTRAL' and m15_bias != direction:
            return None, (f'M15 趋势 {m15_bias} 与入场 {direction} 冲突 '
                          f'(15M 噪音过滤, SKIP)')
        if (not proposal.get('range_mode')) and m15_bias == direction \
                and 'tp' in proposal and 'entry' in proposal:
            atr15 = ce._atr(m15_h, m15_l, m15_c)
            if len(atr15) > 0 and not np.isnan(atr15[-1]) and atr15[-1] > 0:
                sl15_d = atr15[-1] * M15_SL_TIGHT_MULT
                entry = proposal['entry']
                new_sl = (entry - sl15_d) if direction == 'BUY' else (entry + sl15_d)
                new_rr = abs(proposal['tp'] - entry) / sl15_d
                if new_rr < M15_RR_MIN:
                    tp_d = sl15_d * M15_RR_MIN
                    proposal['tp'] = round(entry + tp_d if direction == 'BUY'
                                          else entry - tp_d, 5)
                    proposal['tp_pts'] = round(
                        tp_d / ce.SYMBOL_CONFIG[symbol]['pip'], 2)
                proposal['sl'] = round(new_sl, 5)
                proposal['sl_pts'] = round(
                    sl15_d / ce.SYMBOL_CONFIG[symbol]['pip'], 2)
                proposal['m15_tightened'] = True
                proposal['m15_bias'] = m15_bias

        # P3: 按 MTF 评分缩放仓位(仅缩小不放大, 守双铁律仓位≤0.03)
        if 'lot' in proposal and proposal['lot'] > 0:
            new_lot = max(0.01,
                          math.floor(proposal['lot'] * mtf_lot_scale * 100) / 100)
            proposal['lot'] = new_lot

        proposal['atr'] = atr_now   # 供执行端点差护栏复用(与 SL 同源 ATR 基准)
        return proposal, '多周期共振通过'

    @staticmethod
    def _apply_chanlun_sl(proposal, sl_sug, symbol):
        """用缠论中枢 SL 覆盖提案的 ATR SL (P2)。

        保持原 RR 比例重算 TP; 仅当新 SL 在入场价"外部"且不过宽时覆盖。
        守卫: 方向合理性 + 中枢 SL 不超过原 ATR SL 的 3 倍 (防 lot 过小无意义)。
        """
        direction = proposal['direction']
        entry = proposal['entry']
        pip = ce.SYMBOL_CONFIG[symbol]['pip']
        if direction == 'BUY' and sl_sug >= entry:
            return  # SL 不在入场下方, 弃用中枢 SL
        if direction == 'SELL' and sl_sug <= entry:
            return
        new_sl_pts = abs(entry - sl_sug) / pip
        if new_sl_pts > proposal['sl_pts'] * 3.0:
            return  # 中枢过大, 覆盖会导致 lot 过小, 弃用
        rr = (proposal['tp_pts'] / proposal['sl_pts']) if proposal['sl_pts'] > 0 else 2.0
        new_tp_pts = new_sl_pts * rr
        if direction == 'BUY':
            new_tp = entry + new_tp_pts * pip
        else:
            new_tp = entry - new_tp_pts * pip
        proposal['sl'] = round(sl_sug, 5)
        proposal['sl_pts'] = round(new_sl_pts, 2)
        proposal['tp'] = round(new_tp, 5)
        proposal['tp_pts'] = round(new_tp_pts, 2)
        proposal['chanlun']['sl_override'] = True

    def scan_all(self, symbols=None, dl_preds=None, tc_bias=None,
                 existing_symbols=None, open_dirs=None):
        symbols = symbols or list(ce.SYMBOL_CONFIG.keys())
        if su.DATA_COLLECTION_MODE:
            print(f"[猎场司] ⚠️ 全品种收集模式 ON — EDGE GATE 已放开, "
                  f"扫描 {len(symbols)} 个品种收集实盘数据(仍守双铁律/风控)")
        out = []
        for s in symbols:
            try:
                dp = dl_preds.get(s) if dl_preds else None
                p, r = self.scan_symbol(s, dp, tc_bias, existing_symbols,
                                        open_dirs)
                out.append({'symbol': s, 'proposal': p, 'reason': r})
            except Exception as e:
                out.append({'symbol': s, 'proposal': None,
                            'reason': f'scan error: {e}'})
        return out
