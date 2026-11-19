# run_chunk.py — 分块运行全宇宙回测 (独立进程, 内存隔离, 增量续跑)
# 用法: python run_chunk.py <start> <end>
import sys
import symbol_universe as su
import universe_backtest as ub

syms = list(su.UNIVERSE.keys())
a = int(sys.argv[1]); b = int(sys.argv[2])
risk = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
ub.run(symbols=syms[a:b], allow_mt5=False, account=True, risk_pct=risk)
