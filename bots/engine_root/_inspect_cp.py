
import sys; sys.path.insert(0,"E:/GoldstrategyEngine"); sys.path.insert(0,"E:/GoldstrategyEngine/multi_agent/trading")
# 先确认 analyze_symbol 趋势腿 SL 位置与 run_cycle 里可用的 df 结构
import crypto_pending as cp, inspect
src = inspect.getsource(cp.analyze_symbol)
print("=== 趋势腿 SL 段 ===")
for ln in src.splitlines():
    if "trig - 2.0 * a" in ln or "trig + 2.0 * a" in ln or "dc_hi[i - 1] > 0 and px_bid" in ln:
        print(ln)
