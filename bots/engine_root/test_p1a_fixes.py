# test_p1a_fixes.py — P1a 两处修复的单元测试 (零回归验证)
#
# 运行: <python3.11> -u E:\GoldstrategyEngine\test_p1a_fixes.py
# 不修改任何生产代码; 仅验证 drift_monitor 样本地板 + market_scanner RF 平铺阈值.
import sys
import numpy as np

import drift_monitor as dm
import market_scanner as ms

_FAILS = []


def check(name, cond, detail=""):
    if cond:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name}  {detail}")
        _FAILS.append(name)


# ═══ 测试A: 漂移样本地板 (小样本降级 NO_DATA, 非 RED) ═══
live_small = {'status': 'OK', 'pf': 1.31, 'win_rate': 0.25,
              'trade_count': 8, 'source': 'mt5'}
baseline = {'pf': 3.55, 'win_rate': 0.6364}
r_a = dm.assess_drift(live_small, baseline)
check("A1: live 8笔(小样本)相对漂移降级 NO_DATA",
      r_a.get('status') == 'NO_DATA', f"got {r_a}")

# 反向: 35 笔同 pf/wr → 仍判 RED (1.31 < 3.55*0.6=2.13)
live_big = dict(live_small, trade_count=35)
r_a2 = dm.assess_drift(live_big, baseline)
check("A2: live 35笔同 pf/wr 判 RED (pf 1.31 < 基线*0.6)",
      r_a2.get('status') == 'RED', f"got {r_a2}")


# ═══ 测试B: 绝对净亏线仍硬约束 (样本<30 但 pf<1.0 → RED) ═══
live_loss = {'status': 'OK', 'pf': 0.8, 'win_rate': 0.4, 'trade_count': 8}
r_b = dm.assess_drift(live_loss, baseline)
check("B: 样本<30 但 pf<1.0 净亏 → 硬 RED (优先于样本地板)",
      r_b.get('status') == 'RED', f"got {r_b}")


# ═══ 测试C: RF 阈值平铺 (有edge→0.50, 无edge→0.65) ═══
# 用充分 mock 驱动 scan_symbol 到达 RF gate, 读取 proposal['signal_threshold_dynamic'].
def _make_hunter():
    return ms.MarketHunter(strategies={
        'XAUUSD': {'fitness': 51.6, 'baseline': {'pf': 3.5}, 'params': {}},
        'EURUSD': {'fitness': 0, 'baseline': None, 'params': {}},
    })


def _install_mocks(h):
    ms.RF_QUALITY_GATE = True
    # 行情全部返回强趋势序列 → ADX 高, 不触发硬禁; 多周期全 BUY 同向
    def fake_hist(self, symbol, tf):
        t = np.linspace(0, 100, 400)
        c = 100 + 0.5 * t
        return c, c + 1.0, c - 1.0
    # ADX 恒高, 免去对合成数据 ADX 数值的依赖
    ms.ce._adx = lambda h_arr, l_arr, c_arr: np.array([30.0] * len(c_arr))
    # RF 模型返回有效概率 dict (阈值逻辑在 if sc is not None 内, 必须非 None)
    class _FakeRF:
        def score(self, *a, **k):
            return {'UP': 0.7, 'DOWN': 0.3}
    h._hist = fake_hist.__get__(h)
    h._rf_ensure = (lambda self, s: _FakeRF()).__get__(h)
    h._step_regime = (lambda self, s, hh, hl, hc: (None, None)).__get__(h)
    h.guardian.sizer = None  # 跳过 should_pause 质量门禁
    fake_proposal = {'direction': 'BUY', 'entry': 1.1,
                     'sl_pts': 10, 'tp_pts': 20, 'lot': 0.02}
    h.guardian.build_signal = \
        lambda st, sy, dl, tc: (dict(fake_proposal), 'ok')


hunter = _make_hunter()
_install_mocks(hunter)

p_xau, _ = hunter.scan_symbol('XAUUSD')
check("C1: 有edge品种(XAUUSD fitness>0,baseline非空) RF阈值=0.50",
      p_xau.get('signal_threshold_dynamic') == 0.50,
      f"got {p_xau.get('signal_threshold_dynamic')}")

p_eur, _ = hunter.scan_symbol('EURUSD')
check("C2: 无edge品种(EURUSD fitness=0) RF阈值=0.65 护栏",
      p_eur.get('signal_threshold_dynamic') == 0.65,
      f"got {p_eur.get('signal_threshold_dynamic')}")
check("C3: 无edge品种标记 unproven_edge=True",
      p_eur.get('unproven_edge') is True, f"got {p_eur.get('unproven_edge')}")


# ═══ 汇总 ═══
print("-" * 40)
if _FAILS:
    print(f"RESULT: FAIL ({len(_FAILS)} 项失败: {_FAILS})")
    sys.exit(1)
print("RESULT: ALL PASS")
