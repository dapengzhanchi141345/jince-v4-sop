# -*- coding: utf-8 -*-
"""
币系时段窗增量假设·小回测 (干净版)  2026-11-14 夜间深研·品系4
数据源: E:/GoldstrategyEngine/data/{COIN}USD_H1.csv (MT5 brokerFX 小时bar, 时间戳=UTC)
样本窗: 2024-11-14 ~ 2026-11-13 (最近2年, 现货ETF制度期; 该段数据98.5%完整小时bar)
快照/新鲜度: 末根bar=2026-11-14 01:00 UTC (跑前实读), 距运行~22h

增量假设 H1 (预注册, 单主假设):
  现卡: 币系 go 00-08UTC(亚盘)+13-21UTC(美盘), 茶歇峰16-17, "衰减21:00-01:00 UTC=只减不增(S8)"
  全网3源: QuantPedia: 22-23UTC全关窗=BTC最强(正向)收益时段, 03-04UTC最差;
           MDPI: 波动向美盘迁移, 周末lull(v比~0.6); 学术: 亚盘对BTC量/波几乎无影响.
  => H1: 卡标"衰减窗21-01"其实并非全天最弱|ret|窗; 全天最弱小时桶不在21-01内(实指12:00UTC午间),
        且全关窗C(21,22,23)|ret| >= 亚盘A(0-7) 在 3/4 币成立.
窗口(不重叠): A亚盘={0..7}(8h) B美盘={13..20}(8h) C全关={21,22,23}(3h, 0点已东京开不入C)
同分母: 同币同期同H1bar; 日级配对t(C-A,B-A) + 方向收益(均值/中位) + 周末夜盘(Fri21->Mon00)
闸: 任一组n<30 => 显式FAIL(不静默)
"""
import csv, json, math, os, datetime, statistics

D = "E:/GoldstrategyEngine/data"
OUT = "E:/GoldstrategyEngine/research/coin_hourwindow_test_20261114.json"
T0, T1 = datetime.datetime(2024, 11, 14), datetime.datetime(2026, 11, 13)
N_EXPECT = (T1 - T0).days * 24  # 17520
COINS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"]
A_H = set(range(0, 8))
B_H = set(range(13, 21))
C_H = {21, 22, 23}

def load(sym):
    rows = []
    with open(os.path.join(D, sym + "_H1.csv"), encoding="utf-8") as f:
        r = csv.reader(f); next(r)
        for line in r:
            if len(line) < 5: continue
            try:
                t = datetime.datetime.strptime(line[0], "%Y-%m-%d %H:%M:%S")
                c = float(line[4])
                if c > 0: rows.append((t, c))
            except ValueError:
                continue
    return rows

def paired_t(a, b):
    n = len(a); d = [x - y for x, y in zip(a, b)]
    m = statistics.mean(d); sd = statistics.pstdev(d)
    if n < 2 or sd == 0:
        return (float("inf") if m > 0 else float("-inf") if m < 0 else 0.0), (0.0 if m != 0 else 1.0)
    t = m / (sd / math.sqrt(n))
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2))))
    return t, p

report = {"data_source": "MT5 brokerFX H1 bars, UTC", "window": [str(T0), str(T1)],
          "completeness_expect": N_EXPECT,
          "assumptions": ["bar=UTC", "|ret|/方向=close-to-close 1h", "样本=最近2年现货ETF制度期", "0点(东京开)不入全关窗C"],
          "coins": {}, "gates": {}, "verdict": "PENDING"}

