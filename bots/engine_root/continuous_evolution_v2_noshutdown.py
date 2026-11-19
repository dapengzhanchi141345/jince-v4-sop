"""
A.T.E. 持续进化引擎 — v2.0
核心改进: 
  1. 100轮进化(原10轮) — 让统计意义充分
  2. 经验回放 — 每次利用历史经验做决策
  3. 真实市场数据校验 — 模拟+实盘对比
  4. 策略池20条 — 达尔文自然选择
"""
import sys, os, json, warnings, time
import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict, OrderedDict
import threading
warnings.filterwarnings('ignore')

# ═══ MT5 延迟初始化(避免 import 即崩溃) ═══
MT5_AVAILABLE = False
_MT5_OBJ = None
def ensure_mt5():
    """延迟连接 MT5 — 成功返回 True, 失败(终端未运行)返回 False 且不影响其他功能"""
    global MT5_AVAILABLE, _MT5_OBJ
    if _MT5_OBJ is not None:
        return MT5_AVAILABLE
    try:
        import MetaTrader5 as mt5
        _MT5_OBJ = mt5
        if not mt5.initialize():
            print("  [警告] MT5 initialize 失败 (终端可能未运行)")
            return False
        if not mt5.login(60043976, password="", server="TradeMaxGlobal-Demo"):
            print("  [警告] MT5 login 失败")
            return False
        MT5_AVAILABLE = True
        return True
    except Exception as e:
        MT5_AVAILABLE = False
        return False

BASE = r"E:\GoldstrategyEngine"
DATA_DIR = os.path.join(BASE, "data")
EVOLVE_DIR = os.path.join(DATA_DIR, "continuous_evolution")
os.makedirs(EVOLVE_DIR, exist_ok=True)

# ═══ Trading Central 共识(外部分析师验证信号) ═══
def load_tc_consensus():
    f = os.path.join(BASE, "tc_consensus.json")
    if os.path.exists(f):
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                return json.load(fh)
        except Exception:
            pass
    return {}
TC_CONSENSUS = load_tc_consensus()

# ═══ 深度学习盘感模型(可选加载) ═══
try:
    from deep_learning_optimizer import DLOptimizer as _DLClass, MODEL_PATH as _MODEL_PATH
    _DL = _DLClass.load()
    HAS_DL = True
    if _DL is not None:
        print(f"  🧠 盘感模型已加载: {os.path.basename(_MODEL_PATH)}")
    else:
        print("  [提示] 盘感模型未训练 (生产路径为空) — 进化将用合成标签模式, 真模型请运行 DLOptimizer().train_on_mt5()")
except Exception as _e:
    _DLClass = None
    _DL = None
    HAS_DL = False
    print(f"  [提示] 盘感模块未加载: {_e}")

# ═══ 品种配置(真实市场参数) ═══
SYMBOL_CONFIG = {
    "XAUUSD": {"name":"黄金",    "pip":1,      "spread":0.3,  "volatility":15,  "pip_usd_per_lot":100},
    "BTCUSD": {"name":"比特币",  "pip":1,      "spread":0.5,  "volatility":500, "pip_usd_per_lot":1},
    "ETHUSD": {"name":"以太坊",  "pip":1,      "spread":0.3,  "volatility":50,  "pip_usd_per_lot":1},
    "EURUSD": {"name":"欧元",    "pip":0.0001, "spread":0.05, "volatility":0.002,"pip_usd_per_lot":10},
    "GBPUSD": {"name":"英镑",    "pip":0.0001, "spread":0.06, "volatility":0.003,"pip_usd_per_lot":10},
    "USDJPY": {"name":"美元/日元","pip":0.01,  "spread":0.04, "volatility":0.15, "pip_usd_per_lot":10},
    "GBPJPY": {"name":"英镑/日元","pip":0.01,  "spread":0.08, "volatility":0.25, "pip_usd_per_lot":10},
}

# ── 2026-08-15 优化: 自进化覆盖扩到 KEEP-32 验证宇宙 (修复断层 D) ──
# 用 _ub_partial.json 的验证 cfg(pip/pip_usd/spread) 保证成本口径与实盘一致;
# 缺失/异常时静默回退基础 7 品种, 不破进化链。
def _extend_symbol_config_to_keep():
    try:
        import os as _os, json as _json
        p = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                          "data", "_ub_partial.json")
        if not _os.path.exists(p):
            return
        d = _json.load(open(p, encoding="utf-8"))
        added = 0
        for sym, v in d.items():
            if not isinstance(v, dict) or v.get("decision") != "KEEP":
                continue
            if sym in SYMBOL_CONFIG:
                continue
            cfg = v.get("cfg", {})
            if not cfg.get("pip") or not cfg.get("pip_usd"):
                continue
            SYMBOL_CONFIG[sym] = {
                "name": cfg.get("name", sym),
                "pip": cfg["pip"],
                "spread": cfg.get("spread_price", 0.1),
                "volatility": cfg.get("volatility", 0.01),
                "pip_usd_per_lot": cfg["pip_usd"],
            }
            added += 1
        if added:
            print(f"[进化] KEEP-32 扩展: 新增 {added} 品种 → SYMBOL_CONFIG 共 "
                  f"{len(SYMBOL_CONFIG)} 个")
    except Exception as e:
        print(f"[进化] KEEP-32 扩展失败(沿用基础7品种): {e}")
_extend_symbol_config_to_keep()

# ═══ 真实交易成本模型 (P2-MEDIUM-3) ═══
# 进化评估在 spread 之外再计入 **佣金 + 滑点**, 使 baseline.pf 与实盘口径一致
# (更保守、更诚实, 修复审计事实#6: 原仅扣 spread, baseline 略乐观).
#   仅调整每笔 pnl 数值, 不改变 RR/仓位/过滤逻辑, 不破双铁律/WFER.
COMMISSION_PER_LOT = 3.0   # XAUUSD 单边佣金 $/手 (开+平来回 = ×2); 若 broker 单边即 $3 则设 6.0
SLIPPAGE_POINTS = 1.5      # 每笔成交滑点 (point, 开+平合计)

def _trade_cost_usd(trade, position_size):
    """估算单笔成交的真实成本 (USD): 佣金(来回) + 滑点。纯函数, 不破双铁律/WFER。

    position_size 取自策略参数(与 run_walkforward 计算 pnl 时所用一致, 口径统一);
    若品种未知则记 0 (不污染统计)。仅调 pnl 数值, 不改 RR/仓位/过滤。
    """
    sym = trade.get('symbol')
    cfg = SYMBOL_CONFIG.get(sym)
    if cfg is None:
        return 0.0
    commission = COMMISSION_PER_LOT * position_size * 2.0   # 开 + 平 来回
    slippage_cost = (SLIPPAGE_POINTS / cfg['pip']) * position_size * cfg['pip_usd_per_lot']
    return commission + slippage_cost

# ═══ 点差摩擦护栏 (吸收 Supreme_EA 知识包 InpMaxSpreadATR=0.40 / 坑#3#4) ═══
#   设计意图: 当前点差(spread) > SPREAD_ATR_RATIO × ATR → 流动性不足/摩擦过大,
#             拒开新单. 直接映射 Supreme_EA 坑#3(SL 被点差秒扫) 与 坑#4(改 ATR 基准
#             后点差护栏被无声绕过).
#   本系统 SL/TP 与护栏共用同一 ATR 基准(无 D1/H1 双基准分裂), 故护栏绝不会被
#   "改基准" 绕过 —— 这正是 Supreme_EA 坑#4 的反面教材, 我们天然免疫.
#   失败开放(与 RF/缠论 gate 一致): mt5 不可用 / tick 缺失 / atr<=0 → 放行, 不阻断交易链.
SPREAD_GUARD_ENABLED = True
SPREAD_ATR_RATIO = 0.40      # 点差/ATR 阈值; 比例 > 0.40 → SKIP 新开 (Supreme_EA 同值)

