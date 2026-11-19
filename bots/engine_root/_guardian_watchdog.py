# -*- coding: utf-8 -*-
"""
金策守卫 · 自看护看门狗（admin-free 自愈伴侣）
==================================================================
与 boot_guardian.py 互为守护：
  - 本看门狗每 CHECK 秒检查 boot_guardian.lock 是否由存活进程持有；
  - 若守卫进程已死，立即用 pythonw 无窗口拉起 boot_guardian.py；
  - 本看门狗自身单实例（guardian_watchdog.lock），被 boot_guardian 反过来看护。
无需管理员/计划任务权限，登录后由 boot_guardian 拉起即可持久存活。
"""
import os
import sys
import time
import subprocess
import ctypes

WORKDIR = r"E:\GoldstrategyEngine"
PY = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/pythonw.exe"
GUARDIAN = os.path.join(WORKDIR, "boot_guardian.py")
GUARDIAN_LOCK = os.path.join(WORKDIR, "data", "boot_guardian.lock")
WATCHDOG_LOCK = os.path.join(WORKDIR, "data", "guardian_watchdog.lock")
CHECK = 300                      # 看护周期（秒）
DETACHED = 0x00000008
LOG = os.path.join(WORKDIR, "data", "logs", "guardian_watchdog.log")


def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s WDOG: %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def alive(pid):
    try:
        return ctypes.windll.kernel32.GetProcessVersion(int(pid)) != 0
    except Exception:
        return False


def guardian_alive():
    if not os.path.exists(GUARDIAN_LOCK):
        return False
    try:
        pid = int(open(GUARDIAN_LOCK).read().strip() or 0)
    except Exception:
        return False
    return alive(pid)


def launch_guardian():
    try:
        subprocess.Popen([PY, GUARDIAN], cwd=WORKDIR,
                         creationflags=DETACHED, close_fds=True)
        log("boot_guardian relaunched by watchdog")
    except Exception as e:
        log("relaunch FAILED: %r" % e)


def acquire():
    try:
        fd = os.open(WATCHDOG_LOCK, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        try:
            old = int(open(WATCHDOG_LOCK).read().strip() or 0)
        except Exception:
            old = 0
        if old and alive(old):
            return False
        try:
            os.remove(WATCHDOG_LOCK)
            fd = os.open(WATCHDOG_LOCK, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except Exception:
            return False


def main():
    if not acquire():
        sys.exit(0)
    log("watchdog started (single-instance)")
    while True:
        try:
            if not guardian_alive():
                log("guardian not alive -> relaunch")
                launch_guardian()
        except Exception as e:
            log("loop err: %r" % e)
        time.sleep(CHECK)


if __name__ == "__main__":
    main()
