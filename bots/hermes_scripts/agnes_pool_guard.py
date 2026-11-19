# -*- coding: utf-8 -*-
"""
Agnes Key-Pool Guardian (stdlib only, no deps)
==============================================
Hermes cron watchdog: every 5 minutes ensure the Agnes key pool proxy
(agnes_key_pool.py on 127.0.0.1:8787) is healthy. If /health fails or
the port is not listening, spawn a fresh pool process DETACHED so it
survives the cron run's own process tree.

All child stdout/stderr is redirected to pool_child.log so silent
crashes leave evidence (the pythonw no-stderr trap).

Logs: E:\\workbuddy\\国外模型\\hermes\\logs\\agnes_pool_guard.log
"""
import os
import subprocess
import urllib.request
import urllib.error
from datetime import datetime

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # hermes home
LOG_FILE = os.path.join(HERE, "logs", "agnes_pool_guard.log")
CHILD_LOG = os.path.join(HERE, "logs", "agnes_pool_child.log")
POOL_SCRIPT = os.path.join(HERE, "agnes_key_pool.py")

# interpreters to try, in order (must contain httpx)
PY_CANDIDATES = [
    os.path.join(HERE, "hermes-agent", "venv", "Scripts", "pythonw.exe"),
    os.path.join(HERE, "hermes-agent", "venv", "Scripts", "python.exe"),
]


def log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line)


def health_ok(timeout=6):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8787/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def pick_python():
    for p in PY_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def spawn_pool():
    py = pick_python()
    if not py:
        log("ERROR: no suitable python with httpx found")
        return False
    # DETACHED_PROCESS | CREATE_NO_WINDOW -> survives parent exit
    flags = 0x00000008 | 0x08000000
    try:
        child_log = open(CHILD_LOG, "ab")
        subprocess.Popen(
            [py, POOL_SCRIPT],
            cwd=HERE,
            stdout=child_log,
            stderr=child_log,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
        log("spawned pool via %s" % py)
        return True
    except Exception as e:
        log("ERROR spawning pool: %r" % e)
        return False


def main():
    if health_ok():
        print("OK")  # empty stdout would be silent; print OK for cron records
        return
    log("health FAIL -> spawning pool")
    spawn_pool()
    # give the pool time for its key self-check, then verify once
    import time
    time.sleep(25)
    if health_ok(timeout=10):
        log("pool recovered, /health OK")
        print("RECOVERED")
    else:
        log("pool still unhealthy after spawn (may need next tick)")
        print("STILL_DOWN")  # non-zero? keep exit 0 so cron doesn't flag


if __name__ == "__main__":
    main()
