# test_range_module.py — P1-B 区间/均值回归模块离线单测 (不连 MT5)
#
# 目标: 验证 guardian_executor.build_range_signal 与
#       market_scanner.scan_symbol 的 RANGE_MODE 分支, 且默认关闭时零回归.
#
# 设计: 构造最小可测行情, 直接注入 self.market_state 的 mock 返回值,
#       离线跑通 build_range_signal; 再用 monkeypatch 验证扫描分支触发/零回归.
#       所有数值用与源码一致的公式在测试内独立复算, 只断言稳健不变量,
#       不依赖我手算的精确小数 (抗脆弱).
import sys
import math
import numpy as np

import continuous_evolution_v2 as ce
import guardian_executor as ge
from guardian_executor import (
    RANGE_BB_PERIOD, RANGE_BB_STD, RANGE_KC_MULT, RANGE_SQUEEZE_THR,
    RANGE_ENTRY_BUFFER_PIPS, RANGE_SL_BUFFER_PIPS, RANGE_RR_MIN, RANGE_MAX_LOT,
)
import market_scanner as mh


SYM = 'XAUUSD'          # pip = 1, 价格量级 ~4000
N = 60                  # 行情长度, i = 59
I = N - 1


def _make_state(close, high, low, adx_now=15.0, spread=0.3):
    """构造与 GuardianExecutor.market_state 同构的 mock 状态 dict."""
    return {
        'symbol': SYM, 'close': close, 'high': high, 'low': low,
        'i': I, 'adx_now': adx_now, 'atr_now': 1.0,
        'spread': spread, 'last_close': float(close[I]),
    }


def _flat_range_arrays(last_close, body=4000.0, half=3.0):
    """构造"区间市"行情: 主体贴近 body, 末根 = last_close;
       每根 high=close+half / low=close-half → 宽幅影线 → ATR 大 → KC 宽;
       而 close 几乎不动 → BB 窄 → BB/KC 比值 < 阈值(挤压/区间)."""
    close = np.full(N, float(body), dtype=float)
    close[I] = float(last_close)
    high = close + half
    low = close - half
    return close, high, low


def _ramp_arrays():
    """构造"挤压场景"行情: close 线性剧烈爬升(大方差 → BB 宽),
       但 high==low==close(无实体波动 → ATR 仅来自跳空, 仍远小于 BB 宽)
       → BB/KC >> 阈值(挤压比极大, 即旧的硬拒场景).
       末根价格置于 BB 通道中部(≈mid, 非边界): 新逻辑下 squeeze 不再硬拒,
       落到边界判定 → 价格不近边界 → None('价格未接近区间边界 (非反转区)')."""
    close = np.concatenate([np.full(40, 4000.0),
                            np.linspace(3900.0, 4100.0, 20)])
    close[I] = 4000.0            # 末根置于通道中部, 证明 squeeze 不再硬拒、仅边界判定生效
    high = close.copy()
    low = close.copy()
    return close, high, low


def _expected_band(close, high, low):
    """用与源码完全一致的公式复算 BB/KC 上下轨与挤压比 (供断言不变量)."""
    window = close[I - RANGE_BB_PERIOD + 1:I + 1]
    ma = float(np.mean(window))
    sd = float(np.std(window))
    bb_up = ma + RANGE_BB_STD * sd
    bb_dn = ma - RANGE_BB_STD * sd
    atr = ce._atr(high, low, close)
    kc_atr = float(np.mean(atr[I - RANGE_BB_PERIOD + 1:I + 1]))
    kc_up = ma + RANGE_KC_MULT * kc_atr
    kc_dn = ma - RANGE_KC_MULT * kc_atr
    return {
        'ma': ma, 'sd': sd, 'bb_up': bb_up, 'bb_dn': bb_dn,
        'kc_atr': kc_atr, 'kc_up': kc_up, 'kc_dn': kc_dn,
        'bb_w': bb_up - bb_dn, 'kc_w': kc_up - kc_dn,
    }


def _new_guardian():
    """构造真实 GuardianExecutor (离线, 不连 MT5), 并注入可控的 sizer."""
    g = ge.GuardianExecutor()           # 仅构建 RiskAuditor/TradeJournal/AdaptiveSizer
    g.mt5 = None                        # 确保 _equity() 走默认 10000.0 分支
    g.sizer = _FakeSizer()              # 隔离自适应仓位器, 确定性
    return g


