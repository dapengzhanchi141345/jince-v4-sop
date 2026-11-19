# live_bridge.py — 金策宗师团 · 同源 live 桥接层 (全宇宙版 V3)
#
# 目的: 把 60043976 模拟盘的 live 交易, 接到**与回测同源**的信号引擎上,
#       而不是 run_trader.py 默认的 legacy 通用 ATR/ADX 进化引擎。
#
# 同源保证:
#   - 信号生成: 直接调用 advanced_strategies.STRATEGY_REGISTRY_V4
#               (SDP/ICT/VP/DIV/MR/TREND/BO, 与 universe_backtest 回测同一套代码)
#   - 定手:     直接调用 symbol_universe.risk_lot (净值驱动)
#   - 真实规格: 通过 symbol_universe.build_full_universe 动态接入券商全品种
#               (248 个, 含真实 tick_value 标定的 pip_usd)
#
# 全宇宙扫描:
#   - 不再限于 32-KEEP, 而是轮询 (round-robin) 扫描券商全部可交易品种,
#     每轮只扫 ROTATE_BATCH 个 (cursor 跨重启持久化), 约 total/BATCH 轮覆盖全部。
#   - 每个品种按其资产类别 (cls) 套用 CLASS_STRATEGY_MAP 的有序策略列表。
#   - 单轮受 SCAN_TIME_BUDGET 软时间预算约束, 不拖垮 120s 交易周期。
#
# 产出 proposal 与 guardian_executor.audit_and_execute 完全兼容:
#   {symbol, direction, entry, sl, tp, sl_pts, tp_pts, lot,
#    pip_usd_per_lot, spread, strategy, adx, regime}
# 审计器 (risk_auditor) 只校验 lot×sl_pts×pip_usd_per_lot/equity ≤ max_rpt,
# 以及日累计风险 ≤ max_dr —— 由 run_trader 把 guardian 的 max_rpt/max_dr 设定即可放行。
#
# 安全: 本模块只产出 proposal, 绝不直接下单; 下单仍过 audit_and_execute
#       + LIVE_TRADING_ENABLED 硬开关。DRY-RUN (auto_confirm=False) 下零风险。

import os
import json
import math
import time
import datetime
import pandas as pd
import numpy as np

import symbol_universe as su
import advanced_strategies_v4 as ast  # V4策略层
import regime_router as rr
import edge_tracker as et
from advanced_strategies_v4 import CLASS_STRATEGY_MAP, STRATEGY_REGISTRY_V4
from advanced_filters import get_advanced_filter

# [2026-08-31 V4升级] 策略优先级调整 - V4信号质量更高
STRAT_PRIORITY = {"DIV": 0, "MR": 1, "TREND": 2, "BO": 3, "VP": 4, "SDP": 5, "ICT": 6, "OTAS": 7, "PASD": 8}

# [2026-08-31 V4升级] 优化参数 (来自进化引擎)
V4_CONFIG = {
    'pip': 0.01,
    'lot': 0.1,
    'adx_min': 15,           # SDP优化: 降低ADX门槛(历史, 已废弃-见 ENTRY_ADX_MIN)
    'sl_mult': 1.5,
    'rr_mult': 3.0,
    'disp_threshold': 0.005, # ICT优化
    'lookback': 10,          # BO优化
}

# [2026-09-02 V3.3] 开仓趋势门槛(语义化拒单, 仅大趋势环境进场)
# 全量回测(journal 配对 FILL.adx↔CLOSE.pnl): ADX<20 的 834 笔 PF=0.19/WL=0.57/净亏-190
#   (几乎全部亏损源, 含美股/VIX 等垃圾品种均在低 ADX 震荡市进场);
#   ADX>=30 的 8 笔(部署后干净窗口) PF=1.31/WL=3.92.
# ⇒ 仅当 trend_state=="trend"(adx>=ADX_TREND) 才放行, 震荡市(range)一律拒单.
# 与 regime_router.ADX_TREND 对齐; 只减不增风险, fail-open 由外层 try/except 兜底.
ENTRY_ADX_MIN = 30.0  # V4: 从 25 提升至 30, 实盘验证 PF=1.31

# [2026-09-03 V5 深度优化] 品种白名单: 仅保留 PF>=1.0 且净盈利品种
# 数据来源: edge_tracker.json 实盘诊断, 只保留盈利品种禁用亏损品种
# 盈利品种: CADJPY(PF=5.02), EURJPY(PF=1.66), GBPCAD(PF=1.58), AUDCHF(PF=1.38), GBPUSD(PF=1.01)
# 禁用品种: BTCUSD(亏$11.71), XAGUSD(亏$18.05), USDJPY(亏$9.67), ETHUSD(亏$10.33)等
V4_SYMBOL_GATE = {
    # PF>=1.0 盈利品种 (可靠)
    "CADJPY": {"reason": "PF=5.02, net=+$3.90, 强盈利"},
    "EURJPY": {"reason": "PF=1.66, net=+$6.27, 胜率64%"},
    "GBPCAD": {"reason": "PF=1.58, net=+$7.85, 胜率63%"},
    "AUDCHF": {"reason": "PF=1.38, net=+$1.00, 胜率80%"},
    "GBPUSD": {"reason": "PF=1.01, net=+$0.17, 样本充足"},
    # XAUUSD (进化最佳, 样本少但PF=99)
    "XAUUSD": {"reason": "进化PF=99, n=5, 强趋势品种"},
}
# 禁用后缀 (股票指数/垃圾 CFD)
V4_FORBIDDEN_SUFFIXES = ('.NYS', '.NAS', '.BAT', '.ASX', '.AUS200', '.US500', '.UK100', '.NAS100', '.US30')

# 新鲜信号窗口: 仅接受最近 N 根 H1 触发的信号 (避免用陈旧信号开仓)
# [2026-08-31 V4修复] 3 → 12: 实测V4策略信号多落在5~12根前(FRESH_BARS=3误杀大量有效信号),
#   放宽到12根(12小时)覆盖中线入场, 与BO窗口对齐
FRESH_BARS = 12
# 趋势/突破类需更长信号窗口: 中长线持仓允许更早的入场信号仍有效 (单位: H1 根数)
STRAT_FRESH_BARS = {
    "TREND": 24,   # ~24根H1 ≈ 1个交易日, 趋势拉回容差大
    "BO": 12,      # 突破信号窗口放宽到半日
    "SDP": 16,     # [V4修复] 供需区信号实测落在12根前
    "PASD": 16,    # [V4修复] 供需共振信号实测落在12根前
    "OTAS": 24,    # [V4修复] OTAS高质量信号稀缺, 放宽窗口
}

# 全宇宙轮询: 每轮只扫 BATCH 个品种 (cursor 跨重启持久化), 约 total/BATCH 轮覆盖全部
ROTATE_BATCH = 40
ROTATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "bridge_rotate.json")
# 单轮扫描软时间预算 (秒): 防止 248 品种把 120s 周期拖垮
SCAN_TIME_BUDGET = 70

# ══ P1 优化: WFV品种优先扫描 (2026-08-20) ══
# 策略: 每轮先扫WFV白名单品种 (正edge验证), 再扫其他品种
# 目的: 加速正edge品种开仓, 避免等待cursor轮转 (约245/40=6轮才覆盖一次)
WFV_SYMBOLS_PRIORITY = None  # 运行时填充, 由 _load_wfv_symbols_priority() 初始化

