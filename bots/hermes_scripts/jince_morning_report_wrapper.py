# -*- coding: utf-8 -*-
"""jince_morning_report_wrapper.py — 晨间战报 cron 包装器"""
import subprocess, os, datetime
def main():
    p = subprocess.run([r"D:/jince_sass/.venv/Scripts/python.exe",
                        "E:/GoldstrategyEngine/jince_morning_report.py"],
                       capture_output=True, text=True, timeout=300,
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"), cwd=r"E:/GoldstrategyEngine")
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    print(out if out else f"[晨报故障 rc={p.returncode}] {err[-400:]}")
if __name__ == "__main__":
    main()
