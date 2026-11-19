# -*- coding: utf-8 -*-
"""读 10-07 22:04 研判文件 + market_judges + auto_cycle 调用链, 判回退方案是否成立"""
import json, glob, os, datetime

D = r"E:\GoldstrategyEngine\data"

print("=== 1. 各 daily_advisory 文件的生成时刻(看命名日期 vs 实际生成时刻语义) ===")
for p in sorted(glob.glob(D + "/daily_advisory_*.json")):
    mt = datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%m-%d %H:%M")
    d = json.load(open(p, encoding="utf-8"))
    secs = d.get("sections") or []
    n = sum(len(s.get("items", [])) for s in secs)
    sesss = [s.get("session") or s.get("name") for s in secs]
    print(f"{os.path.basename(p)} | mtime {mt} | items={n} | sections={sesss}")

print("\n=== 2. 最新研判(10-07 22:04)的 items 明细(前 25 条: sym/session/direction/setup/price/target/stop/conf/status) ===")
d = json.load(open(D + "/daily_advisory_20261007.json", encoding="utf-8"))
for s in d.get("sections", []):
    print("section:", s.get("session") or s.get("name"), "| 头部字段:", {k: v for k, v in s.items() if k != "items"})
    for it in (s.get("items") or [])[:25]:
        print("  ", {k: it.get(k) for k in ("sym", "direction", "setup", "price", "target", "stop", "confidence", "status", "grade")})

print("\n=== 3. 文件自带的时间戳字段(判价格新鲜度口径) ===")
print({k: v for k, v in d.items() if k != "sections"})

print("\n=== 4. auto_cycle 里候选生成挂在哪步 + 研判生成挂在哪步 ===")
import re
ac = open(r"E:\GoldstrategyEngine\data\auto_cycle.py", encoding="utf-8", errors="ignore").read() if os.path.exists(r"E:\GoldstrategyEngine\data\auto_cycle.py") else ""
if not ac:
    # 找 auto_cycle 主脚本
    for cand in glob.glob(r"E:\GoldstrategyEngine\*.py") + glob.glob(r"E:\GoldstrategyEngine\multi_agent\*.py"):
        if "auto_cycle" in os.path.basename(cand) or "auto_cycle" in open(cand, encoding="utf-8", errors="ignore").read()[:500]:
            ac = open(cand, encoding="utf-8", errors="ignore").read()
            print("(读到:", cand, ")")
            break
for m in re.finditer(r".*(discretion|advisory|研判|候选).*", ac):
    ln = m.group(0).strip()
    if len(ln) < 200 and not ln.startswith("#"):
        print("  ", ln)

print("\n=== 5. market_judges.json 是否当日活快照 ===")
mj = json.load(open(D + "/market_judges.json", encoding="utf-8"))
print("ts:", mj.get("ts") or mj.get("date"), "| n_bias_bull:", mj.get("n_bias_bull"), "| n_bias_bear:", mj.get("n_bias_bear"), "| judges:", len(mj.get("judges", [])))