def _load_wfv_symbols_priority():
    """加载WFV白名单品种列表 (优先扫描用)"""
    global WFV_SYMBOLS_PRIORITY
    try:
        import edge_tracker as et
        et.load_wfv_edge(force=True)
        WFV_SYMBOLS_PRIORITY = list(set(s for s, _ in et._WFV_WHITELIST))
        print(f"[live_bridge] WFV优先扫描列表: {len(WFV_SYMBOLS_PRIORITY)} 个品种 {WFV_SYMBOLS_PRIORITY}")
    except Exception as e:
        print(f"[live_bridge] 加载WFV优先列表失败: {e}")
        WFV_SYMBOLS_PRIORITY = []
    return WFV_SYMBOLS_PRIORITY

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# [2026-08-26 修复] 配对止损冷却: 配对任一腿止损后, 该对 N 小时内禁止重开,
# 防止"止损→立刻重开→再止损"循环 (8/25 XAGUSD 5连亏 -20.52).
_PAIR_COOLDOWN_SEC = 6 * 3600          # 冷却 6 小时
_PAIR_LAST_STOP = {}                   # pair_ref -> 最近止损时间戳
_PAIR_STOP_FILE = os.path.join(DATA_DIR, "pair_cooldown.json")


def _pair_stop_now(pair_ref):
    """记录配对止损时间 (止损发生时调用)."""
    _PAIR_LAST_STOP[pair_ref] = time.time()
    try:
        with open(_PAIR_STOP_FILE, "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in _PAIR_LAST_STOP.items()
                       if time.time() - v < 48 * 3600}, f)
    except Exception:
        pass


