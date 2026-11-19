# test_scanner.py — 猎场司决策逻辑离线单测 (不连 MT5)
import sys
import numpy as np
import market_scanner as mh


def _uptrend(n=260, start=100.0, step=0.2):
    return np.array([start + step * i for i in range(n)], dtype=float)

def _downtrend(n=260, start=200.0, step=0.2):
    return np.array([start - step * i for i in range(n)], dtype=float)

def _flat(n=260, base=100.0):
    rng = np.random.default_rng(42)
    return base + rng.normal(0, 1e-3, n)

def _choppy(n=260, base=100.0):
    """高波动无净趋势 (正弦往返) → ADX 极低, 模拟震荡市."""
    return base + 8.0 * np.sin(np.linspace(0, 20 * np.pi, n))

def _mk_hl(c):
    rng = np.random.default_rng(0)
    eps = np.abs(rng.normal(0, 0.001, len(c)))
    return c, c * (1 + eps), c * (1 - eps)


class FakeGuardian:
    """只返回固定方向的提案, 隔离 build_signal, 专测多周期共振过滤逻辑."""
    def __init__(self, direction):
        self.direction = direction
        self.sizer = None
    def build_signal(self, strategy, symbol, dl_pred=None, tc_bias=None):
        return {'symbol': symbol, 'direction': self.direction,
                'lot': 0.02, 'entry': 1.0}, 'ok'
    # RANGE_MODE_ENABLED=True 后, ADX硬禁分支会调 build_range_signal;
    # 测试桩默认返回 (None,...) 让区间分支回归 SKIP (测的是硬禁而非区间).
    def build_range_signal(self, symbol, strategy=None):
        return None, "test range stub"


class FakeSizer:
    """模拟自适应仓位器, 控制 should_pause 返回值."""
    def __init__(self, pause=False):
        self._pause = pause
    def should_pause(self, symbol):
        if self._pause:
            return True, "品种近期表现差 (测试)"
        return False, ""


