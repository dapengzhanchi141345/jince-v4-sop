# -*- coding: utf-8 -*-
"""实跑候选生成器(回退逻辑)并验产物: 编译+运行+验 advisory_source/候选/币系0误放"""
import py_compile, subprocess, sys, json, collections

D = r"E:\GoldstrategyEngine\data"
P = D + r"\discretion_candidate.py"

py_compile.compile(P, doraise=True)
print("[1] 编译 OK")

r = subprocess.run([sys.executable, P], capture_output=True, text=True, timeout=180)
print("[2] 实跑 rc =", r.returncode)
print(r.stdout[-2500:] if r.stdout else "(无 stdout)")
if r.stderr:
    print("stderr:", r.stderr[-500:])

d = json.load(open(D + r"\discretion_candidates.json", encoding="utf-8"))
print("[3] 产物验:")
print("  advisory_source:", d.get("advisory_source"))
print("  stale_note:", str(d.get("stale_note"))[:120])
print("  candidates:", len(d.get("candidates", [])))
print("  watch:", len(d.get("watch", [])))
veto = d.get("vetoed", [])
print("  vetoed:", len(veto), dict(collections.Counter(x["why"] for x in veto)))
crypto_pfx = ("BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LTC", "BCH", "DOT", "XLM",
              "KSM", "TAO", "XTZ", "UNI", "POL", "GLM", "AVX", "CMP", "LNK", "CHC", "TRUMP")
bad = [x for x in d.get("candidates", []) if x["sym"].upper().startswith(crypto_pfx)]
print("  币系误放进候选:", len(bad), [x["sym"] for x in bad])
for c in d.get("candidates", [])[:8]:
    print("   [候选]", c["sym"], c["dir"], c["session"], c["setup"], "RR=%.2f" % (c.get("rr") or 0), c["status"])