class _FakeSizer:
    def lot_multiplier(self, symbol):
        return 1.0
    def should_pause(self, symbol):
        return False, ""


# ───────────────────────────────────────────────────────────
# 测试 A: 挤压场景不再硬拒 — BB 宽度 >> KC 宽度(挤压比极大), 但价格居通道
#        中部(非边界) → 不走 squeeze 硬拒, 落到边界判定 → None(价格未接近边界)
# ───────────────────────────────────────────────────────────
def test_A_squeeze_non_range():
    g = _new_guardian()
    close, high, low = _ramp_arrays()
    g.market_state = lambda symbol: _make_state(close, high, low)
    prop, reason = g.build_range_signal(SYM)
    assert prop is None, f"价格居中应返回 None, 实得 {prop}"
    assert "价格未接近区间边界" in reason, \
        f"原因应含'价格未接近区间边界', 实得: {reason}"
    # 复算挤压比确实 >> 阈值 (证明该场景正是旧的硬拒场景, 现改走边界判定)
    b = _expected_band(close, high, low)
    ratio = b['bb_w'] / b['kc_w']
    assert ratio > RANGE_SQUEEZE_THR, \
        f"构造应为挤压场景(BB/KC={ratio:.2f} > {RANGE_SQUEEZE_THR})"
    print(f"  A 通过: 挤压场景(squeeze 不硬拒)→ None, "
          f"原因='{reason}' (BB/KC={ratio:.2f})")
    return True


# ───────────────────────────────────────────────────────────
# 测试 B: 区间反转 BUY — 价格贴近下沿 → BUY, sl 在 bb_dn 下方, RR≥2.0
# ───────────────────────────────────────────────────────────
def test_B_buy_near_lower():
    g = _new_guardian()
    # 末根略高于下沿(仍在 BB 通道内, 未突破)→ 安全落在 BUY 区
    #   (bb_dn <= price <= bb_dn + ebuf, 且 price < bb_up - ebuf)
    last = 4000.1
    close, high, low = _flat_range_arrays(last)
    g.market_state = lambda symbol: _make_state(close, high, low)
    prop, reason = g.build_range_signal(SYM)
    assert prop is not None, f"应产出 BUY 提案, 原因={reason}"
    assert prop['direction'] == 'BUY', f"方向应 BUY, 实得 {prop['direction']}"
    b = _expected_band(close, high, low)
    # sl 应严格在 bb_dn 外侧(下方)
    assert prop['sl'] < b['bb_dn'], \
        f"BUY sl({prop['sl']}) 应在 bb_dn({b['bb_dn']:.3f}) 下方"
    assert prop['sl'] < prop['entry'], "BUY sl 应低于 entry"
    # tp 方向向上(高于 entry)
    assert prop['tp'] > prop['entry'], "BUY tp 应高于 entry"
    # RR 双铁律
    rr = prop['tp_pts'] / prop['sl_pts']
    assert rr >= RANGE_RR_MIN - 1e-9, f"RR {rr:.3f} < {RANGE_RR_MIN}"
    assert prop.get('range_mode') is True, "应标记 range_mode=True"
    assert prop['lot'] <= RANGE_MAX_LOT + 1e-9, \
        f"lot {prop['lot']} 应 ≤ RANGE_MAX_LOT {RANGE_MAX_LOT}"
    print(f"  B 通过: BUY @ {prop['entry']} sl={prop['sl']}(<bb_dn "
          f"{b['bb_dn']:.3f}) tp={prop['tp']} RR={rr:.2f} lot={prop['lot']}")
    return True


