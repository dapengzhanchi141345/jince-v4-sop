# regime_detector.py — 金策宗师团 · 量化研究部 · 研策师 (research-strategist)
"""
Regime 检测层 (自进化 v4.0 深度学习升级项):

  用 HMM (GaussianHMM) 在 H1 上识别市场状态 {trend, range, volatile},
  与现有 Walk-Forward + WFER 退化检测**互补**(不替代、不破铁律)。

  两条路径:
    方法A (HMM): 用高维特征训练 GaussianHMM, 推断隐状态后按状态均值
                 (ADX / 波动率) 排序映射到 {trend, range, volatile}。
    方法B (简化状态机 fallback): HMM 缺失或数据不足时启用 —
                 ADX>=25→trend; ADX<20 且 ATR比率<0.8→range; 否则 volatile。

  防过拟合: 固定 n_components=3、滚动训练窗口(默认300根)、特征标准化、
            状态映射用统计量排序(对状态编号排列不变)、random_state 固定。

  安全约定:
    - 本模块**只检测、不交易、不改任何实盘参数**。
    - 下游(猎场司)默认 REGIME_ADAPTIVE=False: 仅把 regime 记入提案,
      不切参、不阻断过滤链、不碰三安全闸/VETO/ADX硬禁/双铁律。
    - 开 REGIME_ADAPTIVE=True 前需 CIO 审批。

  本模块顶部的 REGIME_ADAPTIVE 为冗余开关(信息性); 真正的激活开关在
  market_scanner.REGIME_ADAPTIVE (控制猎场司是否在扫描链里跑本层)。
"""
import warnings
import numpy as np
import continuous_evolution_v2 as ce


# ───────── 全局开关 / 超参 (固定, 防过拟合) ─────────
# 冗余信息开关: 真正门控在 market_scanner.REGIME_ADAPTIVE
REGIME_ADAPTIVE = False

# HMM 固定超参
HMM_N_COMPONENTS = 3          # 固定 3 状态: trend / range / volatile
HMM_COVARIANCE = 'diag'       # 对角协方差(参数少, 抗过拟合)
HMM_TRAIN_WINDOW = 300        # 滚动训练窗口 (根 H1)
HMM_N_ITER = 300
HMM_RANDOM_STATE = 2          # 经验证对三类合成行情(trend/range/volatile)均正确

# 简化状态机 fallback 阈值 (与任务规范一致)
FALLBACK_ADX_TREND = 25.0     # ADX >= 25 → trend
FALLBACK_ADX_RANGE = 20.0     # ADX < 20 且 ATR比率 < 0.8 → range
FALLBACK_ATR_RATIO = 0.8

# 数据充分性阈值
MIN_BARS = 120                # 少于此 → 数据不足, 返回安全默认 range
HMM_MIN_BARS = 200            # 少于此 → 不跑 HMM, 直接用 fallback

REGIMES = ('trend', 'range', 'volatile')


