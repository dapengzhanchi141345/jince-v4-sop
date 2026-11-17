# -*- coding: utf-8 -*-
"""slv2_sol_1117_wrapper.py — SOL赚钱格哨 cron 包装器(21:00/21:30 BJT)"""
import subprocess, sys, datetime, os

ENV = dict(os.environ, PYTHONIOENCODING="utf-8")
LOG = r"E:/GoldstrategyEngine/data/sl_sensors"


def main():
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    out = os.path.join(LOG, f"slv2_sol_{ts}.log")
    os.makedirs(LOG, exist_ok=True)
    p = subprocess.run(["D:/jince_sass/.venv/Scripts/python.exe", "E:/GoldstrategyEngine/slv2_sol_market_in_1117.py"],
                       capture_output=True, text=True, timeout=300, env=ENV,
                       cwd=r"E:/GoldstrategyEngine")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# slv2-sol-wrapper rc={p.returncode} {datetime.datetime.now().isoformat()}\n"
                f"--- stdout ---\n{p.stdout}\n--- stderr ---\n{p.stderr}")
    print(f"wrapper rc={p.returncode} log={out}")


if __name__ == "__main__":
    main()
