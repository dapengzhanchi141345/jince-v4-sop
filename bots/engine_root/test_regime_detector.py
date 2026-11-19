# test_regime_detector.py — Regime 检测层 (HMM) 离线单测 (不连 MT5)
# 验证点:
#   1) 3 种合成行情 (trend / range / volatile) detect() 返回正确 regime
#   2) HMM 缺失 → 自动降级 fallback 状态机且判定正确
#   3) detect 异常(数据不足 / 缺数据) → 返回安全默认 'range', 绝不抛错
import warnings
import numpy as np
import regime_detector as rd

warnings.filterwarnings('ignore')  # 屏蔽 HMM 收敛警告, 保持输出干净


# ───────── 合成行情生成器 (确定性, 固定种子) ─────────
def _hl2(c):
    """物理合理 high/low: 用相邻收盘变动构造蜡烛范围 (high>=low)."""
    chg = np.diff(c, prepend=c[0])
    return c + np.abs(chg) / 2 + 1e-4, c - np.abs(chg) / 2 - 1e-4


def _trend_seg(n=300):
    """强线性趋势 → ADX 高, 回归距离≈0."""
    return np.array([100.0 + 0.10 * i for i in range(n)], float)


def _range_seg(n=300):
    """低波动震荡 + 末段收缩 → ADX 低, ATR比率<0.8."""
    r = np.random.default_rng(11)
    return 100.0 + np.concatenate(
        [r.normal(0, 0.004, max(1, n - 60)), r.normal(0, 0.0008, 60)])


def _volatile_seg(n=300):
    """高波动均值回复 → 大振幅震荡(高 ATR), 回归距离大, 波动率分位高.
    真实黄金的 volatile regime 表现为大幅双向摆动(非窄幅噪音); 故用
    弱均值回复 + 大波动噪声构造, 与 range(近无波动)在特征空间清晰可分.
    """
    c = np.zeros(n); c[0] = 100.0
    r = np.random.default_rng(7)
    for i in range(1, n):
        reversion = 0.08 * (100.0 - c[i - 1])   # 弱均值回复(向 100)
        shock = r.normal(0, 0.55)                # 大波动噪声(高 ATR)
        c[i] = c[i - 1] + reversion + shock
    return c


# 把某 regime 放在混合序列末尾(其余两个放前面), 用于 HMM 多状态学习
def _mixed_chain(target, seg_len=(80, 80, 140)):
    others = [o for o in ('trend', 'range', 'volatile') if o != target]
    segs = {'trend': _trend_seg, 'range': _range_seg, 'volatile': _volatile_seg}
    a = segs[others[0]](seg_len[0])
    b = segs[others[1]](seg_len[1])
    c = segs[target](seg_len[2])
    return np.concatenate([a, b, c])


# ───────── pytest 用例 ─────────
def test_fallback_three_regimes():
    """HMM 缺失(强制 _use_hmm=False) → 简化状态机对 3 种行情判定正确."""
    det = rd.RegimeDetector()
    det._use_hmm = False
    for name, fn in [('trend', _trend_seg), ('range', _range_seg),
                     ('volatile', _volatile_seg)]:
        c = fn(300)
        h, l = _hl2(c)
        r = det.detect('XAUUSD', h, l, c)
        assert r['regime'] == name, f"fallback {name} 误判为 {r['regime']}"
        assert r['method'] == 'fallback'


def test_hmm_three_regimes():
    """HMM 可用 → 3 种混合行情(末尾=目标 regime)均返回正确 regime."""
    det = rd.RegimeDetector()  # 默认 _use_hmm=True (已装 hmmlearn)
    assert det._use_hmm is True, "本环境应已安装 hmmlearn"
    for tgt in ('trend', 'range', 'volatile'):
        c = _mixed_chain(tgt)
        h, l = _hl2(c)
        r = det.detect('XAUUSD', h, l, c)
        assert r['regime'] == tgt, f"HMM {tgt} 误判为 {r['regime']}"
        assert r['method'] == 'hmm'
        assert 0.5 <= r['confidence'] <= 0.99


def test_hmm_missing_uses_fallback():
    """模拟 HMM 缺失 → detect 自动降级 fallback 且判定正确 (不抛错)."""
    det = rd.RegimeDetector()
    det._use_hmm = False
    det._GaussianHMM = None
    for name, fn in [('trend', _trend_seg), ('range', _range_seg),
                     ('volatile', _volatile_seg)]:
        c = fn(300)
        h, l = _hl2(c)
        r = det.detect('XAUUSD', h, l, c)
        assert r['regime'] == name
        assert r['method'] == 'fallback'


def test_insufficient_data_safe_default():
    """数据不足(< MIN_BARS) → 返回安全默认 'range', 不抛错."""
    det = rd.RegimeDetector()
    # 远少于 MIN_BARS=120 的短序列
    c = np.array([100.0 + 0.01 * i for i in range(30)], float)
    h, l = _hl2(c)
    r = det.detect('XAUUSD', h, l, c)
    assert r['regime'] == 'range'
    assert r['method'] == 'safe_default'
    assert r['confidence'] == 0.0


def test_missing_data_no_exception():
    """缺数据入参 (high/low/close=None) → detect 绝不抛错, 返回合法 regime.

    本环境若 MT5 在线(看护循环保持连接), 则走实时 H1 数据返回真实 regime;
    若离线/加载失败, 则返回安全默认 'range'. 两种情形都必须:
      (1) 不抛异常; (2) regime ∈ {trend,range,volatile}; (3) method 合法.
    安全默认路径由 test_insufficient_data_safe_default 单独确定性覆盖.
    """
    det = rd.RegimeDetector()
    r = det.detect('XAUUSD', None, None, None)
    assert r['regime'] in rd.REGIMES
    assert r['method'] in ('safe_default', 'fallback', 'hmm')
    # 离线时应为安全默认
    if r['method'] == 'safe_default':
        assert r['regime'] == 'range'


def test_hmm_exception_falls_back():
    """HMM 训练异常 → 自动 fallback, 不抛错且返回合法 regime."""
    det = rd.RegimeDetector()
    # 人为破坏特征构造, 触发 HMM 路径异常后回退 fallback
    c = _trend_seg(300)
    h, l = _hl2(c)
    # monkey: 让 _hmm_detect 抛错, 验证 detect 仍能回退
    orig = det._hmm_detect
    def _boom(*a, **k):
        raise RuntimeError("injected HMM failure")
    det._hmm_detect = _boom
    r = det.detect('XAUUSD', h, l, c)
    det._hmm_detect = orig
    assert r['regime'] in rd.REGIMES
    assert r['method'] == 'fallback'


# ───────── 手动运行入口 (与项目 test_*.py 风格一致) ─────────
def run():
    try:
        test_fallback_three_regimes()
        test_hmm_three_regimes()
        test_hmm_missing_uses_fallback()
        test_insufficient_data_safe_default()
        test_missing_data_no_exception()
        test_hmm_exception_falls_back()
        print("SELFTEST PASS: 6/6 Regime 检测层 (fallback+HMM+安全默认) 通过 "
              "(3合成行情正确/HMM缺失降级/数据不足安全默认/异常不抛错)")
        return True
    except AssertionError as e:
        print("SELFTEST FAIL:", e)
        return False
    except Exception as e:
        print("SELFTEST ERROR:", repr(e))
        return False


if __name__ == '__main__':
    import sys
    sys.exit(0 if run() else 1)