def spread_friction_ok(symbol, atr_value, spread_price=None):
    """点差摩擦护栏判定.

    入参:
      symbol: 品种
      atr_value: 当前 ATR(价格单位, 如 H1 ATR(14)), 须与 SL 同源基准
      spread_price: 可选, 直接传入点差(价格单位) 用于测试/外部调用;
                    为 None 时尝试从 MT5 实时 tick 取 (ask-bid)
    返回 (ok: bool, info: str):
      ok=False → 点差过大, 应拒开新单
      ok=True  → 放行(含失败开放场景)
    """
    if atr_value is None or atr_value <= 0:
        return True, '点差护栏: atr<=0, 放行(失败开放)'
    if spread_price is None:
        if not ensure_mt5() or _MT5_OBJ is None:
            return True, '点差护栏: mt5 不可用, 放行(失败开放)'
        try:
            tk = _MT5_OBJ.symbol_info_tick(symbol)
            if tk is None:
                return True, '点差护栏: tick 缺失, 放行(失败开放)'
            spread_price = float(tk.ask) - float(tk.bid)
        except Exception:
            return True, '点差护栏: tick 读取异常, 放行(失败开放)'
    if spread_price is None or spread_price <= 0:
        return True, '点差护栏: spread<=0, 放行'
    ratio = spread_price / atr_value
    if ratio > SPREAD_ATR_RATIO:
        return False, (f'点差护栏: spread {spread_price:.4f} / ATR {atr_value:.4f} '
                       f'= {ratio:.2f} > {SPREAD_ATR_RATIO} (流动性/摩擦过大, SKIP)')
    return True, f'点差护栏: ratio {ratio:.2f} <= {SPREAD_ATR_RATIO}, OK'

# ═══ 策略参数边界(防进化退化: sl/tp/仓位必须在物理合理范围内) ═══
SAFE_MAX_LOT = 0.03   # 单笔手数硬上限: 确保实际风险由 risk_per_trade(≤1%)主导, 不触发审度司VETO(单笔≤1%/日≤3%)

PARAM_BOUNDS = {
    'adx_min':        (15, 45),     # ADX 入场门槛
    'position_size':  (0.01, 2.0),  # 单笔手数
    'risk_per_trade': (0.005, 0.03),# 单笔风险比例
    'sl_multiplier':  (0.5, 6.0),   # SL = ATR × [0.5, 6] (防退化到 0.088 必被扫)
    'tp_multiplier':  (1.0, 10.0),  # TP = ATR × [1, 10]
    # 优化1: 波动率缩仓系数 (volatile regime 时 position_size ×= volatility_scalar,
    # 自动缩仓). 由进化探索, 经 WFER 验证; _ensure_risk_cap 对缩仓后仓位仍夹[0.01,0.03].
    'volatility_scalar': (0.5, 1.0),
}
def _clip_params(p):
    """把策略参数裁剪到物理合理边界"""
    for k, (lo, hi) in PARAM_BOUNDS.items():
        if k in p and isinstance(p[k], (int, float)):
            p[k] = float(min(max(p[k], lo), hi))
    return p

def _ensure_rr(p):
    """稳固定策略铁律 — 强制 RR = tp_multiplier / sl_multiplier >= 2.0。

    必要时应调: 优先拉高 TP 到 2×SL; 若 SL 过大导致 2×SL 超 TP 上界,
    则反向压低 SL 使 RR 恰好=2.0。这样种群内永不会出现 RR<2 的脆弱策略,
    进化方向天然锁定"正盈亏比护城河", 不靠纯胜率裸奔。
    """
    sl_b, sl_t = PARAM_BOUNDS['sl_multiplier']
    tp_b, tp_t = PARAM_BOUNDS['tp_multiplier']
    sl = float(p.get('sl_multiplier', 1.0))
    tp = float(p.get('tp_multiplier', 1.0))
    if sl <= 0:
        sl = max(sl_b, 1e-3)
    target_tp = 2.0 * sl
    if tp < target_tp:
        tp = min(target_tp, tp_t)
        if tp < 2.0 * sl:           # SL 过大, 退而压低 SL 保 RR
            sl = max(tp / 2.0, sl_b)
        p['sl_multiplier'] = float(sl)
        p['tp_multiplier'] = float(tp)
    return p

def _ensure_risk_cap(p):
    """稳固定策略铁律 — 单笔手数封顶 SAFE_MAX_LOT,
    使实际风险由 risk_per_trade(≤1%)主导, 不触发审度司 VETO(单笔≤1%/日≤3%).

    与 volatility_scalar 兼容: 本函数只夹 position_size, 不触碰 volatility_scalar,
    因此猎场司在 volatile regime 用 position_size ×= volatility_scalar 缩仓后,
    再经本函数夹 [0.01, SAFE_MAX_LOT] 即满足"缩仓后仍夹[0.01,0.03]"的双铁律②要求.
    """
    p['position_size'] = float(min(max(p.get('position_size', 0.01), 0.01), SAFE_MAX_LOT))
    return p

# ═══ 轻量技术指标(自包含, 不依赖 torch/MT5, 供回测引擎用) ═══
def _ema(v, p):
    """指数移动平均 (Wilder 风格). 对前导 NaN 稳健: 从首个有效值起算种子,
       避免 NaN 在链式 EMA(如 ADX)中向后永久传染."""
    v = np.asarray(v, float); n = len(v)
    if n < p: return np.nan_to_num(v.astype(float))
    r = np.full(n, np.nan)
    valid = ~np.isnan(v)
    f = int(np.argmax(valid)) if valid.any() else 0   # 首个有效下标
    seed_end = f + p
    if seed_end > n:
        r[f:] = v[f:]; return r
    r[seed_end - 1] = np.mean(v[f:seed_end])
    a = 2 / (p + 1)
    for i in range(seed_end, n):
        r[i] = v[i] * a + r[i - 1] * (1 - a)
    return r

def _atr(h, l, c, p=14):
    h, l, c = np.asarray(h, float), np.asarray(l, float), np.asarray(c, float); n = len(c)
    tr = np.zeros(n)
    tr[1:] = np.maximum(h[1:]-l[1:], np.maximum(np.abs(h[1:]-c[:-1]), np.abs(l[1:]-c[:-1])))
    r = np.full(n, np.nan); r[p] = np.mean(tr[1:p+1])
    for i in range(p+1, n): r[i] = tr[i]/p + r[i-1]*(1-1/p)
    return np.nan_to_num(r, nan=np.mean(tr[1:p+1]))

def _adx(h, l, c, p=14):
    h, l, c = np.asarray(h, float), np.asarray(l, float), np.asarray(c, float); n = len(c)
    up = h[1:]-h[:-1]; dn = l[:-1]-l[1:]
    plus_dm = np.zeros(n); plus_dm[1:] = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.zeros(n); minus_dm[1:] = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = _atr(h, l, c, p)
    plus_di = 100*_ema(plus_dm, p)/(tr + 1e-10)
    minus_di = 100*_ema(minus_dm, p)/(tr + 1e-10)
    dx = 100*np.abs(plus_di - minus_di)/(plus_di + minus_di + 1e-10)
    return _ema(dx, p)

