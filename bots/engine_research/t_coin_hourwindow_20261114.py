# -*- coding: utf-8 -*-
"""
币系时段窗假设小回测 (2026-11-14 夜间深研·品系4)
数据源: E:/GoldstrategyEngine/data/{COIN}USD_H1.csv (MT5 brokerFX 小时bar, 时间戳=UTC)
快照: 各文件末根bar (脚本内读取), 样本窗=最近2年 2024-11-14~2026-11-13 (现货ETF制度期, 对齐MDPI结构断点end-2021后)

增量假设 H (预注册):
  现卡: 币系 go 00-08UTC(亚盘) + 13-21UTC(美盘2.15x), 21-01UTC=衰减窗(S8只减不增)
  全网3源: QuantPedia: 22-23UTC全关窗=BTC最强收益时段, 03-04UTC最差;
           MDPI WallStreetTime: 波动向美盘迁移(US窗>50%日方差); 周末lull加深(vol比~0.6);
           学术(Bitstamp 2015-18): 亚盘对BTC量/波几乎无影响, 03-04UTC全天最低活动.
  => H: 21-01UTC"衰减窗"(=全关窗21,22,23,0) 的小时|ret| >= 亚盘00-07UTC, 且非全天最弱窗.
验证: 小时|ret|分组 + 日级配对t检验(A亚盘 vs C全关, B美盘 vs A); 同分母=同币同期同bar; 4币一致性.
闸: 任一组n<30 => 显式FAIL(不静默). 决策: PASS=C>=A且3/4币成立且p<0.05至少2币; 否则FAIL留痕.
"""
import csv, json, math, os, datetime, statistics

D = "E:/GoldstrategyEngine/data"
OUT = "E:/GoldstrategyEngine/research/coin_hourwindow_test_20261114.json"
T0, T1 = datetime.datetime(2024, 11, 14), datetime.datetime(2026, 11, 13)
COINS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"]

A_H = set(range(0, 8))            # 亚盘 00-07 UTC
B_H = set(range(13, 21))          # 美盘 13-20 UTC
C_H = {21, 22, 23, 0}            # 全关窗 21-00 UTC (现卡"衰减窗21-01")

def load(sym):
    rows = []
    with open(os.path.join(D, sym + "_H1.csv"), encoding="utf-8") as f:
        r = csv.reader(f); next(r)
        for line in r:
            if len(line) < 5: continue
            try:
                t = datetime.datetime.strptime(line[0], "%Y-%m-%d %H:%M:%S")
                c = float(line[4])
                if c <= 0: continue
            except ValueError:
                continue
            rows.append((t, c))
    return rows

def ttest(x, y):
    """paired t on (x-y) diffs; returns (t, p approx via normal)"""
    n = len(x)
    d = [a - b for a, b in zip(x, y)]
    m = statistics.mean(d)
    sd = statistics.pstdev(d)
    if sd == 0 or n < 2:
        return (float("inf") if m > 0 else float("-inf") if m < 0 else 0.0), 0.0 if m == 0 else 1.0
    t = m / (sd / math.sqrt(n))
    # normal approx (n large)
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2))))
    return t, p

report = {"data_source": "MT5 brokerFX H1 bars (UTC timestamps)", "window": [str(T0), str(T1)], "assumptions": ["bar时间戳=UTC", "|ret|=close-to-close小时绝对收益", "样本=最近2年现货ETF制度期"], "coins": {}, "gates": {}, "verdict": "PENDING"}

