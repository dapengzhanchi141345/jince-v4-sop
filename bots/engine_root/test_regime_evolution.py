# test_regime_evolution.py — 深度整体优化单测 (pytest, 不连 MT5)
#
# 覆盖:
#   优化1 — Regime 自适应切参 / 冷却防抖 / 双铁律兜底 / volatility_scalar 缩仓
#   优化2 — 组合相关性风控(DRY-RUN 记录 + ENFORCE 拒开) / 信号质量动态化阈值
#   默认零影响 — REGIME_ADAPTIVE=False 时行为与优化前完全一致
import numpy as np
import pytest
import market_scanner as mh
import continuous_evolution_v2 as ce
from risk_auditor import RiskAuditor


# ── 合成行情 / 缓存辅助 ──
def _uptrend(n=260, start=100.0, step=0.2):
    return np.array([start + step * i for i in range(n)], dtype=float)


def _mk_hl(c):
    rng = np.random.default_rng(0)
    eps = np.abs(rng.normal(0, 0.001, len(c)))
    return c, c * (1 + eps), c * (1 - eps)


BASE_STRATEGY = {'name': 'Strategy_Test', 'params': {
    'adx_min': 25, 'position_size': 0.03, 'risk_per_trade': 0.01,
    'sl_multiplier': 3.0, 'tp_multiplier': 6.0, 'volatility_scalar': 1.0,
    'momentum_filter': False,
}}


class SpyGuardian:
    """记录 build_signal 收到的 strategy params, 返回固定提案(隔离真实计算)."""
    def __init__(self, direction='BUY'):
        self.direction = direction
        self.sizer = None
        self.last_params = None

    def build_signal(self, strategy, symbol, dl_pred=None, tc_bias=None):
        self.last_params = dict(strategy['params'])
        return {'symbol': symbol, 'direction': self.direction,
                'entry': 1.0, 'sl': 0.9, 'tp': 1.1, 'sl_pts': 100.0,
                'tp_pts': 200.0, 'lot': 0.02, 'pip_usd_per_lot': 10,
                'spread': 0.1, 'strategy': 's', 'adx': 30.0}, 'ok'


class CorrGuardian:
    """带 RiskAuditor 的 spy guardian, 供组合相关性测试."""
    def __init__(self, direction='BUY'):
        self.direction = direction
        self.sizer = None
        self.auditor = RiskAuditor()

    def build_signal(self, strategy, symbol, dl_pred=None, tc_bias=None):
        return {'symbol': symbol, 'direction': self.direction,
                'entry': 1.0, 'sl': 0.9, 'tp': 1.1, 'sl_pts': 100.0,
                'tp_pts': 200.0, 'lot': 0.02, 'pip_usd_per_lot': 10,
                'spread': 0.1, 'strategy': 's', 'adx': 30.0}, 'ok'


@pytest.fixture
def isolate():
    """隔离全局: 钉死 ADX, 关闭旧开关, 返回后恢复."""
    saved = {
        'adx': mh.ce._adx,
        'analyze': mh.cl.analyze,
        'REGIME_ADAPTIVE': mh.REGIME_ADAPTIVE,
        'RF_QUALITY_GATE': mh.RF_QUALITY_GATE,
        'CHANLUN_SL_OVERRIDE': mh.CHANLUN_SL_OVERRIDE,
        'DYNAMIC_SIGNAL_THRESHOLD': mh.DYNAMIC_SIGNAL_THRESHOLD,
        'PORTFOLIO_CORR_CHECK': mh.PORTFOLIO_CORR_CHECK,
        'PORTFOLIO_CORR_ENFORCE': mh.PORTFOLIO_CORR_ENFORCE,
        'detect': mh.rd.RegimeDetector.detect,
    }
    mh.ce._adx = lambda h, l, c: np.array([30.0])
    mh.cl.analyze = lambda c, h, l: {'ok': True, 'divergence': None,
                                     'latest_bsp': None, 'trend_type': 'SHOCK',
                                     'bi_count': 4}
    mh.REGIME_ADAPTIVE = False
    mh.RF_QUALITY_GATE = False
    mh.CHANLUN_SL_OVERRIDE = False
    mh.DYNAMIC_SIGNAL_THRESHOLD = False
    mh.PORTFOLIO_CORR_CHECK = False
    mh.PORTFOLIO_CORR_ENFORCE = False
    yield
    mh.ce._adx = saved['adx']
    mh.cl.analyze = saved['analyze']
    mh.REGIME_ADAPTIVE = saved['REGIME_ADAPTIVE']
    mh.RF_QUALITY_GATE = saved['RF_QUALITY_GATE']
    mh.CHANLUN_SL_OVERRIDE = saved['CHANLUN_SL_OVERRIDE']
    mh.DYNAMIC_SIGNAL_THRESHOLD = saved['DYNAMIC_SIGNAL_THRESHOLD']
    mh.PORTFOLIO_CORR_CHECK = saved['PORTFOLIO_CORR_CHECK']
    mh.PORTFOLIO_CORR_ENFORCE = saved['PORTFOLIO_CORR_ENFORCE']
    mh.rd.RegimeDetector.detect = saved['detect']


