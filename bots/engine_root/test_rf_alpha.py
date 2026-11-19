# test_rf_alpha.py — 研策师 RFAlpha 离线单测 (不连 MT5, 不依赖 sklearn 外的包)
#
# 覆盖 (严格按 CIO 落地路线图铁律):
#   1. 标签错位正确 —— 特征 t 不含 t 之后信息; 标签仅用 t+1..t+N
#   2. predict_proba 返回合法概率 (长度2 / 和为1 / 落在[0,1])
#   3. 明显上涨序列上 UP 概率显著高于 DOWN
#   4. 特征工程不泄漏未来 (行为测试 + 故意泄漏的坏实现对比)
#
# 末尾打印: SELFTEST PASS: N/N rf_alpha 通过 ; 退出码 0
import sys
import numpy as np
from rf_alpha import RFAlpha


def _series(n, drift, vol, seed):
    """合成 OHLC (几何随机游走 + 高低影线)。"""
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, n)
    close = np.cumprod(1.0 + rets) * 100.0
    hi = close * (1.0 + np.abs(rng.normal(0, vol * 0.5, n)))
    lo = close * (1.0 - np.abs(rng.normal(0, vol * 0.5, n)))
    return close, hi, lo


def _mixed_train(n_seg=200, vol=0.004, seed=123):
    """交替清晰升/降段 → 标签平衡且线性可分 (供模型学到 ema斜率→方向)。"""
    rng = np.random.default_rng(seed)
    segs = []
    for k in range(4):
        d = 0.003 if (k % 2 == 0) else -0.003
        r = rng.normal(d, vol, n_seg)
        segs.append(r)
    rets = np.concatenate(segs)
    close = np.cumprod(1.0 + rets) * 100.0
    hi = close * (1.0 + np.abs(rng.normal(0, vol * 0.5, len(close))))
    lo = close * (1.0 - np.abs(rng.normal(0, vol * 0.5, len(close))))
    return close, hi, lo


# ═══ 测试用例 ═══
def test_label_misalignment():
    """标签错位: t 的标签只读 t+1..t+N 的未来; 改未来→变, 改过去→不变; 尾部不可标。"""
    N = 20
    close, hi, lo = _series(400, 0.0, 0.004, 7)
    m = RFAlpha(n_future=N)

    # 取一根内部 K 线 t (留出未来 N 根)
    t = 150
    labels = m._make_labels(close, hi, lo)
    base = labels[t]
    assert base in (0, 1), f"label[{t}] 应为 0/1, 得 {base}"

    # (a) 改未来价 t+1 → 标签应改变 (证明标签确实用了未来)
    c2, h2, l2 = close.copy(), hi.copy(), lo.copy()
    c2[t + 1] *= 1.10
    h2[t + 1] = max(h2[t + 1], c2[t + 1] * 1.001)
    l2[t + 1] = min(l2[t + 1], c2[t + 1] * 0.999)
    labels_fut = m._make_labels(c2, h2, l2)
    assert labels_fut[t] != base, \
        f"改未来 t+1 后 label[{t}] 应变 ({base}→{labels_fut[t]})"

    # (b) 改过去价 t-1 → 标签不应改变 (证明标签不偷看过去用于标签)
    c3, h3, l3 = close.copy(), hi.copy(), lo.copy()
    c3[t - 1] *= 1.10
    h3[t - 1] = max(h3[t - 1], c3[t - 1] * 1.001)
    l3[t - 1] = min(l3[t - 1], c3[t - 1] * 0.999)
    labels_past = m._make_labels(c3, h3, l3)
    assert labels_past[t] == base, \
        f"改过去 t-1 后 label[{t}] 不应变 ({base} vs {labels_past[t]})"

    # (c) 尾部 N 根不可标注 (无未来可看, 不窥探)
    assert labels[-1] == -1, "最后一根不应有标签 (无未来)"
    assert labels[len(close) - N] == -1, f"后 {N} 根不应有标签"
    assert labels[len(close) - N - 1] in (0, 1), "倒数第 N+1 根应有标签"
    return True