for sym in COINS:
    rows = load(sym)
    last = rows[-1][0]
    rows = [(t, c) for t, c in rows if T0 <= t < T1]
    # 完整性: 期望 8760 bars; 缺口率
    n = len(rows)
    gap = 1 - n / 8760
    rets = []
    for (t1, c1), (t2, c2) in zip(rows, rows[1:]):
        if (t2 - t1).total_seconds() == 3600:
            rets.append((t1, c2 / c1 - 1.0))
    g = {"sym": sym, "bars_in_window": n, "gap_ratio": round(gap, 4), "snapshot_last_bar": str(rows[-1][0]), "freshness_h": round((datetime.datetime(2026, 11, 14, 23, 31) - last).total_seconds() / 3600, 1), "fail_gate": []}
    byh = {}
    for t, r in rets:
        byh.setdefault(t.hour, []).append(abs(r) * 100)  # 百分点
    for name, hs in (("A_asiatic00-07", A_H), ("B_us13-20", B_H), ("C_allclosed21-00", C_H)):
        vals = [v for h in hs for v in byh.get(h, [])]
        g[name] = {"n": len(vals), "mean_abs_pct": round(statistics.mean(vals), 5) if vals else None, "median_abs_pct": round(statistics.median(vals), 5) if vals else None}
        if len(vals) < 30:
            g["fail_gate"].append(name + " n<30")
    # 日级配对: 每日 A vs C 的 mean|ret|
    days = {}
    for t, r in rets:
        days.setdefault(t.date(), []).append((t, r))
    ax, cx, bx = [], [], []
    for dd, rs in sorted(days.items()):
        am = [abs(r) * 100 for t, r in rs if t.hour in A_H]
        bm = [abs(r) * 100 for t, r in rs if t.hour in B_H]
        cm = [abs(r) * 100 for t, r in rs if t.hour in C_H]
        if len(am) == 8 and len(cm) == 4 and len(bm) == 8:
            ax.append(statistics.mean(am)); cx.append(statistics.mean(cm)); bx.append(statistics.mean(bm))
    t_ac, p_ac = ttest(cx, ax)   # C - A
    t_ba, p_ba = ttest(bx, ax)   # B - A
    g["paired_days"] = len(ax)
    g["t_C_minus_A"] = t_ac; g["p_C_minus_A"] = round(p_ac, 4)
    g["t_B_minus_A"] = t_ba;  g["p_B_minus_A"] = round(p_ba, 4)
    g["ratio_BA"] = round(g["B_us13-20"]["mean_abs_pct"] / g["A_asiatic00-07"]["mean_abs_pct"], 3) if g["A_asiatic00-07"]["mean_abs_pct"] else None
    g["ratio_CA"] = round(g["C_allclosed21-00"]["mean_abs_pct"] / g["A_asiatic00-07"]["mean_abs_pct"], 3) if g["A_asiatic00-07"]["mean_abs_pct"] else None
    # C 是否全天最弱窗(24小时桶比较)
    hourly_med = {h: round(statistics.median(v), 5) for h, v in byh.items() if len(v) >= 100}
    worst = min(hourly_med, key=hourly_med.get)
    g["weakest_hour"] = worst
    g["hourly_median"] = hourly_med
    # 周末vs平日 |ret| 比 (副证据: 周末薄簿量化)
    wk = [abs(r) * 100 for t, r in rets if t.weekday() >= 5]
    wd = [abs(r) * 100 for t, r in rets if t.weekday() < 5]
    g["wk_wd_ratio"] = round(statistics.mean(wk) / statistics.mean(wd), 3) if wk and wd else None
    report["coins"][sym] = g

# 总闸
all_fail = any(v["fail_gate"] for v in report["coins"].values())
ns = [v["paired_days"] for v in report["coins"].values()]
report["gates"]["all_n_ge_30"] = (not all_fail) and all(x >= 30 for x in ns)
if not report["gates"]["all_n_ge_30"]:
    report["verdict"] = "FAIL(样本<30)"
else:
    pass_cnt = sum(1 for v in report["coins"].values() if v["ratio_CA"] is not None and v["ratio_CA"] >= 1.0)
    sig_cnt = sum(1 for v in report["coins"].values() if v["p_C_minus_A"] < 0.05 and v["t_C_minus_A"] > 0)
    report["gates"]["C_ge_A_coins"] = f"{pass_cnt}/4"
    report["gates"]["C_gt_A_significant"] = f"{sig_cnt}/4"
    report["verdict"] = ("PASS(全关窗>=亚盘, 衰减窗定性错)" if (pass_cnt >= 3 and sig_cnt >= 2) else "FAIL(亚盘仍>=全关窗, 卡不变)")

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=1)

for sym, v in report["coins"].items():
    print(f"{sym}: 日对n={v['paired_days']} gap={v['gap_ratio']} B/A={v['ratio_BA']} C/A={v['ratio_CA']} p(C-A)={v['p_C_minus_A']} 最弱时={v['weakest_hour']} 周末比={v['wk_wd_ratio']}")
    print("  A亚盘:", v["A_asiatic00-07"], "B美盘:", v["B_us13-20"], "C全关:", v["C_allclosed21-00"])
print("VERDICT:", report["verdict"], "| gates:", report["gates"])
