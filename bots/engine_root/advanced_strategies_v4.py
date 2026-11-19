# advanced_strategies_v4.py — 金策宗师团 V4 升级整合版
"""
V4 升级整合版 - 所有策略统一到高级 V4 特性
- 机构级风控集成 (RiskManager)
- 动态参数自适应
- 信号质量评分
- 多时间框架确认
- 信号时效衰减
"""

import numpy as np
import pandas as pd
from typing import List, Dict
import importlib

# 尝试导入 V4 修复版
try:
    from v4_strategy_fixes import gen_sdp_v4_fixed, gen_mr_v4_fixed
    _HAS_V4_FIXES = True
except ImportError:
    _HAS_V4_FIXES = False

# 尝试导入其他 V4 策略
try:
    from ict_strategy_v4 import gen_ict_v4 as gen_ict_v4_mod
    _HAS_ICT_V4 = True
except ImportError:
    _HAS_ICT_V4 = False

try:
    from bo_strategy_v4 import gen_bo_v4 as gen_bo_v4_mod
    _HAS_BO_V4 = True
except ImportError:
    _HAS_BO_V4 = False

try:
    from trend_strategy_v4 import gen_trend_v4 as gen_trend_v4_mod
    _HAS_TREND_V4 = True
except ImportError:
    _HAS_TREND_V4 = False

try:
    from div_strategy_v4 import gen_div_v4 as gen_div_v4_mod
    _HAS_DIV_V4 = True
except ImportError:
    _HAS_DIV_V4 = False

try:
    from vp_strategy_v4 import gen_vp_v4 as gen_vp_v4_mod
    _HAS_VP_V4 = True
except ImportError:
    _HAS_VP_V4 = False

# 尝试导入主模块
try:
    from advanced_strategies import (
        gen_sdp, gen_ict, gen_vp, gen_divergence, gen_meanrev,
        gen_trend, gen_breakout, STRATEGY_REGISTRY
    )
    _HAS_ADVANCED = True
except ImportError:
    _HAS_ADVANCED = False


# ═══════════════════════════════════════════════════════════════
# V4 策略包装器 - 提供统一接口
# ═══════════════════════════════════════════════════════════════

def _wrap_v4(gen_func, name: str):
    """包装V4生成器到标准接口"""
    def wrapper(h1, h4, d1, cfg):
        try:
            return gen_func(h1, h4, d1, cfg)
        except Exception as e:
            print(f"[WARN] {name} V4 failed: {e}")
            return []
    return wrapper


# ═══════════════════════════════════════════════════════════════
# V4 策略注册表
# ═══════════════════════════════════════════════════════════════

STRATEGY_REGISTRY_V4 = {}

# 优先使用 V4 版本
if _HAS_V4_FIXES:
    STRATEGY_REGISTRY_V4["SDP"] = _wrap_v4(gen_sdp_v4_fixed, "SDP")
else:
    STRATEGY_REGISTRY_V4["SDP"] = gen_sdp

if _HAS_ICT_V4:
    STRATEGY_REGISTRY_V4["ICT"] = _wrap_v4(gen_ict_v4_mod, "ICT")
elif _HAS_ADVANCED:
    STRATEGY_REGISTRY_V4["ICT"] = gen_ict

if _HAS_BO_V4:
    STRATEGY_REGISTRY_V4["BO"] = _wrap_v4(gen_bo_v4_mod, "BO")
elif _HAS_ADVANCED:
    STRATEGY_REGISTRY_V4["BO"] = gen_breakout

if _HAS_TREND_V4:
    STRATEGY_REGISTRY_V4["TREND"] = _wrap_v4(gen_trend_v4_mod, "TREND")
elif _HAS_ADVANCED:
    STRATEGY_REGISTRY_V4["TREND"] = gen_trend

if _HAS_DIV_V4:
    STRATEGY_REGISTRY_V4["DIV"] = _wrap_v4(gen_div_v4_mod, "DIV")
elif _HAS_ADVANCED:
    STRATEGY_REGISTRY_V4["DIV"] = gen_divergence

if _HAS_VP_V4:
    STRATEGY_REGISTRY_V4["VP"] = _wrap_v4(gen_vp_v4_mod, "VP")
elif _HAS_ADVANCED:
    STRATEGY_REGISTRY_V4["VP"] = gen_vp

if _HAS_V4_FIXES:
    STRATEGY_REGISTRY_V4["MR"] = _wrap_v4(gen_mr_v4_fixed, "MR")
elif _HAS_ADVANCED:
    STRATEGY_REGISTRY_V4["MR"] = gen_meanrev

# 尝试导入 OTAS 和 PASD
try:
    from otas_strategy_v3 import gen_otas_v3
    STRATEGY_REGISTRY_V4["OTAS"] = _wrap_v4(gen_otas_v3, "OTAS")
except ImportError:
    try:
        from otas_strategy import gen_otas
        STRATEGY_REGISTRY_V4["OTAS"] = _wrap_v4(gen_otas, "OTAS")
    except ImportError:
        pass

try:
    from pasd_fusion_v3 import gen_pasd as gen_pasd_v3
    STRATEGY_REGISTRY_V4["PASD"] = _wrap_v4(gen_pasd_v3, "PASD")
except ImportError:
    try:
        from pasd_fusion import gen_pasd
        STRATEGY_REGISTRY_V4["PASD"] = _wrap_v4(gen_pasd, "PASD")
    except ImportError:
        pass