def run():
    try:
        # 测试环境统一钉死 H1 ADX=45, 避免依赖真实 ADX 边界值.
        # 区间模块覆盖带已拓宽到 ADX<35 (RANGE_ADX_CEIL), 钉 45 确保
        # range 分支不拦截, 专测冲突/质量/缠论等其它闸 (测的是那些逻辑
        # 而非 ADX). 若钉 <=35 会落入中等波动带被 range 分支抢跑.
        orig_adx_global = mh.ce._adx
        mh.ce._adx = lambda h, l, c: np.array([45.0])
        # 多周期增强(P1+P2+P3)后 scan_symbol 会加载 W1/M15 真实数据,
        # 测试环境钉死为合成, 避免依赖真实行情导致断言不稳定.
        orig_hist = mh.MarketHunter._hist
        def _test_hist(self, symbol, tf):
            if tf == mh.TF['W1'] and (symbol, tf) not in self._cache:
                self._cache[(symbol, tf)] = _mk_hl(_flat())      # W1→NEUTRAL
            elif tf == mh.TF['M15'] and (symbol, tf) not in self._cache:
                self._cache[(symbol, tf)] = _mk_hl(_uptrend())   # M15→与H1同向(uptrend)
            return orig_hist(self, symbol, tf)
        mh.MarketHunter._hist = _test_hist
        # 1. 趋势判定
        assert mh._trend_bias(_uptrend()) == 'BUY', "uptrend→BUY"
        assert mh._trend_bias(_downtrend()) == 'SELL', "downtrend→SELL"
        assert mh._trend_bias(_flat()) == 'NEUTRAL', "flat→NEUTRAL"

        # 2. 多周期冲突: H4 反向 → SKIP
        h = mh.MarketHunter(strategy={}, guardian=FakeGuardian('BUY'))
        h._cache[('EURUSD', mh.TF['H1'])] = _mk_hl(_uptrend())     # H1 (隔离真实拉取)
        h._cache[('EURUSD', mh.TF['H4'])] = _mk_hl(_downtrend())   # H4 SELL
        h._cache[('EURUSD', mh.TF['D1'])] = _mk_hl(_flat())        # D1 NEUTRAL
        p, r = h.scan_symbol('EURUSD')
        assert p is None and 'H4' in r and '多周期共振不足' in r, f"冲突未拦截: {r}"

        # 3. 多周期共振: H4/D1 同向 → PASS
        h2 = mh.MarketHunter(strategy={}, guardian=FakeGuardian('BUY'))
        h2._cache[('EURUSD', mh.TF['H1'])] = _mk_hl(_uptrend())    # H1 (隔离真实拉取)
        h2._cache[('EURUSD', mh.TF['H4'])] = _mk_hl(_uptrend())    # H4 BUY
        h2._cache[('EURUSD', mh.TF['D1'])] = _mk_hl(_uptrend())    # D1 BUY
        p2, r2 = h2.scan_symbol('EURUSD')
        assert p2 is not None and p2.get('mtf', {}).get('H4') == 'BUY', \
            f"共振失败: {r2}"

        # 4. 已有持仓品种 → 跳过
        p3, r3 = h2.scan_symbol('EURUSD', existing_symbols={'EURUSD'})
        assert p3 is None and '已有' in r3, f"持仓未跳过: {r3}"

        # 5. SELL 入场 + H4 反向(UP) → SKIP
        h3 = mh.MarketHunter(strategy={}, guardian=FakeGuardian('SELL'))
        h3._cache[('GBPUSD', mh.TF['H1'])] = _mk_hl(_uptrend())    # H1 (隔离真实拉取)
        h3._cache[('GBPUSD', mh.TF['H4'])] = _mk_hl(_uptrend())    # H4 BUY
        h3._cache[('GBPUSD', mh.TF['D1'])] = _mk_hl(_flat())
        p4, r4 = h3.scan_symbol('GBPUSD')
        assert p4 is None and 'H4' in r4 and '多周期共振不足' in r4, \
            f"SELL冲突未拦截: {r4}"

        # 6. H1 ADX<35 低/中等波动 → 区间分支接管 → SKIP
        #    (monkeypatch _adx 为低值 5.0, 隔离 ADX 计算;
        #     RANGE_ADX_CEIL=35 后 ADX<35 一律走区间分支, 无 BB 边界信号则 SKIP)
        orig_adx = mh.ce._adx
        mh.ce._adx = lambda h, l, c: np.array([5.0])   # 强制 H1 ADX<35
        h4 = mh.MarketHunter(strategy={}, guardian=FakeGuardian('BUY'))
        h4._cache[('AUDUSD', mh.TF['H1'])] = _mk_hl(_uptrend())
        h4._cache[('AUDUSD', mh.TF['H4'])] = _mk_hl(_uptrend())
        h4._cache[('AUDUSD', mh.TF['D1'])] = _mk_hl(_uptrend())
        p6, r6 = h4.scan_symbol('AUDUSD')
        mh.ce._adx = orig_adx
        assert p6 is None, f"ADX低波动未拦(系统无论区间开/关均硬禁新开, 应SKIP不开仓): {r6}"

        # 6b. P2-A2 路由修正: 区间接管上限=进化 adx_min(封顶35), 非固定35.
        #     ADX∈[adx_min,35) → 趋势优先(区间不被调用);
        #     ADX<adx_min → 区间兜底(被调用). 验证路由修复, 不踩 Test6 回归.
        _orig_rx = mh.RANGE_MODE_ENABLED
        _orig_adx_b = mh.ce._adx
        class CountGuardian:
            def __init__(self):
                self.sizer = None
                self.calls = {'range': 0, 'trend': 0}
            def build_signal(self, strategy, symbol, dl_pred=None, tc_bias=None):
                self.calls['trend'] += 1
                return None, "trend stub"
            def build_range_signal(self, symbol, strategy=None):
                self.calls['range'] += 1
                return None, "range stub"
        try:
            mh.RANGE_MODE_ENABLED = True
            hb = mh.MarketHunter(strategies={'EURUSD': {
                'name': 't', 'params': {'adx_min': 25.0},
                'fitness': 10, 'baseline': {'pf': 1.5, 'win_rate': 0.5}}},
                guardian=CountGuardian())
            hb._cache[('EURUSD', mh.TF['H1'])] = _mk_hl(_uptrend())
            # Case A: ADX=30 ∈ [25,35) → 趋势优先, 区间不应被调用
            mh.ce._adx = lambda h, l, c: np.array([30.0])
            pb, rb = hb.scan_symbol('EURUSD')
            assert hb.guardian.calls['range'] == 0, \
                f"ADX=30(adx_min=25) 不应触发区间: {rb}"
            assert hb.guardian.calls['trend'] == 1, \
                f"ADX=30 应走趋势: {hb.guardian.calls['trend']}"
            # Case B: ADX=20 < 25 → 区间兜底, 应被调用
            hb.guardian.calls = {'range': 0, 'trend': 0}
            mh.ce._adx = lambda h, l, c: np.array([20.0])
            pb, rb = hb.scan_symbol('EURUSD')
            assert hb.guardian.calls['range'] == 1, \
                f"ADX=20(<adx_min25) 应触发区间: {rb}"
        finally:
            mh.RANGE_MODE_ENABLED = _orig_rx
            mh.ce._adx = _orig_adx_b
        print("  [6b] P2-A2 路由修正 OK: ADX∈[adx_min,35)趋势优先 / ADX<adx_min区间兜底")

        # 7. 信号质量门禁: 近期表现差 → 直接 SKIP (ADX 高, 轮到这层)
        fg = FakeGuardian('BUY')
        fg.sizer = FakeSizer(pause=True)
        mh.ce._adx = lambda h, l, c: np.array([45.0])  # 45>=RANGE_ADX_CEIL, range 分支不拦
        h5 = mh.MarketHunter(strategy={}, guardian=fg)
        h5._cache[('AUDUSD', mh.TF['H1'])] = _mk_hl(_uptrend())
        h5._cache[('AUDUSD', mh.TF['H4'])] = _mk_hl(_uptrend())
        h5._cache[('AUDUSD', mh.TF['D1'])] = _mk_hl(_uptrend())
        p7, r7 = h5.scan_symbol('AUDUSD')
        mh.ce._adx = orig_adx
        assert p7 is None and '信号质量门禁' in r7, f"质量门禁未生效: {r7}"

        # 8-10. 缠论 gate 集成 (monkeypatch chanlun.analyze, 隔离真实缠论计算)
        orig_analyze = mh.cl.analyze
        orig_adx2 = mh.ce._adx
        mh.ce._adx = lambda h, l, c: np.array([45.0])  # 过 range 覆盖带(45>=35)
        # 8. 顶背驰 + BUY → 拦截
        mh.cl.analyze = lambda c, h, l: {'ok': True, 'divergence': 'TOP',
                                         'latest_bsp': None, 'trend_type': 'UP',
                                         'bi_count': 5}
        h6 = mh.MarketHunter(strategy={}, guardian=FakeGuardian('BUY'))
        h6._cache[('EURUSD', mh.TF['H1'])] = _mk_hl(_uptrend())
        h6._cache[('EURUSD', mh.TF['H4'])] = _mk_hl(_uptrend())
        h6._cache[('EURUSD', mh.TF['D1'])] = _mk_hl(_uptrend())
        p8, r8 = h6.scan_symbol('EURUSD')
        assert p8 is None and '缠论' in r8, f"缠论gate未拦截顶背驰BUY: {r8}"
        # 9. 底背驰 + BUY → 放行 + 确认
        mh.cl.analyze = lambda c, h, l: {'ok': True, 'divergence': 'BOTTOM',
                                         'latest_bsp': None, 'trend_type': 'DOWN',
                                         'bi_count': 5}
        h7 = mh.MarketHunter(strategy={}, guardian=FakeGuardian('BUY'))
        h7._cache[('EURUSD', mh.TF['H1'])] = _mk_hl(_uptrend())
        h7._cache[('EURUSD', mh.TF['H4'])] = _mk_hl(_uptrend())
        h7._cache[('EURUSD', mh.TF['D1'])] = _mk_hl(_uptrend())
        p9, r9 = h7.scan_symbol('EURUSD')
        assert p9 is not None and p9['chanlun']['tag'] == 'BULLISH_CONFIRM', \
            f"底背驰BUY应确认: {r9} {p9}"
        # 10. 中性 + BUY → 放行
        mh.cl.analyze = lambda c, h, l: {'ok': True, 'divergence': None,
                                         'latest_bsp': None, 'trend_type': 'SHOCK',
                                         'bi_count': 4}
        h8 = mh.MarketHunter(strategy={}, guardian=FakeGuardian('BUY'))
        h8._cache[('EURUSD', mh.TF['H1'])] = _mk_hl(_uptrend())
        h8._cache[('EURUSD', mh.TF['H4'])] = _mk_hl(_uptrend())
        h8._cache[('EURUSD', mh.TF['D1'])] = _mk_hl(_uptrend())
        p10, r10 = h8.scan_symbol('EURUSD')
        assert p10 is not None and p10['chanlun']['tag'] == 'NEUTRAL_ALLOW', \
            f"中性BUY应放行: {r10} {p10}"
        mh.cl.analyze = orig_analyze
        mh.ce._adx = orig_adx2

        # 11. 中枢动态止损覆盖 (P2): 方向合理 + 不过宽 → 覆盖生效
        sl_sug = mh.cl.chanlun_stop('BUY', (1.0900, 1.0970))  # ZG 下方
        proposal = {'symbol': 'EURUSD', 'direction': 'BUY',
                    'entry': 1.1000, 'sl': 1.0950, 'tp': 1.1100,
                    'sl_pts': 50.0, 'tp_pts': 100.0, 'chanlun': {}}
        mh.MarketHunter._apply_chanlun_sl(proposal, sl_sug, 'EURUSD')
        assert proposal['chanlun'].get('sl_override') is True, \
            "应标记中枢SL覆盖"
        assert 1.0950 < proposal['sl'] < 1.1000, \
            f"中枢SL应在入场下方且比ATR更紧: {proposal['sl']}"
        assert proposal['sl_pts'] < 50.0, \
            f"中枢SL点数应小于ATR SL: {proposal['sl_pts']}"
        assert proposal['tp'] < 1.1100, \
            f"TP应按RR重算变小: {proposal['tp']}"

        # 12. 中枢SL方向不合理 → 弃用 (多单 SL 不在入场下方)
        proposal2 = {'symbol': 'EURUSD', 'direction': 'BUY',
                     'entry': 1.1000, 'sl': 1.0950, 'tp': 1.1100,
                     'sl_pts': 50.0, 'tp_pts': 100.0, 'chanlun': {}}
        mh.MarketHunter._apply_chanlun_sl(proposal2, 1.1020, 'EURUSD')
        assert proposal2['chanlun'].get('sl_override') is not True, \
            "方向不合理应弃用中枢SL"
        assert proposal2['sl'] == 1.0950, "方向不合理SL应保持原ATR值"

        # 13. 集成: CHANLUN_SL_OVERRIDE=True → scan_symbol 用中枢SL覆盖提案
        class FullGuardian:
            """返回完整 proposal (含 sl/sl_pts/tp/tp_pts), 供覆盖逻辑使用."""
            def __init__(self, direction):
                self.direction = direction
                self.sizer = None
            def build_signal(self, strategy, symbol, dl_pred=None, tc_bias=None):
                return {'symbol': symbol, 'direction': self.direction,
                        'entry': 1.1000, 'sl': 1.0950, 'tp': 1.1100,
                        'sl_pts': 50.0, 'tp_pts': 100.0, 'lot': 0.02}, 'ok'
            def build_range_signal(self, symbol, strategy=None):
                return None, "test range stub"
        orig_ov = mh.CHANLUN_SL_OVERRIDE
        orig_a2 = mh.cl.analyze
        mh.ce._adx = lambda h, l, c: np.array([45.0])
        mh.CHANLUN_SL_OVERRIDE = True
        mh.cl.analyze = lambda c, h, l: {'ok': True, 'divergence': None,
                                         'latest_bsp': None, 'trend_type': 'SHOCK',
                                         'bi_count': 4, 'zhongshu': (1.0900, 1.0970)}
        h9 = mh.MarketHunter(strategy={}, guardian=FullGuardian('BUY'))
        h9._cache[('EURUSD', mh.TF['H1'])] = _mk_hl(_uptrend())
        h9._cache[('EURUSD', mh.TF['H4'])] = _mk_hl(_uptrend())
        h9._cache[('EURUSD', mh.TF['D1'])] = _mk_hl(_uptrend())
        p13, r13 = h9.scan_symbol('EURUSD')
        mh.CHANLUN_SL_OVERRIDE = orig_ov
        mh.cl.analyze = orig_a2
        mh.ce._adx = orig_adx2
        assert p13 is not None, f"开关开不应拦截: {r13}"
        assert p13['chanlun'].get('sl_override') is True, \
            f"开关开应覆盖中枢SL: {p13['chanlun']}"
        assert p13['sl'] < 1.1000, f"覆盖后SL应<entry: {p13['sl']}"

        # 14. 进化优势门禁 (EDGE GATE)
        #     改动1 (2026-07-08): EDGE_GATE_ENABLED 默认 False — 全品种进池靠
        #     RF/ADX/漂移真实试错, 不在此硬挡. 门禁逻辑本身未删, 仍可临时开启验证.
        #     旧断言(默认开启→拦截)已与新默认行为冲突 → 改为: 默认放行 + 临时开启
        #     验证门禁逻辑仍正确(无回归), 不弱化门禁本身.
        orig_edge = mh.EDGE_GATE_ENABLED
        orig_an_e = mh.cl.analyze
        mh.cl.analyze = lambda c, h, l: {'ok': True, 'divergence': None,
                                         'latest_bsp': None, 'trend_type': 'SHOCK',
                                         'bi_count': 4}  # 缠论中性放行, 隔离 EDGE 决策
        # 14a. 默认关闭 → fitness=0 不在此拦截, 放行给后续闸(新行为, 向后兼容)
        mh.EDGE_GATE_ENABLED = False
        eg = mh.MarketHunter(
            strategies={'EURUSD': {'fitness': 0.0, 'baseline': None,
                                   'params': {'adx_min': 30}}},
            guardian=FakeGuardian('BUY'))
        eg._cache[('EURUSD', mh.TF['H1'])] = _mk_hl(_uptrend())
        eg._cache[('EURUSD', mh.TF['H4'])] = _mk_hl(_uptrend())
        eg._cache[('EURUSD', mh.TF['D1'])] = _mk_hl(_uptrend())
        p14, r14 = eg.scan_symbol('EURUSD')
        assert p14 is not None and '无进化优势' not in r14, \
            f"EDGE默认关闭应放行: {r14}"
        # 14b. 临时开启 → fitness=0 拦截 (门禁逻辑无回归)
        mh.EDGE_GATE_ENABLED = True
        eg2 = mh.MarketHunter(
            strategies={'EURUSD': {'fitness': 0.0, 'baseline': None,
                                   'params': {'adx_min': 30}}},
            guardian=FakeGuardian('BUY'))
        eg2._cache[('EURUSD', mh.TF['H1'])] = _mk_hl(_uptrend())
        eg2._cache[('EURUSD', mh.TF['H4'])] = _mk_hl(_uptrend())
        eg2._cache[('EURUSD', mh.TF['D1'])] = _mk_hl(_uptrend())
        p14b, r14b = eg2.scan_symbol('EURUSD')
        assert p14b is None and '无进化优势' in r14b, \
            f"EDGE开启应拦无优势: {r14b}"
        # 14c. 开启 + fitness达标但 pf<1 → 回测负优势拦截
        eg3 = mh.MarketHunter(
            strategies={'GBPJPY': {'fitness': 5.0,
                                  'baseline': {'pf': 0.5, 'win_rate': 0.3},
                                  'params': {'adx_min': 30}}},
            guardian=FakeGuardian('BUY'))
        eg3._cache[('GBPJPY', mh.TF['H1'])] = _mk_hl(_uptrend())
        eg3._cache[('GBPJPY', mh.TF['H4'])] = _mk_hl(_uptrend())
        eg3._cache[('GBPJPY', mh.TF['D1'])] = _mk_hl(_uptrend())
        p14c, r14c = eg3.scan_symbol('GBPJPY')
        assert p14c is None and '回测负优势' in r14c, \
            f"EDGE开启应拦负优势: {r14c}"
        # 14d. 开启 + 无 fitness 键空策略 → 放行(向后兼容)
        eg4 = mh.MarketHunter(strategy={}, guardian=FakeGuardian('BUY'))
        eg4._cache[('EURUSD', mh.TF['H1'])] = _mk_hl(_uptrend())
        eg4._cache[('EURUSD', mh.TF['H4'])] = _mk_hl(_uptrend())
        eg4._cache[('EURUSD', mh.TF['D1'])] = _mk_hl(_uptrend())
        p14d, r14d = eg4.scan_symbol('EURUSD')
        assert p14d is not None, f"无fitness键应放行门禁: {r14d}"
        # 恢复默认(关闭) + 缠论 mock
        mh.EDGE_GATE_ENABLED = orig_edge
        mh.cl.analyze = orig_an_e

        mh.ce._adx = orig_adx_global  # 恢复真实 _adx
        mh.MarketHunter._hist = orig_hist  # 恢复真实 _hist (测试patch)

        print("SELFTEST PASS: 14/14 猎场司+缠论gate通过 "
              "(趋势判定/多周期冲突/共振/持仓跳过/反向冲突/ADX硬禁/质量门禁/"
              "缠论顶背驰拦截/底背驰确认/中性放行/中枢SL覆盖/中枢SL方向守卫/开关集成/"
              "进化优势门禁拦截/门禁负优势/空策略放行)")
        return True
    except AssertionError as e:
        print("SELFTEST FAIL:", e)
        return False
    except Exception as e:
        print("SELFTEST ERROR:", repr(e))
        return False