def _pair_in_cooldown(pair_ref):
    """检查配对是否在止损冷却期."""
    if pair_ref in _PAIR_LAST_STOP:
        if time.time() - _PAIR_LAST_STOP[pair_ref] < _PAIR_COOLDOWN_SEC:
            return True
    # 从文件恢复 (进程重启后仍生效)
    try:
        if os.path.exists(_PAIR_STOP_FILE):
            with open(_PAIR_STOP_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            if pair_ref in d and time.time() - d[pair_ref] < _PAIR_COOLDOWN_SEC:
                _PAIR_LAST_STOP[pair_ref] = d[pair_ref]
                return True
    except Exception:
        pass
    return False


# [2026-08-26 修复] 品种级止损冷却: 单品种止损后 N 小时内禁止重开 (防
# 8/25 AUDJPY 单日20次"开仓→即止损→重开"循环). 冷却期比配对略短.
SYM_COOLDOWN_SEC = 4 * 3600            # 4 小时
_SYM_LAST_STOP = {}                    # symbol -> 最近止损时间戳


def _sym_stop_now(symbol):
    """记录品种止损时间."""
    _SYM_LAST_STOP[symbol] = time.time()


def _sym_in_cooldown(symbol):
    """检查品种是否在止损冷却期."""
    if symbol in _SYM_LAST_STOP:
        if time.time() - _SYM_LAST_STOP[symbol] < SYM_COOLDOWN_SEC:
            return True
    return False

# ══ 延迟补单机制（P0-5）═══════════════════════════════════════════
# [2026-08-21] 参考博森CCR延迟补单：价格跌至目标位后，等待反弹确认再补单
# 防范两种行情：1) 突然瀑布行情 2) 阴跌行情

DELAYED_ENTRY_THRESHOLD = 0.02  # 默认延迟阈值：2%
DELAYED_ENTRY_CHECK_INTERVAL = 60  # 检查间隔（秒）


def check_delayed_entry(symbol: str, target_price: float, current_price: float,
                        direction: str, delay_threshold: float = None) -> bool:
    """检查是否满足延迟补单条件。

    原理（参考博森CCR延迟补单）：
    - BUY: 价格跌破目标位后，等待反弹确认（从目标位反弹超过阈值）
    - SELL: 价格突破目标位后，等待回落确认（从目标位回落超过阈值）

    示例：
    - BUY目标1.0800，延迟阈值2%
    - 价格跌到1.0770（跌破目标）→ 触发延迟机制
    - 价格继续跌到1.0750 → 继续等待
    - 价格反弹到1.0916（1.0800×1.02）→ 触发补单 ✓

    参数：
        symbol: 品种代码
        target_price: 目标补单价位
        current_price: 当前价格
        direction: 方向（'BUY'或'SELL'）
        delay_threshold: 延迟阈值（默认2%）

    返回：
        True表示可以补单，False表示继续等待
    """
    if delay_threshold is None:
        delay_threshold = DELAYED_ENTRY_THRESHOLD

    if direction == 'BUY':
        # 买入：价格从跌破目标位反弹超过阈值
        # 条件：current_price >= target_price * (1 + delay_threshold)
        return current_price >= target_price * (1 + delay_threshold)
    elif direction == 'SELL':
        # 卖出：价格从突破目标位回落超过阈值
        # 条件：current_price <= target_price * (1 - delay_threshold)
        return current_price <= target_price * (1 - delay_threshold)

    return False


# 硬止损美元上限 (A+B+C/C2, 2026-08-18)
HARD_SL_USD_CAP = 250.0

# [2026-09-03 V5 深度优化] 更新策略映射，只保留盈利品种的策略
SYMBOL_STRATEGY_MAP = {
    # 盈利品种 (PF>=1.0)
    "CADJPY": ["TREND", "ICT", "DIV", "MR", "PASD"],
    "EURJPY": ["TREND", "ICT", "DIV", "MR", "PASD"],
    "GBPCAD": ["TREND", "ICT", "DIV", "MR", "PASD"],
    "AUDCHF": ["TREND", "ICT", "DIV", "MR", "PASD"],
    "GBPUSD": ["BO", "DIV", "MR", "TREND", "PASD", "SESSION"],
    "XAUUSD": ["OTAS", "PASD", "ICT", "SDP", "DIV", "MR", "BO"],
    # BTCUSD (保留，等待进化优化)
    "BTCUSD": ["OTAS", "PASD", "ICT", "DIV", "MR", "BO"],
    "ETHUSD": ["OTAS", "PASD", "ICT", "DIV", "MR", "BO"],
}


def load_keep_list(data_dir=DATA_DIR):
    """从账户模式回测缓存读取 KEEP 品种 (与报告/筛选决策一致)。"""
    path = os.path.join(data_dir, "_ub_partial.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return []
    return [k for k, v in d.items()
            if isinstance(v, dict) and v.get("decision") == "KEEP"]


def load_full_universe(data_dir=DATA_DIR):
    """返回全部可交易品种 (动态宇宙, 由 build_full_universe 填充)。"""
    return [s for s, c in su.UNIVERSE.items()
            if c.get("tradable", False) and c.get("trade_mode", 4) in (1, 2, 4)]


def init_bridge(data_dir=DATA_DIR):
    """接入 KEEP-32 验证宇宙 (回测 PF≥1.15 且 n≥30 的品种), 与回测同源。

    交集逻辑: 品种须同时 (a) 在券商可交易宇宙 su.UNIVERSE(含 pip/pip_usd/spread
    真实规格) 且 (b) 是回测验证通过的 KEEP —— 既保证有真实规格, 又剔除 216 个
    未验证品种 (修复断层 A: 此前误跑全 245 导致实盘 PF 0.87 净亏)。
    KEEP 缓存缺失时安全回退全宇宙, 绝不静默停摆。
    """
    su.build_full_universe(data_dir)
    full = load_full_universe(data_dir)
    keep = set(load_keep_list(data_dir))
    if not keep:
        return full  # 安全回退: KEEP 缓存缺失时不过度收敛
    return [s for s in full if s in keep]


def _fetch_df(mt5, symbol, tf, count):
    """从 MT5 拉取指定周期 K 线 → DataFrame (time/open/high/low/close/volume)。"""
    try:
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    except Exception:
        return None
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    return df


# ── 2026-08-15 优化: 质量闸 / Meta-Labeling / Kelly (P0-2 + P1) ──
_KEEP_BEST_CACHE = None


def _load_keep_best():
    """从回测缓存读 KEEP 品种的最优策略映射 (供 Meta-Labeling 同策略过滤)。"""
    global _KEEP_BEST_CACHE
    if _KEEP_BEST_CACHE is not None:
        return _KEEP_BEST_CACHE
    m = {}
    try:
        p = os.path.join(DATA_DIR, "_ub_partial.json")
        if os.path.exists(p):
            d = json.load(open(p, encoding="utf-8"))
            for sym, v in d.items():
                if isinstance(v, dict) and v.get("decision") == "KEEP":
                    m[sym] = v.get("best")
    except Exception:
        pass
    _KEEP_BEST_CACHE = m
    return m


def _slope_bias(df, window=20):
    """收盘价线性斜率方向 → 'BUY'/'SELL'/'NEUTRAL' (任何异常返回 NEUTRAL)。"""
    try:
        closes = df['close'].astype(float).values
        if len(closes) < window:
            return 'NEUTRAL'
        y = closes[-window:]
        x = np.arange(len(y), dtype=float)
        slope = np.polyfit(x, y, 1)[0]
        ref = y.mean()
        if ref == 0:
            return 'NEUTRAL'
        rel = slope * len(y) / ref
        if rel > 0.004:
            return 'BUY'
        if rel < -0.004:
            return 'SELL'
        return 'NEUTRAL'
    except Exception:
        return 'NEUTRAL'


def _mtf_resonance_gate(h4, d1, direction):
    """多周期共振: H4/D1 趋势与信号方向一致性。

    返回 (ok, scale, msg); 失败开放(默认放行 scale=1.0, 不阻断交易链)。
      - D1 逆势 + H4 逆势 → 硬拒 (双逆势, 高概率逆势单)
      - 仅 D1 逆势         → 放行但降仓 0.6
      - 同向(或部分)       → 共振度 0.7~1.0 微调仓
    修复断层 B: live 信号此前旁路了 EDGE_GATE/多周期共振。
    """
    try:
        d1b = _slope_bias(d1, 20)
        h4b = _slope_bias(h4, 20)
        if d1b != 'NEUTRAL' and d1b != direction:
            if h4b != 'NEUTRAL' and h4b != direction:
                return False, 1.0, f"D1={d1b}/H4={h4b} 双逆势"
            return True, 0.6, f"D1逆势={d1b}"
        agree = sum(1 for b in (h4b, d1b) if b == direction)
        scale = min(1.0, 0.7 + 0.15 * agree)
        return True, scale, f"D1={d1b}/H4={h4b} 共振{agree}"
    except Exception:
        return True, 1.0, "共振闸失败开放"


def _meta_scale(symbol, strat):
    """Meta-Labeling (规则版): 触发策略 == 该品种 KEEP 最优策略 → 1.0,
    否则降 0.5 (2026-08-24: 0.8→0.5, 非best策略信号质量差, 强化降权避免
    频繁最小手亏损). 失败开放(无缓存 → 1.0)。绝不硬拒, 仅调仓。"""
    try:
        best = _load_keep_best().get(symbol)
        if best is None:
            return 1.0
        return 1.0 if strat == best else 0.5
    except Exception:
        return 1.0


def _kelly_fraction(symbol):
    """分数凯利仓位标定 (上限保护, 失败回退 1.0)。

    用回测 win_rate(wr) 与 avg_w/avg_l 推算 payoff b, 算 f=p-(1-p)/b;
    取 0.5×分数凯利(更稳), 封顶 1.0。
    [2026-08-24 优化] 保底 0.3→0.5 (WFV白名单品种 0.6): 此前保底过低导致
    正edge品种也被压到最小手0.01, 赚钱能力被压制 (EURNZD理论f=0.115但保底
    0.3 × 其他降权 → eff_risk仅0.42%). KEEP/WFV品种回测已验证正edge,
    提高保底让仓位匹配实际风险预算。
    """
    try:
        p = os.path.join(DATA_DIR, "_ub_partial.json")
        d = json.load(open(p, encoding="utf-8"))
        st = d.get(symbol, {}).get("stats", {})
        wr = st.get("wr")
        aw = st.get("avg_w")
        al = st.get("avg_l")
        if not (wr and aw and al and al > 0):
            return 1.0
        p = wr / 100.0
        b = aw / al
        if b <= 0:
            return 1.0
        f = p - (1 - p) / b
        f = max(0.0, min(1.0, f)) * 0.5   # 分数凯利, 减半更稳
        floor = 0.6 if et.is_wfv_allowed(symbol) else 0.5
        return max(floor, min(1.0, f))    # 保底(按WFV提权), 封顶 1.0
    except Exception:
        return 1.0


def _calc_real_adx(h1, period=14):
    """从 H1 K 线计算真实 ADX（Wilder 方法）。

    [2026-09-02 V3.4] 替代原 D1 斜率近似: 88% 品种 adx=None/0 导致 V3.3 闸门
    因 float(None) 异常被 except 吞掉而全部绕过。真实 ADX 需 ≥ period+20 根。

    [2026-09-02 V4 修复] 原实现计算的是 DX 而非 ADX。ADX = smoothed average of DX.
    """
    try:
        if len(h1) < period * 3:
            return None
        high = h1['high'][-period*3:].astype(float)
        low = h1['low'][-period*3:].astype(float)
        close = h1['close'][-period*3:].astype(float)

        # 计算 TR (True Range)
        tr = np.zeros(len(high))
        for i in range(1, len(high)):
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i-1]),
                abs(low[i] - close[i-1])
            )
        atr = np.mean(tr[-period:])

        # 计算 +DM 和 -DM
        plus_dm = np.zeros(len(high))
        minus_dm = np.zeros(len(high))
        for i in range(1, len(high)):
            up = high[i] - high[i-1]
            down = low[i-1] - low[i]
            plus_dm[i] = up if (up > down and up > 0) else 0
            minus_dm[i] = down if (down > up and down > 0) else 0

        # 计算 +DI 和 -DI
        if atr > 0:
            plus_di = 100 * np.mean(plus_dm[-period:]) / atr
            minus_di = 100 * np.mean(minus_dm[-period:]) / atr
        else:
            plus_di = 25.0
            minus_di = 25.0

        # 计算 DX (Directional Index)
        if (plus_di + minus_di) > 0:
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        else:
            dx = 0.0

        # ADX = DX 的 smoothed average (Wilder 方法)
        # 需要至少 period 个 DX 值来计算 ADX
        dx_values = []
        for i in range(period, len(high) - period):
            # 重新计算每个窗口内的 DI 和 DX
            atr_i = np.mean(tr[i:i+period])
            if atr_i > 0:
                pdi_i = 100 * np.mean(plus_dm[i:i+period]) / atr_i
                mdi_i = 100 * np.mean(minus_dm[i:i+period]) / atr_i
                if (pdi_i + mdi_i) > 0:
                    dx_i = 100 * abs(pdi_i - mdi_i) / (pdi_i + mdi_i)
                    dx_values.append(dx_i)

        if len(dx_values) >= period:
            adx = np.mean(dx_values[-period:])
        else:
            adx = dx  # 回退到当前 DX

        return adx
    except Exception:
        return None


