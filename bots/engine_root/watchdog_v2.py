# GoldstrategyEngine 纯Python看门狗 (常驻, 脱离父进程) - V2: 替换 wmic 为 tasklist
# 每20s检测 run_trader.py --live 是否存活; 不存活则拉起(DETACHED, 真独立进程).
import os, time, sys, subprocess, datetime, ctypes, atexit

WORKDIR = r"E:\GoldstrategyEngine"
PY = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/pythonw.exe"
PIDFILE = os.path.join(WORKDIR, "data", "live.pid")
SELFLOCK = os.path.join(WORKDIR, "data", "watchdog.lock")
LOGDIR = os.path.join(WORKDIR, "data", "logs")
WATCH_LOG = os.path.join(LOGDIR, "watchdog_py.log")
DETACHED = 0x00000008
CHECK_INTERVAL = 20
GRACE_PERIOD = 90
_LAST_SPAWN_TS = 0.0
_WD_MUTEX_HANDLE = None

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(WATCH_LOG, "a", encoding="utf-8") as f:
            f.write(f"{ts} WATCHDOG: {msg}\n")
    except Exception:
        pass

def pid_alive(pid):
    try:
        pid = int(pid)
        if pid <= 0: return False
        kernel32 = ctypes.windll.kernel32
        ver = kernel32.GetProcessVersion(pid)
        return ver != 0
    except Exception:
        return False

def _force_delete(path):
    try:
        return ctypes.windll.kernel32.DeleteFileW(path) != 0
    except Exception:
        return False

def acquire_self_lock(max_retry=60):
    for _ in range(max_retry):
        try:
            fd = os.open(SELFLOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                with open(SELFLOCK) as f:
                    old = f.read().strip()
                if old.isdigit() and pid_alive(old):
                    return False
                try:
                    _force_delete(SELFLOCK)
                except FileExistsError:
                    continue
                except Exception:
                    pass
            except FileExistsError:
                continue
            except Exception:
                pass
        except Exception:
            return False
    return False

def release_self_lock():
    try:
        if os.path.exists(SELFLOCK):
            with open(SELFLOCK) as f:
                if f.read().strip() == str(os.getpid()):
                    _force_delete(SELFLOCK)
    except Exception:
        pass

def _touch_self_lock():
    try:
        if not os.path.exists(SELFLOCK):
            fd = os.open(SELFLOCK, os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return
        with open(SELFLOCK) as f:
            cur = f.read().strip()
        if cur != str(os.getpid()):
            return
    except Exception:
        pass

def is_alive():
    try:
        if os.path.exists(PIDFILE):
            with open(PIDFILE) as f:
                pid = f.read().strip()
            if pid.isdigit() and pid_alive(pid):
                return True
    except Exception:
        pass
    return False

def create_named_mutex(name):
    try:
        kernel32 = ctypes.windll.kernel32
        ERROR_ALREADY_EXISTS = 183
        kernel32.SetLastError(0)
        h = kernel32.CreateMutexW(None, False, name)
        err = kernel32.GetLastError()
        if h == 0:
            return False
        if err == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(h)
            return False
        return True
    except Exception:
        return False

def _kernel_single_instance(name):
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetLastError.restype = ctypes.c_uint
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        ERROR_ALREADY_EXISTS = 183
        kernel32.SetLastError(0)
        h = kernel32.CreateMutexW(None, 0, name)
        err = kernel32.GetLastError()
        if not h:
            return True
        if err == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(h)
            return False
        global _WD_MUTEX_HANDLE
        _WD_MUTEX_HANDLE = h
        return True
    except Exception:
        return True

def _run_cmd(args, timeout=20):
    try:
        r = subprocess.run(args, capture_output=True, timeout=timeout, creationflags=0x08000000)
        return r.stdout.decode("gbk", "ignore")
    except Exception:
        return ""

def _enum_python_cmds():
    """枚举所有 python.exe 进程 -> [(pid, cmdline)]"""
    res = []
    try:
        o = _run_cmd(["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"])
        for line in o.splitlines():
            parts = [p.strip('"') for p in line.split(",")]
            if len(parts) >= 2 and parts[1].isdigit():
                pid = parts[1]
                try:
                    cl = _run_cmd(["powershell", "-Command",
                                   f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).CommandLine"])
                    cmd = cl.strip()
                except Exception:
                    cmd = ""
                res.append((pid, cmd))
    except Exception:
        pass
    return res

def _live_already_running():
    """枚举系统中是否已有 run_trader.py --live 进程在跑"""
    try:
        for pid, cmd in _enum_python_cmds():
            if ("run_trader.py" in cmd and "--live" in cmd
                    and pid.isdigit() and pid_alive(pid)):
                return int(pid)
    except Exception:
        pass
    return None

def _kill_all_live_loops():
    """清除所有 run_trader --live 进程"""
    try:
        for pid, cmd in _enum_python_cmds():
            if "run_trader.py" in cmd and "--live" in cmd and pid.isdigit():
                if pid_alive(pid):
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                  capture_output=True, creationflags=0x08000000)
                    log(f"killed stray live PID {pid}")
    except Exception as e:
        log(f"_kill_all_live_loops err: {e}")

def launch():
    global _LAST_SPAWN_TS
    try:
        running = _live_already_running()
        if running:
            try:
                with open(PIDFILE, "w") as f:
                    f.write(str(running))
                log(f"live actually alive PID {running} -> pidfile repaired")
            except Exception as e:
                log(f"pidfile repair failed: {e}")
            _LAST_SPAWN_TS = time.time()
            return

        _kill_all_live_loops()
        for _ in range(15):
            if _live_already_running() is None:
                break
            time.sleep(0.5)
        time.sleep(1.5)

        if os.path.exists(PIDFILE):
            try:
                with open(PIDFILE) as f:
                    if not pid_alive(f.read().strip()):
                        _force_delete(PIDFILE)
            except Exception:
                pass
        out = open(os.path.join(LOGDIR, "live_loop_main.log"), "a")
        err = open(os.path.join(LOGDIR, "live_loop_err.log"), "a")
        p = subprocess.Popen(
            [PY, "-u", "run_trader.py", "--live", "--loop"],
            cwd=WORKDIR, stdout=out, stderr=err,
            creationflags=DETACHED,
        )
        _LAST_SPAWN_TS = time.time()
        log(f"live NOT found -> restarted PID {p.pid} (grace {GRACE_PERIOD}s)")
    except Exception as e:
        log(f"restart FAILED: {e}")

if __name__ == "__main__":
    if not _kernel_single_instance("GoldstrategyWatchdog"):
        try:
            sys.stderr.write("another watchdog (kernel mutex) running, exit\n")
        except Exception:
            pass
        sys.exit(0)
    if not acquire_self_lock():
        try:
            sys.stderr.write("another watchdog running, exit\n")
        except Exception:
            pass
        sys.exit(0)
    atexit.register(release_self_lock)
    log("watchdog started (python, detached, self-locked)")
    _touch_self_lock()
    while True:
        try:
            _touch_self_lock()
            in_grace = (time.time() - _LAST_SPAWN_TS) < GRACE_PERIOD
            if not is_alive():
                if in_grace:
                    log("live not yet in pidfile but within grace period, wait")
                else:
                    launch()
        except Exception as e:
            log(f"loop error: {e}")
        time.sleep(CHECK_INTERVAL)
