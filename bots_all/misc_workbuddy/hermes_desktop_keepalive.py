# -*- coding: utf-8 -*-
"""
Hermes 桌面常驻看门狗 + 启动器（沙箱无法用 schtasks/wscript 时的兜底方案）。
- 主循环每 20s 检查 Hermes.exe 是否在运行；不在就拉起。
- 拉起用普通 Popen（cwd 正确 + DEVNULL 重定向，避免 Electron 继承控制台秒退）。
- 本进程作为 Hermes 的稳定父进程常驻，使其脱离一次性 Bash 命令的进程树。
- 不杀网关、不碰其它进程。
"""
import os
import time
import subprocess

EXE = r'E:\workbuddy\国外模型\hermes\hermes-agent\apps\desktop\release\win-unpacked\Hermes.exe'
CWD = r'E:\workbuddy\国外模型\hermes\hermes-agent\apps\desktop\release\win-unpacked'
LOG = r'E:\workbuddy\hermes_desktop_keepalive.log'


def count_hermes():
    try:
        out = subprocess.run(['tasklist.exe'], capture_output=True,
                             encoding='gbk', errors='ignore', timeout=20).stdout
        return sum(1 for l in out.splitlines() if 'Hermes.exe' in l)
    except Exception:
        return -1


def log(msg):
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S') + ' ' + msg + '\n')
    except Exception:
        pass


def launch():
    try:
        p = subprocess.Popen([EXE], cwd=CWD,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log('launched Hermes.exe pid=%s' % p.pid)
        return p.pid
    except Exception as e:
        log('launch failed: %r' % e)
        return None


def main():
    log('keepalive started (pid=%s)' % os.getpid())
    launch()
    while True:
        time.sleep(20)
        n = count_hermes()
        if n <= 0:
            log('Hermes down (count=%s) -> relaunch' % n)
            launch()
        else:
            # 正常运行时静默，仅在状态变化时记录
            pass


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log('keepalive crashed: %r' % e)
