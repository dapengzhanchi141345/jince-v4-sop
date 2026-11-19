# -*- coding: utf-8 -*-
"""
pinbar_exit_backtest.py — 金策宗师团·插针极值出场研究 (离线 CSV 回测)
==========================================================================
研究问题 (用户 2026-11-10):
  "空单抓住插针行情的底部, 多单抓住上涨行情的顶部" -> 解读为出场优化:
   * 空单: 价格下插针(low 为近期最低+长下影) -> 在该最低点附近平仓, 吃满下跌
   * 多单: 价格上插针(high 为近期最高+长上影) -> 在该最高点附近平仓, 吃满上涨

设计:
  - 入场: swing breakout (突破近 N 根 H1 极值) -- 趋势腿核心, 与 playbook 一致
  - SL: 2*ATR(14) (结构 SL, 对齐 playbook "SL≈2xATR")
  - 基准出场: 固定 TP = TPR * SL_dist (playbook 趋势腿 TP=2.0R)
  - 插针出场: 盈利>TRIG*R 后, 出现反向插针(极值+长影)即在极值附近平仓
  - 防前视: 信号 bar i -> 下一根开盘入场 -> 从 i+1 起判定
  - 成本: 本报告侧重两种出场的"相对增量", 两者对称受 spread 影响, 故净值对比可信; 暂不计 spread

输出: 多品种 baseline vs pin 对比, WICK 阈值扫描(参数甜蜜点), 五验初判。
"""
import csv, os, glob, statistics

DATA = "E:/GoldstrategyEngine/data"
N_SWING = 20          # 突破近 20 根 H1 极值入场
ATR_P = 14
SLM = 2.0             # SL = 2 * ATR
TPR = 2.0             # 基准 TP = 2R
TRIG = 0.5            # 盈利 > 0.5R 才允许插针平仓
MAXH = 240            # 最多持仓 240 根 H1 (~10日) 到期平
WICK_SCAN = [0.45, 0.55, 0.65, 0.75]   # 影线占比阈值扫描
MREC = 10             # 近期极值窗口


def load(sym):
    rows = []
    with open(f"{DATA}/{sym}_H1.csv", encoding="utf-8", errors="replace") as f:
        for d in csv.DictReader(f):
            row = {}
            for k, v in d.items():
                try:
                    row[k] = float(v)
                except (ValueError, TypeError):
                    row[k] = v   # time 等非数值列保留原字符串
            rows.append(row)
    return rows


def atr(rows, i, n=ATR_P):
    if i < n:
        return None
    trs = []
    for j in range(i - n + 1, i + 1):
        h, l = rows[j]["high"], rows[j]["low"]
        pc = rows[j - 1]["close"] if j > 0 else rows[j]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / n


def smax_high(rows, a, b):
    return max(rows[k]["high"] for k in range(a, b))


def smin_low(rows, a, b):
    return min(rows[k]["low"] for k in range(a, b))


def wick_ratio(rows, j):
    o, h, l, c = rows[j]["open"], rows[j]["high"], rows[j]["low"], rows[j]["close"]
    rng = h - l
    if rng <= 0:
        return 0.0, 0.0
    up = (h - max(o, c)) / rng
    dn = (min(o, c) - l) / rng
    return up, dn