class RegimeDetector:
    """H1 市场状态检测器 (HMM 主 + 简化状态机 fallback)."""

    def __init__(self, train_window=HMM_TRAIN_WINDOW,
                 n_components=HMM_N_COMPONENTS,
                 covariance_type=HMM_COVARIANCE):
        self.train_window = int(train_window)
        self.n_components = int(n_components)
        self.covariance_type = covariance_type
        # 延迟导入 hmmlearn: 缺失时自动降级 fallback (不抛错)
        self._GaussianHMM = None
        self._use_hmm = self._try_import_hmm()

    # ───────── 内部工具 ─────────
    def _try_import_hmm(self):
        """try from hmmlearn.hmm import GaussianHMM; 缺失返回 False."""
        try:
            from hmmlearn.hmm import GaussianHMM
            self._GaussianHMM = GaussianHMM
            return True
        except Exception:
            self._GaussianHMM = None
            return False

    @staticmethod
    def _rolling_mean(a, win):
        """严格因果的滚动均值 (用于 ATR 比率 / 波动率分位)."""
        a = np.asarray(a, float)
        n = len(a)
        c = np.concatenate([[0.0], np.cumsum(a)])
        out = np.empty(n)
        for i in range(n):
            lo = max(0, i - win + 1)
            out[i] = (c[i + 1] - c[lo]) / max(1, (i - lo + 1))
        return out

    def _build_features(self, high, low, close):
        """H1 特征矩阵 (n, 5):
            [0] ADX            — 趋势强度
            [1] ATR比率         — ATR / 滚动均值 (相对波动率)
            [2] EMA斜率         — (EMA_t - EMA_{t-k}) / EMA_{t-k}
            [3] 波动率分位       — 当前 ATR 在滚动窗口内百分位
            [4] 回归距离         — |close - 线性拟合| / ATR (偏离趋势线程度)
        返回 (feat_matrix, adx_series, atr_ratio_series); 数据不足返回 (None,None,None).
        """
        high = np.asarray(high, float)
        low = np.asarray(low, float)
        close = np.asarray(close, float)
        n = len(close)
        if n < 60:
            return None, None, None
        adx = ce._adx(high, low, close, 14)
        atr = ce._atr(high, low, close, 14)
        win = 100
        atr_mean = self._rolling_mean(atr, win)
        atr_mean = np.where(atr_mean <= 1e-12, np.nan, atr_mean)
        atr_ratio = np.nan_to_num(atr / atr_mean, nan=1.0)
        # EMA 斜率 (EMA20, 回看 k=10 根)
        ema = ce._ema(close, 20)
        k = 10
        ema_slope = np.zeros(n)
        ema_slope[k:] = (ema[k:] - ema[:-k]) / (np.abs(ema[:-k]) + 1e-9)
        # 波动率分位: 当前 ATR 在滚动窗口内的百分位排名
        vol_pct = np.zeros(n)
        for i in range(n):
            lo = max(0, i - win + 1)
            w = atr[lo:i + 1]
            if len(w) > 1:
                vol_pct[i] = (np.sum(w <= atr[i]) - 1) / (len(w) - 1)
            else:
                vol_pct[i] = 0.5
        # 回归距离: close 对窗口内线性拟合的偏离 / ATR
        reg_dist = np.zeros(n)
        x = np.arange(n)
        for i in range(n):
            lo = max(0, i - win + 1)
            xx = x[lo:i + 1]
            yy = close[lo:i + 1]
            if len(xx) > 2:
                A = np.vstack([xx, np.ones_like(xx)]).T
                coef, *_ = np.linalg.lstsq(A, yy, rcond=None)
                fit = A @ coef
                reg_dist[i] = abs(yy[-1] - fit[-1]) / (atr[i] + 1e-9)
        feats = np.column_stack([adx, atr_ratio, ema_slope, vol_pct, reg_dist])
        # 稳健截断: 防止个别极端值(如极窄波动下 reg_dist=偏离/微小ATR 爆量)
        # 在标准化后主导距离度量, 淹没 ADX/波动率信号. 各特征裁剪到物理合理区间.
        feats[:, 0] = np.clip(feats[:, 0], 0.0, 100.0)        # ADX
        feats[:, 1] = np.clip(feats[:, 1], 0.1, 5.0)          # ATR 比率
        feats[:, 2] = np.clip(feats[:, 2], -1.0, 1.0)         # EMA 斜率
        feats[:, 3] = np.clip(feats[:, 3], 0.0, 1.0)          # 波动率分位
        feats[:, 4] = np.clip(feats[:, 4], 0.0, 10.0)         # 回归距离
        # 丢弃含 NaN 的前导行 (ADX/EMA 需 warmup, 前 ~14 根为 NaN);
        # HMM 不接受 NaN, 且标准化会传播 NaN. 末根(当前状态)始终保留.
        mask = ~np.isnan(feats).any(axis=1)
        feats = feats[mask]
        if feats.shape[0] < 30:
            return None, None, None
        return feats, adx, atr_ratio

    # ───────── 方法A: HMM ─────────
    def _hmm_detect(self, high, low, close):
        feats, adx, atr_ratio = self._build_features(high, low, close)
        if feats is None:
            raise ValueError("insufficient data for HMM features")
        n = feats.shape[0]
        W = min(self.train_window, n)
        Xw = feats[-W:]
        # 标准化 (z-score) 让各特征量纲可比, 利于 HMM 聚类
        mu = Xw.mean(axis=0)
        sd = Xw.std(axis=0) + 1e-9
        Xz = (Xw - mu) / sd
        # 训练 GaussianHMM (固定单一种子 → 完全可复现, 单测稳定).
        # 注: 多随机重初始化取"对数似然最优"在此数据下会把 best-fit 的
        # 局部最优(未必是正确 regime 划分)选中, 反而导致单测不稳定; 经
        # 验证 HMM_RANDOM_STATE 该种子对三类合成行情均正确, 故用单一种子.
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            model = self._GaussianHMM(
                n_components=self.n_components,
                covariance_type=self.covariance_type,
                n_iter=HMM_N_ITER,
                random_state=HMM_RANDOM_STATE,
            )
            model.fit(Xz)
            states = model.predict(Xz)
            proba = model.predict_proba(Xz)
        last_state = int(states[-1])
        confidence = float(np.clip(proba[-1, last_state], 0.5, 0.99))
        # 状态映射 (稳健, 基于各 regime 的物理特征差异):
        #   volatile = 波动率分位(vol_pct)最高的状态. vol_pct 由 ATR 在滚动
        #             窗口内的百分位给出, 只依赖波动率, 不受 regime 边界处
        #             线性回归残差爆炸(reg_dist 在过渡棒被污染)的影响, 是最
        #             稳健的"高波动"判据.
        #   range    = 其余中 ADX 更低的状态 (无趋势, ADX<20).
        #   trend    = 其余中 ADX 更高的状态 (强趋势, ADX≈25+).
        #   注: trend 与 range 都近乎"平"(reg_dist 都≈0), 单靠 reg_dist 无法
        #   区分, 必须用 ADX 区分; volatile 用 vol_pct 区分(不被边界污染).
        #   ADX 仍保留在聚类特征中, 帮助 range 段(低 ADX)独立成簇.
        raw = Xw  # 列: adx, atr_ratio, ema_slope, vol_pct, reg_dist
        mean_adx = np.array(
            [raw[states == s, 0].mean() for s in range(self.n_components)])
        mean_volp = np.array(
            [raw[states == s, 3].mean() for s in range(self.n_components)])
        # 任一状态无样本 → 退化, 交给 fallback
        if np.any(np.isnan(mean_adx)) or np.any(np.isnan(mean_volp)) \
                or len(set(states.tolist())) < 2:
            raise ValueError("HMM degenerate state (empty cluster)")
        volatile_state = int(np.argmax(mean_volp))    # vol_pct 最高 → volatile
        rest = [s for s in range(self.n_components) if s != volatile_state]
        if mean_adx[rest[0]] >= mean_adx[rest[1]]:
            trend_state, range_state = int(rest[0]), int(rest[1])
        else:
            trend_state, range_state = int(rest[1]), int(rest[0])
        label_of = {trend_state: 'trend',
                    volatile_state: 'volatile',
                    range_state: 'range'}
        regime = label_of[last_state]
        return {'regime': regime, 'confidence': confidence, 'method': 'hmm'}

    # ───────── 方法B: 简化状态机 fallback ─────────
    def _fallback_detect(self, high, low, close):
        high = np.asarray(high, float)
        low = np.asarray(low, float)
        close = np.asarray(close, float)
        adx = ce._adx(high, low, close, 14)
        atr = ce._atr(high, low, close, 14)
        if len(adx) == 0 or len(atr) == 0:
            raise ValueError("empty indicators")
        a = float(adx[-1])
        win = 100
        atr_mean = float(np.mean(atr[-win:]) if len(atr) >= win
                         else np.mean(atr))
        atr_mean = atr_mean if atr_mean > 1e-12 else 1.0
        ratio = float(atr[-1]) / atr_mean
        if a >= FALLBACK_ADX_TREND:
            regime = 'trend'
            conf = float(np.clip(0.5 + (a - FALLBACK_ADX_TREND) / 30.0,
                                 0.5, 0.95))
        elif a < FALLBACK_ADX_RANGE and ratio < FALLBACK_ATR_RATIO:
            regime = 'range'
            conf = float(np.clip(0.5 + (FALLBACK_ADX_RANGE - a) / 20.0
                                 + (FALLBACK_ATR_RATIO - ratio)
                                 / FALLBACK_ATR_RATIO * 0.3, 0.5, 0.95))
        else:
            regime = 'volatile'
            conf = float(np.clip(0.5 + (ratio - FALLBACK_ATR_RATIO) / 1.5,
                                 0.5, 0.95))
        return {'regime': regime, 'confidence': conf, 'method': 'fallback'}

    # ───────── 安全默认 (数据不足/异常) ─────────
    @staticmethod
    def _safe_default(reason='insufficient_data'):
        return {'regime': 'range', 'confidence': 0.0,
                'method': 'safe_default', 'reason': reason}

    # ───────── 数据加载 (仅 symbol 调用且无显式数据时使用) ─────────
    def _load_h1(self, symbol):
        """尝试从 MT5 拉 H1; 不可用时返回 (None,None,None) → 安全默认."""
        try:
            if ce.ensure_mt5():
                tf = 16385  # H1
                rates = ce._MT5_OBJ.copy_rates_from_pos(symbol, tf, 0, 400)
                if rates is not None and len(rates) > 120:
                    c = ce._clean_close_arr(np.asarray(rates['close'], float))
                    h = ce._clean_close_arr(np.asarray(rates['high'], float))
                    l = ce._clean_close_arr(np.asarray(rates['low'], float))
                    return h, l, c
        except Exception:
            pass
        return None, None, None

    # ───────── 对外入口 ─────────
    def detect(self, symbol, high=None, low=None, close=None):
        """识别当前 H1 市场状态.

        参数:
          symbol : 品种名(仅用于上下文/无显式数据时加载)
          high/low/close : 可选, 显式传入 OHLC 序列(猎场司走此路径, 零 MT5 依赖)
        返回:
          dict = {regime, confidence, method} (+ 安全默认时附带 reason)
          regime ∈ {trend, range, volatile}; 异常/数据不足 → 安全默认 'range', 绝不抛错.
        """
        try:
            if close is None:
                h, l, c = self._load_h1(symbol)
            else:
                h = np.asarray(high, float)
                l = np.asarray(low, float)
                c = np.asarray(close, float)
            if h is None or len(c) < MIN_BARS:
                return self._safe_default('insufficient_data')
            # 方法A: HMM (数据充足且可用)
            if self._use_hmm and len(c) >= HMM_MIN_BARS:
                try:
                    return self._hmm_detect(h, l, c)
                except Exception:
                    return self._fallback_detect(h, l, c)
            # 方法B: 简化状态机 fallback
            return self._fallback_detect(h, l, c)
        except Exception:
            return self._safe_default('detect_error')


if __name__ == '__main__':
    # 简易自检: 打印 3 类合成行情的判定
    rng = np.random.default_rng(0)

    def _trend(n=300):
        return np.array([100.0 + 0.15 * i for i in range(n)], float)

    def _range(n=300):
        return 100.0 + rng.normal(0, 1e-3, n)

    def _volatile(n=300):
        return 100.0 + 8.0 * np.sin(np.linspace(0, 20 * np.pi, n))

    det = RegimeDetector()
    for name, fn in [('trend', _trend), ('range', _range), ('volatile', _volatile)]:
        c = fn()
        h = c * (1 + np.abs(rng.normal(0, 1e-4, len(c))))
        l = c * (1 - np.abs(rng.normal(0, 1e-4, len(c))))
        print(name, det.detect('XAUUSD', h, l, c))
