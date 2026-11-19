# -*- coding: utf-8 -*-
"""
StrategyFusionBridge V1.0
策略融合桥接器 — 将MasterCoordinator集成到现有系统

这个模块提供两个功能:
1. 替换现有scan_symbol的逻辑，使用多策略融合
2. 保持与现有 guardian_executor 的兼容性
"""

import sys
import os
import numpy as np
import pandas as pd
from typing import Tuple, Optional, Dict, List

# 导入现有模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regime_router as rr
import edge_tracker as et
import symbol_universe as su
# [2026-08-31 V4升级] 优先V4策略注册表, 失败回退V1
try:
    from advanced_strategies_v4 import (CLASS_STRATEGY_MAP, STRATEGY_REGISTRY,
                                        STRATEGY_REGISTRY_V4)
    import advanced_strategies_v4 as ast
except Exception:
    import advanced_strategies as ast
    from advanced_strategies import CLASS_STRATEGY_MAP, STRATEGY_REGISTRY
    STRATEGY_REGISTRY_V4 = STRATEGY_REGISTRY

# 导入新模块
from master_coordinator import MasterCoordinator, SignalPriority


# ═══════════════════════════════════════════════════════════════
# 全局协调器实例 (懒加载)
# ═══════════════════════════════════════════════════════════════

_master_coordinator = None
_coordinator_initialized = False


def get_coordinator() -> MasterCoordinator:
    """获取或初始化MasterCoordinator单例"""
    global _master_coordinator, _coordinator_initialized
    
    if _coordinator_initialized and _master_coordinator:
        return _master_coordinator
    
    # 加载KEEP列表
    keep_symbols = []
    try:
        from live_bridge import load_keep_list
        keep_symbols = load_keep_list()
    except Exception as e:
        print(f"[FusionBridge] 加载KEEP列表失败: {e}")
    
    # 初始化协调器
    _master_coordinator = MasterCoordinator(
        keep_symbols=keep_symbols if keep_symbols else ['XAUUSD', 'BTCUSD', 'EURUSD'],
        initial_equity=10000.0,
        max_total_risk_pct=0.05,
    )
    _coordinator_initialized = True
    
    return _master_coordinator


