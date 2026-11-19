# -*- coding: utf-8 -*-
"""order_xp_daily_1119.py — 每日XP日报 cron 包装器 (20:15)"""
import subprocess, os

# 11-19故障补跑哨修: 子进程 env 剥离 cron runner 注入的 python 环境变量
# (PYTHONHOME/PYTHONPATH 指向外层运行时会打崩 3.13.12 的 numpy C 扩展:
#  numpy._core.multiarray failed to import; 干净 env 下 import numpy+MT5 已实测全绿)
_STRIP = ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONUSERBASE",
          "VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV", "__PYVENV_LAUNCHER__")
_env = {k: v for k, v in os.environ.items() if k not in _STRIP}
_env["PYTHONIOENCODING"] = "utf-8"

p = subprocess.run([r"D:/workbuddy/binaries/python/versions/3.13.12/python.exe",
                    r"E:/GoldstrategyEngine/research/order_xp_1119.py", "--daily"],
                   capture_output=True, text=True, timeout=300,
                   cwd=r"E:/GoldstrategyEngine", env=_env)
out = (p.stdout or "").strip()
if out:
    print(out)
if p.returncode != 0:
    print(f"[XP日报故障 rc={p.returncode}] {(p.stderr or '').strip()[-300:]}")
    raise SystemExit(1)
