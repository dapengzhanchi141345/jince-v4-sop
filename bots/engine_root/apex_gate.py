# -*- coding: utf-8 -*-
"""
apex_gate.py — Apex 结构门控过滤器 (可复用的信号质量过滤器)
==========================================================
来源: 朋友「Godking Apex Short v4.2」唯一值得借用的部分 —— 其
      「结构上下文 + 供给/需求区」判定, 作为信号质量门控注入我们已有的
      双向策略 (SDP/ICT), Walk-Forward 验证可提升 PF 且 OOS 提升最大(非过拟合)。

逻辑:
  - 对每根 H1 信号, 取其管辖的 H4 结构(截至该 bar, 无前视):
      * 空单 -> 需 bearish_ctx 且价格回抽进入供给区 (zone_top/zone_bottom)
      * 多单 -> 需 bullish_ctx 且价格回踩进入需求区 (demand_top/demand_bottom)
  - 不满足则丢弃该信号(只减不增, 降低过度交易)。

安全:
  - 结构映射按 h4 长度缓存(首次构建后复用, 避免每次扫描重建 ~170s)。
  - 任何异常 -> 返回原始信号(不过滤), 绝不吞掉策略信号。
"""
import numpy as np
import pandas as pd
from apex_strategy_v5 import DEFAULT_CFG

_STRUCT_CACHE = {}   # symbol -> (h4_len, structs)


def _build_structs(h4, cfg, symbol):
    cached = _STRUCT_CACHE.get(symbol)
    if cached and cached[0] == len(h4):
        return cached[1]
    from backtest_apex_v5 import build_struct_map
    structs = build_struct_map(h4, cfg)
    _STRUCT_CACHE[symbol] = (len(h4), structs)
    return structs


def gate_signals(h1, signals, h4, cfg=None, symbol="XAUUSD"):
    """
    用 Apex 结构门控过滤信号列表。返回过滤后的列表。
    异常时返回原列表(安全回退)。
    """
    if not signals:
        return signals
    if cfg is None:
        cfg = dict(DEFAULT_CFG)
    try:
        from backtest_apex_v5 import h4_index_for_times
        structs = _build_structs(h4, cfg, symbol)
        h4_idx = h4_index_for_times(h4['time'].values, h1['time'].values)
        hi = h1['high'].values.astype(float)
        lo = h1['low'].values.astype(float)
        cl = h1['close'].values.astype(float)
        kept = []
        for s in signals:
            i = s.get('bar')
            if i is None or i < 2 or i >= len(hi) - 1:
                continue
            k = int(h4_idx[i])
            st = structs[k]
            if st is None:
                continue
            side = int(s.get('side', -1))
            if side < 0:
                if not st.get('bearish_ctx'):
                    continue
                zt = st['zone_top']; zb = st['zone_bottom']; inv = st['invalidation']
                if cl[i] >= inv:
                    continue
                if not (hi[i] >= zb and hi[i] <= zt + 40 and cl[i] <= zt):
                    continue
            else:
                if not st.get('bullish_ctx'):
                    continue
                zt = st['demand_top']; zb = st['demand_bottom']; inv = st['invalidation_low']
                if cl[i] <= inv:
                    continue
                if not (lo[i] <= zt and lo[i] >= zb - 40 and cl[i] >= zb):
                    continue
            kept.append(s)
        return kept
    except Exception as e:
        print(f"[APEX_GATE] fallback to raw (err: {e})")
        return signals


def gate_wrap(gen_func, name, symbol="XAUUSD"):
    """包装一个策略生成器, 输出信号经 Apex 门控过滤。
    仅对 symbol(默认 XAUUSD, 已 Walk-Forward 验证)启用; 其他品种跳过(零成本)。
    """
    def wrapper(h1, h4, d1, cfg):
        try:
            sigs = gen_func(h1, h4, d1, cfg)
        except Exception as e:
            print(f"[WARN] {name} gen failed: {e}")
            return []
        if not sigs:
            return []
        sym = (cfg or {}).get("symbol") or (cfg or {}).get("apex_symbol") or symbol
        if sym != "XAUUSD":
            return sigs   # 仅 XAUUSD 启用门控(其他品种未验证, 跳过以免误删/耗时)
        return gate_signals(h1, sigs, h4, cfg, sym)
    return wrapper