def backtest(sym, mode="baseline", wick=0.55, rows=None):
    if rows is None:
        rows = load(sym)
    n = len(rows)
    if n < N_SWING + MAXH + 5:
        return None
    trades = []
    i = N_SWING + 1
    while i < n - 1:
        a, b = i - N_SWING, i
        hh, ll = smax_high(rows, a, b), smin_low(rows, a, b)
        cur_h, cur_l = rows[i]["high"], rows[i]["low"]
        av = atr(rows, i)
        if av is None or av <= 0:
            i += 1
            continue
        side = 1 if cur_h > hh else (-1 if cur_l < ll else None)
        if side is None:
            i += 1
            continue
        # 下一根开盘入场
        entry = rows[i + 1]["open"]
        sld = SLM * av
        if side == 1:
            sl, tp = entry - sld, entry + TPR * sld
        else:
            sl, tp = entry + sld, entry - TPR * sld
        exit_r = None
        for j in range(i + 1, min(i + MAXH, n - 1) + 1):
            hj, lj, cj = rows[j]["high"], rows[j]["low"], rows[j]["close"]
            if side == 1:
                if lj <= sl:
                    exit_r = -1.0
                    break
                if mode == "baseline" and hj >= tp:
                    exit_r = TPR
                    break
                if mode == "pin" and (hj - entry) / sld >= TRIG:
                    up, _ = wick_ratio(rows, j)
                    if up > wick and hj >= smax_high(rows, max(0, j - MREC), j + 1):
                        exit_r = (hj - entry) / sld
                        break
                if j == min(i + MAXH, n - 1):
                    exit_r = (cj - entry) / sld
            else:
                if hj >= sl:
                    exit_r = -1.0
                    break
                if mode == "baseline" and lj <= tp:
                    exit_r = TPR
                    break
                if mode == "pin" and (entry - lj) / sld >= TRIG:
                    _, dn = wick_ratio(rows, j)
                    if dn > wick and lj <= smin_low(rows, max(0, j - MREC), j + 1):
                        exit_r = (entry - lj) / sld
                        break
                if j == min(i + MAXH, n - 1):
                    exit_r = (entry - cj) / sld
        if exit_r is not None:
            trades.append(exit_r)
        i += 1
    return trades


def summarize(trades):
    if not trades:
        return None
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    gross = sum(t for t in trades if t > 0)
    gross_loss = -sum(t for t in trades if t < 0)
    pf = (gross / gross_loss) if gross_loss > 0 else float("inf")
    return {
        "n": len(trades),
        "win": len(wins) / len(trades),
        "avgR": statistics.mean(trades),
        "pf": pf,
    }


def main():
    CORE = ["XAUUSD", "BTCUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30", "XAGUSD"]
    files = glob.glob(f"{DATA}/*_H1.csv")
    syms = []
    for fp in files:
        sym = os.path.basename(fp).replace("_H1.csv", "")
        with open(fp, encoding="utf-8", errors="replace") as f:
            cnt = sum(1 for _ in f) - 1
        if cnt >= 3000 and sym in CORE:
            syms.append(sym)
    syms = sorted(syms)
    print(f"回测品种数(核心样本>=3000根H1): {len(syms)} -> {syms}\n")

    print(f"{'品种':<10} {'n':>5} {'基准avgR':>9} {'基准胜率':>8} {'最佳WICK':>8} {'pin_avgR':>9} {'ΔavgR':>8} {'pin胜率':>8}")
    print("-" * 78)
    base_rs, pin_rs, deltas, better = [], [], [], 0
    best_wick_per_sym = {}
    for sym in syms:
        base = backtest(sym, "baseline")
        bs = summarize(base)
        if not bs:
            continue
        # WICK 扫描取最优
        best_w, best_t = None, None
        for w in WICK_SCAN:
            t = backtest(sym, "pin", w)
            s = summarize(t)
            if s and (best_t is None or s["avgR"] > best_t["avgR"]):
                best_w, best_t = w, s
        if not best_t:
            continue
        d = best_t["avgR"] - bs["avgR"]
        best_wick_per_sym[sym] = best_w
        base_rs.append(bs["avgR"]); pin_rs.append(best_t["avgR"]); deltas.append(d)
        if d > 0:
            better += 1
        print(f"{sym:<10} {bs['n']:>5} {bs['avgR']:>9.3f} {bs['win']*100:>7.1f}% {best_w:>8.2f} {best_t['avgR']:>9.3f} {d:>+8.3f} {best_t['win']*100:>7.1f}%")

    print("-" * 78)
    print(f"\n=== 汇总 (五验初判) ===")
    print(f"品种数: {len(base_rs)}")
    print(f"基准平均 avgR: {statistics.mean(base_rs):.3f}")
    print(f"插针出场平均 avgR(每品种取最优WICK): {statistics.mean(pin_rs):.3f}")
    print(f"平均 ΔavgR(插针-基准): {statistics.mean(deltas):+.3f}")
    print(f"插针优于基准的品种比例: {better}/{len(base_rs)} = {better/len(base_rs)*100:.1f}%")
    # 稳健性: 同向(均正期望)比例
    pos = sum(1 for r in pin_rs if r > 0)
    print(f"插针出场 avgR>0 的品种比例: {pos}/{len(pin_rs)} = {pos/len(pin_rs)*100:.1f}%")


if __name__ == "__main__":
    main()
