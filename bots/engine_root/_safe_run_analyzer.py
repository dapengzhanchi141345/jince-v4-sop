"""
安全运行器 —— live 交易活跃期间执行 technical_analyzer.py

MT5 铁律（2026-08-17 实测确立）：
  - mt5.initialize()  ✅ 安全：attach 到已登录 terminal64，不重启
  - mt5.shutdown()    🚫 禁忌：会断掉 live 共享连接

technical_analyzer.py 第 815 行有 mt5.shutdown()。
本运行器在导入阶段把 shutdown 置为 no-op，再以 __main__ 语义执行原脚本，
从而在不修改原文件的前提下保护 live 连接。
"""
import os
import runpy
import sys

import MetaTrader5 as mt5

_orig_shutdown = mt5.shutdown


def _noop_shutdown(*args, **kwargs):
    print("[safe-runner] mt5.shutdown() 已被拦截（live 交易活跃，保护共享连接）")
    return True


mt5.shutdown = _noop_shutdown

TARGET = r"E:\GoldstrategyEngine\technical_analyzer.py"
os.chdir(r"E:\GoldstrategyEngine")
sys.argv = [TARGET]

print("[safe-runner] 开始执行 technical_analyzer.py（shutdown 已置空）")
try:
    runpy.run_path(TARGET, run_name="__main__")
finally:
    print("[safe-runner] 执行结束，未调用真实 shutdown")
