# -*- coding: utf-8 -*-
r"""金策·执行预检日检包装 (07:30 cron, 确定性 0LLM)
BUGFIX 11-14(李彦明"测试数据是否有效"实锤): 原 cron 直接跑 jince_exec_preflight.py 自检,
从不跑 --fetch -> fixture 快照会过期, 自检在旧价/旧规格上跑, 72h 后天天误报。
本包装: ① ATE python 实读刷新 fixture(含实读价快照 bid_now) ② 再跑自检(自带数据有效性闸)。
任一阶段失败=非零退出=cron 报错投递, 绝不静默。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PRE = os.path.join(HERE, "jince_exec_preflight.py")
ATE = r"C:\Users\ASUS\.workbuddy\binaries\python\envs\ate\Scripts\python.exe"

# [11-15 修] cron 包装器 PYTHONPATH 污染 ATE 子进程实证(07:30拍 exit3): hermes installs venv 的 3.14 版 numpy 被 3.13 ATE 的 MetaTrader5 捡到, 编译库不兼容炸 multiarray. 与 MFE 包装同法: spawn 前剥干净 Python 环境变量, ATE 走自家 site-packages
_env_clean = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE", "VIRTUAL_ENV")}
r = subprocess.run([ATE, PRE, "--fetch"], capture_output=True, text=True, timeout=240, env=_env_clean)
out1 = (r.stdout or "") + (r.stderr or "")
if r.returncode != 0:
    print("[PREFLIGHT-DAILY] FAIL: ATE --fetch 未过(MT5 终端未起/断网/缺模块):")
    print(out1[-2000:])
    sys.exit(3)
print("[PREFLIGHT-DAILY] ① 实读刷新 OK:\n" + out1.strip())

rc = subprocess.run([sys.executable, PRE]).returncode
if rc == 0:
    print("[PREFLIGHT-DAILY] ② 自检全绿(结果存 exec_preflight_selftest.json, 静默=正常)")
else:
    print("[PREFLIGHT-DAILY] FAIL: 自检未过 exit=%d, 明细见 E:\\GoldstrategyEngine\\data\\exec_preflight_selftest.json" % rc)
sys.exit(0 if rc == 0 else rc)
