# rf_alpha.py — 金策宗师团 · 研究部 · 研策师 (research-strategist)
"""
随机森林 Alpha 模型 (新一条 Alpha 产线, 与 XGBoost/LSTM 并列)

设计原则 (与金策宗师团 v4.0 铁律一致):
  - 单文件自包含: 自带 EMA/ADX/MACD/RSI/ATR 指标, 不依赖 continuous_evolution_v2 / MT5
    (可离线 import + 单测, 与 chanlun_analyzer.py 同风格)
  - 纯函数式特征工程: 给定 (close, high, low) 数组即产出特征, 不读全局/不碰网络
  - 严格错位标签: 特征用 [0, t], 标签用 [t+1, t+N] 的未来极值方向 —— 绝对禁止未来函数
  - 小样本抗过拟合: H1 仅 ~400 根, 必须控 max_depth / min_samples_leaf / class_weight

落地定位 (详见 random_forest_review_report.md):
  - Phase 0: 研策师主导, 新建本模块, 滚动训练 RandomForestClassifier
  - Phase 1: 猎场司 signal_quality 增强层 (RF_QUALITY_GATE 开关, 默认关闭)
  - Phase 2: 纳入 continuous_evolution_v2 策略参数池, 享 WFER 验证 + 优胜劣汰
  - RF 永远在审度司 VETO 下游; 仅增强, 不替代任何硬阈值/铁律

接口:
  model = RFAlpha()          # 构造 (含抗过拟合参数)
  ok = model.fit(history)    # history = (close, high, low); 滚动用最近 train_window 根
  proba = model.predict_proba(features)   # features: 2D 数组
  sc = model.score(close, high, low)      # 便捷: 取最新一根特征 → {'UP':, 'DOWN':, 'confidence':}
  model.is_trained          # 是否已训练好
"""
import numpy as np

# ═══ sklearn 延迟/容错导入 ═══
# 装包失败(编译/网络)时给出清晰报错, 不静默吞掉, 便于 CIO 决策。
try:
    from sklearn.ensemble import RandomForestClassifier
    _HAS_SK = True
    _SK_ERR = None
except Exception as _e:  # pragma: no cover
    RandomForestClassifier = None
    _HAS_SK = False
    _SK_ERR = _e


# ════════════════════════════════════════════════════════════
# 底层指标 (自包含纯函数, 全部因果 — 第 t 根只依赖 ≤ t 的数据, 无未来泄漏)
# ════════════════════════════════════════════════════════════
def _ema(v, p):
    """指数移动平均 (递推, 因果, NaN 健壮)。

    种子从首个有效值起算 (吸收 continuous_evolution_v2 做法), 避免前导 NaN
    (如 MACD 的 dif 前 26 根为 NaN) 经 mean(NaN) 永久向后传染。
    """
    v = np.asarray(v, dtype=float)
    n = len(v)
    out = np.full(n, np.nan)
    if n < p:
        return out
    valid = ~np.isnan(v)
    if not valid.any():
        return out
    f = int(np.argmax(valid))          # 首个有效下标
    seed_end = f + p
    if seed_end > n:
        out[f:] = v[f:]
        return out
    out[seed_end - 1] = float(np.mean(v[f:seed_end]))
    a = 2.0 / (p + 1.0)
    for i in range(seed_end, n):
        out[i] = v[i] * a + out[i - 1] * (1.0 - a)
    return out


def _sma(v, p):
    """简单移动平均 (因果, NaN 健壮)。窗口内忽略 NaN, 前导 NaN 不传染。"""
    v = np.asarray(v, dtype=float)
    n = len(v)
    out = np.full(n, np.nan)
    if n < p:
        return out
    for i in range(p - 1, n):
        w = v[i - p + 1:i + 1]
        m = float(np.nanmean(w))
        if not np.isnan(m):
            out[i] = m
    return out


def _rsi(close, p=14):
    """Wilder RSI (因果)。前 p 根为 NaN。"""
    close = np.asarray(close, dtype=float)
    n = len(close)
    out = np.full(n, np.nan)
    if n < p + 1:
        return out
    diff = np.diff(close)
    gain = np.where(diff > 0, diff, 0.0)
    loss = np.where(diff < 0, -diff, 0.0)
    ag = np.zeros(n)
    al = np.zeros(n)
    ag[p] = float(np.mean(gain[:p]))
    al[p] = float(np.mean(loss[:p]))
    for i in range(p + 1, n):
        ag[i] = (ag[i - 1] * (p - 1) + gain[i - 1]) / p
        al[i] = (al[i - 1] * (p - 1) + loss[i - 1]) / p
    rs = ag / (al + 1e-10)
    out[p:] = 100.0 - 100.0 / (1.0 + rs[p:])
    return out