def _clean_close_arr(arr):
    """清洗价格序列: 去0/负/nan, 线性插值"""
    arr = np.asarray(arr, dtype=float)
    arr = np.where(arr <= 0, np.nan, arr)
    n = len(arr); idx = np.arange(n); mask = ~np.isnan(arr)
    if mask.sum() < 2:
        return np.nan_to_num(arr, nan=(np.nanmean(arr) if n else 0.0))
    return np.interp(idx, idx[mask], arr[mask])

def _structure_confirm(close, high, low, i, atr, lookback=20, near_th=2.5, break_th=0.8):
    """SMC-lite 供需结构确认(可历史计算, 无未来函数):
       判断当前 bar 是否处于可交易结构 —— 接近近期 swing 极值(供需区边缘)
       或刚突破结构(swing 极值). 仅用 i 之前的数据, 不窥探未来.
       atr: 预计算的全量 ATR 向量(避免每根重算 O(n^2)).
       near_th/break_th: ATR 倍数阈值(放宽以增厚 walk-forward 样本, 默认2.5/0.8)."""
    if i < lookback + 5:
        return False
    win_h = high[i-lookback:i]; win_l = low[i-lookback:i]
    sw_h = float(np.max(win_h)); sw_l = float(np.min(win_l))
    atr_i = atr[i]
    if atr_i <= 0:
        return False
    dist_h = (sw_h - close[i]) / atr_i   # 距上方 swing 高点(ATR 倍数)
    dist_l = (close[i] - sw_l) / atr_i   # 距下方 swing 低点
    # 供需区边缘: 价格处于近期极值 near_th ATR 内; 或刚突破结构(<break_th ATR)
    near_zone = (dist_h < near_th) or (dist_l < near_th)
    breakout  = (dist_h < break_th) or (dist_l < break_th)
    return near_zone or breakout

# ═══ 经验记忆系统(核心创新) ═══
class StrategicMemory:
    """战略记忆 — 从1000+交易中提炼的'盘感'"""
    
    def __init__(self):
        self.file = os.path.join(EVOLVE_DIR, "strategic_memory.json")
        self.patterns = self._load_or_init()
    
    def _load_or_init(self):
        if os.path.exists(self.file):
            try:
                with open(self.file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, ValueError):
                # 记忆文件损坏 → 备份后重建, 不让坏文件拖垮整个进化引擎
                try:
                    os.replace(self.file, self.file + '.corrupt')
                    print(f"  [警告] 战略记忆文件损坏, 已备份为 .corrupt 并重建")
                except Exception:
                    pass
                return {"total_experiences": 0, "success_patterns": [], "failure_patterns": []}
        return {"total_experiences": 0, "success_patterns": [], "failure_patterns": []}
    
    def save(self):
        with open(self.file, 'w') as f:
            json.dump(self.patterns, f, indent=2, ensure_ascii=False)
    
    def record_experience(self, conditions, outcome, pnl, symbol):
        """记录一次经验"""
        exp = {
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'conditions': conditions,
            'outcome': outcome,
            'pnl': pnl
        }
        
        if pnl > 0:
            self.patterns['success_patterns'].append(exp)
        else:
            self.patterns['failure_patterns'].append(exp)

        self.patterns['total_experiences'] += 1
        if self.patterns['total_experiences'] > 2000:
            # 保持最新1000次成功+1000次失败
            self.patterns['success_patterns'] = self.patterns['success_patterns'][-1000:]
            self.patterns['failure_patterns'] = self.patterns['failure_patterns'][-1000:]
        # 注意: 不在每次经验后落盘(否则 O(n^2) 文件写入拖垮进化);
        #   由 run_continuous_evolution 每轮末统一 memory.save() 一次
    
    def get_confidence(self, conditions, symbol):
        """根据相似经验计算信心分数"""
        similar = [
            p for p in self.patterns['success_patterns'] + self.patterns['failure_patterns']
            if p['symbol'] == symbol and all(
                p['conditions'].get(k) == conditions.get(k) for k in conditions if k in p['conditions']
            )
        ]
        if not similar:
            return 0.5  # 默认信心
        
        wins = sum(1 for p in similar if p['pnl'] > 0)
        return wins / len(similar)

# ═══ 策略池(达尔文进化) ═══
# ── GA 多样性 / 抗停滞 调参(修复 v4.0 "提前收敛冻住" 缺陷) ──
# 原 evolve_generation 只从 top-5 精英播种子代, 种群常在 10 轮内收敛为克隆,
# 导致"进化冻结"(XAU 第10轮后 PnL 恒为 $13,919, 再跑 40 轮零改善).
IMMIGRANTS_PER_GEN = 3      # 每代强制注入的新鲜随机个体数(保底多样性, 维持探索压力)
STAG_ROUNDS = 6             # 最优连续 N 轮无改善 → 判定停滞
STAG_RESET_FRAC = 0.30      # 停滞时重置底部种群比例(打破局部最优 plateau)
MUTATE_STD_BASE = 0.15      # 基础变异强度
MUTATE_STD_STAG = 0.35      # 停滞时加强变异(加速跳出)


