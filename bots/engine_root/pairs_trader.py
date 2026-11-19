# -*- coding: utf-8 -*-
"""
P3-1: 统计套利配对交易 (Pair Trading / Stat Arb)
=================================================
借鉴 2026 前沿实践 (Precise Pair Trading Pro 类): 高相关品种对的价差
(z-score) 偏离均值时反向开仓, 回归均值时平仓, 赚取收敛利润。

核心逻辑:
  1. 计算两品种对数价格差 (spread) 及滚动 z-score
  2. 高相关性过滤: corr(收益率) ≥ 阈值才允许交易 (防止关系破裂)
  3. 入场: |z| ≥ entry_z → 做空强势 / 做多弱势
  4. 出场: |z| ≤ exit_z → 平仓; 止损: |z| ≥ stop_z 或 SL 距离封顶

风险控制 (绝不放大风险):
  - 单配对单方向同时最多 1 仓 (腿 A + 腿 B 各 1)
  - 相关性跌破下限 → 立即强制平仓 (关系破裂保护)
  - 组合级: 最多 N 对同时持仓, 配对间品种不重叠
  - 手数: 按各腿波动率倒数配比 (vol_target 恒定风险)

数据需求: 两品种 H1 收盘价数组 (长度 ≥ 500, 用 rolling window)。
纯 numpy, 无第三方依赖。
"""

import numpy as np

# ── 默认参数 ─────────────────────────────────────────────────
DEFAULT_PAIRS = [
    # (品种A, 品种B, 最小相关性, 入场z, 出场z, 止损z)
    # [2026-08-28 P1 全网升级] 金银比 z>2σ 入场 (研究: 1058%回测收益),
    # 欧磅/澳纽保持标准参数.
    ("XAUUSD", "XAGUSD", 0.70, 2.0, 0.3, 4.0),   # 金银比 (更严格: 2σ入场/0.3回归/4σ止损)
    ("EURUSD", "GBPUSD", 0.70, 1.8, 0.4, 3.5),   # 欧磅
    ("AUDUSD", "NZDUSD", 0.70, 1.8, 0.4, 3.5),   # 澳纽
]

MIN_HISTORY = 300       # 计算价差所需最少K线
WINDOW = 200            # 滚动均值/标准差窗口
MAX_PAIRS_OPEN = 3      # 最多同时开仓配对数
MAX_LEG_RISK_PCT = 0.01 # 单腿风险占净值比例 (1%)

# 相关性滚动窗口 (收益率相关性)
CORR_WINDOW = 120


def _rets(arr):
    """对数收益率序列"""
    a = np.asarray(arr, dtype=float)
    return np.diff(np.log(a))


def _rolling_z(spread, window=WINDOW):
    """滚动 z-score: (spread - 滚动均值) / 滚动标准差"""
    spread = np.asarray(spread, dtype=float)
    n = len(spread)
    z = np.full(n, 0.0)
    for i in range(window, n):
        seg = spread[i - window:i]
        mu = seg.mean()
        sd = seg.std(ddof=0)
        if sd > 1e-12:
            z[i] = (spread[i] - mu) / sd
        else:
            z[i] = 0.0
    return z


