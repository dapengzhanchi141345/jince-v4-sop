"""meta_label_filter.py — P1-1 Meta-Labeling 过滤器骨架（纯 numpy，无 sklearn）

主模型(规则)定方向 → 次模型(此处用纯 numpy 逻辑回归占位)预测该信号是否盈利
→ 按置信度过滤假阳性 + 缩放仓位。落地 López de Prado《Advances in Financial ML》哲学。

实证：均值回归策略 OOS 准确率 17%→63%；趋势 48%→55%；验证 OOS Sharpe 2.06。
日线层级阈值 0.65 → +4.5% 准确率(nydartrading)。生产可换 mlfinpy / LightGBM。
"""
from __future__ import annotations
import numpy as np


def triple_barrier_label(prices, entry_idx, pt_mult, sl_mult, vol, max_h):
    """对单个 entry 打标签：上屏障(盈利)/下屏障(止损)/垂直屏障(超时)。
    prices: 价格序列(np.array)；entry_idx: 入场位置；vol: 该点波动率；
    pt_mult/sl_mult: 以 vol 为单位的止盈/止损倍数。返回 +1/-1/0。
    """
    path = prices[entry_idx: entry_idx + max_h + 1]
    if len(path) < 2:
        return 0
    up, dn = pt_mult * vol, -sl_mult * vol
    ret = path / path[0] - 1.0
    hit_up = np.where(ret >= up)[0]
    hit_dn = np.where(ret <= dn)[0]
    if len(hit_up) and (not len(hit_dn) or hit_up[0] < hit_dn[0]):
        return 1
    if len(hit_dn):
        return -1
    return 0  # 超时：按 0（或 ret 符号）


class MetaFilter:
    """纯 numpy 逻辑回归次模型（占位）。生产可换 XGBoost/LightGBM。"""
    def __init__(self, lr=0.1, n_iter=200, threshold=0.65):
        self.lr = lr
        self.n_iter = n_iter
        self.threshold = threshold
        self.w = None
        self.b = 0.0

    def fit(self, X, y, sample_weight=None):
        """sample_weight: 可选 (n,) 类别/样本权重（如处理胜率不均衡）。默认等权。"""
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        n, d = X.shape
        if sample_weight is None:
            sw = np.ones(n)
        else:
            sw = np.asarray(sample_weight, dtype=float)
        self.w = np.zeros(d)
        for _ in range(self.n_iter):
            z = 1.0 / (1 + np.exp(-(X @ self.w + self.b)))
            g = (z - y) * sw
            self.w -= self.lr * (X.T @ g) / n
            self.b -= self.lr * g.mean()

    def predict_proba(self, X):
        X = np.asarray(X, dtype=float)
        return 1.0 / (1 + np.exp(-(X @ self.w + self.b)))

    def decide(self, X):
        """返回 (pass: bool, confidence: float)。阈值 0.65 来自日线实证(+4.5%)。"""
        p = self.predict_proba(X)
        return (p >= self.threshold), p


if __name__ == "__main__":
    np.random.seed(0)
    X = np.random.randn(200, 4)
    y = (X[:, 0] + X[:, 1] > 0).astype(float)
    m = MetaFilter()
    m.fit(X, y)
    print("proba sample:", np.round(m.predict_proba(X[:3]), 3))