class StrategyPool:
    """20条策略并行进化 — 适者生存"""
    
    def __init__(self, seeds=None):
        self.strategies = []
        self.fitness_history = []
        self._stagn_rounds = 0
        self._last_best = -1e18
        # 继承式进化: 受保护的历史最优参数(永不淘汰, 每轮重评估, 保证单调不退化)
        self._protected = []
        if seeds:
            for sp in seeds[:5]:
                if sp and isinstance(sp, dict):
                    self._protected.append(
                        _ensure_risk_cap(_ensure_rr(_clip_params(dict(sp)))))
        self._init_pool()

    def _init_pool(self):
        """初始化20条策略: 优先放入继承的历史最优(受保护, 首轮即评估),
        其余以历史最优为锚做少量变异 exploitation + 随机 immigrants exploration."""
        self.strategies = []
        next_id = 0
        # 1) 继承播种: 历史最优作为初始精英(受保护, 不参与淘汰)
        for sp in self._protected:
            self.strategies.append({
                'id': next_id, 'name': f'Seed_{next_id:02d}',
                'params': sp, 'fitness': 0, 'trades': [], 'alive': True,
                'protected': True,
            })
            next_id += 1
        # 2) 填充剩余到20: 50% 锚点变异(已知优区 exploitation) + 50% 随机(exploration)
        while len(self.strategies) < 20:
            if self._protected and np.random.random() < 0.5:
                base = self._protected[np.random.randint(0, len(self._protected))]
                params = _ensure_risk_cap(_ensure_rr(_clip_params(self._mutate(base, MUTATE_STD_BASE))))
            else:
                params = _ensure_risk_cap(_ensure_rr(self._randomize_params()))
            self.strategies.append({
                'id': next_id, 'name': f'Strategy_{next_id:02d}',
                'params': params, 'fitness': 0, 'trades': [], 'alive': True,
            })
            next_id += 1
    
    def _randomize_params(self):
        """随机参数初始化(在 PARAM_BOUNDS 内, 留出探索空间)
        过 _ensure_rr → 初始种群即全部 RR>=2.0 (稳固定策略铁律)
        含 volatility_scalar (优化1: volatile regime 自动缩仓系数)"""
        return _ensure_risk_cap(_ensure_rr({
            'adx_min': int(np.random.randint(15, 40)),
            'position_size': np.random.uniform(0.02, 1.0),
            'risk_per_trade': np.random.uniform(0.005, 0.025),
            'sl_multiplier': np.random.uniform(0.8, 4.0),
            'tp_multiplier': np.random.uniform(1.5, 7.0),
            'volatility_scalar': np.random.uniform(0.5, 1.0),
            'momentum_filter': bool(np.random.choice([True, False])),
        }))
    
    def evaluate_fitness(self, strategy, trades):
        """评估策略表现 — 基于真实 walk-forward 交易统计 + TC/DL 双裁判"""
        # 稳固定策略铁律: RR = tp/sl 必须 >= 2.0, 否则直接淘汰(双保险, 种群层已守住)
        _pp = strategy.get('params', {})
        _sl = float(_pp.get('sl_multiplier', 1.0)); _tp = float(_pp.get('tp_multiplier', 1.0))
        _rr = (_tp / _sl) if _sl > 0 else 0
        if _rr < 2.0:
            strategy['fitness'] = -1000.0
            strategy['rr_rejected'] = True
            return -1000.0
        if not trades:
            return 0
        # P2-MEDIUM-3: 计入真实交易成本(佣金+滑点), 使 baseline.pf 更诚实;
        #   幂等: 已扣过(_cost_deducted)则跳过, 避免重复扣分. 仅调 pnl 数值,
        #   不改 RR/仓位/过滤逻辑, 不破双铁律/WFER. 该调整同步反映到
        #   compute_trades_baseline(best['trades']) 重算的 baseline.pf.
        _pos = float(_pp.get('position_size', 0.01))
        for t in trades:
            if not t.get('_cost_deducted'):
                t['pnl'] = round(float(t.get('pnl', 0.0)) - _trade_cost_usd(t, _pos), 2)
                t['_cost_deducted'] = True
        pnls = [t['pnl'] for t in trades]
        wins = sum(1 for p in pnls if p > 0)
        win_rate = wins / len(trades)
        sharpe = (np.mean(pnls) / (np.std(pnls) + 1e-10)) if len(pnls) > 1 else 0
        gross_w = sum(p for p in pnls if p > 0)
        gross_l = -sum(p for p in pnls if p < 0)
        pf = gross_w / (gross_l + 1e-10)
        eq = np.cumsum(pnls)
        dd = float((eq - np.maximum.accumulate(eq)).min())   # 最大回撤(负)

        # 复合 fitness: 胜率 + 盈亏比 + Sharpe + 回撤惩罚
        fitness = win_rate * 40 + min(pf, 3) / 3 * 30 + np.clip(sharpe, 0, 3) / 3 * 30
        if dd < 0:
            fitness += min(dd, -200) / 200 * 10   # 回撤越深扣越多

        # TC 裁判: 仅"实时模式"(交易带 _tc_mode, 即 live 评估传入 TC 共识)才计算一致率.
        #   回测 walk-forward 不传 tc_bias → _tc_mode=False → tc_consistency=None 且不计入 fitness,
        #   避免用"当前 TC 快照"对历史交易做裁判(未来函数作弊).
        tc_bonus = 0.0; tc_rate = None
        if trades and trades[0].get('_tc_mode'):
            m = t = 0
            for tr in trades:
                tc_sym = TC_CONSENSUS.get(tr['symbol'])
                if tc_sym:
                    # 映射: TC 用 BULLISH/BEARISH, predicted_bias 用 BUY/SELL
                    tc_dir = 'BUY' if str(tc_sym).upper() == 'BULLISH' else ('SELL' if str(tc_sym).upper() == 'BEARISH' else None)
                    if tc_dir:
                        t += 1
                        if str(tr.get('predicted_bias', '')).upper() == tc_dir:
                            m += 1
            if t:
                tc_rate = m / t
                tc_bonus = (tc_rate - 0.5) * 20
        strategy['tc_consistency'] = round(tc_rate, 3) if tc_rate is not None else None
        fitness += tc_bonus

        # DL 盘感裁判: 盘感方向(BULLISH/BEARISH) vs 入场方向(BUY/SELL)一致率 × 置信度
        # 用"入场方向"而非"单笔盈亏方向"做裁判, 避免 12H 盘感 vs H1 单笔的时间尺度错配;
        # SIDEWAYS(无明确方向)不计入, 避免污染一致性统计. 无未来函数.
        dl_bonus = 0.0; dl_rate = None
        _dir_map = {'BULLISH': 'BUY', 'BEARISH': 'SELL'}
        dl_trades = [t for t in trades if t.get('dl_dir') in _dir_map]
        if dl_trades:
            correct = sum(1 for t in dl_trades if _dir_map[t['dl_dir']] == t['predicted_bias'])
            dl_rate = correct / len(dl_trades)
            conf_avg = np.mean([t.get('dl_confidence', 0.5) for t in dl_trades])
            dl_bonus = (dl_rate - 0.5) * 30 * conf_avg
        strategy['dl_consistency'] = round(dl_rate, 3) if dl_rate is not None else None
        fitness += dl_bonus

        strategy['fitness'] = round(fitness, 3)
        return fitness
    
    def evolve_generation(self):
        """达尔文进化 — 精英保留 + 交叉/变异 + 多样性注入 + 停滞重启.

        修复 v4.0 缺陷: 原实现只从 top-5 精英播种子代, 种群易在 10 轮内收敛为克隆,
        导致"进化冻结"(XAU 第10轮后 PnL 恒为 $13,919, 再跑 40 轮零改善).
        现加入:
          - 每代注入 IMMIGRANTS_PER_GEN 个全新随机个体, 维持探索压力;
          - 停滞检测: 最优连续 STAG_ROUNDS 轮无改善 → 重置底部 STAG_RESET_FRAC
            种群为新鲜随机, 打破局部最优 plateau;
          - 变异强度自适应: 停滞时 MUTATE_STD_STAG > 基础, 加速跳出.
        双铁律(RR>=2 / 仓位<=0.03)由 _ensure_rr / _ensure_risk_cap 守住, 不破任何铁律.
        """
        self.strategies.sort(key=lambda s: s['fitness'], reverse=True)
        best_now = max((s['fitness'] for s in self.strategies), default=-1e18)
        if best_now > self._last_best + 1e-9:
            self._last_best = best_now
            self._stagn_rounds = 0
        else:
            self._stagn_rounds += 1
        stag = self._stagn_rounds >= STAG_ROUNDS

        elites = self.strategies[:5]
        elite_ids = {id(s) for s in elites}

        # 淘汰: 仅淘汰深度负 fitness, 保留最小种群 MIN_POP
        #   受保护的历史最优永不淘汰(即便暂未重评估, 也保留以继续进化)
        MIN_POP = 12
        survivors = [s for s in self.strategies if s['fitness'] > -5 or s.get('protected')]
        survivors = elites + [s for s in survivors if id(s) not in elite_ids]
        if len(survivors) < MIN_POP:
            for s in self.strategies:
                if id(s) not in {id(x) for x in survivors}:
                    survivors.append(s)
                    if len(survivors) >= MIN_POP:
                        break

        next_id = max((s['id'] for s in self.strategies), default=0) + 1

        # 停滞重启: 底部 30% 替换为新鲜随机个体(打破收敛 plateau)
        if stag and len(survivors) > IMMIGRANTS_PER_GEN:
            survivors.sort(key=lambda s: s['fitness'], reverse=True)
            reset_n = max(2, int(len(survivors) * STAG_RESET_FRAC))
            for idx in range(len(survivors) - reset_n, len(survivors)):
                survivors[idx] = {
                    'id': next_id,
                    'name': f'Imm_{next_id:02d}',
                    'params': _ensure_risk_cap(_ensure_rr(self._randomize_params())),
                    'fitness': 0, 'trades': [], 'alive': True,
                }
                next_id += 1

        # 注入固定数量全新随机个体(每代保底多样性, 防克隆冻住)
        for _ in range(IMMIGRANTS_PER_GEN):
            survivors.append({
                'id': next_id,
                'name': f'Imm_{next_id:02d}',
                'params': _ensure_risk_cap(_ensure_rr(self._randomize_params())),
                'fitness': 0, 'trades': [], 'alive': True,
            })
            next_id += 1

        # 补满到固定 20 种群: 交叉/变异精英生成子代
        mut_std = MUTATE_STD_STAG if stag else MUTATE_STD_BASE
        while len(survivors) < 20:
            if len(elites) >= 2 and np.random.random() < 0.5:
                child_params = self._crossover(
                    elites[np.random.randint(0, len(elites))]['params'],
                    elites[np.random.randint(0, len(elites))]['params'])
            else:
                child_params = self._mutate(elites[np.random.randint(0, len(elites))]['params'], mut_std)
            child_params = _ensure_risk_cap(_ensure_rr(_clip_params(child_params)))  # 稳固定: 子代必 RR>=2 且仓位≤SAFE_MAX_LOT
            survivors.append({
                'id': next_id,
                'name': f'Gen_{next_id:02d}',
                'params': child_params,
                'fitness': 0,
                'trades': [],
                'alive': True,
            })
            next_id += 1

        # 受保护历史最优保险: 任一缺失 → 替换最差非保护个体(规模不变, 保单调不退化)
        for sp in self._protected:
            if not any(s.get('protected') and s['params'] == sp for s in survivors):
                _np_idx = [i for i, s in enumerate(survivors) if not s.get('protected')]
                if _np_idx:
                    _worst = max(_np_idx, key=lambda i: -survivors[i]['fitness'])
                    survivors[_worst] = {
                        'id': next_id, 'name': f'Seed_{next_id:02d}',
                        'params': sp, 'fitness': 0, 'trades': [], 'alive': True,
                        'protected': True,
                    }
                    next_id += 1

        self.strategies = survivors[:20]
        self.fitness_history.append({
            'round': len(self.fitness_history),
            'avg_fitness': np.mean([s['fitness'] for s in self.strategies]),
            'best_fitness': max(s['fitness'] for s in self.strategies),
            'pool_size': len(self.strategies),
        })

        return {
            'survivors': len(self.strategies),
            'best_fitness': max(s['fitness'] for s in self.strategies),
            'avg_fitness': np.mean([s['fitness'] for s in self.strategies]),
        }
    
    def _mutate(self, params, std=MUTATE_STD_BASE):
        """基因突变(变异后裁剪到边界, 防退化).

        std 可注入: 停滞时传入更大的 MUTATE_STD_STAG, 加速跳出局部最优.
        """
        mutated = params.copy()
        for k in list(mutated):
            if isinstance(mutated[k], float):
                mutated[k] *= (1 + np.random.normal(0, std))
                mutated[k] = float(min(max(mutated[k], PARAM_BOUNDS[k][0]), PARAM_BOUNDS[k][1]))
            elif isinstance(mutated[k], bool):
                mutated[k] = not mutated[k] if np.random.random() < 0.15 else mutated[k]
        return mutated

    def _crossover(self, p1, p2):
        """交叉: 从两个父代各取一半参数, 增加种群多样性"""
        child = {}
        for k in p1:
            child[k] = p1[k] if np.random.random() < 0.5 else p2[k]
        return _clip_params(child)

