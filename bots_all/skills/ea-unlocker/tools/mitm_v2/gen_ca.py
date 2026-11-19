#!/usr/bin/env python
"""MITM v2 套件一键 CA 生成
openssl 生成 ca.crt/ca.key(3650天) → import_ca.bat(用户级,无需管理员)
产物: tools/mitm_v2/ca/ca.crt, ca/key, import_ca.bat
"""
import os, subprocess, sys, stat

BASE = os.path.dirname(os.path.abspath(__file__))
CA_DIR = os.path.join(BASE, "ca")
CRT = os.path.join(CA_DIR, "ca.crt")
KEY = os.path.join(CA_DIR, "ca.key")

def main():
    os.makedirs(CA_DIR, exist_ok=True)
    if os.path.exists(CRT) and os.path.exists(KEY):
        print("CA 已存在: %s (删除 ca/ 目录可重建)" % CA_DIR)
        return
    r1 = subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:4096", "-sha256",
        "-nodes", "-keyout", KEY, "-out", CRT, "-days", "3650",
        "-subj", "/CN=EA Unlocker Local CA/O=Hermes EA-Unlocker",
        "-addext", "basicConstraints=critical,CA:TRUE",
        "-addext", "keyUsage=critical,keyCertSign,cRLSign"],
        capture_output=True, text=True)
    if r1.returncode != 0:
        print("openssl CA 失败:\n" + r1.stderr)
        sys.exit(1)
    if os.name == "nt":
        try:
            os.chmod(KEY, stat.S_IRUSR | stat.S_IWUSR)  # 600
        except Exception:
            pass
    # 用户级导入 bat（无需管理员）
    bat = os.path.join(CA_DIR, "import_ca.bat")
    with open(bat, "w", encoding="gbk") as f:
        f.write('@echo off\r\nrem 用户级信任本地CA(无需管理员). 撤销: remove_ca.bat\r\n'
                'certutil -addstore -user "%~dp0ca.crt"\r\npause\r\n')
    rb = os.path.join(CA_DIR, "remove_ca.bat")
    with open(rb, "w", encoding="gbk") as f:
        f.write('@echo off\r\nrem 撤销用户级本地CA(还原)\r\n'
                'certutil -delstore -user -f "EA Unlocker Local CA"\r\npause\r\n')
    print("OK CA 生成于 %s" % CA_DIR)
    print("下一步: 1)双击 ca/import_ca.bat  2)起 run_mitm_v2.py")

if __name__ == "__main__":
    main()