# SESSION 策略
try:
    from advanced_strategies import gen_session
    STRATEGY_REGISTRY_V4["SESSION"] = _wrap_v4(gen_session, "SESSION")
except ImportError:
    pass

# APEX 策略 (V5) — 来自朋友账户 60129252「Godking Apex Short v4.2」的迁移版
# ⚠️ 回测验证为负 (XAUUSD 2015-2026, 纯空 PF=0.34 / 双向 PF=0.49, 均<1):
#    该逻辑无可复现正 edge, 仅作研究/回测可用, 禁止加入实盘 strategy_configs 启用!
#    注册进来是为了 (a) 保留模块 (b) 供离线回测与后续双向增强实验。
try:
    from apex_strategy_v5 import gen_apex as gen_apex_v5
    STRATEGY_REGISTRY_V4["APEX"] = _wrap_v4(gen_apex_v5, "APEX")
except ImportError:
    pass

# Apex 结构门控: 唯一值得借用的部分 —— 把「结构上下文+供给/需求区」作质量过滤注入 SDP/ICT。
# Walk-Forward 验证: 门控提升 PF 且 OOS 提升最大(非过拟合), 交易数砍半、质量更高。
# 仅过滤删除信号(不新增), 异常自动回退原信号。实盘首选策略启用。
try:
    from apex_gate import gate_wrap as _gate_wrap
    for _nm in ["SDP", "ICT"]:
        if _nm in STRATEGY_REGISTRY_V4:
            STRATEGY_REGISTRY_V4[_nm] = _gate_wrap(STRATEGY_REGISTRY_V4[_nm], _nm, "XAUUSD")
except ImportError:
    pass


# ═══════════════════════════════════════════════════════════════
# 混合模式 - 核心策略用 V4，其他用 V1
# ═══════════════════════════════════════════════════════════════

def get_strategy_registry(use_v4: bool = True) -> Dict[str, callable]:
    """
    获取策略注册表
    参数:
        use_v4: 是否优先使用 V4 版本
    返回:
        策略注册表字典
    """
    if use_v4:
        return STRATEGY_REGISTRY_V4
    elif _HAS_ADVANCED:
        return STRATEGY_REGISTRY
    else:
        return STRATEGY_REGISTRY_V4




# ═══════════════════════════════════════════════════════════════
# CLASS_STRATEGY_MAP - 品种策略映射
# ═══════════════════════════════════════════════════════════════
CLASS_STRATEGY_MAP = {
    "forex_major": ["SDP", "ICT", "DIV", "MR", "VP", "TREND", "PASD", "OTAS"],
    "forex_cross": ["SDP", "ICT", "DIV", "MR", "VP", "TREND", "PASD", "OTAS"],
    "jpy_cross":   ["SDP", "ICT", "DIV", "MR", "VP", "TREND", "PASD", "OTAS"],
    "exotic":      ["SDP", "ICT", "MR", "TREND", "PASD", "OTAS"],
    "metal":       ["PASD", "ICT", "SDP", "TREND", "MR", "DIV", "OTAS"],
    "metal_ag":    ["PASD", "ICT", "SDP", "TREND", "MR", "DIV", "OTAS"],
    "metal_pgm":   ["PASD", "ICT", "SDP", "TREND", "MR", "OTAS"],
    "energy":      ["TREND", "SDP", "MR", "PASD", "OTAS"],
    "energy_gas":  ["TREND", "SDP", "MR", "PASD", "OTAS"],
    "crypto":      ["PASD", "TREND", "MR", "SDP", "ICT", "DIV", "OTAS"],
    "crypto_alt":  ["PASD", "TREND", "MR", "SDP", "ICT", "DIV", "OTAS"],
    "crypto_small":["PASD", "TREND", "MR", "SDP", "ICT", "DIV", "OTAS"],
    "index":       ["TREND", "PASD", "SDP", "ICT", "MR", "VP", "OTAS"],
    "index_asia":  ["TREND", "PASD", "SDP", "ICT", "MR", "VP", "OTAS"],
    "stock":       ["TREND", "BO", "MR", "SDP", "PASD", "OTAS"],
    "etf":         ["TREND", "MR", "BO", "PASD", "OTAS"],
    "commodity_soft": ["TREND", "SDP", "MR", "PASD", "OTAS"],
    "commodity_grain":["TREND", "SDP", "MR", "PASD", "OTAS"],
    "bond":        ["TREND", "SDP", "MR", "PASD", "OTAS"],
}

# 测试代码
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("V4 策略整合系统")
    print("=" * 70)
    print()
    print("已注册的 V4 策略:")
    for name in STRATEGY_REGISTRY_V4.keys():
        print(f"  - {name}")
    print()
    print(f"总计: {len(STRATEGY_REGISTRY_V4)} 个策略")
    print()
    print("可用模块:")
    print(f"  - V4 Fixes: {_HAS_V4_FIXES}")
    print(f"  - ICT V4: {_HAS_ICT_V4}")
    print(f"  - BO V4: {_HAS_BO_V4}")
    print(f"  - TREND V4: {_HAS_TREND_V4}")
    print(f"  - DIV V4: {_HAS_DIV_V4}")
    print(f"  - VP V4: {_HAS_VP_V4}")
    print(f"  - Advanced: {_HAS_ADVANCED}")
    print("=" * 70)
