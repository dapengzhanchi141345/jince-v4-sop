# 调度包装: 用 3.13.12 MT5 解释器跑 slv2 ETH 市价进场哨, stdout 原样投递
import subprocess, sys
r = subprocess.run([r"D:/workbuddy/binaries/python/versions/3.13.12/python.exe",
                    r"E:/GoldstrategyEngine/slv2_eth_market_in_1117.py"],
                   capture_output=True, text=True, timeout=180)
sys.stdout.write(r.stdout or "")
if r.stderr:
    sys.stdout.write("STDERR: " + r.stderr[-400:])
sys.stdout.write("\n[exit=%s]" % r.returncode)