# ───────────────────────────────────────────────────────────
# 测试 C: 区间反转 SELL — 价格贴近上沿 → SELL, sl 在 bb_up 上方, RR≥2.0
# ───────────────────────────────────────────────────────────
def test_C_sell_near_upper():
    g = _new_guardian()
    # 末根略低于上沿(仍在 BB 通道内, 未突破)→ 安全落在 SELL 区
    #   (bb_up - ebuf <= price <= bb_up, 且 price > bb_dn)
    last = 3999.85
    close, high, low = _flat_range_arrays(last)
    g.market_state = lambda symbol: _make_state(close, high, low)
    prop, reason = g.build_range_signal(SYM)
    assert prop is not None, f"应产出 SELL 提案, 原因={reason}"
    assert prop['direction'] == 'SELL', f"方向应 SELL, 实得 {prop['direction']}"
    b = _expected_band(close, high, low)
    assert prop['sl'] > b['bb_up'], \
        f"SELL sl({prop['sl']}) 应在 bb_up({b['bb_up']:.3f}) 上方"
    assert prop['sl'] > prop['entry'], "SELL sl 应高于 entry"
    assert prop['tp'] < prop['entry'], "SELL tp 应低于 entry"
    rr = prop['tp_pts'] / prop['sl_pts']
    assert rr >= RANGE_RR_MIN - 1e-9, f"RR {rr:.3f} < {RANGE_RR_MIN}"
    assert prop.get('range_mode') is True, "应标记 range_mode=True"
    assert prop['lot'] <= RANGE_MAX_LOT + 1e-9, \
        f"lot {prop['lot']} 应 ≤ RANGE_MAX_LOT {RANGE_MAX_LOT}"
    print(f"  C 通过: SELL @ {prop['entry']} sl={prop['sl']}(>bb_up "
          f"{b['bb_up']:.3f}) tp={prop['tp']} RR={rr:.2f} lot={prop['lot']}")
    return True


# ───────────────────────────────────────────────────────────
# 测试 D: RR 硬校验 — 价格居中使 tp 被迫=sl*RR_MIN, 守 2.0
# ───────────────────────────────────────────────────────────
def test_D_rr_floor():
    g = _new_guardian()
    # 主体 4000 ± 0.1 小幅振荡(小 sd), 末根 = 4000 (= mid, 价格居中)
    # → mid-price ≈ 0 → tp_dist = max(sl_dist*RR_MIN, ~0) = sl_dist*RR_MIN
    # → RR 精确 = RR_MIN.
    body = 4000.0 + np.array(
        [0.1 if k % 2 == 0 else -0.1 for k in range(19)], dtype=float)
    close = np.full(N, 4000.0, dtype=float)
    close[40:59] = body
    close[I] = 4000.0
    high = close + 3.0
    low = close - 3.0
    g.market_state = lambda symbol: _make_state(close, high, low)
    prop, reason = g.build_range_signal(SYM)
    assert prop is not None, f"应产出提案, 原因={reason}"
    rr = prop['tp_pts'] / prop['sl_pts']
    assert abs(rr - RANGE_RR_MIN) < 1e-6, \
        f"RR 应精确守 {RANGE_RR_MIN}, 实得 {rr:.6f}"
    # 复算: tp_dist 应 = sl_dist * RR_MIN (即 max 取前者)
    b = _expected_band(close, high, low)
    sl_dist = abs(prop['sl'] - prop['entry'])
    b = _expected_band(close, high, low)
    exp_tp_dist = max(sl_dist * RANGE_RR_MIN, abs(b['ma'] - prop['entry']))
    assert abs(exp_tp_dist - abs(prop['tp'] - prop['entry'])) < 1e-6, \
        "tp_dist 应 = max(sl_dist*RR_MIN, |mid-price|)"
    print(f"  D 通过: 价格居中 → RR 精确守 {RANGE_RR_MIN} (实得 {rr:.4f}), "
          f"tp_dist=sl_dist*RR_MIN 验证通过")
    return True


