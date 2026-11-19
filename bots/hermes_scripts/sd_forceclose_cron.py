"""金策 SD 12h 强平哨 cron 包装 (live 模式, 30min 循环用)
无持仓时哨输出为空 -> watchdog 静默; 有超12h持仓 -> 市价强平+报数."""
import os, subprocess, sys

os.environ["SD_FORCE_LIVE"] = "1"
r = subprocess.run([sys.executable, r"E:\workbuddy\国外模型\hermes\scripts\sd_e3s1_12h_forceclose.py"],
                   capture_output=True, timeout=300)
out = (r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")).strip()
if "Traceback" in out:
    print("forceclose 哨异常:\n" + out[-1500:])
    sys.exit(1)
if out:
    print(out)  # 有持仓/有强平才报
sys.exit(0)
