# -*- coding: utf-8 -*-
"""auto_soul_exit_watch_1119.py — 10min出场反馈哨 cron 包装器"""
import subprocess, os

# 11-19故障补跑哨修: 子进程 env 剥离 cron runner 注入的 python 环境变量
# (PYTHONHOME/PYTHONPATH 指向外层运行时会打崩 3.13.12 的 numpy C 扩展:
#  numpy._core.multiarray failed to import; 干净 env 下 import numpy+MT5 已实测全绿)
_STRIP = ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONUSERBASE",
          "VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV", "__PYVENV_LAUNCHER__")
_env = {k: v for k, v in os.environ.items() if k not in _STRIP}
_env["PYTHONIOENCODING"] = "utf-8"

p = subprocess.run([r"D:/workbuddy/binaries/python/versions/3.13.12/python.exe",
                    r"E:/GoldstrategyEngine/research/auto_soul_exit_watch_1119.py"],
                   capture_output=True, text=True, timeout=420,
                   cwd=r"E:/GoldstrategyEngine", env=_env)
out = (p.stdout or "").strip()
if out:
    print(out)
if p.returncode != 0:
    print(f"[出场哨故障 rc={p.returncode}] {(p.stderr or '').strip()[-300:]}")
    raise SystemExit(1)
