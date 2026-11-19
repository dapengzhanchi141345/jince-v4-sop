#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策宗师团 · MT5 模块安全启动器 (根治 PYTHONPATH 污染坑, 2026-09-28)
=====================================================================
背景: Hermes 的 terminal 工具会把 Hermes 自身 venv 的 site-packages
(numpy 2.4.6, cp311 编译件) 注入子进程的 PYTHONPATH。ate env 是 Python 3.13,
那个坏 numpy 会遮蔽 ate env 里装好的 numpy → MetaTrader5 import 报
`numpy._core.multiarray failed to import`, 看着像 ate env 坏了, 实际是 PATH 污染。

根治: 本脚本在 launch 前先 os.environ.pop 掉 PYTHONPATH/PYTHONHOME,
再 sys.execv 调 ate python。所有需要 MT5 的 L0 模块统一从这里进,
不必每次手动 `env -u PYTHONPATH`。

用法:
  python mt5_launch.py multi_agent/trading/daily_advisory.py --session all
  python mt5_launch.py auto_run_cycle.py
  python mt5_launch.py -c "import MetaTrader5 as m; print(m.initialize())"

注意: 交易循环宿主是 Windows 计划任务 JinCeAutoCycle (跑 auto_run_cycle.py),
它本身在干净环境里跑、不受 Hermes 污染, 不需要经此脚本; 本脚本服务的是
Hermes 会话内手动触发的 MT5 命令 (总调度/chief 按需拉行情/研判)。
"""
import os
import sys

ATE_PY = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/pythonw.exe"

def main():
    # 根治: 剥掉 Hermes 注入的坏 PYTHONPATH/PYTHONHOME
    os.environ.pop("PYTHONPATH", None)
    os.environ.pop("PYTHONHOME", None)
    argv = sys.argv[1:]
    if not argv:
        print("用法: python mt5_launch.py <模块|脚本> [args...]  或  -c \"code\"")
        sys.exit(1)
    # 用当前解释器(ATe python)以同一行参启动, 但带清洗后的环境
    # Windows 上 os.execve 不可靠, 直接 execv 同进程重入:
    # 因为本脚本就是用 ate python 跑的, 清洗完环境后直接 exec 自身逻辑
    # —— 改用 spawn 同参再跑一次, 环境变量已剥净
    import subprocess
    args = [sys.executable, "-c", sys.argv[2]] if sys.argv[1] == "-c" else [sys.executable, sys.argv[1]] + sys.argv[2:]
    r = subprocess.run(args, env=os.environ)
    sys.exit(r.returncode)

if __name__ == "__main__":
    main()
