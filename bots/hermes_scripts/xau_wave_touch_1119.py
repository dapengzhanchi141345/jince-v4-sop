# -*- coding: utf-8 -*-
"""xau_wave_touch_1119.py — 黄金触价开仓 cron 包装器 (22:00/23:30 one-shots)"""
import subprocess, os
def main():
    p = subprocess.run([r"D:/workbuddy/binaries/python/versions/3.13.12/python.exe",
                        r"E:/GoldstrategyEngine/scripts/exec_wave/xau_wave_touch_1119.py"],
                       capture_output=True, text=True, timeout=300,
                       cwd=r"E:/GoldstrategyEngine", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    out = (p.stdout or "").strip()
    if "未触价" in out or "已有黄金仓" in out:
        return  # 静默
    print(out or f"[xauwave故障 rc={p.returncode}] {(p.stderr or '').strip()[-300:]}")
    if p.returncode != 0:
        raise SystemExit(1)
if __name__ == "__main__":
    main()
