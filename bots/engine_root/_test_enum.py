# -*- coding: utf-8 -*-
import subprocess, ctypes, sys

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

def enum_powershell_text():
    try:
        o = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | ForEach-Object { ($_.ProcessId.ToString())+[char]9+($_.CommandLine) }"],
            capture_output=True, text=True, creationflags=NO_WINDOW, timeout=30)
        return ("text", o.returncode, len(o.stdout), o.stdout[:200])
    except Exception as e:
        return ("text-ERR", str(e)[:200], None, None)

def enum_powershell_bytes():
    try:
        o = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | ForEach-Object { ($_.ProcessId.ToString())+[char]9+($_.CommandLine) }"],
            capture_output=True, creationflags=NO_WINDOW, timeout=30)
        txt = o.stdout.decode("utf-8", "replace")
        return ("bytes", o.returncode, len(txt), txt[:200])
    except Exception as e:
        return ("bytes-ERR", str(e)[:200], None, None)

def enum_powershell_utf8():
    try:
        env = dict(__import__("os").environ)
        env["PYTHONIOENCODING"] = "utf-8"
        o = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$OutputEncoding=[System.Text.Encoding]::UTF8; [Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
             "Get-CimInstance Win32_Process | ForEach-Object { ($_.ProcessId.ToString())+[char]9+($_.CommandLine) }"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=NO_WINDOW, timeout=30, env=env)
        return ("utf8", o.returncode, len(o.stdout), o.stdout[:200])
    except Exception as e:
        return ("utf8-ERR", str(e)[:200], None, None)

for fn in (enum_powershell_text, enum_powershell_bytes, enum_powershell_utf8):
    name, rc, n, head = fn()
    print(f"=== {name} rc={rc} len={n} ===")
    print(repr(head))
    print()