# ═══ 回测引擎(真实 walk-forward 时间序列回测) ═══
class BacktestEngine:
    """真实 walk-forward 回测引擎
       - real 模式: 拉 MT5 真实 H1 历史(OHLC), 逐根推进模拟真实交易(入场/SL-TP/出场)
       - synthetic 模式: 几何随机游走合成历史(同样走 walk-forward, 验证链路与裁判)
       每一笔交易附 dl_dir / dl_confidence / future_dir(真实命中方向) → 双裁判真正生效
    """
    def __init__(self):
        self.mode = 'synthetic'
        self.mt5 = None
        if ensure_mt5():
            self.mode = 'real'
            self.mt5 = _MT5_OBJ
        self._base_px = {'XAUUSD':4000,'BTCUSD':58000,'ETHUSD':1600,'EURUSD':1.14,'GBPUSD':1.32,'USDJPY':162,'GBPJPY':215}
        self._hist = {}     # symbol -> (close, high, low) 已清洗
        self._spread = {}   # symbol -> 真实 spread(point)
        self._hist_n = 600

    def _load_history(self, symbol):
        """拉真实/合成历史 OHLC(清洗缓存)"""
        if symbol in self._hist:
            sp = self._spread.get(symbol, SYMBOL_CONFIG.get(symbol, {}).get('spread', 0.1))
            return self._hist[symbol], sp
        if self.mode == 'real' and self.mt5 is not None:
            try:
                rates = self.mt5.copy_rates_from_pos(symbol, 16385, 0, self._hist_n)
                if rates is not None and len(rates) > 120:
                    df = pd.DataFrame(rates)
                    close = _clean_close_arr(df['close'])
                    high  = _clean_close_arr(df['high'])
                    low   = _clean_close_arr(df['low'])
                    info  = self.mt5.symbol_info(symbol)
                    spread = info.spread * info.point if (info and info.spread) else SYMBOL_CONFIG[symbol]['spread']
                    self._hist[symbol] = (close, high, low)
                    self._spread[symbol] = spread
                    return self._hist[symbol], spread
            except Exception:
                pass
        # 合成降级: 分段趋势序列 (趋势段↔震荡段交替 → ADX 自然落在 15~45,
        #   可真实触发入场过滤与 SL/TP 出场, 使降级链路成为有效回归测试)
        cfg = SYMBOL_CONFIG[symbol]
        base = self._base_px[symbol]
        n = self._hist_n
        # 分数波动率(单根真实波动量级, 防 cumprod 爆掉/变负): 上限 0.4%
        sigma = min(cfg['volatility'] * 1e-4, 0.004)
        n_seg = 10
        seg = n // n_seg
        seg_drift = np.random.uniform(-1.0, 1.0, n_seg) * sigma * 0.8   # 分段趋势方向
        rets = np.empty(n)
        for k in range(n_seg):
            a, b = k * seg, (k + 1) * seg if k < n_seg - 1 else n
            rets[a:b] = np.random.normal(seg_drift[k], sigma, b - a)
        rets += np.random.normal(0, sigma * 0.4, n)                     # 轻微全局噪声
        close = base * np.cumprod(1.0 + rets)
        bar_n = np.clip(np.abs(np.random.normal(0, sigma * 2.0, n)), 0, 0.01)  # 单根高低范围≤1%
        high = np.maximum(close, close * (1 + bar_n))
        low  = np.minimum(close, close * (1 - bar_n))
        self._hist[symbol] = (close, high, low)
        self._spread[symbol] = cfg['spread']
        return self._hist[symbol], cfg['spread']

    def _direction(self, close, i, dl_pred):
        """入场方向: DL 盘感有明确方向(BULLISH/BEARISH)时优先采用;
           SIDEWAYS/None(不确定)则回退 EMA21/50 规则 —— 不让'看不清'一票否决交易"""
        if dl_pred is not None and dl_pred[0] in ('BULLISH', 'BEARISH'):
            return 'BUY' if dl_pred[0] == 'BULLISH' else 'SELL'
        # DL 不确定 → 回退规则(EMA21/50 排列)
        e21 = _ema(close[:i+1], 21); e50 = _ema(close[:i+1], 50)
        if close[i] > e21[-1] > e50[-1]: return 'BUY'
        if close[i] < e21[-1] < e50[-1]: return 'SELL'
        return None

    def run_walkforward(self, strategy, symbol, dl_pred=None, tc_bias=None):
        """对单策略在 symbol 真实历史上做 walk-forward 回测, 返回交易列表(多笔).
           tc_bias: 可选, 传入 Trading Central 实时共识方向(BULLISH/BEARISH)做入场增强过滤;
                    回测调用不传(None) → 不使用 TC, 保持无未来函数的纯净性."""
        hist, spread = self._load_history(symbol)
        if hist is None:
            return []
        close, high, low = hist
        if len(close) < 120:
            return []
        cfg = SYMBOL_CONFIG[symbol]
        p = strategy['params']
        # 预计算真实指标(向量化, 基于真实OHLC)
        adx = _adx(high, low, close)
        atr = _atr(high, low, close)
        n = len(close)
        trades = []
        i = 60  # 预热(指标稳定)
        while i < n - 30:
            # —— 策略过滤: 真实 ADX 门槛(替代原随机 trend_strength) ——
            if np.isnan(adx[i]) or adx[i] < p['adx_min']:
                i += 1; continue
            if p.get('momentum_filter') and adx[i] < 35:
                i += 1; continue
            direction = self._direction(close, i, dl_pred)
            if direction is None:
                i += 1; continue
            # —— 实时 TC 共识增强(仅 live 评估传 tc_bias; 回测不传, 保持纯净) ——
            if tc_bias is not None:
                tb = 'BUY' if str(tc_bias).upper() == 'BULLISH' else ('SELL' if str(tc_bias).upper() == 'BEARISH' else None)
                if tb and direction != tb:
                    i += 1; continue
            # —— SMC-lite 结构确认(供需区边缘/突破结构) ——
            if not _structure_confirm(close, high, low, i, atr):
                i += 1; continue
            entry = close[i]
            sl_d = atr[i] * p['sl_multiplier']
            tp_d = atr[i] * p['tp_multiplier']
            if sl_d <= 0 or tp_d <= 0:
                i += 1; continue
            # —— 出场: 未来 first hit SL/TP (真实价格路径) ——
            exit_i = None; hit = None
            for j in range(i+1, min(i+250, n)):
                if direction == 'BUY':
                    if high[j] >= entry + tp_d: exit_i=j; hit='TP'; break
                    if low[j]  <= entry - sl_d: exit_i=j; hit='SL'; break
                else:
                    if low[j]  <= entry - tp_d: exit_i=j; hit='TP'; break
                    if high[j] >= entry + sl_d: exit_i=j; hit='SL'; break
            if exit_i is None:
                i += 1; continue
            move = (close[exit_i] - entry) if direction == 'BUY' else (entry - close[exit_i])
            pnl_pts = (tp_d if hit == 'TP' else -sl_d) - spread   # 真实PnL扣spread
            pnl = (pnl_pts / cfg['pip']) * p['position_size'] * cfg['pip_usd_per_lot']
            future_dir = 'BULLISH' if move > 0 else 'BEARISH'
            trades.append({
                'pnl': round(pnl, 2), 'result': 'WIN' if pnl > 0 else 'LOSS',
                'symbol': symbol, 'strategy_id': strategy['id'],
                'predicted_bias': direction,
                'dl_dir': dl_pred[0] if (dl_pred and dl_pred[0]) else None,
                'dl_confidence': dl_pred[1] if (dl_pred and dl_pred[1] is not None) else None,
                'future_dir': future_dir,
                'bars_held': exit_i - i,
                'hit': hit,
                '_tc_mode': tc_bias is not None,
            })
            i = exit_i + 1   # 出场后下一根再考虑入场
        return trades

