# -*- coding: utf-8 -*-
import sys, importlib.util
spec = importlib.util.spec_from_file_location("bg", r"E:\GoldstrategyEngine\boot_guardian.py")
bg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bg)

print("=== enum_all_cmdlines() count ===")
rows = bg.enum_all_cmdlines()
print("rows:", len(rows))
hits = [cl for pid, cl in rows if "runner.py" in cl or "auto_run_cycle" in cl or "hermes.exe serve" in cl or "jince_watchdog" in cl]
print("relevant cmdlines found:", len(hits))
for cl in hits[:10]:
    print("  >>", cl[:160])
print()
print("proc_alive runner.py/--equity:", bg.proc_alive(["runner.py", "--equity"]))
print("proc_alive auto_run_cycle.py:", bg.proc_alive(["auto_run_cycle.py"]))
print("proc_alive hermes.exe/serve:", bg.proc_alive(["hermes.exe", "serve"]))
print("proc_alive jince_watchdog.py:", bg.proc_alive(["jince_watchdog.py"]))
print("count runner.py/--equity:", bg.count_procs(["runner.py", "--equity"]))
