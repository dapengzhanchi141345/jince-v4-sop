# -*- coding: utf-8 -*-
"""auto_wave_soul_1119.py — 灵魂门自动开仓 cron 包装器 (21:35 one-shot)
委托 E:/GoldstrategyEngine/scripts/exec_wave/auto_wave_soul_1119.py (3.13 解释器).
有开仓=逐行报; 0信号=静默(仅写台账不留声, 防刷屏).
"""
import subprocess, os, datetime
def main():
    p = subprocess.run([r"D:/workbuddy/binaries/python/versions/3.13.12/python.exe",
                        r"E:/GoldstrategyEngine/scripts/exec_wave/auto_wave_soul_1119.py"],
                       capture_output=True, text=True, timeout=300,
                       cwd=r"E:/GoldstrategyEngine",
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    out = (p.stdout or "").strip()
    if "DONE: 0/" in out or "0 信号" in out:
        return  # 无开仓=静默
    print(out or f"[soulwave故障 rc={p.returncode}] {(p.stderr or '').strip()[-300:]}")
    if p.returncode != 0:
        raise SystemExit(1)
if __name__ == "__main__":
    main()
