# -*- coding: utf-8 -*-
"""jince_param_officer_wrapper.py — 参数官30min哨 cron 包装器(静默=正常, 异常/里程碑出声)"""
import subprocess, sys, os, datetime

ENV = dict(os.environ, PYTHONIOENCODING="utf-8")


def main():
    p = subprocess.run(["D:/jince_sass/.venv/Scripts/python.exe", "E:/GoldstrategyEngine/jince_param_officer.py"],
                       capture_output=True, text=True, timeout=120, env=ENV,
                       cwd=r"E:/GoldstrategyEngine")
    # watchdog: stdout 原样交付(异常才非空), stderr 非空=故障也要出声
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    if p.returncode == 0:
        if out:
            print(out)
        # 静默=参数全一致且无新工单
    else:
        ts = datetime.datetime.now().strftime("%m-%d %H:%M")
        print(f"[参数官哨故障] rc={p.returncode} {ts}\n{out}\n{err[-500:]}")


if __name__ == "__main__":
    main()
