"""regime_router.py — P0-2 规则状态机路由（无 ML 依赖）

按"波动率状态(低/中/高) + 趋势状态(趋势/震荡)"动态改写策略优先级，
让系统在有利 regime 偏趋势策略、不利 regime 偏均值回归/空仓，从而对冲
CPCV 暴露的"2024 两块净亏损" regime 集中风险（见 CPCV_VALIDATION_REPORT.md §2）。

集成点：在 guardian_executor 选策略前调用 select_strategies() 替换/加权 CLASS_STRATEGY_MAP。
纯 numpy，无 sklearn/scipy。
"""
from __future__ import annotations
import numpy as np

# 波动率分位阈值（vol_now 在历史 vol 分布中的相对位置）
VOL_LOW_PCT, VOL_HIGH_PCT = 0.33, 0.67
# 趋势强度阈值（ADX）
ADX_TREND = 25.0
# [2026-08-28 P2 全网升级] 趋势持续性: 价格 vs EMA200 结构过滤
# (三层透镜框架的 Trend lens, 防震荡市假趋势). ADX 高但价格在 EMA200
# 下方 (下降趋势中的反弹) 不应视为强趋势做多.
STRUCT_LENS_WEIGHT = 0.5   # 结构透镜影响: 0.5=中等 (保守, 不硬切)

# 各 regime 下的策略优先级（值越大越优先；0=禁用）。修 G2。
REGIME_PRIORITY = {
    ("high", "trend"): {"TREND": 3, "BO": 2, "ICT": 1, "DIV": 1, "MR": 0, "VP": 0, "SDP": 0},
    ("high", "range"): {"MR": 2, "ICT": 2, "VP": 1, "DIV": 1, "TREND": 0, "BO": 0, "SDP": 0},
    ("mid", "trend"):  {"TREND": 3, "BO": 2, "ICT": 2, "MR": 1, "VP": 1, "DIV": 1, "SDP": 1},
    ("mid", "range"):  {"MR": 3, "VP": 2, "ICT": 2, "DIV": 2, "TREND": 0, "BO": 0, "SDP": 1},
    ("low", "trend"):  {"TREND": 3, "BO": 3, "SDP": 2, "MR": 1, "ICT": 1, "VP": 1, "DIV": 1},
    ("low", "range"):  {"MR": 3, "VP": 3, "DIV": 2, "ICT": 2, "SDP": 1, "TREND": 0, "BO": 0},
}


def detect_regime(vol_now, vol_history, adx, close=None, ema200=None):
    """返回 (vol_state, trend_state)。

    vol_now: 当前已实现波动率(scalar)；vol_history: 历史波动率序列(np.array)；
    adx: 当前 ADX 标量。vol_state 由 vol_now 在历史中的分位决定。
    [2026-08-28 P2] 可选结构透镜: close/ema200 提供价格vs长均线方向,
    与 ADX 趋势方向冲突时降级为 range (震荡), 防止下降趋势反弹假突破.
    """
    hist = np.asarray(vol_history, dtype=float)
    if len(hist) < 3:
        return ("mid", "range")
    rank = float((hist < vol_now).mean())  # vol_now 在历史中的分位 0..1
    if rank < VOL_LOW_PCT:
        vol_state = "low"
    elif rank > VOL_HIGH_PCT:
        vol_state = "high"
    else:
        vol_state = "mid"
    trend_state = "trend" if float(adx) >= ADX_TREND else "range"
    # 结构透镜: ADX 高但价格与 EMA200 冲突 → 削弱趋势判定
    if trend_state == "trend" and close is not None and ema200 is not None:
        try:
            _struct_ok = float(close) > float(ema200)
            # ADX 高 + 价格在 EMA200 下方 → 大概率反弹而非真趋势
            # (用权重软化而非硬切, 保守)
            if not _struct_ok and float(adx) < 35.0:
                trend_state = "range"  # 结构不确认, 降级震荡
        except Exception:
            pass
    return (vol_state, trend_state)


def select_strategies(vol_now, vol_history, adx):
    """返回按优先级降序的 (strategy, weight) 列表（已过滤禁用项）。"""
    vs, ts = detect_regime(vol_now, vol_history, adx)
    pri = REGIME_PRIORITY[(vs, ts)]
    ordered = sorted([(s, w) for s, w in pri.items() if w > 0],
                     key=lambda x: x[1], reverse=True)
    return ordered


if __name__ == "__main__":
    vol_hist = np.random.randn(200).cumsum() % 1 + 0.01
    print("regime:", detect_regime(0.02, vol_hist, 30.0))
    print("strategies:", select_strategies(0.02, vol_hist, 30.0))