def fusion_scan_symbol(
    guardian,
    symbol: str,
    cfg: dict,
    equity: float,
    risk_pct: float = 0.4,
    strategies: Optional[List[str]] = None
) -> Tuple[Optional[Dict], str]:
    """
    融合扫描 — 使用MasterCoordinator生成协调信号
    
    返回 (proposal | None, reason)
    """
    # 1. 获取协调器
    coordinator = get_coordinator()
    
    # 2. 更新净值
    coordinator.equity = equity
    
    # 3. 获取K线数据
    mt5 = guardian.mt5
    h1 = _fetch_df(mt5, symbol, mt5.TIMEFRAME_H1, 400)
    h4 = _fetch_df(mt5, symbol, mt5.TIMEFRAME_H4, 300)
    d1 = _fetch_df(mt5, symbol, mt5.TIMEFRAME_D1, 200)
    
    if h1 is None or h4 is None or d1 is None:
        return None, f"{symbol} K线数据缺失 (H1/H4/D1 不全)"
    
    # 4. 实盘edge门控
    if not et.is_symbol_allowed(symbol):
        return None, f"{symbol} 实盘edge不达标"
    
    # 5. 波动率恐慌闸
    try:
        _close_arr = h1['close'].values.astype(float)
        if len(_close_arr) >= 22:
            _r = np.diff(np.log(_close_arr))
            _roll = np.array([float(np.std(_r[max(0, i-20):i+1]))
                             for i in range(20, len(_r))])
            if len(_roll) >= 10:
                _p99 = float(np.percentile(_roll, 99))
                vol_now = float(np.std(_r[-20:]))
                if vol_now > _p99 * 1.5 and vol_now > 0:
                    return None, f"{symbol} 波动率恐慌, 暂停新开仓"
    except Exception:
        pass
    
    # 6. 生成协调信号
    strat_list = strategies or SYMBOL_STRATEGY_MAP.get(symbol, list(STRATEGY_REGISTRY_V4.keys())[:8])
    # [2026-08-31 V4修复] 原cfg缺 adx_min/sl_mult/rr_mult → SDP等策略KeyError"sdk"直接报错退出,
    # 是"无有效信号"的另一主因. 现对齐 live_bridge.V4_CONFIG
    cfg_fusion = {
        'pip': 0.01,
        'lot': 0.1,
        'adx_min': 15,        # SDP/OTAS 趋势强度门槛(进化引擎优化值)
        'sl_mult': 1.5,
        'rr_mult': 3.0,
        'disp_threshold': 0.005,
        'lookback': 10,
    }
    
    try:
        signals = coordinator.generate_coordinated_signals(
            symbol, h1, h4, d1, cfg_fusion
        )
    except Exception as e:
        return None, f"{symbol} 信号生成失败: {e}"
    
    if not signals:
        return None, f"{symbol} 无有效信号"
    
    # 7. [2026-08-31 进化] WFV正edge先验加权:
    #    系统已积累 45 个经 Walk-Forward 验证为正edge 的 (symbol, strategy) 组合,
    #    但选信号时原完全未用此先验知识 —— 相当于放着已验证的优势不用。
    #    现对命中白名单的信号加权, 使其在额度竞争中优先胜出。
    try:
        _wfv = set(et._WFV_WHITELIST) if getattr(et, '_WFV_WHITELIST', None) else set()
    except Exception:
        _wfv = set()

    if _wfv:
        for _s in signals:
            _sts = set(getattr(_s, 'triggering_strategies', None) or [])
            if any((symbol, _st) in _wfv for _st in _sts):
                _s.confidence = min(_s.confidence * 1.15, 1.0)  # 白名单加成15%

    # 8. 按优先级排序，选择最佳信号
    signals.sort(key=lambda s: (s.priority.value, s.confidence), reverse=True)
    best = signals[0]
    
    # 9. 计算仓位 — [2026-08-31 修复] 原用 coordinator._calculate_lot 直接出
    #    手数(曾算出 GBPUSD 1.0 手, 对小额账户风险失控). 改为与 live_bridge
    #    同源: 先取真实品种规格 pip/pip_usd, 再由 su.risk_lot 按风险%标定。
    try:
        spec = su.UNIVERSE.get(symbol, {})
        pip = float(spec.get('pip') or cfg.get('pip') or 0.0001)
        pip_usd = float(spec.get('pip_usd') or cfg.get('pip_usd') or 10.0)
    except Exception:
        pip = float(cfg.get('pip') or 0.0001)
        pip_usd = float(cfg.get('pip_usd') or 10.0)

    if pip <= 0 or best.entry <= 0 or not best.sl or not best.tp:
        return None, f"{symbol} 信号缺 SL/TP 或规格异常"

    sl_pips = abs(float(best.entry) - float(best.sl)) / pip
    tp_pips = abs(float(best.tp) - float(best.entry)) / pip
    if sl_pips <= 0:
        return None, f"{symbol} SL距离异常 (sl_pips=0)"

    # 风险标定手数 (与 live_bridge 同源, 风控闸在此生效)
    try:
        lot, risk_usd, ok = su.risk_lot(
            dict(spec, pip=pip, pip_usd=pip_usd),
            sl_pips, equity, risk_pct, allow_min_lot=True
        )
    except Exception:
        lot, risk_usd, ok = float(best.lot or 0.01), 0.0, True
    if not ok or lot <= 0:
        return None, (f"{symbol} 开不起(最小手风险超限 "
                      f"sl={sl_pips:.1f}pip 风险${risk_usd:.2f})")

    # 10. [2026-09-04 V5] K线形态+动能方向硬闸 (与 live_bridge 同源)
    #     融合信号同样须过 V5 方向确认, 否则逆势信号被拒.
    _v5_gate = "V5未启用"
    try:
        from _v5_entry_optimizer import EntryOptimizerV5
        _v5a = EntryOptimizerV5().analyze_df(h1)
        _v5ok, _v5scale, _v5why = EntryOptimizerV5.direction_veto(
            _v5a, 'BUY' if best.side == 1 else 'SELL')
        if not _v5ok:
            return None, f"{symbol} V5形态/动能拒单 ({_v5why})"
        _v5_gate = _v5why
    except Exception:
        _v5_gate = "V5模块异常(fail-open)"

    # 11. 构建proposal (与现有系统兼容: 必须带 sl_pts/tp_pts 供 risk_auditor 审计)
    proposal = {
        'symbol': symbol,
        'direction': 'BUY' if best.side == 1 else 'SELL',
        'entry': round(float(best.entry), 5),
        'sl': round(float(best.sl), 5),
        'tp': round(float(best.tp), 5),
        'sl_pts': round(sl_pips, 2),
        'tp_pts': round(tp_pips, 2),
        'lot': lot,
        'strategy': best.triggering_strategies[0] if best.triggering_strategies else 'FUSION',
        'confidence': best.confidence,
        'priority': best.priority.name,
        'resonance_strategies': best.coordinated_strategies,
        'pip_usd_per_lot': pip_usd,
        'spread': cfg.get('spread', 0),
        'adx': best.meta.get('adx', 0) if hasattr(best, 'meta') else 0,
        'regime': 'FUSION',
    }
    
    reason = f"FUSION: {best.priority.name} Conf={best.confidence:.2f} "
    reason += f"Strategies={best.triggering_strategies} Lot={lot} SL={sl_pips:.1f}pip "
    reason += f"[V5:{_v5_gate}]"
    
    return proposal, reason