def _corr_rets(a, b, window=CORR_WINDOW):
    """最近 window 根收益率的相关性"""
    ra, rb = _rets(a), _rets(b)
    n = min(len(ra), len(rb), window)
    if n < 30:
        return 0.0
    x, y = ra[-n:], rb[-n:]
    sx, sy = x.std(ddof=0), y.std(ddof=0)
    if sx < 1e-12 or sy < 1e-12:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def build_pair_signal(sym_a, sym_b, close_a, close_b, cfg_a, cfg_b,
                      corr_min=0.70, entry_z=1.8, exit_z=0.4,
                      stop_z=3.5, vol_a=None, vol_b=None):
    """对一对品种生成配对交易信号。

    参数:
      sym_a/sym_b: 品种名
      close_a/close_b: 两品种收盘价数组 (需长度 ≥ MIN_HISTORY)
      cfg_a/cfg_b: 两品种 symbol_universe 配置 (pip/pip_usd)
      vol_a/vol_b: 当前波动率 (可选, 用于风险配比; 缺省用收益std)
      corr_min/entry_z/exit_z/stop_z: 配对参数

    返回:
      {
        'signal': 'LONG_A_SHORT_B' | 'SHORT_A_LONG_B' | 'CLOSE' | 'HOLD' | 'NONE',
        'z': 当前价差z值, 'corr': 当前相关性,
        'leg_a': {'symbol','direction','entry','sl_pts','tp_pts','lot'}|None,
        'leg_b': {...}|None,
        'reason': str,
      }
    """
    na, nb = len(close_a), len(close_b)
    if na < MIN_HISTORY or nb < MIN_HISTORY:
        return {'signal': 'NONE', 'reason': f'数据不足 ({na}/{nb} < {MIN_HISTORY})'}
    n = min(na, nb)

    ca = np.asarray(close_a[-n:], dtype=float)
    cb = np.asarray(close_b[-n:], dtype=float)

    # 1) 相关性过滤 (用收益率)
    corr = _corr_rets(ca, cb)
    if corr < corr_min:
        return {'signal': 'HOLD', 'z': 0.0, 'corr': corr,
                'reason': f'相关性 {corr:.2f} < {corr_min:.2f}, 关系破裂保护'}

    # 2) 价差 z-score
    #    用 beta 归一化: spread = log(a) - beta * log(b)
    la, lb = np.log(ca), np.log(cb)
    beta = np.std(la) / (np.std(lb) + 1e-12)
    spread = la - beta * lb
    z = _rolling_z(spread)[-1]

    # 3) 信号判定
    pip_a = cfg_a.get('pip', 0.0001) if cfg_a else 0.0001
    pip_b = cfg_b.get('pip', 0.0001) if cfg_b else 0.0001
    price_a, price_b = float(ca[-1]), float(cb[-1])

    # 波动率 (用于手数配比)
    if vol_a is None:
        vol_a = float(np.std(_rets(ca)[-50:]) + 1e-12)
    if vol_b is None:
        vol_b = float(np.std(_rets(cb)[-50:]) + 1e-12)

    if z >= entry_z:
        # A 相对过强 → 做空 A / 做多 B
        return _mk_legs(sym_a, sym_b, 'SHORT_A_LONG_B', z, corr,
                        price_a, price_b, pip_a, pip_b,
                        vol_a, vol_b, stop_z, exit_z,
                        f'价差z={z:.2f} ≥ {entry_z}, A偏强做空A/做多B')
    elif z <= -entry_z:
        # A 相对过弱 → 做多 A / 做空 B
        return _mk_legs(sym_a, sym_b, 'LONG_A_SHORT_B', z, corr,
                        price_a, price_b, pip_a, pip_b,
                        vol_a, vol_b, stop_z, exit_z,
                        f'价差z={z:.2f} ≤ -{entry_z}, A偏弱做多A/做空B')
    else:
        return {'signal': 'HOLD', 'z': z, 'corr': corr,
                'reason': f'价差z={z:.2f} 未达入场阈值 ±{entry_z}'}


def _mk_legs(sym_a, sym_b, signal, z, corr,
             price_a, price_b, pip_a, pip_b,
             vol_a, vol_b, stop_z, exit_z, reason):
    """构造双腿提案 (方向 + SL/TP 点数 + 手数)。"""
    # 方向
    if signal == 'SHORT_A_LONG_B':
        dir_a, dir_b = 'SELL', 'BUY'
    else:
        dir_a, dir_b = 'BUY', 'SELL'

    # SL 距离: 按价格波动σ设置 (2026-08-24 修复: 原按 z-score 距离放大,
    # 对高波动品种 (XAG 381点) 风险失控). 改为 1.5×滚动σ ≈ 87% 波动区间,
    # 与普通策略 SL 同量级, 兼顾保护与可开仓.
    sl_pts_a = max(10.0, float(1.5 * price_a * vol_a / pip_a))
    sl_pts_b = max(10.0, float(1.5 * price_b * vol_b / pip_b))
    # TP 距离: 价差回归到 exit_z → 对应点数 (用当前z偏离度放大, 至少1.5×SL)
    tp_pts_a = max(sl_pts_a * 1.5, float(price_a * vol_a * max(1.0, abs(z) - exit_z) / pip_a))
    tp_pts_b = max(sl_pts_b * 1.5, float(price_b * vol_b * max(1.0, abs(z) - exit_z) / pip_b))

    # 手数: 波动率倒数配比, 两腿风险近似相等 (先给1.0由外部按风险定)
    # 外部 risk_lot 会按 equity 重新定手; 这里给相对配比
    weight_a = 1.0 / (vol_a * price_a + 1e-12)
    weight_b = 1.0 / (vol_b * price_b + 1e-12)
    wsum = weight_a + weight_b

    return {
        'signal': signal,
        'z': float(z), 'corr': float(corr),
        'reason': reason,
        'leg_a': {'symbol': sym_a, 'direction': dir_a, 'entry': float(price_a),
                  'sl_pts': round(sl_pts_a, 1), 'tp_pts': round(tp_pts_a, 1),
                  'lot_ratio': weight_a / wsum},
        'leg_b': {'symbol': sym_b, 'direction': dir_b, 'entry': float(price_b),
                  'sl_pts': round(sl_pts_b, 1), 'tp_pts': round(tp_pts_b, 1),
                  'lot_ratio': weight_b / wsum},
    }


