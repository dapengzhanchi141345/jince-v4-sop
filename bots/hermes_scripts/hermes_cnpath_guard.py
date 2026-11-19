# -*- coding: utf-8 -*-
"""Hermes 桌面端 · 中文路径守护哨（watchdog 静默模式）
职责：
  1) E:\\hb junction(别名) 丢=自动重建;
  2) 两个 Hermes.lnk 若被改回中文路径=自动纠回 ASCII 别名;
  3) 全绿时 stdout 为空(不投递), 有干预才出一行。
物理树仍在 E:\\workbuddy\\国外模型\\hermes(中文), 别名 E:\\hb 走 ASCII。
"""
import os, subprocess, json, time
ALIAS = r"E:\hb"
REAL  = r"E:\workbuddy\国外模型\hermes"
DESK  = ALIAS + r"\hermes-agent\apps\desktop\release\win-unpacked"
LNKS = [
    r"C:\Users\Administrator\Desktop\Hermes.lnk",
    r"C:\Users\Administrator\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Hermes.lnk",
]
STATE = os.path.join(os.path.dirname(REAL), "ops", "hermes_cnpath", "guard_state.json")

def ps(cmd, t=45):
    try:
        return subprocess.run(["powershell","-NoProfile","-Command",cmd],
                              capture_output=True, text=True, encoding="gbk", errors="replace", timeout=t).stdout.strip()
    except Exception:
        return ""

def lnk_target(p):
    return ps("(New-Object -ComObject WScript.Shell).CreateShortcut('%s').TargetPath" % p)

def main():
    acts = []
    # 1) junction
    if not os.path.exists(ALIAS):
        out = ps('cmd /c mklink /J "%s" "%s"' % (ALIAS, REAL))
        acts.append("junction重建:" + (out[:60] or "ok"))
    # 2) lnk 纠偏
    for L in LNKS:
        if not os.path.exists(L):
            continue
        t = lnk_target(L)
        if not t.startswith(ALIAS):
            ps("(New-Object -ComObject WScript.Shell).CreateShortcut('%s') | ForEach-Object { $_.TargetPath='%s\\Hermes.exe'; $_.WorkingDirectory='%s'; $_.Save() }" % (L, DESK, DESK))
            acts.append("lnk纠回:%s" % os.path.basename(os.path.dirname(L)))
    # 3) 桌面 exe 可达性
    exe_ok = os.path.exists(DESK + r"\Hermes.exe")
    if acts or not exe_ok:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            os.makedirs(os.path.dirname(STATE), exist_ok=True)
            json.dump({"ts": ts, "actions": acts, "exe_ok": exe_ok, "alias": ALIAS, "real": REAL},
                      open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        except Exception:
            pass
        print("[hermes中文路径守护] " + ts + " | " + ("; ".join(acts) if acts else "无干预") + " | exe可达:" + str(exe_ok))
    # 全绿且无干预 → 什么都不打印(静默)

if __name__ == "__main__":
    main()