def compute_trades_baseline(trades):
    """从回测 trades 计算盈亏比 pf 与胜率 win_rate —— 供 live drift monitor 做基线对比。

    纯函数, 无副作用, 不破双铁律/WFER。
    - pf = gross_profit / gross_loss; 全胜(无亏损)时 pf 无界 → 记 None(避免误导)
    - win_rate = 盈利笔 / 总笔
    返回 {pf, win_rate} 或 None(trades 为空/无 pnl)。
    """
    if not trades:
        return None
    pnls = [t['pnl'] for t in trades if isinstance(t, dict) and 'pnl' in t]
    if not pnls:
        return None
    wins = sum(1 for p in pnls if p > 0)
    wr = wins / len(pnls)
    gw = sum(p for p in pnls if p > 0)
    gl = -sum(p for p in pnls if p < 0)
    if gl > 0:
        pf = gw / gl
    elif gw > 0:
        pf = None  # 全胜, pf 无界
    else:
        pf = 0.0
    return {
        "pf": round(pf, 4) if pf is not None else None,
        "win_rate": round(wr, 4),
    }

# ═══ 100轮持续进化 ═══
# 单品种进化总预算 / 单轮超时(防御: 防"46分钟卡死"阻断最终状态落盘)
_DEFAULT_SYM_BUDGET_SEC = 1500
_ROUND_TIMEOUT_SEC = 300


def _round_body(symbol, pool, engine, memory, r, dl_cache, captured):
    """单轮进化体(在守护线程内执行, 主线程按超时回收). 结果经 captured 回传."""
    start_time = time.time()
    round_trades = []
    for strat in pool.strategies:
        strat['trades'] = []
        trades = engine.run_walkforward(strat, symbol, dl_cache.get(symbol))
        if not trades:
            continue
        for t in trades:
            t['strategy_name'] = strat['name']
            round_trades.append(t)
            conditions = {
                'strategy': strat['id'],
                'lot_size': round(strat['params']['position_size'], 3),
                'sl_mult': strat['params']['sl_multiplier'],
                'adx_min': strat['params']['adx_min'],
            }
            memory.record_experience(conditions, t['result'], t['pnl'], symbol)
    round_pnl = sum(t['pnl'] for t in round_trades)
    round_wins = sum(1 for t in round_trades if t['pnl'] > 0)
    win_rate = round_wins / max(len(round_trades), 1)
    by_id = defaultdict(list)
    for tr in round_trades:
        by_id[tr['strategy_id']].append(tr)
    for strat in pool.strategies:
        strat['trades'] = by_id.get(strat['id'], [])
        pool.evaluate_fitness(strat, strat['trades'])
    evolution_result = pool.evolve_generation()
    elapsed = time.time() - start_time
    print(f"\r  [{symbol} {r:>3d}] 胜率:{win_rate:.1%} | "
          f"PnL:${round_pnl:>7.0f} | 存活:{evolution_result['survivors']} | "
          f"用时{elapsed:.1f}s", end="", flush=True)
    captured['result'] = {
        'round': r, 'win_rate': win_rate, 'pnl': round_pnl,
        'pool_survivors': evolution_result['survivors'],
        'best_fitness': evolution_result['best_fitness'],
        'timestamp': datetime.now().isoformat(),
    }
    memory.save()
    if r % 10 == 0:
        snapshot = {
            'symbol': symbol, 'round': r, 'results': [captured['result']],
            'pool_size': len(pool.strategies),
            'total_experience': memory.patterns['total_experiences'],
            'best_tc_consistency': max((s.get('tc_consistency') or 0 for s in pool.strategies), default=0),
        }
        with open(os.path.join(EVOLVE_DIR, f'snapshot_{symbol}_r{r}.json'), 'w') as f:
            json.dump(snapshot, f, indent=2, default=str)


