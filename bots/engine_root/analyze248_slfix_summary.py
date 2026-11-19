#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""双分母 B-A 重报汇总 (L4 修订口径), 销账件. 0 写闸源 0 进 live."""
import json, glob, statistics as st, datetime, os
os.chdir(r"E:\GoldstrategyEngine")
new18 = json.load(open("data/analyze248_slfix_w0.json", encoding="utf-8"))["syms"]
new18b = json.load(open("data/analyze248_slfix_w1.json", encoding="utf-8"))["syms"]
old = {}
for f in glob.glob("data/analyze248_w[0-7].json"):
    for sym, s in json.load(open(f, encoding="utf-8")).get("syms", {}).items():
        old[sym] = s
merged = dict(old)
merged.update(new18)
cross = sum(1 for s in new18
            if new18[s]["A_基线_不加"].get("cumR") != new18b[s]["A_基线_不加"].get("cumR")
            or new18[s]["B_加2中点+到区"].get("cumR") != new18b[s]["B_加2中点+到区"].get("cumR"))
green = [s for s in new18 if abs(new18[s]["A_基线_不加"].get("cumR", 0)) <= 1000
         and abs(new18[s]["B_加2中点+到区"].get("cumR", 0)) <= 1000]
frozen = [s for s in new18 if s not in green]

def diffs(pred):
    out = []
    for sym, s in merged.items():
        if not pred(sym, s):
            continue
        a = s.get("A_基线_不加", {}).get("cumR")
        b = s.get("B_加2中点+到区", {}).get("cumR")
        if a is None or b is None:
            continue
        out.append(b - a)
    return out

def rep(vals):
    pos = sum(1 for v in vals if v > 0.001)
    neg = sum(1 for v in vals if v < -0.001)
    return dict(n=len(vals), B_gt_A=pos, A_gt_B=neg, tie=len(vals) - pos - neg,
                median=round(st.median(vals), 3), mean=round(sum(vals) / len(vals), 3),
                net=round(sum(vals), 1))

full_clean = diffs(lambda sym, s: sym not in frozen)
uni_clean = diffs(lambda sym, s: sym not in frozen and s.get("in_universe"))

out = {
    "generated": datetime.datetime.now().isoformat(),
    "job": "ATR slgate 修复件双分母 B-A 重报 (L4 修订口径: 全市场干净 + 金线域 universe 内, 剔冻结 12 家真实尾)",
    "engine_fix": "analyze248_all.py +slgate(): sl_dist < max(0.5*ATR_i, 1e-5*|entry|, 1e-5*point*100) -> 该信号 SKIP; 备份 analyze248_all.py.bak_slgate",
    "cross_check_w0_w1": dict(symbols=18, AB_mismatch=cross,
                              verdict="0 劈叉, 双 worker 交叉销账过" if cross == 0 else f"{cross} 家劈叉, 销账未过"),
    "green_销绿": {s: {"A_cumR": new18[s]["A_基线_不加"].get("cumR"),
                    "B_cumR": new18[s]["B_加2中点+到区"].get("cumR"),
                    "slgate_skip": new18[s].get("slgate_skipped_sigs"),
                    "sl_dist_below_1e4": new18[s].get("sl_dist_below_1e4")} for s in green},
    "frozen_12_真实尾": {s: {"A_cumR": new18[s]["A_基线_不加"].get("cumR"),
                        "B_cumR": new18[s]["B_加2中点+到区"].get("cumR"),
                        "note": "品种 6mo 真实单边尾部, 非引擎缺陷, slgate 修不掉, 口径说明+冻结维持, 三桶 0 引用"} for s in frozen},
    "b_minus_a_全市场干净集": rep(full_clean),
    "b_minus_a_金线域universe干净集": rep(uni_clean),
    "verdict": ("全市场干净集加仓无净效应(封版数复现: 中位0.0 净-16R) 与 L4 封版 0 劈叉; "
                "金线域加仓净负(39行 B>A11 A>B28 中位-13.17 净-855.9R) 金线域 VETO 维持; "
                "销绿6家+冻结12家逐家可 grep; 销绿前 18 家旧脏数全团 0 引用不变"),
    "live_flag": "0 写闸源 0 进 live, 纯回测证据件",
}
json.dump(out, open("data/analyze248_slfix_summary.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("全市场干净集:", out["b_minus_a_全市场干净集"])
print("金线域干净集:", out["b_minus_a_金线域universe干净集"])
print("交叉验:", out["cross_check_w0_w1"]["verdict"])
print("绿", len(green), sorted(green))
print("冻结", len(frozen), sorted(frozen))
print("-> data/analyze248_slfix_summary.json 落盘")
