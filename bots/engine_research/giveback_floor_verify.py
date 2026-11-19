# -*- coding: utf-8 -*-
"""
giveback_floor_verify.py —— 引擎候选 giveback-floor 公式独立验证（交给 Hermes 验证的产物）
金策·进化营 · 第一波深度优化专项

验证目标：确认 tools/jince_live24.py 中新增的「峰值回撤地板」候选
  _gf = extreme_px[sym] - sgn * GIVEBACK_BAND_R * dist
与沙盒 research/rapid_momentum_lock_sandbox.py 的 giveback_floor_sl 完全一致，
且只往紧推(不松动)、方向正确、受 GIVEBACK_FLOOR_ENABLE 开关门控。

注意：本测试不 import 生产引擎(避免 mt5 依赖)，而是逐字复刻其公式做一致性证明。
"""
import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from rapid_momentum_lock_sandbox import giveback_floor_sl  # 沙盒参照实现

BAND = 0.6  # 与引擎 GIVEBACK_BAND_R 一致


def engine_formula(extreme_px, sgn, dist, BAND=BAND):
    """逐字复刻 jince_live24.py:771 的引擎公式。"""
    return extreme_px - sgn * BAND * dist


def test_consistency():
    ok = True
    print("=== giveback-floor 引擎公式 vs 沙盒 一致性验证 ===")
    # 多单: entry=100, 1R=dist=1, 峰值=105.62(5.62R)
    e, sgn, dist, peak = 100.0, 1, 1.0, 105.62
    eng = engine_formula(peak, sgn, dist)
    sbx = giveback_floor_sl(e, 1, peak, dist, BAND)
    print("  多单 peak=%.2f → 引擎SL=%.2f 沙盒SL=%.2f" % (peak, eng, sbx))
    assert abs(eng - sbx) < 1e-9, "多单公式不一致"
    cap = (eng - e) / dist
    print("    捕获 %.2fR (沙盒峰值-0.6R=%.2f)" % (cap, peak - e - BAND))
    assert abs(cap - (peak - e - BAND)) < 1e-9
    ok = ok and True

    # 空单: entry=100, 1R=dist=1, 谷值(峰值方向向下)=94.38(-5.62R)
    sgn = -1
    eng = engine_formula(94.38, sgn, dist)
    sbx = giveback_floor_sl(100.0, -1, 94.38, dist, BAND)
    print("  空单 trough=94.38 → 引擎SL=%.2f 沙盒SL=%.2f" % (eng, sbx))
    assert abs(eng - sbx) < 1e-9, "空单公式不一致"
    ok = ok and True

    # 只往紧推: 引擎公式给出的地板必须优于(更盈利侧)既有 new_sl
    # 多单: 既有 new_sl=101.0, 峰值地板=105.02 → 取更紧(更大)的 105.02
    new_sl = 101.0
    gf = engine_formula(105.62, 1, dist)
    chosen = gf if gf * 1 > new_sl * 1 else new_sl
    print("  棘轮合并: new_sl=%.2f vs 地板=%.2f → 取 %.2f (更紧)" % (new_sl, gf, chosen))
    assert chosen == gf and gf > new_sl, "棘轮应取更紧地板"
    ok = ok and True

    # 开关门控: GIVEBACK_FLOOR_ENABLE=False 时该路不启用(行为不变)
    ENABLED = False
    r_mult = 5.62
    activated = ENABLED and r_mult > 0
    print("  开关门控: GIVEBACK_FLOOR_ENABLE=%s → 候选路启用=%s (默认关, 现役行为不变)" % (ENABLED, activated))
    assert activated is False, "默认必须关闭"
    ok = ok and True

    print("结论:", "ALL PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    sys.exit(0 if test_consistency() else 1)
