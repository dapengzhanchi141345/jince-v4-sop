#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gateway_401_selfheal.py  —  auto-clear the recurring desktop 401 storm.

ROOT CAUSE (diagnosed 2026-11-12, confirmed against hermes-agent source 2026-11-13):
  The Hermes multiplex gateway's internal native-HTTP auth-ticket state drifts
  (session_ticket_store / session_runtime_descriptor / session_authorities lose
  consistency). The Desktop then gets batched 401 {"detail":"Unauthorized"} on
  every native HTTP call -> "会话控制不可用". A CLEAN gateway restart rebuilds that
  state and clears it.

CORRECT RESTART PATH (learned from hermes_cli source, NOT guesswork):
  On THIS machine the gateway is a *Desktop-spawned backend* — Hermes.exe (the
  Desktop app) IS the gateway's supervisor (gateway.py:5512, AGENTS.md:205). The
  running argv has NO --external-supervisor and the gateway was NOT installed as a
  service. Therefore the right recovery is:
      kill ONLY the gateway pid  ->  the Desktop detects death and respawns it
      cleanly with the correct (multiplex, no --profile) argv.
  We must NEVER `taskkill /F /IM Hermes.exe` (that kills the supervisor itself and
  churns the respawn -> re-drift), and we must NOT self-relaunch with
  `--profile default` (that creates a non-Desktop-managed gateway that drifts
  again — this was the bug causing the 2-minute storm recurrence on 2026-11-13).

  Official CLI `hermes gateway restart` exists but, for a Desktop-spawned gateway
  with no external supervisor, falls into the manual stop+foreground path that
  wedges KeepAlive (#110637). So we rely on the Desktop supervisor respawn, which
  is exactly how Hermes itself recovers a Desktop-spawned backend.

  A cross-process cooldown file prevents two detectors (e.g. the sandbox loop +
  a host schtasks task) from double-killing the gateway during one recovery.

USAGE:
  python gateway_401_selfheal.py            # detect + heal if needed (one shot)
  python gateway_401_selfheal.py --detect-only
  python gateway_401_selfheal.py --force    # restart regardless of storm
  python gateway_401_selfheal.py --loop     # poll every GW401_LOOP_INTERVAL sec
"""
import os, sys, time, json, subprocess, logging

HERE = os.path.dirname(os.path.abspath(__file__))
HERMES_HOME = os.environ.get("HERMES_HOME", r"E:\workbuddy\国外模型\hermes")
HERMES_AGENT = r"E:\workbuddy\国外模型\hermes\hermes-agent"
GW_PY = os.environ.get(
    "HERMES_GW_PY",
    r"E:\workbuddy\国外模型\hermes\tools\python-3.14.9+20261021-win32-x64\python.exe",
)
DESKTOP_LOG = os.path.join(HERMES_HOME, "logs", "desktop.log")
GW_STATE = os.path.join(HERMES_HOME, "gateway_state.json")
SELFHEAL_LOG = os.path.join(HERE, "selfheal.log")
COOLDOWN_FILE = os.path.join(HERE, "selfheal_cooldown.txt")

THRESHOLD = int(os.environ.get("GW401_THRESHOLD", "5"))      # >=5 in window
WINDOW_SEC = int(os.environ.get("GW401_WINDOW", "180"))      # last 3 minutes
HEAL_COOLDOWN = int(os.environ.get("GW401_COOLDOWN", "120")) # min sec between heals
RESPawn_TIMEOUT = int(os.environ.get("GW401_RESPAWN_TIMEOUT", "90"))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(SELFHEAL_LOG, encoding="utf-8"),
              logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("gw401")

# Honor the "no writes to C:" rule: keep temp off the system drive for any child
# process (taskkill/tasklist/python) this script spawns.
for _v in ("TMPDIR", "TEMP", "TMP"):
    if not os.environ.get(_v):
        os.environ[_v] = r"E:\workbuddy\tmp"


# ---- cross-process cooldown (shared by every detector instance) -------------
def load_cooldown():
    try:
        with open(COOLDOWN_FILE, "r", encoding="utf-8") as f:
            return float(f.read().strip() or "0")
    except Exception:
        return 0.0

def save_cooldown(epoch):
    try:
        with open(COOLDOWN_FILE, "w", encoding="utf-8") as f:
            f.write(str(epoch))
    except Exception:
        pass


def now_epoch():
    return time.time()


def read_tail(path, max_bytes=200000):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            return f.read().decode("utf-8", "ignore")
    except Exception as exc:
        log.warning("cannot read %s: %s", path, exc)
        return ""


def count_recent_401(text, window_sec):
    cutoff = now_epoch() - window_sec
    cnt = 0
    for line in text.splitlines():
        if "401" not in line and "Unauthorized" not in line:
            continue
        try:
            ts = time.mktime(time.strptime(line[:19], "%Y-%m-%d %H:%M:%S"))
        except Exception:
            continue
        if ts >= cutoff:
            cnt += 1
    return cnt


def current_gw_pid():
    try:
        with open(GW_STATE, "r", encoding="utf-8") as f:
            d = json.load(f)
        if d.get("gateway_state") == "running":
            return d.get("pid")
    except Exception:
        pass
    return None


def gw_running(pid):
    if not pid:
        return False
    try:
        out = subprocess.run(["tasklist.exe", "/FI", f"PID eq {pid}"],
                             capture_output=True, text=True, errors="ignore", timeout=10)
        return str(pid) in out.stdout
    except Exception:
        return False


def kill_gateway_only(pid):
    """Kill ONLY the gateway process. The Desktop app (Hermes.exe) is the
    gateway's supervisor on Windows and will respawn it cleanly. Killing
    Hermes.exe would kill the supervisor itself -> churn -> re-drift."""
    log.info("killing gateway pid %s (Desktop supervisor will respawn it)", pid)
    subprocess.run(["taskkill.exe", "/F", "/PID", str(pid)],
                   capture_output=True, text=True, errors="ignore", timeout=15)


def launch_gateway_last_resort():
    """Only used if the Desktop did NOT respawn the gateway within timeout.
    Matches the healthy Desktop-spawned argv (no --profile) to avoid drift."""
    env = os.environ.copy()
    env["HERMES_HOME"] = HERMES_HOME
    env["TMPDIR"] = env.get("TMPDIR", r"E:\workbuddy\tmp")
    env["TEMP"] = env.get("TEMP", r"E:\workbuddy\tmp")
    env["TMP"] = env.get("TMP", r"E:\workbuddy\tmp")
    log.info("LAST-RESORT relaunch: %s -m hermes_cli.main gateway run --quiet", GW_PY)
    return subprocess.Popen(
        [GW_PY, "-m", "hermes_cli.main", "gateway", "run", "--quiet"],
        cwd=HERMES_AGENT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def wait_for_recovery(timeout=RESPawn_TIMEOUT, expect_old=None):
    deadline = now_epoch() + timeout
    while now_epoch() < deadline:
        pid = current_gw_pid()
        if pid and gw_running(pid) and (expect_old is None or pid != expect_old):
            log.info("gateway recovered, new pid=%s", pid)
            return pid
        time.sleep(3)
    return None


def heal(force=False):
    text = read_tail(DESKTOP_LOG)
    cnt = count_recent_401(text, WINDOW_SEC)
    log.info("recent 401 in last %ds = %d (threshold %d)%s",
             WINDOW_SEC, cnt, THRESHOLD, " [FORCE]" if force else "")

    if not force and cnt < THRESHOLD:
        log.info("no 401 storm detected — nothing to do")
        return False

    # cross-process cooldown so multiple detectors never double-kill
    if not force:
        since = now_epoch() - load_cooldown()
        if since < HEAL_COOLDOWN:
            log.info("heal cooldown active (%ds left) — skip", int(HEAL_COOLDOWN - since))
            return False

    pid = current_gw_pid()
    if not pid or not gw_running(pid):
        log.warning("gateway not running per state file — last-resort relaunch")
        launch_gateway_last_resort()
        wait_for_recovery()
        save_cooldown(now_epoch())
        return True

    old_pid = pid
    # PRIMARY: kill gateway only, let the Desktop (supervisor) respawn cleanly.
    kill_gateway_only(old_pid)
    time.sleep(3)
    new_pid = wait_for_recovery(expect_old=old_pid)
    if new_pid:
        log.info("Desktop respawned gateway cleanly, new pid=%s", new_pid)
        save_cooldown(now_epoch())
        return True

    log.warning("Desktop did not respawn gateway in %ds — last-resort relaunch",
                RESPawn_TIMEOUT)
    launch_gateway_last_resort()
    new_pid = wait_for_recovery()
    if not new_pid:
        log.error("GATEWAY DID NOT RECOVER — manual intervention needed")
        save_cooldown(now_epoch())
        return False
    log.info("heal complete (last-resort relaunch), gateway pid=%s", new_pid)
    save_cooldown(now_epoch())
    return True


if __name__ == "__main__":
    if "--detect-only" in sys.argv:
        text = read_tail(DESKTOP_LOG)
        cnt = count_recent_401(text, WINDOW_SEC)
        print(json.dumps({"recent_401": cnt, "threshold": THRESHOLD,
                          "gw_pid": current_gw_pid(),
                          "cooldown_left": max(0, int(HEAL_COOLDOWN - (now_epoch() - load_cooldown()))),
                          "would_heal": cnt >= THRESHOLD}, ensure_ascii=False))
    elif "--loop" in sys.argv:
        interval = int(os.environ.get("GW401_LOOP_INTERVAL", "30"))
        log.info("self-heal LOOP started, checking every %ds (Desktop-supervised restart)", interval)
        while True:
            try:
                heal(force=False)
            except Exception as exc:  # noqa: BLE001
                log.error("heal iteration error: %s", exc)
            time.sleep(interval)
    elif "--force" in sys.argv:
        heal(force=True)
    else:
        heal(force=False)