def _set_detect(regime):
    def fake_detect(self, symbol, high=None, low=None, close=None):
        return {'regime': regime, 'confidence': 0.7, 'method': 'stub'}
    mh.rd.RegimeDetector.detect = fake_detect


def _cache(h, symbol):
    h._cache[(symbol, mh.TF['H1'])] = _mk_hl(_uptrend())
    h._cache[(symbol, mh.TF['H4'])] = _mk_hl(_uptrend())
    h._cache[(symbol, mh.TF['D1'])] = _mk_hl(_uptrend())


# ── 1. 默认 REGIME_ADAPTIVE=False → 零影响 ──
def test_default_no_regime(isolate):
    h = mh.MarketHunter(strategy=BASE_STRATEGY, guardian=SpyGuardian())
    _cache(h, 'EURUSD')
    p, r = h.scan_symbol('EURUSD')
    assert p is not None, r
    assert 'regime' not in p, "默认应无 regime 信息写入"
    assert h._regime_state == {}, "默认不应触发 regime 检测状态"


# ── 2. REGIME_ADAPTIVE=True → 切参生效 (adx_min/sl/tp 覆盖) ──
def test_regime_override_applied(isolate):
    mh.REGIME_ADAPTIVE = True
    _set_detect('trend')
    spy = SpyGuardian()
    h = mh.MarketHunter(strategy=BASE_STRATEGY, guardian=spy)
    _cache(h, 'EURUSD')
    p, r = h.scan_symbol('EURUSD')
    assert p is not None, r
    lp = spy.last_params
    assert lp['adx_min'] == 20, f"应切到 trend adx_min=20, 实际 {lp['adx_min']}"
    assert lp['sl_multiplier'] == 2.5
    assert lp['tp_multiplier'] == 5.0
    assert p['regime_applied'] == 'trend'
    assert p['regime'] == 'trend'
    assert p['regime_preset'] == mh.REGIME_PRESETS['trend']


# ── 3. 双铁律: 切参后仍 RR>=2, 仓位夹 [0.01,0.03] ──
def test_regime_override_rr_iron_rule():
    strat = dict(BASE_STRATEGY['params'])
    merged = mh.MarketHunter._apply_regime_preset(strat, 'trend')
    rr = merged['tp_multiplier'] / merged['sl_multiplier']
    assert rr >= 2.0, f"切参后 RR 必须>=2, 实际 {rr}"
    assert 0.01 <= merged['position_size'] <= 0.03


# ── 4. volatility_scalar 自动缩仓 (volatile) ──
def test_volatility_scalar_scaling():
    strat = dict(BASE_STRATEGY['params'])
    strat['position_size'] = 0.03
    strat['volatility_scalar'] = 0.5
    merged = mh.MarketHunter._apply_regime_preset(strat, 'volatile')
    assert abs(merged['position_size'] - 0.015) < 1e-9, merged['position_size']

    # 地板: 0.01 * 0.5 = 0.005 -> 夹到 0.01
    strat2 = dict(BASE_STRATEGY['params'])
    strat2['position_size'] = 0.01
    strat2['volatility_scalar'] = 0.5
    merged2 = mh.MarketHunter._apply_regime_preset(strat2, 'volatile')
    assert abs(merged2['position_size'] - 0.01) < 1e-9

    # 无 volatility_scalar 的旧策略: 不改变仓位
    strat3 = dict(BASE_STRATEGY['params'])
    strat3.pop('volatility_scalar', None)
    strat3['position_size'] = 0.02
    merged3 = mh.MarketHunter._apply_regime_preset(strat3, 'volatile')
    assert abs(merged3['position_size'] - 0.02) < 1e-9


