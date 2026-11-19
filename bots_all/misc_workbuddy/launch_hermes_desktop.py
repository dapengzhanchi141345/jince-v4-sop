# -*- coding: utf-8 -*-
"""
拉起 Hermes 桌面 GUI（不杀网关，只救桌面）。
关键修正：Popen 不能带 close_fds=True（Windows 下会让 Electron 丢失继承句柄而秒退）。
拉起后不杀进程，反复验证进程数 + desktop.log 是否停止 401。
"""
import os
import time
import subprocess

EXE = r'E:\workbuddy\国外模型\hermes\hermes-agent\apps\desktop\release\win-unpacked\Hermes.exe'
CWD = r'E:\workbuddy\国外模型\hermes\hermes-agent\apps\desktop\release\win-unpacked'


def count_hermes():
    try:
        out = subprocess.run(['tasklist.exe'], capture_output=True,
                             encoding='gbk', errors='ignore', timeout=20).stdout
        return sum(1 for l in out.splitlines() if 'Hermes.exe' in l)
    except Exception as e:
        return -1


def recent_401():
    try:
        log = r'E:\workbuddy\国外模型\hermes\logs\desktop.log'
        data = open(log, encoding='utf-8', errors='ignore').read().splitlines()
        tail = [l for l in data[-60:] if '401' in l]
        return len(tail)
    except Exception:
        return -1


def main():
    print('[launch] 开始:', time.strftime('%H:%M:%S'))
    print('[launch] 拉起前 Hermes.exe 数量:', count_hermes())

    # 关键：stdout/stderr 重定向(DEVNULL) + DETACHED 脱离父进程独立存活
    try:
        p = subprocess.Popen([EXE], cwd=CWD,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
        print('[launch] Popen 已调用(DETACHED), pid=', p.pid)
    except Exception as e:
        print('[launch] Popen 失败:', repr(e))
        return

    # 逐步验证：Electron 冷启动较慢，给足时间
    for i in (8, 8, 8, 10, 10, 15):
        time.sleep(i)
        n = count_hermes()
        print(f'[launch] +{i}s Hermes.exe 数量: {n} | 最近401(末60行): {recent_401()}')
        if n > 0:
            print('[launch] 桌面进程已稳定起来。等待日志确认连接...')
            break
    else:
        print('[launch] 警告：进程仍未起来。')

    # 再等 15 秒看 desktop.log 是否停止 401（表示桌面已重建原生会话连上网关）
    time.sleep(15)
    print('[launch] 收尾检查 Hermes.exe 数量:', count_hermes(), '| 最近401(末60行):', recent_401())


if __name__ == '__main__':
    main()