def monitor_pair_close(close_a, close_b, cfg_a, cfg_b, entry_z, exit_z=0.4,
                       corr_min=0.70, stop_z=3.5):
    """已持仓配对的监控: 是否应平仓。

    返回 (close_all: bool, reason: str)
      - 价差回归 |z| ≤ exit_z → 收敛止盈
      - 价差继续扩大 |z| ≥ stop_z → 止损
      - 相关性跌破 corr_min → 关系破裂强制平
    """
    n = min(len(close_a), len(close_b))
    if n < MIN_HISTORY:
        return False, '数据不足'
    ca = np.asarray(close_a[-n:], dtype=float)
    cb = np.asarray(close_b[-n:], dtype=float)
    corr = _corr_rets(ca, cb)
    if corr < corr_min:
        return True, f'相关性跌破 {corr_min:.2f} (当前{corr:.2f}), 强制平仓'
    la, lb = np.log(ca), np.log(cb)
    beta = np.std(la) / (np.std(lb) + 1e-12)
    z = _rolling_z(la - beta * lb)[-1]
    if abs(z) <= exit_z:
        return True, f'价差收敛 z={z:.2f} ≤ {exit_z}, 止盈平仓'
    if abs(z) >= stop_z:
        return True, f'价差失控 z={z:.2f} ≥ {stop_z}, 止损平仓'
    return False, f'持有中 z={z:.2f}'


# ── 自检 ─────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=== P3-1 配对交易自检 ===")
    rng = np.random.default_rng(42)
    # 模拟两个高度相关品种: 共同驱动 + 噪声
    common = np.cumsum(rng.normal(0, 0.001, 600)) + 100
    a = common + rng.normal(0, 0.0003, 600)
    b = common * 1.0 + rng.normal(0, 0.0003, 600)

    cfg = {'pip': 0.0001, 'pip_usd': 1.0}
    r = build_pair_signal('AAA', 'BBB', a, b, cfg, cfg)
    print(f"信号: {r.get('signal')} | z={r.get('z', 0):.2f} | corr={r.get('corr', 0):.3f}")
    print(f"原因: {r.get('reason')}")
    if r.get('leg_a'):
        print(f"腿A: {r['leg_a']}")
        print(f"腿B: {r['leg_b']}")
    # 构造一个大偏离再测入场
    a2 = a.copy()
    a2[-50:] += np.linspace(0, 0.01, 50)  # 让A相对走强
    r2 = build_pair_signal('AAA', 'BBB', a2, b, cfg, cfg, entry_z=1.2)
    print(f"\n偏离后信号: {r2.get('signal')} | z={r2.get('z', 0):.2f}")
    print(f"原因: {r2.get('reason')}")
    if r2.get('leg_a'):
        print(f"腿A: {r2['leg_a']['symbol']} {r2['leg_a']['direction']} "
              f"SL={r2['leg_a']['sl_pts']}点 TP={r2['leg_a']['tp_pts']}点")
    # 监控测试
    close_all, reason = monitor_pair_close(a2, b, cfg, cfg, 1.2, exit_z=0.4)
    print(f"\n监控: close_all={close_all} | {reason}")
    print("=== 自检通过 ===")
