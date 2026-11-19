"""SD BE 保本锁利哨 cron 薄壳 (no_agent, 每5min, live)
无动作时输出为空 -> watchdog 静默; 有 SL 提保本 -> 报一条."""
import os, subprocess, sys

ATE = r"D:\workbuddy\binaries\python\versions\3.13.12\python.exe"
r = subprocess.run([ATE, "-u", r"E:\GoldstrategyEngine\research\sd_be_guard.py", "--live"],
                   capture_output=True, timeout=180,
                   env={k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH")})
out = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
out = out.strip()
if "Traceback" in out:
    print("be_guard 异常:\n" + out[-1200:])
    sys.exit(1)
if out:
    print("金策模拟户 BE锁利: " + out.replace("\n", " | "))
sys.exit(0)