def _regime_inputs(h1, h4, d1):
    """从 K 线构造 regime_router 所需的 (vol_now, vol_history, adx).

    [2026-08-17 修复] 原 scan_symbol 调 rr.classify/route/pref_index, 但 regime_router
    已重写为 detect_regime/select_strategies 接口 (无 classify/route/pref_index)。
    这里从 H1 收益率算波动率、从 D1 收盘价斜率近似 ADX, 适配新接口, 消除
    AttributeError: module 'regime_router' has no attribute 'classify' (此前被 MAX_POS=8
    的永久 SKIP 掩盖, 从未真正开仓故未触发)。

    [2026-09-02 V3.4] 优先使用真实 ADX (H1 Wilder): D1 斜率近似 88% 失败导致
    float(None) 异常被吞 → V3.3 闸门失效。真实 ADX 在 H1≥34 根时可用。
    """
    try:
        c = np.asarray(h1['close'], dtype=float)
        if len(c) >= 2:
            rets = np.diff(np.log(c))
        else:
            rets = np.array([0.01])
        vol_now = float(np.std(rets[-20:])) if len(rets) >= 20 else float(np.std(rets)) if len(rets) else 0.01
        vol_hist = rets.astype(float)
        # V3.4: 真实 ADX (优先) → 斜率近似 (兜底)
        real_adx = _calc_real_adx(h1, period=14)
        if real_adx is not None:
            adx = real_adx
        else:
            cd = np.asarray(d1['close'], dtype=float)
            if len(cd) >= 2:
                slope = abs((cd[-1] - cd[0]) / (abs(cd[0]) + 1e-9))
                adx = float(min(50.0, 15.0 + slope * 200.0))
            else:
                adx = 20.0
        return vol_now, vol_hist, adx
    except Exception:
        return 0.01, np.array([0.01]), 20.0


def _ema_fast(a, p):
    """快速EMA (纯numpy, 供结构透镜使用)."""
    a = np.asarray(a, dtype=float)
    if len(a) == 0:
        return np.array([])
    k = 2.0 / (p + 1)
    e = np.full(len(a), np.nan)
    e[0] = a[0]
    for i in range(1, len(a)):
        e[i] = a[i] * k + e[i - 1] * (1 - k)
    return e