def _atr(h, l, c, p=14):
    """Wilder ATR (因果)。前 p 根为 NaN。"""
    h = np.asarray(h, dtype=float)
    l = np.asarray(l, dtype=float)
    c = np.asarray(c, dtype=float)
    n = len(c)
    tr = np.zeros(n)
    tr[1:] = np.maximum(h[1:] - l[1:],
                         np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    out = np.full(n, np.nan)
    if n <= p:
        return out
    out[p] = float(np.mean(tr[1:p + 1]))
    for i in range(p + 1, n):
        out[i] = tr[i] / p + out[i - 1] * (1.0 - 1.0 / p)
    return out


def _adx(h, l, c, p=14):
    """Wilder ADX + DI 差 (因果)。返回 (adx, di_spread)。"""
    h = np.asarray(h, dtype=float)
    l = np.asarray(l, dtype=float)
    c = np.asarray(c, dtype=float)
    n = len(c)
    up = h[1:] - h[:-1]
    dn = l[:-1] - l[1:]
    plus_dm = np.zeros(n)
    plus_dm[1:] = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.zeros(n)
    minus_dm[1:] = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = _atr(h, l, c, p)
    plus_di = 100.0 * _ema(plus_dm, p) / (tr + 1e-10)
    minus_di = 100.0 * _ema(minus_dm, p) / (tr + 1e-10)
    dx = 100.0 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
    adx = _ema(dx, p)
    di_spread = plus_di - minus_di
    return adx, di_spread


def _macd(close, fast=12, slow=26, signal=9):
    """返回 (dif, dea, bar)。bar = 2*(dif-dea) 与主流软件一致。"""
    close = np.asarray(close, dtype=float)
    dif = _ema(close, fast) - _ema(close, slow)
    dea = _ema(dif, signal)
    bar = 2.0 * (dif - dea)
    return dif, dea, bar


# ════════════════════════════════════════════════════════════
# RFAlpha 随机森林 Alpha 模型
# ════════════════════════════════════════════════════════════
class RFAlpha:
    """随机森林方向概率评分器 (二分类: UP=1 / DOWN=0)。

    特征 (每根 K 线一个向量, 全部因果 — 仅用 ≤ t 的数据):
      - ema_cross   : (EMA21 - EMA50) / close   —— 趋势斜率/方向
      - adx         : ADX(14)                    —— 趋势强度
      - di_spread   : +DI - -DI                  —— 多空动能差
      - macd_bar    : MACD 柱 / close            —— 动量加速度
      - rsi         : RSI(14)                    —— 超买超卖/反转
      - atr_rel     : ATR / close                —— 相对波幅
      - atr_ratio   : ATR / SMA(ATR,50)         —— 波动率 regime
      - range_pos   : 价格在近期高低区间的位置    —— 可选结构特征(缠论式区间定位)

    标签 (严格错位, 防未来函数 —— 最关键):
      对第 t 根, 特征仅用 [0, t];
      标签用 t 之后的 N 根 (默认 N=20) 的极值相对 close[t] 的偏移:
        up_exc = (max(high[t+1:t+N+1]) - close[t]) / close[t]
        dn_exc = (close[t] - min(low[t+1:t+N+1])) / close[t]
        label = 1 (UP) 若 up_exc > dn_exc  else 0 (DOWN)
      → 捕捉"未来 N 根哪一方向突破更大", 干净二分类, 不窥探 t 之后用于特征。

    抗过拟合 (小样本 H1 ~400 根, 训练窗口 ~300):
      - max_depth=7         : 限制单树深度, 防记忆噪声
      - min_samples_leaf=20 : 叶子至少 20 样本, 防过拟合单点
      - n_estimators=100    : 100 棵树取平均, 降方差
      - class_weight='balanced' : 标签可能不平衡, 平衡权重
      - max_features=0.5    : 每节点随机看一半特征, 增树间多样性(降相关)
      - 训练前校验: 样本数 < 50 或 仅单一类别 → 拒绝训练 (is_trained=False)
    """

    # 特征名 (顺序即特征向量顺序, 务必与 _build_features 一致)
    FEATURE_NAMES = [
        'ema_cross', 'adx', 'di_spread', 'macd_bar',
        'rsi', 'atr_rel', 'atr_ratio', 'range_pos',
    ]

    def __init__(self, n_future=20, train_window=300, warmup=70,
                 n_estimators=100, max_depth=7, min_samples_leaf=20,
                 random_state=42):
        if not _HAS_SK:
            raise RuntimeError(
                "scikit-learn 未安装, 无法构建 RFAlpha。请先: "
                "py -V:Astral\\CPython3.11.15 -m pip install --break-system-packages scikit-learn"
            ) from _SK_ERR
        self.n_future = n_future          # 标签前瞻 N 根
        self.train_window = train_window  # 滚动训练窗口(最近多少根)
        self.warmup = warmup              # 指标预热根数(特征有效起点)
        self.random_state = random_state

        # ── 抗过拟合参数 (小样本必控) ──
        self.model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            max_features=0.5,
            class_weight='balanced',
            n_jobs=1,
            random_state=random_state,
        )
        self.is_trained = False
        self.n_samples_ = 0
        self.classes_ = np.array([0, 1])

    # ── 特征工程 (因果: 第 t 行仅依赖 ≤ t) ──
    def _build_features(self, close, high, low):
        """返回 (features_2d, valid_mask)。

        features_2d: shape (n, 8), 每行一根 K 线的特征; 预热段为 NaN。
        valid_mask : bool 数组, 特征全部有限且达预热要求 → True。
        关键: 所有指标因果, 第 t 行仅用 close/high/low 的 [0, t]。
        """
        close = np.asarray(close, dtype=float)
        high = np.asarray(high, dtype=float)
        low = np.asarray(low, dtype=float)
        n = len(close)

        ema21 = _ema(close, 21)
        ema50 = _ema(close, 50)
        adx, di_spread = _adx(high, low, close)
        _, _, macd_bar = _macd(close)
        rsi = _rsi(close, 14)
        atr = _atr(high, low, close)
        atr_rel = atr / (close + 1e-10)
        atr_sma = _sma(atr, 50)
        atr_ratio = atr / (atr_sma + 1e-10)

        # 可选结构特征: 价格处于最近 lookback 根高低区间的位置 (0=底部,1=顶部)
        lookback = 30
        range_pos = np.full(n, np.nan)
        for t in range(lookback, n):
            hi = float(np.max(high[t - lookback:t + 1]))
            lo = float(np.min(low[t - lookback:t + 1]))
            rng = hi - lo
            if rng > 1e-12:
                range_pos[t] = (close[t] - lo) / rng

        feats = np.column_stack([
            (ema21 - ema50) / (close + 1e-10),  # ema_cross
            adx,                                 # adx
            di_spread,                           # di_spread
            macd_bar / (close + 1e-10),          # macd_bar
            rsi,                                 # rsi
            atr_rel,                             # atr_rel
            atr_ratio,                           # atr_ratio
            range_pos,                           # range_pos
        ])

        valid = np.isfinite(feats).all(axis=1) & (np.arange(n) >= self.warmup)
        return feats, valid

    # ── 标签 (严格错位: 仅用 t+1 .. t+N) ──
    def _make_labels(self, close, high, low):
        """返回标签数组 (长度 n), 不可标注的尾部为 -1。

        对第 t 根: 仅读取 high/low 的 [t+1, t+N] (严格错位, 不含 t 本身),
        比较未来向上/向下极值相对 close[t] 的偏移, 取更大者为方向。
        """
        close = np.asarray(close, dtype=float)
        high = np.asarray(high, dtype=float)
        low = np.asarray(low, dtype=float)
        n = len(close)
        labels = np.full(n, -1, dtype=int)
        N = self.n_future
        for t in range(n - N):
            # 仅未来窗口 t+1 .. t+N (含端点)
            fh = float(np.max(high[t + 1:t + 1 + N]))
            fl = float(np.min(low[t + 1:t + 1 + N]))
            base = close[t]
            if base <= 0:
                continue
            up_exc = (fh - base) / base
            dn_exc = (base - fl) / base
            labels[t] = 1 if up_exc > dn_exc else 0
        return labels

    # ── 训练 (滚动: 取最近 train_window 根) ──
    def fit(self, history, verbose=False):
        """用 (close, high, low) 训练。成功返回 True, 样本不足/退化返回 False。

        history: tuple(close, high, low) 任意长度; 自动取最近 train_window 根。
        """
        close, high, low = history
        close = np.asarray(close, dtype=float)
        high = np.asarray(high, dtype=float)
        low = np.asarray(low, dtype=float)
        n = len(close)
        min_need = self.warmup + self.n_future + 10
        if n < min_need:
            if verbose:
                print(f"  [RF] 样本不足 ({n}<{min_need}), 跳过训练")
            self.is_trained = False
            return False

        # 取最近 train_window 根 (滚动窗口; 调用方传入新历史即天然 retrain)
        if n > self.train_window:
            close = close[-self.train_window:]
            high = high[-self.train_window:]
            low = low[-self.train_window:]
            n = len(close)

        feats, valid = self._build_features(close, high, low)
        labels = self._make_labels(close, high, low)
        # 仅保留特征有效且标签可标注的样本
        sel = valid & (labels >= 0)
        X = feats[sel]
        y = labels[sel].astype(int)
        if len(y) < 50:
            if verbose:
                print(f"  [RF] 有效样本过少 ({len(y)}<50), 跳过训练")
            self.is_trained = False
            return False
        classes = np.unique(y)
        if len(classes) < 2:
            if verbose:
                print(f"  [RF] 标签仅单一类别 {classes.tolist()}, 无法二分类, 跳过")
            self.is_trained = False
            return False

        self.model.fit(X, y)
        self.is_trained = True
        self.n_samples_ = int(len(y))
        self.classes_ = np.asarray(self.model.classes_)
        if verbose:
            print(f"  [RF] 训练完成: {self.n_samples_} 样本, "
                  f"类别 {self.classes_.tolist()}")
        return True

    # ── 概率预测 (底层接口) ──
    def predict_proba(self, features):
        """features: 2D 数组 (n_samples, 8) 或 1D (8,)。返回 (n,2) 概率。"""
        if not self.is_trained:
            raise RuntimeError("RFAlpha 尚未训练, 请先 fit()")
        X = np.asarray(features, dtype=float)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        return self.model.predict_proba(X)

    # ── 便捷评分 (猎场司 gate 用) ──
    def score(self, close, high, low):
        """取最新一根 K 线的特征, 返回方向概率 dict。

        返回 {'UP': p_up, 'DOWN': p_down, 'confidence': max(p_up,p_down)}
        未训练 / 数据不足 / 特征含 NaN → 返回 None (调用方应放行, 不阻断交易链)。
        """
        if not self.is_trained:
            return None
        close = np.asarray(close, dtype=float)
        high = np.asarray(high, dtype=float)
        low = np.asarray(low, dtype=float)
        feats, valid = self._build_features(close, high, low)
        idx = np.where(valid)[0]
        if len(idx) == 0:
            return None
        last = feats[idx[-1]]  # 最新一根有效特征
        if np.any(np.isnan(last)):
            return None
        proba = self.model.predict_proba(last.reshape(1, -1))[0]
        cls = list(self.classes_)
        p_down = float(proba[cls.index(0)]) if 0 in cls else 0.0
        p_up = float(proba[cls.index(1)]) if 1 in cls else 0.0
        return {'UP': p_up, 'DOWN': p_down,
                'confidence': max(p_up, p_down)}

    # ── 特征重要性 (研策师反哺因子筛选用) ──
    def feature_importances(self):
        if not self.is_trained:
            return None
        imp = self.model.feature_importances_
        return dict(zip(self.FEATURE_NAMES, [float(x) for x in imp]))


# ═══ 独立运行: 轻量演示 (不连 MT5) ═══
if __name__ == '__main__':
    print("rf_alpha: 自包含随机森林 Alpha 层, import 使用 RFAlpha()")
    if not _HAS_SK:
        print("  [警告] scikit-learn 不可用:", _SK_ERR)
    else:
        rng = np.random.default_rng(0)
        # 合成: 升-降-升-降 交替, 每段清晰趋势 → 标签可分
        n = 600
        seg = n // 4
        close = np.cumprod(1.0 + np.concatenate([
            rng.normal(0.0015, 0.002, seg),
            rng.normal(-0.0015, 0.002, seg),
            rng.normal(0.0015, 0.002, seg),
            rng.normal(-0.0015, 0.002, seg),
        ])) * 100
        high = close * (1 + np.abs(rng.normal(0, 0.001, n)))
        low = close * (1 - np.abs(rng.normal(0, 0.001, n)))
        m = RFAlpha()
        ok = m.fit((close, high, low), verbose=True)
        print("  trained:", ok, "samples:", m.n_samples_)
        sc = m.score(close, high, low)
        print("  last score:", sc)
        print("  importances:", m.feature_importances())