def test_rf_direction_flip():
    """改动2: RF 双方向择优翻转 — 提案 SELL 但 UP 概率远高于 DOWN 时,
    应翻转入场为 BUY; 几何(sl/tp 价位)/方向/翻转后 RR 均正确, 后续缠论/MTF/15M
    流程因都用 proposal['direction'] 而自动对齐. 端到端走 scan_symbol(RF门禁开)."""
    orig_adx = mh.ce._adx
    orig_ra = mh.REGIME_ADAPTIVE
    orig_rqg = mh.RF_QUALITY_GATE
    orig_analyze = mh.cl.analyze
    try:
        mh.ce._adx = lambda h, l, c: np.array([45.0])  # 过 range 覆盖带(45>=35), 隔离
        mh.REGIME_ADAPTIVE = False                       # 去 regime 切参, thr 恒 0.5
        mh.RF_QUALITY_GATE = True                        # 开启翻转逻辑
        mh.cl.analyze = lambda c, h, l: {'ok': True, 'divergence': None,
                                         'latest_bsp': None, 'trend_type': 'SHOCK',
                                         'bi_count': 4}  # 缠论中性放行, 隔离

        class FakeRF:
            is_trained = True
            def score(self, c, h, l):
                return {'UP': 0.85, 'DOWN': 0.15}

        class FlipGuardian:
            def __init__(self, direction):
                self.direction = direction
                self.sizer = None
            def build_signal(self, strategy, symbol, dl_pred=None, tc_bias=None):
                return {'symbol': symbol, 'direction': self.direction,
                        'entry': 1.1000, 'sl': 1.0950, 'tp': 1.1100,
                        'sl_pts': 50.0, 'tp_pts': 100.0, 'lot': 0.02}, 'ok'
            def build_range_signal(self, symbol, strategy=None):
                return None, "test range stub"

        h = mh.MarketHunter(strategy={}, guardian=FlipGuardian('SELL'),
                            rf_alpha=FakeRF())
        # 共振周期同向 BUY(翻转后方向=BUY); M15 中性避免 15M 缩止损改写 sl/tp
        for tf in ('H1', 'H4', 'D1', 'W1'):
            h._cache[('EURUSD', mh.TF[tf])] = _mk_hl(_uptrend())
        h._cache[('EURUSD', mh.TF['M15'])] = _mk_hl(_flat())

        p, r = h.scan_symbol('EURUSD')

        assert p is not None, f"翻转后应放行: {r}"
        assert p['direction'] == 'BUY', f"方向应翻转为BUY: {p['direction']}"
        assert p.get('rf_flipped') is True, "应标记 rf_flipped=True"
        assert p['tp_pts'] / p['sl_pts'] >= 2.0, \
            f"翻转后RR应>=2.0: {p['tp_pts']}/{p['sl_pts']}"
        pip = mh.ce.SYMBOL_CONFIG['EURUSD']['pip']
        exp_sl = round(1.1000 - 50.0 * pip, 5)
        exp_tp = round(1.1000 + 100.0 * pip, 5)
        assert abs(p['sl'] - exp_sl) < 1e-9, \
            f"sl几何错误(应{exp_sl}): {p['sl']}"
        assert abs(p['tp'] - exp_tp) < 1e-9, \
            f"tp几何错误(应{exp_tp}): {p['tp']}"
        print("RF方向翻转测试 PASS: SELL→BUY, sl/tp几何正确, RR>=2.0, "
              f"rf_flipped=True (sl={p['sl']}, tp={p['tp']})")
        return True
    except AssertionError as e:
        print("RF方向翻转测试 FAIL:", e)
        return False
    except Exception as e:
        print("RF方向翻转测试 ERROR:", repr(e))
        return False
    finally:
        mh.ce._adx = orig_adx
        mh.REGIME_ADAPTIVE = orig_ra
        mh.RF_QUALITY_GATE = orig_rqg
        mh.cl.analyze = orig_analyze


