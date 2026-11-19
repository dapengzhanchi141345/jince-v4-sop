#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策日结·家族盈亏汇总（no_agent 20:00，免 LLM 免 429 影响）。

读 family_pnl_ledger.jsonl 全部行，按家族聚合今日 R/pnl，
判定升降档（累计 R<-2 且 n>=3 降档观察 / >+3 且 n>=3 升档），
输出大白话简报（有家族数据才出声，空账本静默）。
"""
import os
os.environ["PYTHONIOENCODING"] = "utf-8"
import sys, io, json, time
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

LEDGER = "E:/GoldstrategyEngine/data/family_pnl_ledger.jsonl"

def main():
    if not os.path.exists(LEDGER):
        return 0  # 空账本静默
    rows = []
    bad = []
    with open(LEDGER, encoding="utf-8") as f:
        for i, ln in enumerate(f, 1):
            ln = ln.strip()
            if ln:
                try:
                    rows.append(json.loads(ln))
                except Exception as e:
                    # [11-17 加固] 坏行不再崩整job: 跳过+显式报(stderr), 数据有效性闸铁律=缺/坏显式禁静默
                    bad.append((i, str(e)[:60]))
    if bad:
        for i, e in bad:
            sys.stderr.write("WARN 台账坏行%d跳过(显式报): %s\n" % (i, e))
    today = time.strftime("%Y-%m-%d")
    fam = defaultdict(lambda: {"pnl": 0.0, "n": 0, "open": 0, "pending": 0})
    for r in rows:
        # [2026-11-05 双进程共写事故后] 只认 owner=hermes 的行（LX/WRCH 的持仓登记行 date/position_id 无 pnl，混入会串账）
        if r.get("owner") and r.get("owner") != "hermes":
            continue
        d = str(r.get("ts", r.get("date", "")))[:10]
        if d != today:
            continue
        f = fam[r.get("family", "?")]
        f["pnl"] += float(r.get("pnl_usd") or 0.0)
        if r.get("type") == "open":
            f["open"] += 1
        elif r.get("type") == "pending":
            f["pending"] += 1
        elif r.get("type") == "close":
            f["n"] += 1
    if not fam:
        return 0
    out = [f"[家族盈亏 {today}]"]
    for name, f in sorted(fam.items(), key=lambda kv: -kv[1]["pnl"]):
        flag = ""
        if f["n"] >= 3 and f["pnl"] < -2:
            flag = " [降档观察:下批减半只打TOP]"
        if f["n"] >= 3 and f["pnl"] > 3:
            flag = " [升档:可加1档手数]"
        out.append(f"  {name}: 今日实收 ${f['pnl']:+.2f} | 在仓 {f['open']} 张 | 挂单 {f['pending']} 张{flag}")
    total = sum(f["pnl"] for f in fam.values())
    out.append(f"  合计实收 ${total:+.2f} (未平仓浮盈另计)")
    print("\n".join(out))
    return 0

if __name__ == "__main__":
    sys.exit(main())