def test_predict_proba_valid():
    """fit 后 predict_proba 返回合法概率 (长度2 / 和为1 / 落在[0,1])。"""
    close, hi, lo = _mixed_train()
    m = RFAlpha()
    assert m.fit((close, hi, lo)), "混合序列应能训练"
    # 取一个有效特征向量
    feats, valid = m._build_features(close, hi, lo)
    idx = np.where(valid)[0]
    x = feats[idx[len(idx) // 2]]
    proba = m.predict_proba(x)
    assert proba.shape == (1, 2), f"proba 形状应为 (1,2), 得 {proba.shape}"
    s = float(proba.sum())
    assert abs(s - 1.0) < 1e-6, f"概率和应为1, 得 {s}"
    assert np.all(proba >= -1e-9) and np.all(proba <= 1.0 + 1e-9), \
        f"概率应∈[0,1], 得 {proba}"
    # 对整批
    P = m.predict_proba(feats[valid])
    assert P.shape[0] == valid.sum()
    assert np.allclose(P.sum(axis=1), 1.0)
    return True


def test_uptrend_up_dominant():
    """明显上涨序列 → score() 的 UP 概率显著高于 DOWN。"""
    train_c, train_h, train_l = _mixed_train()
    m = RFAlpha()
    assert m.fit((train_c, train_h, train_l)), "训练失败"

    # 一条干净的上涨序列 (明显上行: drift >> vol, 尾部最后一根作为评分点)
    up_c, up_h, up_l = _series(200, 0.005, 0.002, 99)
    sc = m.score(up_c, up_h, up_l)
    assert sc is not None, "score 应返回 dict"
    up_p = sc['UP']
    down_p = sc['DOWN']
    assert up_p > down_p, f"上涨序列 UP({up_p:.3f}) 应 > DOWN({down_p:.3f})"
    # 显著: 差距 > 0.2 且 UP 至少 0.7 (模型确实学到上行偏向)
    assert up_p >= 0.70, f"上涨序列 UP 概率应≥0.70, 得 {up_p:.3f}"
    assert (up_p - down_p) > 0.20, \
        f"UP-DOWN 差距应>0.20, 得 {up_p - down_p:.3f}"
    # 对称: 下跌序列 DOWN 应主导
    dn_c, dn_h, dn_l = _series(200, -0.005, 0.002, 7)
    sc2 = m.score(dn_c, dn_h, dn_l)
    assert sc2['DOWN'] > sc2['UP'], \
        f"下跌序列 DOWN({sc2['DOWN']:.3f}) 应 > UP({sc2['UP']:.3f})"
    return True


def test_feature_no_future_leak():
    """特征工程不泄漏未来: 改未来价 t+5, 第 t 根特征不变。"""
    close, hi, lo = _series(300, 0.0, 0.004, 7)
    m = RFAlpha()
    feats1, valid1 = m._build_features(close, hi, lo)
    t = 150
    assert valid1[t], "第 t 根特征应有效"
    f_before = feats1[t].copy()

    # 改未来价 t+5
    c2, h2, l2 = close.copy(), hi.copy(), lo.copy()
    c2[t + 5] *= 1.05
    h2[t + 5] = max(h2[t + 5], c2[t + 5] * 1.001)
    l2[t + 5] = min(l2[t + 5], c2[t + 5] * 0.999)
    feats2, _ = m._build_features(c2, h2, l2)
    assert np.allclose(feats1[t], feats2[t]), \
        "特征 t 不应受 t+5 未来价影响 (未来函数泄漏!)"

    # 对比: 故意"看未来"的坏实现——改未来会令其特征改变 (证明本测试能抓出泄漏)
    def _leaky_row(c, t):
        # 坏实现: 把 t+5 的未来收盘价混进特征
        return np.array([c[t], c[t + 5]])

    before = _leaky_row(close, t)
    after = _leaky_row(c2, t)
    assert not np.allclose(before, after), \
        "泄漏检测器 sanity-check: 坏实现应被本测试抓出 (实现无误则不会到达)"
    return True


def run():
    tests = [
        ("标签错位正确", test_label_misalignment),
        ("predict_proba 合法", test_predict_proba_valid),
        ("上涨UP概率主导", test_uptrend_up_dominant),
        ("特征无未来泄漏", test_feature_no_future_leak),
    ]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"  [✓] {name}")
        except AssertionError as e:
            print(f"  [✗] {name}: {e}")
        except Exception as e:
            print(f"  [!] {name}: 异常 {repr(e)}")
    if passed == len(tests):
        print(f"SELFTEST PASS: {passed}/{len(tests)} rf_alpha 通过")
        return True
    print(f"SELFTEST FAIL: {passed}/{len(tests)} rf_alpha 通过")
    return False


if __name__ == '__main__':
    sys.exit(0 if run() else 1)