def test_spread_guard():
    """改动3: 点差摩擦护栏 (吸收 Supreme_EA 知识包 坑#3/#4).
       (a) ce.spread_friction_ok 纯逻辑: 点差/ATR>0.40→拒; ≤0.40→放行;
           atr<=0 / spread<=0 失败开放(与 RF/缠论 gate 一致).
       (b) scanner 预检接线: 护栏返回拒 → scan_symbol 在阶段0.2 直接 None."""
    orig = mh.ce.spread_friction_ok
    orig_adx = mh.ce._adx
    try:
        # (a) 纯逻辑 (spread_price 直传, 不依赖 MT5)
        ok_w, _ = mh.ce.spread_friction_ok('XAUUSD', 3.0, spread_price=2.0)
        assert ok_w is False, "点差/ATR=0.67>0.40 应拒"
        ok_n, _ = mh.ce.spread_friction_ok('XAUUSD', 3.0, spread_price=0.2)
        assert ok_n is True, "点差/ATR=0.067<0.40 应放"
        ok_a, ia = mh.ce.spread_friction_ok('XAUUSD', 0.0, spread_price=2.0)
        assert ok_a is True and 'atr<=0' in ia, "atr<=0 失败开放"
        ok_s, is_ = mh.ce.spread_friction_ok('XAUUSD', 3.0, spread_price=0.0)
        assert ok_s is True and 'spread<=0' in is_, "spread<=0 失败开放"
        # (b) scanner 接线: mock 护栏返回拒 → 阶段0.2 直接 SKIP
        mh.ce.spread_friction_ok = lambda sym, atr: (False, 'GUARD WIDE')
        mh.ce._adx = lambda h, l, c: np.array([45.0])  # 过 range 覆盖带, 隔离
        h = mh.MarketHunter(strategy={}, guardian=FakeGuardian('BUY'))
        h._cache[('EURUSD', mh.TF['H1'])] = _mk_hl(_uptrend())
        h._cache[('EURUSD', mh.TF['H4'])] = _mk_hl(_uptrend())
        h._cache[('EURUSD', mh.TF['D1'])] = _mk_hl(_uptrend())
        p, r = h.scan_symbol('EURUSD')
        assert p is None and 'GUARD' in r, f"点差护栏未拦截: {r}"
        print("点差摩擦护栏测试 PASS: 逻辑(宽拒/窄放/失败开放) + scanner阶段0.2接线 OK")
        return True
    except AssertionError as e:
        print("点差摩擦护栏测试 FAIL:", e)
        return False
    except Exception as e:
        print("点差摩擦护栏测试 ERROR:", repr(e))
        return False
    finally:
        mh.ce.spread_friction_ok = orig
        mh.ce._adx = orig_adx


if __name__ == '__main__':
    ok = run()
    ok_flip = test_rf_direction_flip()
    ok_spread = test_spread_guard()
    sys.exit(0 if (ok and ok_flip and ok_spread) else 1)
