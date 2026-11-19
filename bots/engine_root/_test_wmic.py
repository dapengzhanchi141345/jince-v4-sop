# -*- coding: utf-8 -*-
import subprocess
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, creationflags=NO_WINDOW, timeout=40)
        return r.returncode, (r.stdout or b"").decode("utf-8", "replace")
    except Exception as e:
        return -1, str(e)

# wmic
rc, out = run(["wmic", "process", "where", "name='pythonw.exe'", "get", "ProcessId,CommandLine"])
print("=== wmic rc=%s len=%s ===" % (rc, len(out)))
# print lines that mention runner/auto_run/watchdog
for line in out.splitlines():
    if "runner.py" in line or "auto_run_cycle" in line or "jince_watchdog" in line or "hermes.exe serve" in line:
        print("  >>", line.strip()[:160])
print("  (total wmic lines:", len(out.splitlines()), ")")
