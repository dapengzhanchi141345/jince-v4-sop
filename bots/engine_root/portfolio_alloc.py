"""portfolio_alloc.py — P0-3 组合层：分数 Kelly + 风险平价 + 矩阵 Kelly（Ledoit-Wolf 收缩）

解决 G5(无组合风险预算) + G8(策略选择过拟合)：用**分数 Kelly** 分配跨策略资金，
用**逆波动风险平价**做底仓，避免赌单一最优子策略（CPCV 显示 PBO=0.625 过拟合）。

2026-09-06 升级（对标 2026 SOTA 共识）：
  - 新增 `ledoit_wolf_shrink`：协方差**收缩估计**（Ledoit-Wolf 族，旋转不变目标）。
    2026 共识（coriva / quantrading / marketmaker / theledgermind）：多资产 Kelly/均值-方差
    对协方差估计误差极度敏感，"Ledoit-Wolf 收缩必备"，否则 Σ⁻¹ 把噪声放大成致命权重。
  - 新增 `matrix_kelly`：多资产 Kelly f* = Σ_shrunk⁻¹·μ，收缩 + 分数化 + 单策略/杠杆硬上限。
    与单笔 `fractional_kelly` 一致哲学，但考虑策略间相关性（相关策略=一笔放大赌注）。

实证依据：15 资产 5 年 Full Kelly -21.44% / Optimized(Fractional) Kelly +22.86% / Risk Parity -11.13%。
→ 满 Kelly 灾难，分数 Kelly 碾压风险平价。本模块默认分数 Kelly 占比 50% + 风险平价 50%。
纯 numpy（无 sklearn/scipy）。
"""
from __future__ import annotations
import numpy as np


def fractional_kelly(win_rate, payoff_ratio, fraction=0.5):
    """Kelly 分数 = fraction * (p*(b+1)-1)/b。fraction<1 防满 Kelly 灾难(实证 -21%)。"""
    p = float(win_rate)
    b = max(float(payoff_ratio), 1e-6)
    k = (p * (b + 1) - 1) / b
    return max(0.0, fraction * k)


def risk_parity_weights(vols):
    """逆波动权重（简单风险平价，无需协方差矩阵）。vols: 各策略/资产波动率。"""
    inv = 1.0 / np.asarray(vols, dtype=float)
    s = inv.sum()
    return inv / s if s > 0 else np.ones_like(inv) / len(inv)


def ledoit_wolf_shrink(X, target="identity"):
    """Ledoit-Wolf 族协方差收缩估计（纯 numpy，旋转不变/常数相关目标）。

    X: (T, N) 收益率矩阵（行=时间, 列=资产/策略）。返回 (S_shrunk, delta)。
    收缩强度 δ = min(1, ΣΣ π_ij / ||S - F||²)（pi_ij = 样本协方差的方差）。
    目标 F：'identity' → μ·I（平均方差对角，旋转不变）；'diagonal' → 仅保留对角。
    2026 共识：协方差收缩是矩阵 Kelly/均值-方差的生产前置条件，消除满 Kelly 灾难的放大链。
    """
    X = np.asarray(X, dtype=float)
    T, N = X.shape
    Xc = X - X.mean(0)
    S = (Xc.T @ Xc) / T
    mu = np.trace(S) / N
    if target == "identity":
        F = mu * np.eye(N)
    elif target == "diagonal":
        F = np.diag(np.diag(S))
    else:
        raise ValueError("target must be 'identity' or 'diagonal'")
    # γ = ||S - F||_F²
    gamma = float(np.sum((S - F) ** 2))
    # π_ij = (1/T) Σ_t (x_ti x_tj - S_ij)²  （已去中心，均值修正项为 0）
    XtX = np.einsum("ti,tj->tij", Xc, Xc)          # (T,N,N)
    pi = np.mean((XtX - S) ** 2, axis=0)           # (N,N)
    pi_total = float(np.sum(pi))
    delta = min(1.0, pi_total / gamma) if gamma > 0 else 0.0
    S_shrunk = (1.0 - delta) * S + delta * F
    return S_shrunk, delta


