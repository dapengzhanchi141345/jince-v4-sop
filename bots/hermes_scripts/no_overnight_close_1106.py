#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策 11-06 22:20 兜底强平 (ATE 通道版, 2026-11-05 22:5x 重写, 废 MetaTrader5 直 import 地雷)。
平 magic=20261105 全部未平仓 (预期: 美股批 22:20 才挂 -> 本哨静默; 若有提前开的仓则平)。
"""
import subprocess, sys, time
import os
# 11-07 保护: 非 ATE venv 执行时自动重跑(ATE python 有 MetaTrader5, hermes runner venv numpy 裂)
ATE_PY = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe"
if ATE_PY not in os.path.abspath(sys.executable):
    import subprocess as _sp
    _env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH","PYTHONHOME","PYTHONNOUSERSITE")}
    sys.exit(_sp.run([ATE_PY, os.path.abspath(__file__)] + sys.argv[1:], env=_env).returncode)

ATE = r"C:\Users\ASUS\.workbuddy\binaries\python\envs\ate\Scripts\python.exe"
CLOSE = r"E:\workbuddy\国外模型\hermes\scripts\jince_ate_close.py"
# 60s 错峰: 22:20 美股批挂单先落地, 哨兵再扫尾强平, 避免同刻快照漏掉刚成交的仓 (CR-1106-强平优化①)
# 注意: time.sleep(60) 在父进程计时; subprocess timeout=180 只约束子进程自身, 两者独立 (审核修正)
time.sleep(60)
r = subprocess.run([ATE, CLOSE, "--magic", "20261105", "--tag", "usbatch-1106"], capture_output=True, text=True, timeout=180)
print(r.stdout.strip() or "(静默: 无 20261105 仓, 无动作)")
if r.returncode != 0:
    print("ATE close 异常:", r.stderr.strip()[:300])
    sys.exit(1)
