# 11-07 03:50 专用: 平掉 magic 20261104 全部未平仓(12h禁隔夜红线)
import subprocess, sys, os, json
PY = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe"
env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "PYTHONNOUSERSITE")}
r = subprocess.run([PY, r"E:/workbuddy/国外模型/hermes/scripts/jince_ate_close.py",
                   "--magic", "20261104", "--tag", "lxclean_1107_0350"],
                  env=env, capture_output=True, text=True, timeout=300)
print(r.stdout[-2000:])
if r.stderr: print("STDERR:", r.stderr[-800:])
sys.exit(0 if r.returncode == 0 else 1)