def scan_symbol(guardian, symbol, cfg, equity, risk_pct=0.4, strategies=None):
    """对单品种跑指定策略列表 (类别适配), 取最近一根的新鲜信号, 用 risk_lot 定手。

    返回 (proposal | None, reason)
    """
    # [2026-09-02 V4] 品种白名单: 仅允许 W/L>1 且净盈利品种, 禁用垃圾股票指数
    # 来源: 全月 842 笔平仓, 834 笔亏损均来自 ADX<25 的垃圾品种 (XPEV/CMPUSD/TME/VIX 等)
    if symbol not in V4_SYMBOL_GATE:
        return None, f"{symbol} V4 拒单(非白名单品种: {V4_SYMBOL_GATE.get(symbol, '无盈利记录')})"
    for suffix in V4_FORBIDDEN_SUFFIXES:
        if symbol.endswith(suffix):
            return None, f"{symbol} V4 拒单(禁用后缀 {suffix})"

    # [2026-08-20] 品种-策略适配: 优先使用 WFV 验证过的策略列表
    if strategies is None:
        strategies = SYMBOL_STRATEGY_MAP.get(symbol, ["SDP", "ICT", "DIV", "MR", "VP", "TREND", "BO"])
    # [2026-08-18 D1] 实盘 edge 门控: 实盘 pf<1.0 或 样本不足且回测 pf<1.2 → 禁开.
    #   治本核心: 把系统从"全开负 edge"变成"只开正 edge 品种".
    if not et.is_symbol_allowed(symbol):
        return None, (f"{symbol} 实盘edge不达标(禁开: 负edge品种 / 样本不足且回测pf<1.2)")
    mt5 = guardian.mt5
    h1 = _fetch_df(mt5, symbol, mt5.TIMEFRAME_H1, 400)
    h4 = _fetch_df(mt5, symbol, mt5.TIMEFRAME_H4, 300)
    d1 = _fetch_df(mt5, symbol, mt5.TIMEFRAME_D1, 200)
    if h1 is None or h4 is None or d1 is None:
        return None, f"{symbol} K线数据缺失 (H1/H4/D1 不全)"

    # [2026-09-02 V3.3+V3.4] 开仓趋势门槛(主路径前置): 仅大趋势环境(adx>=ENTRY_ADX_MIN)进场,
    #   震荡市(range)拒单——全月 -190 净亏主源(chop 进场). 回测验证 PF 0.19→1.31.
    #   ⚠️ 必须置于融合扫描(fusion_scan_symbol, line 461 提前 return)之前, 否则主路径绕过本闸.
    #   V3.4: adx 缺失时保守拒单（宁可错过不可错开）.
    vol_now, vol_hist, adx = _regime_inputs(h1, h4, d1)
    try:
        adx_val = float(adx) if adx is not None else 0.0
        if adx_val < ENTRY_ADX_MIN:
            return None, f"{symbol} 震荡市拒单(ADX={adx_val:.1f}<{ENTRY_ADX_MIN:.0f})"
    except Exception:
        return None, f"{symbol} 震荡市拒单(ADX={adx})"

    # --- [2026-08-30 P7] 融合引擎优先: 若策略列表含 OTAS/PASD 则走融合扫描 ---
    # 融合扫描自动处理共振、权重、风控; 否则回退原有路由逻辑.
    _has_fusion = any(_s in ("OTAS", "PASD") for _s in (strategies or []))
    if _has_fusion:
        try:
            from strategy_fusion_bridge import fusion_scan_symbol
            _prop, _reason = fusion_scan_symbol(guardian, symbol, cfg, equity, risk_pct, strategies)
            if _prop:
                _prop["fusion"] = True
            return _prop, _reason
        except Exception as _e:
            print(f"[live_bridge] fusion_scan 失败, 回退: {_e}")

    # --- P0-2 状态机路由: 按市况动态选策略 (适配 regime_router 当前接口) ---
    vol_now, vol_hist, adx = _regime_inputs(h1, h4, d1)

    # [2026-08-18 B] 波动率恐慌闸: 当前波动率处近期滚动 99 分位 1.5 倍以上(极端波动)→
    #   暂停新开仓, 防高波动尾部爆亏(USDSEK -1395pip 类). 失败开放.
    try:
        _c = np.asarray(h1['close'], dtype=float)
        if len(_c) >= 22:
            _r = np.diff(np.log(_c))
            _roll = np.array([float(np.std(_r[max(0, i - 20):i + 1]))
                              for i in range(20, len(_r))])
            if len(_roll) >= 10:
                _p99 = float(np.percentile(_roll, 99))
                if vol_now > _p99 * 1.5 and vol_now > 0:
                    return None, (f"{symbol} 波动率恐慌(vol={vol_now:.4f}>"
                                  f"{_p99 * 1.5:.4f}), 暂停新开仓")
    except Exception:
        pass

    # [2026-08-28 P2] 结构透镜: 传入价格/EMA200 判定方向与ADX冲突时降级震荡
    try:
        _close_arr = h1['close'].values.astype(float)
        _ema200 = _ema_fast(_close_arr, 200)
        _c_now = float(_close_arr[-1])
        _e200 = float(_ema200[-1]) if not np.isnan(_ema200[-1]) else None
        ordered = rr.select_strategies(vol_now, vol_hist, adx,
                                       close=_c_now, ema200=_e200)
    except Exception:
        ordered = rr.select_strategies(vol_now, vol_hist, adx)
    routed = [s for s, _ in ordered]
    pidx = {s: i for i, (s, _) in enumerate(ordered)}

    # [2026-08-24 优化] KEEP最优策略优先: 市况路由可能不含该品种回测验证的
    # best策略 (如 EURNZD best=DIV 但市况路由优先 TREND/MR), 导致频繁开
    # 非best信号 → 质量差+最小手亏损. 将 best 策略插入路由最前, 保证
    # 回测最优策略优先评估 (仅当信号新鲜度满足时).
    try:
        _best = _load_keep_best().get(symbol)
        if _best and _best in STRATEGY_REGISTRY_V4:
            if _best in routed:
                routed.remove(_best)
            routed.insert(0, _best)
            # 同步更新 pidx (best 优先级最高)
            pidx = {s: i for i, s in enumerate(routed)}
    except Exception:
        pass

    # [2026-08-26 P4-1] SESSION 时段动量: 若品种配置含 SESSION 且路由未含,
    # 追加到路由尾部 (时段策略只在特定小时触发, 不影响其他信号).
    try:
        if 'SESSION' in (strategies or []) and 'SESSION' not in routed:
            routed.append('SESSION')
            pidx['SESSION'] = len(routed) - 1
    except Exception:
        pass

    n = len(h1)
    cands = []
    for name in routed:
        gen = STRATEGY_REGISTRY_V4.get(name)
        if gen is None:
            continue
        fb = STRAT_FRESH_BARS.get(name, FRESH_BARS)
        fresh = n - fb
        try:
            sigs = gen(h1, h4, d1, cfg)
        except Exception:
            continue
        for s in sigs:
            _st = s.get("strat", "")
            if _st and not et.is_strategy_allowed(_st):
                continue   # [2026-08-18 D5] 该策略实盘负 edge, 跳过其信号
            # [2026-08-21 优化] WFV 品种-策略组合级精确门控: 白名单品种只允许
            # 样本外验证通过的策略开仓. 此前 US500/NZDUSD 等白名单品种混跑
            # TREND(样本外 pf=0.62/0.81) 等未验证策略 → 实盘亏损. 用 WFV
            # 白名单组合(最可靠)精确约束, 未通过组合仅记录不阻断非白名单品种.
            # [2026-08-26 例外] SESSION 时段动量: 独立统计alpha (时段方向性
            # 偏差), 非回测类策略, 不受 WFV 组合约束 (无样本外数据可验证).
            if _st == 'SESSION':
                pass  # 时段策略独立放行
            elif _st and et.is_wfv_allowed(symbol, _st):
                pass  # 该组合已通过样本外验证, 放行
            elif _st and et.is_wfv_allowed(symbol):
                # 品种在白名单, 但该策略组合未通过 → 拒绝 (严格约束)
                continue
            # 非白名单品种走原品种级/策略级门控, 不受此约束
            bar = s.get("bar", -1)
            if isinstance(bar, int) and bar >= fresh:
                cands.append(s)

    if not cands:
        return None, f"{symbol} 近窗口内无新鲜信号 ({'/'.join(strategies)})"

    # 取状态机优先级最高的信号; 同优先级取最新一根
    cands.sort(key=lambda s: (pidx.get(s.get("strat"), 99), -s["bar"]))
    sig = cands[0]

    entry = float(sig["entry"])
    sl = float(sig["sl"])
    tp = float(sig["tp"])
    pip = cfg["pip"]
    sl_pips = abs(sl - entry) / pip
    if sl_pips <= 0 or not math.isfinite(sl_pips):
        return None, f"{symbol} SL无效 (sl_pips={sl_pips})"

    direction = "BUY" if sig["side"] == 1 else "SELL"

    # ── P0-2 多周期共振质量闸 (修复断层 B: 信号旁路 EDGE_GATE/共振) ──
    res_ok, res_scale, res_msg = _mtf_resonance_gate(h4, d1, direction)
    if not res_ok:
        return None, f"{symbol} 多周期逆势拒单 ({res_msg})"

    # ── P3-3 FVG 回补确认过滤 (SMC 扫流动性 + 公允价值缺口) ──
    # [2026-09-04 修复] 原块位于共振闸之前引用未定义 res_scale → NameError 被
    # try/except 吞掉 → FVG 过滤从未生效. 移到共振闸赋值之后, 逻辑真正落地.
    try:
        import fvg_filter as fvgf
        _fok, _fscore, _fdet = fvgf.fvg_confirm(
            h1['high'].values, h1['low'].values, h1['close'].values,
            direction, pip)
        if _fok:
            res_scale *= (1.0 + min(0.2, _fscore * 0.2))  # 有结构确认, 小幅加分
        else:
            res_scale *= 0.7  # 无SMC结构确认, 降权 (不硬拒)
    except Exception:
        pass

    # ── [2026-09-04 V5] K线形态 + 动能方向硬闸 ──
    # 用户需求: "学会看K线形态/动能, 提高进场点准确率, 进场就赚钱".
    # 用 H1 最近50根K线识别 (吞没/锤子/流星) + 趋势/RSI/量能, 与信号方向
    # 冲突(逆势/见顶见底形态) → 拒单; 同向形态确认 → 放行加分.
    # fail-closed 由 _v5_entry_optimizer.direction_veto 的 allow=False 硬拒实现,
    # 模块异常时 fail-open (不阻断交易链).
    try:
        from _v5_entry_optimizer import EntryOptimizerV5
        _v5a = EntryOptimizerV5().analyze_df(h1)
        _v5ok, _v5scale, _v5why = EntryOptimizerV5.direction_veto(_v5a, direction)
        if not _v5ok:
            return None, f"{symbol} V5形态/动能拒单 ({_v5why})"
        res_scale *= _v5scale   # 同向确认加分(≤1.15) / 中性1.0
        _v5_gate = _v5why
    except Exception:
        _v5_gate = "V5模块异常(fail-open)"

    # ── [2026-08-26 P4-2] 时段偏差融合 (Session Bias Fusion) ──
    # 将 SESSION 时段统计优势注入所有策略: 强偏差时段(服务器h8/h9)同向信号
    # 加分(最高1.3x), 反向信号降权(0.7x). 让时段alpha增强全系统而非独立跑.
    try:
        import session_momentum as _sm
        _scfg = _sm.SESSION_STRATEGY_MAP.get(symbol)
        if _scfg:
            _now_ts = h1['time'].values[-1]
            _cur_h = datetime.datetime.fromtimestamp(float(_now_ts)).hour
            _bias_hour = _scfg['hour']
            _bias_dir = _scfg['direction']
            if _cur_h == _bias_hour:
                if direction == _bias_dir:
                    res_scale *= 1.3   # 同向: 时段优势加成
                else:
                    res_scale *= 0.7   # 反向: 时段逆势降权
    except Exception:
        pass

    # ── P1+P2: 高级过滤器（多时间框架 + ML + 微观模式 + VaR）──
    try:
        adv_filter = get_advanced_filter()
        atr_val = float(np.std(np.diff(np.log(h1['close'].values[-20:])))) if len(h1) > 20 else 0.01
        adx_val = float(sig.get('adx', 25.0))
        positions_list = []  # 简化：暂不传入持仓列表
        filter_ok, filter_scale, filter_reason = adv_filter.filter_signal(
            symbol, h1['close'].values, h4['close'].values, d1['close'].values,
            direction, sig.get('strat', ''), atr_val, adx_val, equity, positions_list
        )
        if not filter_ok:
            return None, f"{symbol} 高级过滤器拒单: {filter_reason}"
        # 应用过滤器缩放
        res_scale *= filter_scale
    except Exception as e:
        # 失败开放，不阻断交易链
        pass

    # ── P1 Meta-Labeling (规则版): 触发策略须为该品种 KEEP 最优策略, 否则降仓 ──
    meta_scale = _meta_scale(symbol, sig.get("strat", ""))

    # ── P1 Kelly 仓位标定: 用回测 wr/pf 算分数凯利, 封顶保护 (绝不放大风险) ──
    kelly = _kelly_fraction(symbol)

    eff_risk = risk_pct * res_scale * meta_scale * kelly

    # ── V2 进化层 (2026-09-01 全网研究落地): 波动率目标化 + regime权重 + Meta硬闸 ──
    # 全部失败开放: 任何异常 → 保持旧 eff_risk, 绝不阻断交易链. 仅减不增风险.
    try:
        from evolution_engine import (
            EVOLUTION_V2_ENABLED, ev2_symbol_daily_vol_from_h1,
            ev2_size_multiplier, ev2_meta_gate, ev2_composite_confidence,
            ev2_vol_spike_ratio_now,
        )
        if EVOLUTION_V2_ENABLED:
            _dv = ev2_symbol_daily_vol_from_h1(h1['close'].values)
            _vn, _vh, _adx = _regime_inputs(h1, h4, d1)
            try:
                _vs, _ts = rr.detect_regime(_vn, _vh, _adx)
                _prio = dict(rr.select_strategies(_vn, _vh, _adx)).get(sig.get("strat", ""), 1)
            except Exception:
                _vs, _prio = "mid", 1
            _mult, _bd = ev2_size_multiplier(_dv, _prio, regime_vol_state=_vs)
            # Meta 硬闸: 低置信度/波动尖峰 → 拒单
            _stt = {}
            try:
                _ubp = os.path.join(DATA_DIR, "_ub_partial.json")
                _stt = json.load(open(_ubp, encoding="utf-8")).get(symbol, {}).get("stats", {})
            except Exception:
                pass
            _conf = ev2_composite_confidence(_stt.get("wr"), _stt.get("pf"))
            _spike = ev2_vol_spike_ratio_now(_vn, _vh)
            _gok, _gwhy = ev2_meta_gate(_conf, _spike, _vs)
            if not _gok:
                return None, f"{symbol} V2 Meta闸拒单({_gwhy})"
            eff_risk = eff_risk * _mult
    except Exception:
        pass  # 失败开放: 保持旧 eff_risk

    # [2026-08-18 C1] 收集数据阶段: allow_min_lot 放开最小手地板(修 5191 拒单);
    #   hard_usd_cap 仍卡住极端宽 SL(防爆亏). 与 guardian 硬$上限双保险.
    lot, risk, ok = su.risk_lot(cfg, sl_pips, equity, eff_risk,
                                allow_min_lot=True, hard_usd_cap=HARD_SL_USD_CAP)
    if not ok or lot <= 0:
        return None, (f"{symbol} 开不起(最小手风险超限 "
                      f"sl={sl_pips:.1f}pip 风险${risk:.2f})")

    proposal = {
        "symbol": symbol,
        "direction": direction,
        "entry": round(entry, 5),
        "sl": round(sl, 5),
        "tp": round(tp, 5),
        "sl_pts": round(sl_pips, 2),
        "tp_pts": round(abs(tp - entry) / pip, 2),
        "lot": lot,
        "pip_usd_per_lot": cfg["pip_usd"],
        "spread": cfg.get("spread_price", 0.0),
        "strategy": sig.get("strat", "unknown"),
        "adx": adx,  # V3.4: 真实 ADX（非 None）
        "regime": sig.get("regime", ""),
    }
    return proposal, (f"{sig.get('strat')} 信号 @bar{sig['bar']} "
                      f"{direction} lot={lot} sl={sl_pips:.1f}pip 风险${risk:.2f} "
                      f"[共振{res_scale:.2f}·V5:{_v5_gate}·元标签{meta_scale:.2f}·Kelly{kelly:.2f}]")


