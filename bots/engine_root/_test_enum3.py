# -*- coding: utf-8 -*-
import subprocess, importlib.util
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SCRIPT = "Get-CimInstance Win32_Process | ForEach-Object { ($_.ProcessId.ToString())+[char]9+($_.CommandLine) }"

# A) known-working bytes call (from _test_enum.py)
r = subprocess.run(["powershell", "-NoProfile", "-Command", SCRIPT],
                  capture_output=True, creationflags=NO_WINDOW, timeout=30)
print("A) bytes: rc=%s stdout_len=%s stdout_is_None=%s" % (r.returncode, len(r.stdout) if r.stdout else 0, r.stdout is None))

# B) import module and use its run_ps
spec = importlib.util.spec_from_file_location("bg", r"E:\GoldstrategyEngine\boot_guardian.py")
bg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bg)
rc, out = bg.run_ps(SCRIPT)
print("B) run_ps: rc=%s out_len=%s out_is_None=%s" % (rc, len(out), out is None))
print("B) out head:", repr(out[:200]))
