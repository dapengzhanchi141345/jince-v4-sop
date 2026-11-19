# -*- coding: utf-8 -*-
r"""币系茶歇12h红线 close_obs 哨外层 (hermes cron no-agent, 系统python): 调 ATE 环境跑内层,
stdout 直投群。失败 exit 1 = 红报。"""
import subprocess, os, sys

ATE = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe"
INNER = r"E:/workbuddy/国外模型/hermes/scripts/close_obs_tea_1115_inner.py"

env = {k: v for k, v in os.environ.items()
       if k not in ("PYTHONPATH", "PYTHONHOME", "PYTHONNOUSERSITE")}
try:
    r = subprocess.run([ATE, INNER], capture_output=True, text=True,
                       timeout=180, env=env)
except Exception as ex:
    print("RED: close_obs哨调用失败(子进程异常): %r, 需人工跟进12h红线" % ex)
    sys.exit(1)
out = (r.stdout or "").strip()
err = (r.stderr or "").strip()
if out:
    print(out)
if err:
    print("[stderr] " + err)
if r.returncode != 0:
    print("RED: close_obs哨内层rc=%d, 12h红线处置未闭环, 需跟进" % r.returncode)
    sys.exit(1)