for sym in COINS:
    rows = [x for x in load(sym) if T0 <= x[0] < T1]
    last = rows[-1][0]
    rets = []
    for (t1, c1), (t2, c2) in zip(rows, rows[1:]):
        if (t2 - t1).total_seconds() == 3600:
            rets.append((t1, c2 / c1 - 1.0))
    g = {"sym": sym, "bars": len(rows), "completeness": round(len(rows) / N_EXPECT, 3),
         "valid_ret": len(rets), "snapshot_last_bar": str(rows[-1][0]),
         "freshness_h": round((datetime.datetime(2026, 11, 14, 23, 31) - last).total_seconds() / 3600, 1),
         "fail_gate": []}
    h_abs, h_dir = {}, {}
    for t, r in rets:
        h_abs.setdefault(t.hour, []).append(abs(r) * 100)
        h_dir.setdefault(t.hour, []).append(r * 100)
    g["hourly"] = {h: {"abs_med": round(statistics.median(v), 4), "dir_med": round(statistics.median(h_dir.get(h, [0])), 4),
                        "n": len(v)} for h, v in sorted(h_abs.items())}
    win = {}
    for name, hs in (("A_asia00-07", A_H), ("B_us13-20", B_H), ("C_allclose21-23", C_H)):
        av = [v for h in hs for v in h_abs.get(h, [])]
        dv = [v for h in hs for v in h_dir.get(h, [])]
        win[name] = {"n": len(av), "abs_mean": round(statistics.mean(av), 5) if av else None,
                     "abs_med": round(statistics.median(av), 5) if av else None,
                     "dir_mean": round(statistics.mean(dv), 5) if dv else None,
                     "dir_med": round(statistics.median(dv), 5) if dv else None}
        if len(av) < 30: g["fail_gate"].append(name + " n<30")
    g["windows"] = win
    days = {}
    for t, r in rets:
        days.setdefault(t.date(), []).append((t, r))
    ax, cx, bx, ad, cd = [], [], [], [], []
    for dd, rs in sorted(days.items()):
        am = [abs(r)*100 for t, r in rs if t.hour in A_H]; cm = [abs(r)*100 for t, r in rs if t.hour in C_H]
        bm = [abs(r)*100 for t, r in rs if t.hour in B_H]
        ad_ = [r*100 for t, r in rs if t.hour in A_H]; cd_ = [r*100 for t, r in rs if t.hour in C_H]
        if len(am) == 8 and len(cm) == 3 and len(bm) == 8:
            ax.append(statistics.mean(am)); cx.append(statistics.mean(cm)); bx.append(statistics.mean(bm))
            ad.append(statistics.mean(ad_)); cd.append(statistics.mean(cd_))
    t_ac, p_ac = paired_t(cx, ax); t_ba, p_ba = paired_t(bx, ax)
    t_dac, p_dac = paired_t(cd, ad)
    g["paired_days"] = len(ax)
    g["t_CA"] = t_ac; g["p_CA"] = round(p_ac, 4)
    g["t_BA"] = t_ba; g["p_BA"] = round(p_ba, 4)
    g["dir_t_CA"] = t_dac; g["dir_p_CA"] = round(p_dac, 4)
    g["ratio_BA"] = round(win["B_us13-20"]["abs_mean"] / win["A_asia00-07"]["abs_mean"], 3)
    g["ratio_CA"] = round(win["C_allclose21-23"]["abs_mean"] / win["A_asia00-07"]["abs_mean"], 3)
    hm = {h: g["hourly"][h]["abs_med"] for h in g["hourly"] if g["hourly"][h]["n"] >= 100}
    g["weakest_hour"] = min(hm, key=hm.get); g["strongest_hour"] = max(hm, key=hm.get)
    g["weakest_in_C"] = g["weakest_hour"] in C_H
    wk = [abs(r)*100 for t, r in rets if t.weekday() >= 5]; wd = [abs(r)*100 for t, r in rets if t.weekday() < 5]
    g["wk_wd_ratio"] = round(statistics.mean(wk) / statistics.mean(wd), 3) if wk and wd else None
    fric = {}; mons = {}
    for t, c in rows:
        if t.weekday() == 4 and t.hour == 21: fric[t.date()] = c
        if t.weekday() == 0 and t.hour == 0: mons[t.date()] = c
    night = []
    for mdate in mons:
        fdate = mdate - datetime.timedelta(days=3)  # 周一-3天=周五
        if fdate in fric:
            night.append((mdate, mons[mdate] / fric[fdate] - 1))
    g["night_weeks"] = len(night)
    if night:
        g["night_win_rate"] = round(sum(1 for _, r in night if r > 0) / len(night), 3)
        g["night_mean_pct"] = round(statistics.mean([r * 100 for _, r in night]), 4)
    report["coins"][sym] = g

fails = [v for v in report["coins"].values() if v["fail_gate"]]
report["gates"]["all_n_ge_30"] = (not fails) and all(v["paired_days"] >= 30 for v in report["coins"].values())
if not report["gates"]["all_n_ge_30"]:
    report["verdict"] = "FAIL(样本<30, 显式)"
else:
    cge = sum(1 for v in report["coins"].values() if v["ratio_CA"] is not None and v["ratio_CA"] >= 1.0)
    weakest_notC = sum(1 for v in report["coins"].values() if not v["weakest_in_C"])
    sig = sum(1 for v in report["coins"].values() if v["p_CA"] < 0.05 and v["t_CA"] > 0)
    report["gates"]["C_ge_A"] = f"{cge}/4"; report["gates"]["weakest_not_in_C"] = f"{weakest_notC}/4"
    report["gates"]["C_gt_A_sig"] = f"{sig}/4"
    report["verdict"] = ("PASS(H1: 21-01非全天最弱, 全关窗>=亚盘) -> 卡需改衰减窗定性"
                         if (weakest_notC >= 3 and cge >= 3) else "FAIL(H1不成立, 卡不变)")

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=1)

for sym, v in report["coins"].items():
    w = v["windows"]
    print(f"{sym}: 完整度{v['completeness']} 配对口径n={v['paired_days']} "
          f"A|ret|={w['A_asia00-07']['abs_mean']} B={w['B_us13-20']['abs_mean']} C={w['C_allclose21-23']['abs_mean']}")
    print(f"   B/A={v['ratio_BA']} C/A={v['ratio_CA']} p(C-A)={v['p_CA']} C方向均值={w['C_allclose21-23']['dir_mean']} "
          f"最弱时={v['weakest_hour']}(在C={v['weakest_in_C']}) 最强时={v['strongest_hour']} 周末比={v['wk_wd_ratio']}")
    nh = {k: v.get(k) for k in ("night_weeks","night_win_rate","night_mean_pct") if k in v}
    print("   夜盘(Fri21->Mon00):", nh)
print("GATES:", report["gates"]); print("VERDICT:", report["verdict"])