def _load_cursor():
    try:
        with open(ROTATE_FILE, "r", encoding="utf-8") as f:
            return int(json.load(f).get("idx", 0))
    except Exception:
        return 0


def _save_cursor(idx):
    try:
        with open(ROTATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"idx": idx}, f)
    except Exception:
        pass


def scan_all(guardian, symbols, existing, open_dirs=None,
             equity=None, risk_pct=0.4, max_pos=15, data_dir=DATA_DIR,
             class_map=None, batch=ROTATE_BATCH, time_budget=SCAN_TIME_BUDGET):
    """对全宇宙品种做同源 live 扫盘 (轮询 + 时间预算 + 类别适配策略)。

    每轮从持久化 cursor 起扫 BATCH 个品种后回绕, 确保全部品种周期性被覆盖;
    受最大持仓约束; 单轮超 time_budget 秒即停 (不拖垮 120s 周期)。
    返回 [ {symbol, proposal|None, reason}, ... ]
    """
    if class_map is None:
        class_map = CLASS_STRATEGY_MAP
    out = []
    all_cands = []       # [2026-08-21 P1P2] 候选信号收集器 (WFV优先扫描段使用, 修复NameError)
    scanned = 0          # 本轮已扫品种计数
    skip_info = []       # 被拒品种原因记录
    existing = set(existing)  # 已在持仓品种集合 (调用方传list, 统一转set)
    mt5 = guardian.mt5
    try:
        positions = mt5.positions_get() or []
    except Exception:
        positions = []
    # [2026-08-18 D1] 定期刷新实盘 edge (5分钟一次, 不阻塞交易周期)
    try:
        et.refresh_if_stale(mt5)
    except Exception:
        pass
    open_count = len(positions)
    if open_count >= max_pos:
        out.append({"symbol": None, "proposal": None,
                    "reason": f"已达最大持仓 {max_pos}, 本轮不开新仓"})
        return out

    # ── [2026-08-22 P3-1] 统计套利配对扫描 (每轮限1对, 防拖垮周期) ──
    # 高相关品种对价差 z-score 偏离 → 反向开双腿, 回归平仓.
    # 只做双腿都未持仓的配对; 配对内两腿各占一仓, 计入 max_pos.
    try:
        import pairs_trader as pt
        _pairs_used = 0
        for _pa, _pb, _cmin, _ez, _xz, _sz in pt.DEFAULT_PAIRS:
            if _pa in existing or _pb in existing:
                continue  # 任一腿已持仓, 跳过该配对
            _pref = f"{_pa}/{_pb}"
            # [2026-08-26 修复] 止损冷却: 该对最近止损过则暂缓重开
            if _pair_in_cooldown(_pref):
                continue
            if _pairs_used >= 1:
                break
            _da = _fetch_df(mt5, _pa, mt5.TIMEFRAME_H1, 500)
            _db = _fetch_df(mt5, _pb, mt5.TIMEFRAME_H1, 500)
            if _da is None or _db is None or len(_da) < 300 or len(_db) < 300:
                continue
            _cfa = su.UNIVERSE.get(_pa) or {}
            _cfb = su.UNIVERSE.get(_pb) or {}
            _pr = pt.build_pair_signal(_pa, _pb, _da['close'].values,
                                       _db['close'].values, _cfa, _cfb,
                                       corr_min=_cmin, entry_z=_ez,
                                       exit_z=_xz, stop_z=_sz)
            if _pr.get('signal') in ('LONG_A_SHORT_B', 'SHORT_A_LONG_B'):
                _la, _lb = _pr['leg_a'], _pr['leg_b']
                # [2026-08-24 修复] 配对腿风险失控: hard_usd_cap=250 绝对美元
                # 对 $518 净值账户过松 (XAG 腿曾算到 $190 = 37%净值!).
                # 改为相对净值 cap: 单腿最大 = 净值 × 单笔风险% × 2 (双腿合计
                # ≤ 2×单笔风险预算, 且每条腿都过审度司单笔上限).
                _leg_cap = max(1.0, equity * (risk_pct / 100.0) * 2.0)
                # 双腿各按 eff_risk 的一半定手 (配对合计 ≈ 单笔风险)
                _lot_a, _risk_a, _oka = su.risk_lot(
                    _cfa, _la['sl_pts'], equity, risk_pct * 0.5,
                    allow_min_lot=True, hard_usd_cap=_leg_cap)
                _lot_b, _risk_b, _okb = su.risk_lot(
                    _cfb, _lb['sl_pts'], equity, risk_pct * 0.5,
                    allow_min_lot=True, hard_usd_cap=_leg_cap)
                if _oka and _okb and _lot_a > 0 and _lot_b > 0:
                    # [2026-08-24 修复] SL价格用真实 pip 换算 (原硬编码0.0001,
                    # 对 XAU(pip=0.01)/XAG(pip=0.001)/指数(pip=1.0) 全错)
                    _pipa = float(_cfa.get('pip', 0.0001) or 0.0001)
                    _pipb = float(_cfb.get('pip', 0.0001) or 0.0001)
                    _pa_pp = {
                        "symbol": _pa, "direction": _la['direction'],
                        "entry": _la['entry'], "sl": round(_la['entry'] -
                            (_pipa * _la['sl_pts'] if _la['direction']=='BUY'
                             else -_pipa * _la['sl_pts']), 5),
                        "tp": 0.0, "sl_pts": _la['sl_pts'],
                        "tp_pts": _la['tp_pts'], "lot": _lot_a,
                        "pip_usd_per_lot": _cfa.get('pip_usd', 1.0),
                        "spread": _cfa.get('spread_price', 0.0),
                        "strategy": "PAIR", "adx": None,
                        "regime": "pair_trade",
                        "pair_ref": f"{_pa}/{_pb}"}
                    _pb_pp = {
                        "symbol": _pb, "direction": _lb['direction'],
                        "entry": _lb['entry'], "sl": round(_lb['entry'] -
                            (_pipb * _lb['sl_pts'] if _lb['direction']=='BUY'
                             else -_pipb * _lb['sl_pts']), 5),
                        "tp": 0.0, "sl_pts": _lb['sl_pts'],
                        "tp_pts": _lb['tp_pts'], "lot": _lot_b,
                        "pip_usd_per_lot": _cfb.get('pip_usd', 1.0),
                        "spread": _cfb.get('spread_price', 0.0),
                        "strategy": "PAIR", "adx": None,
                        "regime": "pair_trade",
                        "pair_ref": f"{_pa}/{_pb}"}
                    all_cands.append((_pa, _pa_pp,
                                      f"配对z={_pr['z']:.2f} {_pr['reason']}"))
                    all_cands.append((_pb, _pb_pp,
                                      f"配对z={_pr['z']:.2f} {_pr['reason']}"))
                    _pairs_used += 1
                    print(f"[live_bridge] 配对信号: {_pa}/{_pb} "
                          f"z={_pr['z']:.2f} corr={_pr['corr']:.2f}")
    except Exception as _pex:
        print(f"[live_bridge] 配对扫描跳过: {_pex}")
    # [2026-08-18 D2] 总浮亏预算: 账户浮亏>净值2% 暂停新开, 防慢血失控
    try:
        _eq = float(mt5.account_info().equity)
        _float_loss = sum(p.profit for p in positions)
        if _float_loss < -_eq * et.FLOAT_LOSS_BUDGET:
            out.append({"symbol": None, "proposal": None,
                        "reason": f"总浮亏 ${_float_loss:.2f} > 净值{et.FLOAT_LOSS_BUDGET*100:.0f}% 预算, 暂停新开"})
            return out
    except Exception:
        pass

    slots = max_pos - open_count
    if equity is None:
        try:
            acc = mt5.account_info()
            equity = float(acc.equity) if acc else 1000.0
        except Exception:
            equity = 1000.0

    total = len(symbols)
    if total == 0:
        return out
    start = _load_cursor() % total

    # ══ P1 优化: WFV品种优先扫描 ══
    # 先尝试扫描WFV白名单品种 (正edge验证), 每轮最多WFV_PRIORITY_BATCH个
    WFV_PRIORITY_BATCH = 12
    # [2026-08-28 修复] SESSION 时段优先: 目标时段(h8/h9)先扫 SESSION 品种,
    # 确保时段策略不因轮转错过触发窗口 (今日13-14点未触发根因).
    try:
        import session_momentum as _sm
        _sess_syms = [s for s in symbols
                      if s in _sm.SESSION_STRATEGY_MAP]
        if _sess_syms:
            _now_h = datetime.datetime.fromtimestamp(
                float(mt5.copy_rates_from_pos(_sess_syms[0], mt5.TIMEFRAME_H1, 0, 1)[0][0])
            ).hour if _sess_syms else -1
            for _ss in _sess_syms:
                _scfg = _sm.SESSION_STRATEGY_MAP.get(_ss, {})
                if _now_h != _scfg.get('hour'):
                    continue  # 非目标时段, 跳过
                if _ss in existing or _ss in {s for s, _, _ in all_cands}:
                    continue
                if _sym_in_cooldown(_ss):
                    continue
                _cfg = su.UNIVERSE.get(_ss)
                if _cfg is None or not _cfg.get("tradable", True):
                    continue
                _strs = SYMBOL_STRATEGY_MAP.get(_ss, [])
                _prop, _reason = scan_symbol(guardian, _ss, _cfg, equity,
                                             risk_pct, _strs)
                if _prop:
                    all_cands.append((_ss, _prop, _reason))
                else:
                    skip_info.append((_ss, _reason))
                scanned += 1
                if scanned >= batch:
                    pass  # 时段优先不阻塞, 但继续
    except Exception:
        pass
    if WFV_SYMBOLS_PRIORITY and len(WFV_SYMBOLS_PRIORITY) > 0:
        vfv_scanned = 0
        for sym in WFV_SYMBOLS_PRIORITY:
            if sym in existing:
                continue
            # [2026-08-26 修复] 品种止损冷却
            if _sym_in_cooldown(sym):
                continue
            cfg = su.UNIVERSE.get(sym)
            if cfg is None or not cfg.get("tradable", True):
                continue
            strs = SYMBOL_STRATEGY_MAP.get(sym, CLASS_STRATEGY_MAP.get(cfg.get("cls"), ["SDP", "ICT", "DIV", "MR", "VP", "TREND", "BO"]))
            proposal, reason = scan_symbol(guardian, sym, cfg, equity, risk_pct, strs)
            if proposal:
                all_cands.append((sym, proposal, reason))
                scanned += 1
                vfv_scanned += 1
            else:
                skip_info.append((sym, reason))
                scanned += 1
            if vfv_scanned >= WFV_PRIORITY_BATCH or scanned >= batch:
                break
        if vfv_scanned > 0:
            print(f"[live_bridge] WFV优先扫描: {vfv_scanned} 个品种, {len(all_cands)} 个候选")

    # 然后继续从cursor位置扫描其他品种
    idx = start
    # scanned 延续 WFV 优先段已扫计数, 避免重复超过 batch 限制
    t0 = time.time()
    for _ in range(total - len(all_cands)):
        sym = symbols[idx]
        idx = (idx + 1) % total
        if sym in existing or sym in {s for s, _, _ in all_cands}:
            continue
        # [2026-08-26 修复] 品种止损冷却: 止损后4h内不重开 (防8/25循环)
        if _sym_in_cooldown(sym):
            continue
        cfg = su.UNIVERSE.get(sym)
        if cfg is None or not cfg.get("tradable", True):
            continue
        # [2026-08-28 修复] 非WFV段策略列表: 优先品种映射(SYMBOL_STRATEGY_MAP
        # 含SESSION), 回退类别映射. 此前用 class_map 导致 USDJPY/GBPUSD/
        # EURUSD 的 SESSION 时段策略从未被调用 (SESSION零触发).
        strs = SYMBOL_STRATEGY_MAP.get(
            sym, class_map.get(cfg.get("cls"),
                               ["SDP", "ICT", "DIV", "MR", "VP", "TREND", "BO"]))
        proposal, reason = scan_symbol(guardian, sym, cfg, equity, risk_pct, strs)
        if proposal:
            all_cands.append((sym, proposal, reason))
        else:
            skip_info.append((sym, reason))
        scanned += 1
        if scanned >= batch:
            break
        if time.time() - t0 > time_budget:
            break
    _save_cursor(idx)
    # ── A 层: 板块配额 + 截面排名(只保留最优选, 防同质化满仓/相关性暴露) ──
    kept = _select_positions(all_cands, slots, existing)
    kept_syms = {s for s, _, _ in kept}
    out = [{"symbol": s, "proposal": p, "reason": r} for s, p, r in kept]
    for s, r in skip_info:
        out.append({"symbol": s, "proposal": None, "reason": r})
    dropped = len(all_cands) - len(kept)
    if dropped > 0:
        out.append({"symbol": None, "proposal": None,
                    "reason": f"截面排名/板块配额裁掉 {dropped} 个次优信号 (保留 {len(kept)}/{slots})"})
    return out


