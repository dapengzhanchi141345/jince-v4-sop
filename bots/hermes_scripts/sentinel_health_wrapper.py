# -*- coding: utf-8 -*-
"""sentinel_health_wrapper.py — 执行哨体检30min哨 cron 包装器(静默=正常)"""
import subprocess, sys, os, datetime

ENV = dict(os.environ, PYTHONIOENCODING="utf-8")


def main():
    p = subprocess.run([r"D:/workbuddy/binaries/python/versions/3.13.12/python.exe",
                        "E:/GoldstrategyEngine/jince_sentinel_health.py"],
                       capture_output=True, text=True, timeout=300, env=ENV,
                       cwd=r"E:/GoldstrategyEngine")
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    if p.returncode == 0:
        if out:
            print(out)
    else:
        ts = datetime.datetime.now().strftime("%m-%d %H:%M")
        print(f"[哨体检故障] rc={p.returncode} {ts}\n{out}\n{err[-500:]}")


if __name__ == "__main__":
    main()
