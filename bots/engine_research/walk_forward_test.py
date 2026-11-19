# -*- coding: utf-8 -*-
"""
walk_forward_test.py — 金策宗师团·插针极值出场 时间稳定验证 (五验最后一关)
把每品种历史分 3 段(前/中/后), 各段独立回测 pin vs baseline, 看 ΔavgR 方向是否一致不反转。
"""
import pinbar_exit_backtest as P

CORE = ["XAUUSD", "BTCUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30", "XAGUSD"]
WICK = 0.55   # 取扫描中段值, 避免用全史最优 wick 造成前视


def seg_rs(rows):
    n = len(rows)
    if n < 900:
        return None
    base = P.backtest("__slice__", "baseline", WICK, rows=rows)
    pin = P.backtest("__slice__", "pin", WICK, rows=rows)
    bs, ps = P.summarize(base), P.summarize(pin)
    if not bs or not ps:
        return None
    return {"n": bs["n"], "d": ps["avgR"] - bs["avgR"], "pinR": ps["avgR"]}


def main():
    print(f"{'品种':<8} {'段1(n/ΔR)':>14} {'段2(n/ΔR)':>14} {'段3(n/ΔR)':>14} {'三段同向?':>10}")
    print("-" * 64)
    ok = 0
    for sym in CORE:
        rows = P.load(sym)
        n = len(rows)
        segs = [rows[: n // 3], rows[n // 3: 2 * n // 3], rows[2 * n // 3:]]
        res = [seg_rs(s) for s in segs]
        if any(r is None for r in res):
            print(f"{sym:<8} 样本不足跳过")
            continue
        ds = [r["d"] for r in res]
        same = all(d > 0 for d in ds)
        if same:
            ok += 1
        cells = " ".join(f"{r['n']}/{r['d']:+.3f}" for r in res)
        print(f"{sym:<8} {cells}  {'✓' if same else '✗'}({ds[0]:+.2f}/{ds[1]:+.2f}/{ds[2]:+.2f})")
    print("-" * 64)
    print(f"时间稳定(3段Δ全正不反转): {ok}/{len(CORE)} 品种通过")


if __name__ == "__main__":
    main()