# ══ A 层: 板块配额 + 截面排名 (2026-08-18) ══
# 每类资产同时最多持有 N 仓, 防同类(如 30 个 forex_major)同质化满仓、降低相关性暴露.
# 截面分 = 回测 edge(Kelly) × 紧 SL 偏好, 只保留最优选, 让有限仓位给最高质量信号.
CLASS_MAX_POS = {
    "forex_major": 8, "forex_cross": 6, "forex_exotic": 4,
    "crypto": 6, "index": 5, "stock": 0, "metal": 4,
    "commodity": 4, "energy": 3, "bond": 3,
}


def _cand_score(symbol, proposal):
    """截面排名分: 实盘 edge(D4) × 紧 SL 偏好; 越高越优先开仓."""
    try:
        sc = et.live_edge_score(symbol)        # 实盘 pf×胜率, 替代虚高回测 kelly
    except Exception:
        sc = 1.0
    sl = float(proposal.get("sl_pts", 999) or 999)
    return sc * (1.0 / (1.0 + sl / 100.0))      # 高 edge + 紧 SL 优先


def _select_positions(all_cands, slots, existing):
    """按截面分降序 + 板块配额, 取最优 slots 个. 返回 [(sym,proposal,reason)]."""
    if not all_cands:
        return []
    # 现有持仓板块分布(已有持仓计入配额占用)
    cls_count = {}
    for s in existing:
        c = su.UNIVERSE.get(s, {}).get("cls")
        if c:
            cls_count[c] = cls_count.get(c, 0) + 1
    ranked = sorted(all_cands, key=lambda x: _cand_score(x[0], x[1]),
                    reverse=True)
    out = []
    # [2026-08-26 修复] 配对候选原子性: 配对两腿必须一起开/一起不开.
    # 此前两腿作独立候选按分数排序, 只开了分数高的一条腿 (XAG), 变成裸空
    # 单腿被反复打止损 (8/25 XAG -20.52). 现先挑出所有配对对, 两腿同时
    # 满足板块配额才整体入选.
    pair_groups = {}
    for sym, proposal, reason in all_cands:
        pr = proposal.get('pair_ref')
        if pr:
            pair_groups.setdefault(pr, []).append((sym, proposal, reason))
    # 配对对先整体评估 (分数取两腿平均), 通过则直接入选
    non_pair = [(s, p, r) for s, p, r in all_cands if not p.get('pair_ref')]
    for pr, legs in pair_groups.items():
        if len(legs) < 2 or len(out) >= slots:
            continue  # 配对腿不完整或名额满
        # 两腿板块配额检查
        _ok = True
        for sym, proposal, reason in legs:
            c = su.UNIVERSE.get(sym, {}).get("cls", "other")
            cap = CLASS_MAX_POS.get(c, 6)
            if cls_count.get(c, 0) >= cap:
                _ok = False
                break
        if not _ok:
            continue
        # 两腿一起入选
        for sym, proposal, reason in legs:
            if len(out) >= slots:
                break
            out.append((sym, proposal, reason))
            c = su.UNIVERSE.get(sym, {}).get("cls", "other")
            cls_count[c] = cls_count.get(c, 0) + 1
    # 非配对候选按分数排序
    ranked = sorted(non_pair, key=lambda x: _cand_score(x[0], x[1]),
                    reverse=True)
    for sym, proposal, reason in ranked:
        if len(out) >= slots:
            break
        c = su.UNIVERSE.get(sym, {}).get("cls", "other")
        cap = CLASS_MAX_POS.get(c, 6)
        if cls_count.get(c, 0) >= cap:
            continue   # 该板块已达配额, 跳过
        out.append((sym, proposal, reason))
        cls_count[c] = cls_count.get(c, 0) + 1
    return out


if __name__ == "__main__":
    # 独立自检: 不连 MT5 也能验证宇宙/类别/策略映射
    full = load_full_universe()
    print(f"[live_bridge] 全宇宙可交易品种数: {len(full)}")
    print("[live_bridge] 类别计数:",
          {c: sum(1 for s in full if su.UNIVERSE[s]['cls'] == c)
           for c in sorted(set(su.UNIVERSE[s]['cls'] for s in full))})
    print("[live_bridge] 策略注册表:", STRATEGY_REGISTRY_V4.keys())
    print("[live_bridge] 类别→策略映射示例:",
          {k: CLASS_STRATEGY_MAP[k] for k in ("index", "crypto", "stock", "forex_major")})