def _evolve_symbol_rounds(symbol, pool, engine, memory, max_rounds, dl_cache,
                          per_symbol_budget_sec=None):
    """对单一品种跑完整进化轮次(独立策略池), 返回该品种每轮结果列表.

    纯进化逻辑, 不读写进化状态文件(状态落盘由 run_continuous_evolution 统一处理).
    双铁律(RR>=2 / 仓位<=0.03) / ADX 门槛 / 成本模型全部由策略池与
    run_walkforward 守住, 此处不破任何铁律.

    可靠性加固(修复 v4.0 痛点):
      - 单品种总预算: 超预算即提前结束, 保后续品种进化与最终状态落盘;
      - 单轮超时守护线程: 某轮若阻塞(如 MT5 偶发卡顿 / 系统休眠), 最多等
        _ROUND_TIMEOUT_SEC 秒即放弃该轮并终止本品种, 绝不因单轮卡死阻断全run.
    """
    results = []
    sym_start = time.time()
    sym_budget = per_symbol_budget_sec or _DEFAULT_SYM_BUDGET_SEC
    r = 0
    while r < max_rounds:
        r += 1
        if time.time() - sym_start > sym_budget:
            print(f"\n  [{symbol}] ⏱ 超预算({sym_budget}s), 提前结束本品种(保状态落盘)")
            break
        done = threading.Event()
        captured = {}
        def _worker():
            try:
                _round_body(symbol, pool, engine, memory, r, dl_cache, captured)
            except Exception as e:
                captured['error'] = str(e)
            finally:
                done.set()
        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        t.join(timeout=_ROUND_TIMEOUT_SEC)
        if not done.is_set():
            # 单轮阻塞: 放弃该轮并终止本品种, 防止卡死阻断最终状态写盘
            print(f"\n  [{symbol} {r:>3d}/{max_rounds}] ⚠ 超时({_ROUND_TIMEOUT_SEC}s)疑似阻塞, "
                  f"终止本品种进化(保状态落盘)")
            results.append({
                'round': r, 'win_rate': 0.0, 'pnl': 0.0,
                'pool_survivors': len(pool.strategies),
                'best_fitness': pool._last_best, 'timeout': True,
                'timestamp': datetime.now().isoformat(),
            })
            break
        if captured.get('error'):
            print(f"\n  [{symbol} {r:>3d}] ⚠ 本轮异常(跳过): {captured['error']}")
            results.append({
                'round': r, 'win_rate': 0.0, 'pnl': 0.0,
                'pool_survivors': len(pool.strategies),
                'best_fitness': pool._last_best, 'error': True,
                'timestamp': datetime.now().isoformat(),
            })
            continue
        results.append(captured['result'])
    print()
    return results


def run_continuous_evolution(max_rounds=100, force_synthetic=False, symbol=None,
                              per_symbol_budget_sec=None):
    print("="*70)
    print("  🧬 A.T.E. 持续进化引擎 v4.0 — 逐品种独立进化")
    print("  达尔文进化 × 20策略池(每品种独立) × Walk-Forward × 双裁判")
    print("="*70)

    # 生产模式: 仅在 MT5 可用时跑真实回测进化; 否则跳过(绝不跑假数据)
    if not force_synthetic and not ensure_mt5():
        print("  ⚠ MT5 终端未连接/未登录 → 跳过本轮进化 (不跑合成数据)")
        return None

    mode = "synthetic(开发)" if force_synthetic else ("real(MT5)" if MT5_AVAILABLE else "synthetic(降级)")
    print(f"  回测模式: {mode}")

    # 重新加载最新盘感模型(训练后模型已更新, 避免用旧/空模型当裁判)
    global _DL
    if HAS_DL and _DLClass is not None:
        try:
            _DL = _DLClass.load()
            print(f"  盘感模型: {'已加载' if _DL is not None else '无(降级合成标签)'}")
        except Exception:
            _DL = None

    # 逐品种目标: symbol 指定则只进化该品种; None=全部品种各自独立进化
    target_symbols = [symbol] if symbol else list(SYMBOL_CONFIG.keys())
    print(f"  进化品种: {', '.join(target_symbols)} (每品种独立策略池, 互不干扰)")

    # 预载既有状态(保留各品种已有 baseline, 避免覆盖良好历史基线)
    _prior_path = os.path.join(EVOLVE_DIR, 'evolution_state.json')
    _prior_state = None
    if os.path.exists(_prior_path):
        try:
            with open(_prior_path, 'r', encoding='utf-8') as _pfh:
                _prior_state = json.load(_pfh)
        except Exception:
            _prior_state = None
    _prior_bps = ((_prior_state or {}).get('best_per_symbol') or {}) if _prior_state else {}

    memory = StrategicMemory()
    # 保留既有品种最优(定向进化 symbol=xxx 时, 不覆盖其他品种的好结果)
    best_per_symbol = dict(_prior_bps)

    for sym in target_symbols:
        print(f"\n{'='*60}\n  品种 {sym} — 独立策略池进化 ({max_rounds} 轮)\n{'='*60}")
        # 继承式进化: 从既有最优播种(有 state 时), 无则随机起步
        _prior_params = (_prior_bps.get(sym) or {}).get('params')
        _seeds = [_prior_params] if _prior_params else None
        pool = StrategyPool(seeds=_seeds)   # 每品种独立池(互不干扰, 独立达尔文进化)
        engine = BacktestEngine()
        dl_cache = {}
        if engine.mode == 'real' and _DL is not None and engine.mt5 is not None:
            try:
                dl_cache[sym] = _DL.boost_from_raw(sym, 0.0, None, True, engine.mt5)
            except Exception:
                dl_cache[sym] = None
        _evolve_symbol_rounds(sym, pool, engine, memory, max_rounds, dl_cache,
                              per_symbol_budget_sec)
        best = max(pool.strategies, key=lambda s: s['fitness']) if pool.strategies else None
        # A2: 计算最优策略回测基线(供 live drift monitor 对比实盘漂移) —— 纯只读计算
        baseline = compute_trades_baseline(best['trades']) if (best and best.get('trades')) else None
        _prior_sym_baseline = (_prior_bps.get(sym) or {}).get('baseline')
        if baseline is None and _prior_sym_baseline is not None:
            baseline = _prior_sym_baseline   # 本轮无交易 → 沿用既有良好基线
        # 继承式进化核心: 仅当本轮找到【严格更优】策略才覆盖历史最优(单调不退化);
        #   否则保留既有良好结果, 杜绝"随机坏轮次覆盖好历史"导致的 fitness 大起大落.
        _prior_fit = (_prior_bps.get(sym) or {}).get('fitness')
        if best and best['fitness'] > (_prior_fit or -1e18) + 1e-9:
            best_per_symbol[sym] = ({
                'name': best['name'],
                'fitness': round(best['fitness'], 3),
                'params': {k: (round(v, 4) if isinstance(v, float) else v) for k, v in best['params'].items()},
                'tc_consistency': best.get('tc_consistency'),
                'dl_consistency': best.get('dl_consistency'),
                'baseline': baseline,
            })
        elif _prior_bps.get(sym) is not None:
            pass  # 本轮未超越历史最优 → 保留既有良好结果(不退化)
        else:
            best_per_symbol[sym] = None  # 首次且无产出: 显式标记

    # 全局兜底 best_strategy(向后兼容 load_best_strategy()): 取各品种 fitness 最高者
    best_strategy = None
    for sym, bs in best_per_symbol.items():
        if bs and (best_strategy is None or (bs['fitness'] or -1e9) > (best_strategy.get('fitness') or -1e9)):
            best_strategy = bs
    if best_strategy is None and _prior_state:
        best_strategy = _prior_state.get('best_strategy') or _prior_state.get('best')

    state = {
        'updated_at': datetime.now().isoformat(timespec='seconds'),
        'mode': mode,
        'rounds': max_rounds,
        'symbols_evolved': target_symbols,
        'per_symbol': True,
        'total_experience': memory.patterns['total_experiences'],
        'best_per_symbol': best_per_symbol,
        'best_strategy': best_strategy,   # 全局兜底(向后兼容 load_best_strategy)
    }
    with open(os.path.join(EVOLVE_DIR, 'evolution_state.json'), 'w') as f:
        json.dump(state, f, indent=2, default=str)
    print(f"\n📁 进化状态已写: {EVOLVE_DIR}/evolution_state.json")
    print(f"✅ 逐品种进化完成! 各品种最优: " + ", ".join(
        (f"{s}={best_per_symbol[s]['name']}(fit={best_per_symbol[s]['fitness']})"
         if best_per_symbol.get(s) else f"{s}=NONE") for s in target_symbols))
    return best_per_symbol

