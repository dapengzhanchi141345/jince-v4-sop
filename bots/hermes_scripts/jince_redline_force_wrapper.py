# -*- coding: utf-8 -*-
"""jince_redline_force_wrapper.py — 12h红线处置(通用FORCE版) cron 包装器"""
import subprocess, os, datetime
def main():
    env = dict(os.environ, PYTHONIOENCODING="utf-8", JINCE_REDLINE_FORCE="1")
    p = subprocess.run([r"D:/workbuddy/binaries/python/versions/3.13.12/python.exe",
                        "E:/GoldstrategyEngine/jince_redline_handle_1118.py"],
                       capture_output=True, text=True, timeout=300, env=env,
                       cwd=r"E:/GoldstrategyEngine")
    out = (p.stdout or "").strip(); err = (p.stderr or "").strip()
    print(out if out else f"[红线哨故障 rc={p.returncode}] {err[-400:]}")
if __name__ == "__main__":
    main()
