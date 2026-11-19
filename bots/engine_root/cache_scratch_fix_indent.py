# -*- coding: utf-8 -*-
"""[L5 2026-11-04] 修 crypto_pending.py 函数体缩进 (splice 时 dedent 8 应为 dedent 4, 末两行掉到模块级):
   把 _run_obs_exception_legs 函数体 (def 行之后到 'return n_placed, n_failed' 之前) 整体 +4 空格."""
import re

p = "multi_agent/trading/crypto_pending.py"
lines = open(p, encoding="utf-8").read().split("\n")

# 找 def 行与函数体边界
i_def = next(i for i, ln in enumerate(lines) if ln.startswith("def _run_obs_exception_legs"))
i_ret = next(i for i, ln in enumerate(lines) if "return n_placed, n_failed" in ln and i > i_def)
# 函数体 = def 之后 (含 docstring/import/计数行) 到 return 之前
body = lines[i_def + 1:i_ret]
fixed = []
for ln in body:
    if ln.strip() == "":
        fixed.append(ln)
    else:
        fixed.append("    " + ln)
lines[i_def + 1:i_ret] = fixed
open(p, "w", encoding="utf-8", newline="").write("\n".join(lines))
print("re-indented %d lines (def@%d, ret@%d)" % (len(fixed), i_def + 1, i_ret))
