# hermes runner 薄壳: subprocess 调 ATE 查 trade_mode, OK 则调 ATE 四步下单
import subprocess, os, sys
ATE = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "PYTHONNOUSERSITE")}
r = subprocess.run([ATE, os.path.join(HERE, "trade_mode_check_ate.py")], env=env,
                   capture_output=True, text=True, timeout=120)
out = r.stdout.strip()
print(out)
if "TRADE_MODE_OK" in out:
    print("→ trade_mode 已放开, 执行四步下单(重读盘重判)")
    r2 = subprocess.run([ATE, os.path.join(HERE, "usbatch_4step_open_1106.py")], env=env,
                        capture_output=True, text=True, timeout=300)
    print(r2.stdout[-3000:])
    if r2.returncode != 0:
        print("STDERR:", r2.stderr[-500:])
    sys.exit(r2.returncode)
else:
    print("→ 仍 close-only, 顺延 11-07 22:20 批(四步判断已留痕, 03:55 哨兜底)")
    sys.exit(0)
