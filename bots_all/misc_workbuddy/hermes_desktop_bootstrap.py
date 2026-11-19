# -*- coding: utf-8 -*-
"""
Hermes 桌面引导 + 看门狗（彻底重置版）。
- 启动时：强杀所有 Hermes 进程 -> 清理 Roaming\hermes 中可能卡死桌面的前端状态
  （保留 Preferences / secure-token-storage.json 以维持登录态）-> 拉起桌面。
- 之后每 20s 自愈检查：桌面掉则重拉。
- 作为 run_in_background 任务常驻，桌面以本进程为稳定父，脱离一次性命令树。
"""
import os
import time
import shutil
import subprocess

EXE = r'E:\workbuddy\国外模型\hermes\hermes-agent\apps\desktop\release\win-unpacked\Hermes.exe'
CWD = r'E:\workbuddy\国外模型\hermes\hermes-agent\apps\desktop\release\win-unpacked'
LOG = r'E:\workbuddy\hermes_desktop_bootstrap.log'
FRONTEND = r'C:\Users\Administrator\AppData\Roaming\hermes'
KEEP = {'Preferences', 'secure-token-storage.json'}


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


def clean_frontend():
    """清理可能卡死桌面的前端状态，保留登录态相关文件。"""
    if not os.path.isdir(FRONTEND):
        return
    cleaned = []
    for name in os.listdir(FRONTEND):
        if name in KEEP or name.startswith('en-US'):
            continue
        p = os.path.join(FRONTEND, name)
        try:
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)
            cleaned.append(name)
        except Exception:
            pass
    log('cleaned frontend state (kept Preferences/secure-token): %s' % ','.join(cleaned[:12]))


def kill_all():
    try:
        subprocess.run(['taskkill.exe', '/F', '/IM', 'Hermes.exe'],
                       capture_output=True, encoding='gbk', errors='ignore', timeout=15)
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
    log('bootstrap started (pid=%s)' % os.getpid())
    kill_all()
    time.sleep(2)
    clean_frontend()
    launch()
    while True:
        time.sleep(20)
        n = count_hermes()
        if n <= 0:
            log('Hermes down -> relaunch')
            launch()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log('bootstrap crashed: %r' % e)