def matrix_kelly(mu, cov, fraction=0.5, r=0.0, lev_cap=2.0, per_asset_cap=0.20):
    """多资产 Kelly 权重（收缩 + 分数化 + 硬上限）。

    f* = fraction · Σ_shrunk⁻¹·(μ - r)，默认 cov 已收缩；按 1/4~1/2 分数化。
    相关策略共享风险预算（Σ⁻¹ 自动削减重复押注）；单资产≤per_asset_cap、总杠杆≤lev_cap。
    返回权重向量（可含负向对冲权重，已 clip 至 [-per_asset_cap, per_asset_cap]）。
    """
    mu = np.asarray(mu, dtype=float) - r
    cov = np.asarray(cov, dtype=float)
    # 收缩后求逆（若 cov 已是收缩版则 delta≈0，等价于直接用）
    try:
        inv = np.linalg.inv(cov)
    except np.linalg.LinAlgError:
        inv = np.linalg.pinv(cov)
    raw = inv @ mu
    target = fraction * raw
    target = np.clip(target, -per_asset_cap, per_asset_cap)
    lev = np.abs(target).sum()
    if lev > lev_cap:
        target = target * (lev_cap / lev)
    return target


def allocate(strategy_metrics, kelly_fraction=0.5, rp_weight=0.5):
    """strategy_metrics: list of dict {name, win_rate, payoff_ratio, vol}
    返回 {name: weight} 归一化权重 = rp_weight*风险平价 + (1-rp_weight)*分数Kelly。
    """
    names = [m["name"] for m in strategy_metrics]
    vols = np.array([m["vol"] for m in strategy_metrics], dtype=float)
    kelly = np.array([fractional_kelly(m["win_rate"], m["payoff_ratio"], kelly_fraction)
                      for m in strategy_metrics], dtype=float)
    rp = risk_parity_weights(vols)
    if kelly.sum() <= 0:
        w = rp
    else:
        w = rp_weight * rp + (1 - rp_weight) * (kelly / kelly.sum())
    w = w / w.sum()
    return dict(zip(names, w))


def allocate_kelly_matrix(strategy_metrics, returns_matrix=None, fraction=0.4,
                          r=0.0, rp_weight=0.5):
    """矩阵 Kelly 组合层（2026-09-06 新增）：当提供逐策略收益矩阵时，用收缩协方差
    估计跨策略相关，按 f*=Σ⁻¹μ 分配；否则退化为单笔分数 Kelly。

    strategy_metrics: list of dict {name, win_rate, payoff_ratio, vol}
    returns_matrix: (T, N) 逐策略逐期收益（用于协方差收缩）；None 则退化为单笔 Kelly 路径。
    """
    names = [m["name"] for m in strategy_metrics]
    n = len(names)
    if returns_matrix is not None and returns_matrix.shape[1] == n and returns_matrix.shape[0] > n:
        S_shrunk, delta = ledoit_wolf_shrink(returns_matrix, target="identity")
        mu = returns_matrix.mean(0)
        mk = matrix_kelly(mu, S_shrunk, fraction=fraction, r=r)
        # 与风险平价底仓混合（防单策略崩溃 + 收缩估计误差兜底）
        rp = risk_parity_weights([m["vol"] for m in strategy_metrics])
        w = (1 - rp_weight) * mk + rp_weight * rp
        w = w - w.min() if w.min() < 0 else w          # 去负（demo 实盘暂不做空策略层）
        w = np.clip(w, 0, None)
        w = w / w.sum()
        return dict(zip(names, w)), {"shrinkage_delta": round(float(delta), 4),
                                      "method": "matrix_kelly+rp"}
    # 退化路径：单笔分数 Kelly + RP
    w = allocate(strategy_metrics, kelly_fraction=fraction, rp_weight=rp_weight)
    return w, {"shrinkage_delta": None, "method": "scalar_kelly+rp"}


if __name__ == "__main__":
    m = [{"name": "MR", "win_rate": 0.44, "payoff_ratio": 1.15, "vol": 0.020},
         {"name": "DIV", "win_rate": 0.43, "payoff_ratio": 1.10, "vol": 0.018},
         {"name": "VP", "win_rate": 0.46, "payoff_ratio": 1.20, "vol": 0.030}]
    print("scalar weights:", {k: round(v, 3) for k, v in allocate(m).items()})
    # 演示矩阵 Kelly（合成相关收益矩阵）
    rng = np.random.default_rng(0)
    R = np.column_stack([rng.normal(0.001, 0.02, 200),
                         rng.normal(0.0008, 0.018, 200),
                         rng.normal(0.0012, 0.030, 200)])
    w, info = allocate_kelly_matrix(m, returns_matrix=R, fraction=0.4)
    print("matrix weights:", {k: round(v, 3) for k, v in w.items()}, "|", info)