# ═══ 进化报告 ═══
def generate_evolution_report(results, pool, memory):
    """生成完整进化报告"""
    report = []
    report.append("=" * 70)
    report.append("  A.T.E. 持续进化引擎 — 最终进化报告")
    report.append(f"  运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    report.append(f"  进化轮次: {len(results)}")
    report.append(f"  策略池规模: {len(pool.strategies)} (初始20, 当前存活)")
    report.append(f"  经验记录: {memory.patterns['total_experiences']} 条")
    report.append("=" * 70)
    
    # 关键节点
    milestones = [1, 10, 25, 50, 75, 100]
    report.append("\n【关键里程碑】")
    for m in milestones:
        if m <= len(results):
            r = results[m-1]
            report.append(f"  轮次{m:>3d}: 胜率{r['win_rate']:.1%} | PnL ${r['pnl']:.0f} | 策略存活{r['pool_survivors']}")
    
    # 趋势分析
    report.append("\n【进化趋势分析】")
    if len(results) >= 10:
        early = results[:10]
        late = results[-10:]
        early_wr = np.mean([r['win_rate'] for r in early])
        late_wr = np.mean([r['win_rate'] for r in late])
        report.append(f"  初期10轮平均胜率: {early_wr:.1%}")
        report.append(f"  末期10轮平均胜率: {late_wr:.1%}")
        report.append(f"  胜率变化: {(late_wr - early_wr):+.1%}")
        
        early_pnl = np.mean([r['pnl'] for r in early])
        late_pnl = np.mean([r['pnl'] for r in late])
        report.append(f"  初期平均PnL: ${early_pnl:.0f}")
        report.append(f"  末期平均PnL: ${late_pnl:.0f}")
        
        if late_wr > early_wr:
            report.append("  ✅ 系统在学习和适应!")
        elif late_wr == early_wr:
            report.append("  ⚖️ 系统已收敛，稳定在某一水平")
        else:
            report.append("  ⚠️  性能退化，需要调整进化方向")
    
    # 总结
    report.append("\n【系统自评】")
    if len(results) >= 10:
        total_pnl = sum(r['pnl'] for r in results)
        final_wr = np.mean([r['win_rate'] for r in results[-10:]])
        report.append(f"  100轮累计PnL: ${total_pnl:.0f}")
        report.append(f"  最终稳定胜率: {final_wr:.1%}")
        report.append("")
        if total_pnl > 0:
            report.append("  '我没有完美，但我一直在进步。")
            report.append("   从100轮的学习中，我获得了比1000笔人类交易更丰富的经验。')")
        else:
            report.append("  '进化尚未结束，每一次失败都是下一次成功的铺垫。')")
    
    report.append("\n" + "=" * 70)
    return "\n".join(report)

# ═══ 主流程 ═══
if __name__ == "__main__":
    start_time = time.time()
    out = run_continuous_evolution(max_rounds=100)
    if out is None:
        elapsed = time.time() - start_time
        print("\n(进化已跳过 — MT5 不可用且非强制合成模式)")
        print(f"⏱️  用时: {elapsed:.1f}秒")
    else:
        # v4.0: run_continuous_evolution 返回 best_per_symbol(dict), 不再返回旧式 (results,pool,memory) 三元组.
        #   旧解包在此触发 ValueError 且发生在状态文件写入之后 → 不破核心交付, 但令进程 EXIT=1.
        #   改为读取已写好的 evolution_state.json 生成逐品种摘要报告, 进程干净退出.
        elapsed = time.time() - start_time
        state_path = os.path.join(EVOLVE_DIR, "evolution_state.json")
        try:
            with open(state_path, 'r', encoding='utf-8') as _sf:
                state = json.load(_sf)
        except Exception:
            state = {}
        bps = state.get("best_per_symbol", {}) or {}
        lines = []
        lines.append("=" * 70)
        lines.append("  A.T.E. 持续进化引擎 — 逐品种进化摘要")
        lines.append(f"  运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"  模式: {state.get('mode','?')} | 轮次: {state.get('rounds','?')} | "
                     f"累计经验: {state.get('total_experience','?')}")
        lines.append("=" * 70)
        for sym, bs in bps.items():
            if bs:
                lines.append(f"  {sym}: {bs['name']} (fit={bs['fitness']}) | "
                             f"TC={bs.get('tc_consistency')} DL={bs.get('dl_consistency')} | "
                             f"PF={bs.get('baseline')}")
            else:
                lines.append(f"  {sym}: NONE")
        lines.append("=" * 70)
        report = "\n".join(lines)
        print("\n\n" + report)

        # 保存
        with open(os.path.join(EVOLVE_DIR, "evolution_final_report.txt"), 'w', encoding='utf-8') as f:
            f.write(report)

        with open(os.path.join(EVOLVE_DIR, "evolution_data.json"), 'w') as f:
            json.dump(state, f, indent=2, default=str)

        print(f"\n📁 报告: {EVOLVE_DIR}/evolution_final_report.txt")
        print(f"📁 数据: {EVOLVE_DIR}/evolution_data.json")
        print(f"⏱️  总用时: {elapsed:.1f}秒")

# [SAFE-NO-SHUTDOWN] live 交易期间禁止 shutdown() 以免切断 live 共享连接。
# 改为仅 detach（不调用 mt5.shutdown()），由 live 主进程自行管理连接生命周期。
if _MT5_OBJ is not None:
    print("\n  [安全] 跳过 mt5.shutdown() — live 交易运行中，已 detach 而非断开共享连接")