# ───────────────────────────────────────────────────────────
# 测试 E: 扫描分支触发 + 零回归
#   E1: RANGE_MODE_ENABLED=True + mock build_range_signal → 返回区间提案
#       含 range_mode=True 且被标 _range_mode=True
#   E2: RANGE_MODE_ENABLED=False + H1 ADX<20 → 仍 SKIP(零回归)
# ───────────────────────────────────────────────────────────
def test_E_branch_trigger_and_zero_regression():
    orig_adx = mh.ce._adx
    orig_tb = mh._trend_bias
    orig_analyze = mh.cl.analyze
    orig_range = mh.RANGE_MODE_ENABLED
    orig_regime = mh.REGIME_ADAPTIVE

    class FakeRangeGuardian:
        def __init__(self):
            self.sizer = _FakeSizer()
        def build_range_signal(self, symbol, strategy=None):
            return {
                'symbol': symbol, 'direction': 'BUY', 'entry': 4000.0,
                'sl': 3998.0, 'tp': 4004.0, 'sl_pts': 20.0, 'tp_pts': 40.0,
                'lot': 0.02, 'range_mode': True,
            }, '区间反转信号'

    try:
        # 隔离外部不确定性: ADX 强制低(触发硬禁/区间分支), MTF/15M 置中性,
        # 缠论中性放行; 关 regime 切参(与区间分支正交, 仅去抖动).
        mh.ce._adx = lambda h, l, c: np.array([5.0])
        mh._trend_bias = lambda c: 'NEUTRAL'
        mh.cl.analyze = lambda c, h, l: {'ok': True, 'divergence': None,
                                         'latest_bsp': None,
                                         'trend_type': 'SHOCK', 'bi_count': 4}
        mh.REGIME_ADAPTIVE = False

        # ── E1: 开启区间模式 → 返回区间提案 ──
        mh.RANGE_MODE_ENABLED = True
        hunter = mh.MarketHunter(guardian=FakeRangeGuardian())
        p1, r1 = hunter.scan_symbol(SYM)
        assert p1 is not None, f"RANGE 开启应返回区间提案, 原因={r1}"
        assert p1.get('range_mode') is True, \
            f"应含 range_mode=True, 实得 {p1}"
        assert p1.get('_range_mode') is True, \
            f"扫描分支应标 _range_mode=True, 实得 {p1}"
        # 区间提案应跳过趋势专属段(无 EDGE_GATE/build_signal 痕迹):
        # direction 来自 mock 区间提案(BUY), 而非重新计算
        assert p1['direction'] == 'BUY', \
            f"方向应沿用区间提案 BUY, 实得 {p1['direction']}"
        print(f"  E1 通过: RANGE 开启 → 返回区间提案 "
              f"(range_mode={p1.get('range_mode')}, "
              f"_range_mode={p1.get('_range_mode')}, dir={p1['direction']})")

        # ── E2: 关闭区间模式 → H1 ADX<20 仍 SKIP(零回归) ──
        mh.RANGE_MODE_ENABLED = False
        hunter2 = mh.MarketHunter(guardian=FakeRangeGuardian())
        p2, r2 = hunter2.scan_symbol(SYM)
        assert p2 is None, f"RANGE 关闭且 ADX<20 应 SKIP, 实得 {p2}"
        assert '震荡市' in r2, f"原因应含'震荡市', 实得: {r2}"
        print(f"  E2 通过: RANGE 关闭 + ADX<20 → SKIP (零回归), 原因='{r2}'")
        return True
    except AssertionError as e:
        print("  E 断言失败:", e)
        return False
    except Exception as e:
        print("  E 异常:", repr(e))
        return False
    finally:
        mh.ce._adx = orig_adx
        mh._trend_bias = orig_tb
        mh.cl.analyze = orig_analyze
        mh.RANGE_MODE_ENABLED = orig_range
        mh.REGIME_ADAPTIVE = orig_regime


# ───────────────────────────────────────────────────────────
def run():
    tests = [
        ("A 挤压判定→非区间市", test_A_squeeze_non_range),
        ("B 区间反转 BUY", test_B_buy_near_lower),
        ("C 区间反转 SELL", test_C_sell_near_upper),
        ("D RR 硬校验守 2.0", test_D_rr_floor),
        ("E 分支触发+零回归", test_E_branch_trigger_and_zero_regression),
    ]
    passed = 0
    for name, fn in tests:
        try:
            ok = fn()
        except AssertionError as e:
            print(f"[FAIL] {name}: {e}")
            ok = False
        except Exception as e:
            print(f"[ERROR] {name}: {repr(e)}")
            ok = False
        if ok:
            passed += 1
    print(f"\nRANGE MODULE TEST: {passed}/{len(tests)} 通过")
    return passed == len(tests)


if __name__ == '__main__':
    ok = run()
    sys.exit(0 if ok else 1)