# ── 5. REGIME_SWITCH_COOLDOWN 防抖 (默认 6 根才切换) ──
def test_regime_switch_cooldown(isolate):
    mh.REGIME_ADAPTIVE = True
    queue = iter(['trend'] + ['range'] * 7)  # 1 trend + 7 range
    def fake_detect(self, symbol, high=None, low=None, close=None):
        return {'regime': next(queue), 'confidence': 0.7, 'method': 'stub'}
    mh.rd.RegimeDetector.detect = fake_detect
    h = mh.MarketHunter(strategy=BASE_STRATEGY, guardian=SpyGuardian())
    c = _mk_hl(_uptrend())
    applied = [h._step_regime('EURUSD', c[1], c[2], c[0])[0] for _ in range(8)]
    assert applied[0] == 'trend'
    assert applied[2] == 'trend', "稳定不足不应切换"
    assert applied[5] == 'trend', "稳定不足不应切换"
    assert applied[6] == 'range', "连续 6 根相同才切换"
    assert applied[7] == 'range'


# ── 6. 组合相关性: DRY-RUN 仅记录, 不拦截 ──
def test_portfolio_corr_dryrun_record(isolate):
    mh.PORTFOLIO_CORR_CHECK = True
    mh.PORTFOLIO_CORR_ENFORCE = False
    h = mh.MarketHunter(strategy=BASE_STRATEGY, guardian=CorrGuardian())
    _cache(h, 'USDJPY')
    p, r = h.scan_symbol('USDJPY', open_dirs={'GBPJPY': 'BUY'})
    assert p is not None, "DRY-RUN 不应拦截"
    assert p['portfolio_corr']['action'] == 'REJECT', p['portfolio_corr']
    assert 'daily_risk' in p


# ── 7. 组合相关性: ENFORCE=True 才拒开 ──
def test_portfolio_corr_enforce_reject(isolate):
    mh.PORTFOLIO_CORR_CHECK = True
    mh.PORTFOLIO_CORR_ENFORCE = True
    h = mh.MarketHunter(strategy=BASE_STRATEGY, guardian=CorrGuardian())
    _cache(h, 'USDJPY')
    p, r = h.scan_symbol('USDJPY', open_dirs={'GBPJPY': 'BUY'})
    assert p is None, "ENFORCE 应拒开"
    assert '组合相关性拒开' in r, r


# ── 8. 组合相关性: 反向持仓 = 降权建议 ──
def test_portfolio_corr_downweight(isolate):
    mh.PORTFOLIO_CORR_CHECK = True
    mh.PORTFOLIO_CORR_ENFORCE = False
    h = mh.MarketHunter(strategy=BASE_STRATEGY, guardian=CorrGuardian())
    _cache(h, 'USDJPY')
    p, _ = h.scan_symbol('USDJPY', open_dirs={'GBPJPY': 'SELL'})
    assert p is not None
    assert p['portfolio_corr']['action'] == 'DOWNWEIGHT'


# ── 9. 信号质量动态化: volatile 收紧阈值 ──
def test_dynamic_threshold_volatile_tighten(isolate):
    mh.REGIME_ADAPTIVE = True
    mh.RF_QUALITY_GATE = True
    _set_detect('volatile')

    class FakeRF:
        is_trained = True
        def score(self, c, h, l):
            return {'UP': 0.52, 'DOWN': 0.48}  # BUY 时 p_dir=0.52

    spy = SpyGuardian('BUY')
    h = mh.MarketHunter(strategy=BASE_STRATEGY, guardian=spy)
    h._rf_injected = FakeRF()
    _cache(h, 'EURUSD')

    # 动态开启 (volatile 阈值 0.55): 0.52 < 0.55 → SKIP
    mh.DYNAMIC_SIGNAL_THRESHOLD = True
    p1, r1 = h.scan_symbol('EURUSD')
    assert p1 is None and 'RF质量门禁' in r1, r1

    # 动态关闭 (固定 0.5): 0.52 >= 0.5 → 通过
    mh.DYNAMIC_SIGNAL_THRESHOLD = False
    p2, r2 = h.scan_symbol('EURUSD')
    assert p2 is not None, r2


# ── 10. 进化参数空间含 volatility_scalar ──
def test_evolution_param_space_has_scalar():
    assert 'volatility_scalar' in ce.PARAM_BOUNDS
    lo, hi = ce.PARAM_BOUNDS['volatility_scalar']
    assert lo == 0.5 and hi == 1.0
    sp = ce.StrategyPool()
    params = sp._randomize_params()
    assert 'volatility_scalar' in params
    assert 0.5 <= params['volatility_scalar'] <= 1.0


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
