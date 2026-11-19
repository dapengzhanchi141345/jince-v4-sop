#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策 11-06 03:55 兜底强平 (ATE 通道版, 2026-11-05 22:5x 重写)。
美股批推迟到 11-06 22:20 挂 -> 11-06 03:55 时 20261105 无隔夜仓(预期静默); 若有则平 (双保险)。
"""
import subprocess, sys
import os
# 11-07 保护: 非 ATE venv 执行时自动重跑(ATE python 有 MetaTrader5, hermes runner venv numpy 裂)
ATE_PY = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe"
if ATE_PY not in os.path.abspath(sys.executable):
    import subprocess as _sp
    _env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH","PYTHONHOME","PYTHONNOUSERSITE")}
    sys.exit(_sp.run([ATE_PY, os.path.abspath(__file__)] + sys.argv[1:], env=_env).returncode)

ATE = r"C:\Users\ASUS\.workbuddy\binaries\python\envs\ate\Scripts\python.exe"
CLOSE = r"E:\workbuddy\国外模型\hermes\scripts\jince_ate_close.py"
r = subprocess.run([ATE, CLOSE, "--magic", "20261105", "--tag", "usbatch-1106am"], capture_output=True, text=True, timeout=120)
print(r.stdout.strip() or "(静默: 无 20261105 仓, 无动作)")
if r.returncode != 0:
    print("ATE close 异常:", r.stderr.strip()[:300])
    sys.exit(1)