def _fetch_df(mt5, symbol: str, timeframe, count: int):
    """获取K线数据 (最近 count 根)

    [2026-08-31 重大修复] 原用 copy_rates_from(sym, tf, 0, count):
        第3参是 date_from, 传 0 (=1970-01-01) 会取到**最老的一段K线**,
        融合层因此永远在分析陈旧历史 → 信号全落在远古bar → 被 FRESH_BARS
        过滤 → 长期 "无有效信号" 不开单。
    改用 copy_rates_from_pos(sym, tf, 0, count): start_pos=0 表示从最新往回取。
    """
    try:
        import MetaTrader5 as mt5_module
        rates = mt5_module.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None or len(rates) == 0:
            return None
        return pd.DataFrame(rates)
    except Exception:
        return None


def update_coordinator_equity(equity: float):
    """更新协调器净值"""
    global _master_coordinator
    if _master_coordinator:
        _master_coordinator.equity = equity


def get_coordinator_status() -> Dict:
    """获取协调器状态"""
    coordinator = get_coordinator()
    return coordinator.get_status_report()


def trigger_evolution():
    """手动触发进化优化"""
    coordinator = get_coordinator()
    coordinator._trigger_evolution()
    return coordinator.get_evolution_report() if hasattr(coordinator, 'get_evolution_report') else {}


# 兼容性: 保留原有SYMBOL_STRATEGY_MAP引用
SYMBOL_STRATEGY_MAP = {
    "EURUSD": ["OTAS", "DIV", "TREND", "MR", "PASD"],
    "GBPUSD": ["OTAS", "DIV", "TREND", "MR", "PASD"],
    "AUDUSD": ["OTAS", "DIV", "TREND", "MR"],
    "NZDUSD": ["OTAS", "DIV", "TREND", "MR"],
    "USDJPY": ["OTAS", "TREND", "DIV", "MR"],
    "USDCHF": ["OTAS", "TREND", "DIV"],
    "USDCAD": ["OTAS", "TREND", "DIV"],
    "GBPJPY": ["OTAS", "TREND", "DIV"],
    "XAUUSD": ["OTAS", "PASD", "ICT", "TREND", "DIV"],
    "XAGUSD": ["OTAS", "PASD", "ICT", "TREND"],
    "BTCUSD": ["OTAS", "PASD", "TREND", "DIV"],
    "ETHUSD": ["OTAS", "PASD", "TREND", "DIV"],
    "US500": ["TREND", "BO", "MR"],
}
