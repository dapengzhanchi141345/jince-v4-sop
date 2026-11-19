# test_unproven_guard.py — 验证 market_scanner.py L505-514
# "无真实 edge 品种智能护栏": 当 self.strategies[symbol] 的 fitness<=0 或
# baseline 为 None 时, RF 质量门禁阈值从 0.50 抬高到 0.65 (非禁止, 仍受
# ADX硬禁/VETO/双铁律/审度司保护). 有真实 edge 品种(fitness>0,baseline非空)
# 仍用 0.50. 只验证, 不改生产代码.
import sys
import numpy as np
import market_scanner as mh


def _uptrend(n=260, start=100.0, step=0.2):
    return np.array([start + step * i for i in range(n)], dtype=float)

def _flat(n=260, base=100.0):
    rng = np.random.default_rng(42)
    return base + rng.normal(0, 1e-3, n)

def _mk_hl(c):
    rng = np.random.default_rng(0)
    eps = np.abs(rng.normal(0, 0.001, len(c)))
    return c, c * (1 + eps), c * (1 - eps)


class FakeGuardian:
    """隔离 build_signal, 固定 BUY 方向提案."""
    def __init__(self, direction='BUY'):
        self.direction = direction
        self.sizer = None
    def build_signal(self, strategy, symbol, dl_pred=None, tc_bias=None):
        return {'symbol': symbol, 'direction': self.direction,
                'lot': 0.02, 'entry': 1.0}, 'ok'


class FakeRF:
    """可注入的 RF 质量模型, score() 返回固定概率分布."""
    is_trained = True
    def __init__(self, sc):
        self._sc = sc
    def score(self, c, h, l):
        return dict(self._sc)


def _setup(hunter, symbol):
    """喂合成行情: H1/H4/D1/W1 同向 uptrend 过共振, M15 中性避免改写."""
    for tf in ('H1', 'H4', 'D1', 'W1'):
        hunter._cache[(symbol, mh.TF[tf])] = _mk_hl(_uptrend())
    hunter._cache[(symbol, mh.TF['M15'])] = _mk_hl(_flat())


def run():
    orig_adx = mh.ce._adx
    orig_ra = mh.REGIME_ADAPTIVE
    orig_rqg = mh.RF_QUALITY_GATE
    orig_eg = mh.EDGE_GATE_ENABLED
    orig_an = mh.cl.analyze
    try:
        mh.ce._adx = lambda h, l, c: np.array([30.0])   # 过 ADX 硬禁, 隔离
        mh.REGIME_ADAPTIVE = False                      # thr 恒 RF_GATE_THRESHOLD
        mh.RF_QUALITY_GATE = True                       # 开启门禁+护栏
        mh.EDGE_GATE_ENABLED = False                    # 隔离进化优势门禁
        mh.cl.analyze = lambda c, h, l: {'ok': True, 'divergence': None,
                                         'latest_bsp': None, 'trend_type': 'SHOCK',
                                         'bi_count': 4}  # 缠论中性放行

        # 用例A: 无 edge 品种, 但 RF 信号 0.66 已超 0.65 护栏 → 应放行,
        #         且 proposal 必须被打上 unproven_edge=True 标记.
        h_a = mh.MarketHunter(
            strategies={'EURUSD': {'fitness': 0.0, 'baseline': None,
                                  'params': {'adx_min': 30}}},
            guardian=FakeGuardian('BUY'),
            rf_alpha=FakeRF({'UP': 0.66, 'DOWN': 0.34}))
        _setup(h_a, 'EURUSD')
        p_a, r_a = h_a.scan_symbol('EURUSD')
        assert p_a is not None, f"无edge但0.66应过护栏: {r_a}"
        assert p_a.get('unproven_edge') is True, \
            f"应标记 unproven_edge=True: {p_a}"
        print(f"  [A] 无edge+0.66 → PASS, unproven_edge={p_a.get('unproven_edge')}")

        # 用例B: 无 edge 品种, RF 信号 0.55 (高于标准0.50, 低于护栏0.65) →
        #         护栏应把它 SKIP (thr 抬到 0.65). 返回原因含 0.65.
        h_b = mh.MarketHunter(
            strategies={'EURUSD': {'fitness': 0.0, 'baseline': None,
                                  'params': {'adx_min': 30}}},
            guardian=FakeGuardian('BUY'),
            rf_alpha=FakeRF({'UP': 0.55, 'DOWN': 0.45}))
        _setup(h_b, 'EURUSD')
        p_b, r_b = h_b.scan_symbol('EURUSD')
        assert p_b is None, f"无edge+0.55应被护栏SKIP(thr=0.65>0.55): {r_b}"
        assert '0.65' in r_b, f"SKIP原因应暴露抬高的阈值0.65: {r_b}"
        print(f"  [B] 无edge+0.55 → SKIP, 原因={r_b}")

        # 用例C: 有真实 edge 品种(fitness=10, baseline pf=1.5), 同 0.55 信号 →
        #         护栏不触发(thr=0.50<0.55), 应放行, 且不应有 unproven_edge 标记.
        h_c = mh.MarketHunter(
            strategies={'XAUUSD': {'fitness': 10.0,
                                  'baseline': {'pf': 1.5, 'win_rate': 0.6},
                                  'params': {'adx_min': 30}}},
            guardian=FakeGuardian('BUY'),
            rf_alpha=FakeRF({'UP': 0.55, 'DOWN': 0.45}))
        _setup(h_c, 'XAUUSD')
        p_c, r_c = h_c.scan_symbol('XAUUSD')
        assert p_c is not None, f"有edge+0.55应放行(thr=0.50): {r_c}"
        assert 'unproven_edge' not in p_c, \
            f"有edge品种不应标记 unproven_edge: {p_c}"
        print(f"  [C] 有edge+0.55 → PASS, unproven_edge={'unproven_edge' in p_c}")

        print("UNPROVEN_GUARD PASS: A(0.66过+标记) / B(0.55被护栏SKIP) / "
              "C(有edge同0.55放行) 三用例全过")
        return True
    except AssertionError as e:
        print("UNPROVEN_GUARD FAIL:", e)
        return False
    except Exception as e:
        print("UNPROVEN_GUARD ERROR:", repr(e))
        return False
    finally:
        mh.ce._adx = orig_adx
        mh.REGIME_ADAPTIVE = orig_ra
        mh.RF_QUALITY_GATE = orig_rqg
        mh.EDGE_GATE_ENABLED = orig_eg
        mh.cl.analyze = orig_an


if __name__ == '__main__':
    sys.exit(0 if run() else 1)
