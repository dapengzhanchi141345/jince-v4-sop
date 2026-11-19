#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""金策·验尸进化哨 runner 副本 (11-17 防再犯修复): hermes cron runner 的 venv 无 MetaTrader5,
本副本只启动 ATE python 执行 research 目录的真脚本, exit/stdout 直通。
单一事实源 = E:/GoldstrategyEngine/research/sd_evolution_postmortem.py (勿在此处改逻辑)。
根因留痕: 11-17 02:31 runner 用 environments/<hash>/venv 跑本文件 -> import MetaTrader5 崩 (ModuleNotFoundError);
本哨 04:34 补跑 ok (gate=PASS) 后落此修复, 防每晚 02:30 复发。"""
import os, subprocess, sys

ATE = r"D:\workbuddy\binaries\python\versions\3.13.12\python.exe"
IMPL = r"E:\GoldstrategyEngine\research\sd_evolution_postmortem.py"
ENV = {k: v for k, v in os.environ.items()
       if k not in ("PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE", "VIRTUAL_ENV", "TMP", "TEMP", "TMPDIR")}
ENV.update({"TMP": r"E:\GoldstrategyEngine\scratch", "TEMP": r"E:\GoldstrategyEngine\scratch",
            "TMPDIR": r"E:\GoldstrategyEngine\scratch"})
os.makedirs(ENV["TMP"], exist_ok=True)
r = subprocess.run([ATE, "-u", IMPL] + sys.argv[1:], env=ENV)
sys.exit(r.returncode)
