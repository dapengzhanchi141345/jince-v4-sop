# -*- coding: utf-8 -*-
"""
进场质量反事实分析（基于真实实盘成交，非合成回测）
=================================================
目的：直接回答 "如果进场时加一道 ADX 上限闸，真实成交的净R 会怎样？"
数据：trade_lifecycle_analyzer 产出的 01_per_trade_table.csv（逐单 entry_adx + 实现R）
优势：用的是引擎真实放行的成交种群，规避合成回测与 live 进场种群不一致的问题。

红线：本脚本只算反事实、出候选，绝不改 live 参数；参数变更须 WFO 五验 + chief R11。
"""
import os
import csv
import glob

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "trade_deep_analysis", "runs")


def latest_csv():
    files = sorted(glob.glob(os.path.join(RUNS, "*", "01_per_trade_table.csv")))
    return files[-1] if files else None


def load_rows(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        r = csv.DictReader(f)
        for d in r:
            try:
                d["adx"] = float(d["adx"]) if d["adx"] not in ("", None) else None
                d["R"] = float(d["R"])
                d["mfe"] = float(d["MFE_R"]) if d["MFE_R"] not in ("", None) else 0.0
                d["exit_type"] = d["exit_type"]
            except Exception:
                continue
            rows.append(d)
    return rows


def net_of(rows, adx_max):
    """adx_max=None 表示无上限(基线)。只排除 'adx 已知且 >= adx_max' 的成交。"""
    kept, excl = [], []
    for d in rows:
        if adx_max is not None and d["adx"] is not None and d["adx"] >= adx_max:
            excl.append(d)
        else:
            kept.append(d)
    n = len(kept)
    net = sum(d["R"] for d in kept)
    win = sum(1 for d in kept if d["R"] > 0)
    return dict(n=n, net=net, avg=net / n if n else 0, win=win,
                win_rate=win / n if n else 0, excl_n=len(excl),
                excl_net=sum(d["R"] for d in excl))


def main():
    p = latest_csv()
    if not p:
        print("无 01_per_trade_table.csv"); return
    print(">> 读 %s" % p)
    rows = load_rows(p)
    base = net_of(rows, None)
    print("\n基线(全部真实成交): n=%d 净R=%.4f 均值R=%.4f 胜率=%.1f%%" %
          (base["n"], base["net"], base["avg"], base["win_rate"] * 100))

    print("\n%-8s %6s %9s %9s %8s %6s %9s" %
          ("ADX上限", "保留n", "净R", "均值R", "胜率%", "剔除n", "剔除净R"))
    print("-" * 60)
    recs = []
    for thr in [38, 40, 42, 45]:
        s = net_of(rows, thr)
        recs.append((thr, s))
        print("%-8d %6d %9.4f %9.4f %7.1f%% %6d %9.4f" %
              (thr, s["n"], s["net"], s["avg"], s["win_rate"] * 100, s["excl_n"], s["excl_net"]))

    # 关键交叉验证：被剔除的高ADX成交，其亏损是否集中在 B0 假突破？
    print("\n== 被 ADX>=40 剔除的成交，按出场类型分布 ==")
    excl40 = [d for d in rows if d["adx"] is not None and d["adx"] >= 40]
    from collections import defaultdict
    bt = defaultdict(lambda: [0, 0.0])
    for d in excl40:
        bt[d["exit_type"]][0] += 1
        bt[d["exit_type"]][1] += d["R"]
    for k, (nn, nr) in sorted(bt.items(), key=lambda x: x[1][1]):
        print("  %s: n=%d 净R=%.4f" % (k, nn, nr))

    # 推荐判定：剔除后净R改善且保留n足够、且保留部分胜率不崩
    print("\n== 反事实结论 ==")
    best = None
    for thr, s in recs:
        delta = s["net"] - base["net"]
        verdict = "改善" if (delta > 0.05 and s["n"] >= 20) else "不足"
        print("  ADX上限=%d: 净R %.4f (Δ%.4f) 保留n=%d 胜率%.1f%% -> %s" %
              (thr, s["net"], delta, s["n"], s["win_rate"] * 100, verdict))
        if delta > 0.05 and s["n"] >= 20:
            if best is None or delta > best[1]:
                best = (thr, delta, s)
    if best:
        print("\n>>> 反事实候选：ADX上限=%d 可把净R从 %.4f 改善到 %.4f (Δ+%.4f)，保留 %d 笔真实成交" %
              (best[0], base["net"], best[2]["net"], best[1], best[2]["n"]))
        print("    但样本仅 %d 笔(单期亏损窗口)，须 WFO 五验 + chief R11 后方可翻闸，禁止直接改 live。" % base["n"])
    else:
        print("\n>>> 反事实未给出稳健改善候选（Δ不足或保留样本过小），维持现役参数，不翻闸。")


if __name__ == "__main__":
    main()
