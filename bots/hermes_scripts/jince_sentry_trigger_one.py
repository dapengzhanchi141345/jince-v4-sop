#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sentry: re-trigger a single failed cron job (contended-safe writer).
Reloads the LIVE jobs.json (preserving any in-flight fire_claims of other jobs),
sets trigger_job fields for the target, atomic-replaces with bounded retry on
Windows contention, then verifies the write landed. Used to recover 6f3d24b639c0
whose re-run hit a transient EACCES race during the first trigger batch."""
import json, os, sys, time, datetime as dt, tempfile

CRON = "E:/workbuddy/国外模型/hermes/cron"
JOBS = os.path.join(CRON, "jobs.json")
LOCK = os.path.join(CRON, ".jobs.lock")
TZ = dt.timezone(dt.timedelta(hours=8))

TARGET = "6f3d24b639c0"

def now_iso():
    return dt.datetime.now(TZ).isoformat()

def acquire_lock(timeout=15.0):
    try:
        import msvcrt
    except ImportError:
        return None
    fd = open(LOCK, "a+", encoding="utf-8")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            msvcrt.locking(fd.fileno(), msvcrt.LK_LOCK, 1)
            return fd
        except OSError:
            time.sleep(0.2)
    return fd  # degrade to in-proc only (system tolerates brief racing write)

def release_lock(fd):
    if fd is None:
        return
    try:
        import msvcrt
        msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
    except Exception:
        pass
    try:
        fd.close()
    except Exception:
        pass

def contended(exc):
    we = getattr(exc, "winerror", None)
    return we in (5, 32, 33)  # ACCESS_DENIED / SHARING_VIOLATION / PIPE_BUSY-ish

def main():
    lock_fd = acquire_lock()
    try:
        raw = open(JOBS, "rb").read()
        d = json.loads(raw.decode("utf-8-sig"))
        by_id = {j.get("id"): j for j in d["jobs"]}
        j = by_id.get(TARGET)
        if j is None:
            print("TARGET MISSING"); return 1
        now = now_iso()
        old_next = j.get("next_run_at")
        j["enabled"] = True
        j["state"] = "scheduled"
        j["paused_at"] = None
        j["paused_reason"] = None
        j["next_run_at"] = now
        j["manual_run_at"] = now
        j["manual_run_restore_at"] = old_next
        j["manual_run_prompt"] = None
        d["updated_at"] = now
        payload = json.dumps(d, ensure_ascii=False, indent=2)
        # atomic replace with bounded retry on Windows contention
        fd2, tmp = tempfile.mkstemp(prefix=".tmp_jobs_", dir=CRON)
        with os.fdopen(fd2, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        last = None
        for attempt in range(1, 9):
            try:
                os.replace(tmp, JOBS)
                last = None
                break
            except OSError as e:
                last = e
                if not contended(e):
                    break
                time.sleep(0.2 * attempt)
        if last is not None:
            print("REPLACE FAILED (winerror=%s): %s" % (getattr(last, "winerror", None), last))
            try:
                os.unlink(tmp)
            except Exception:
                pass
            return 2
        time.sleep(1.0)
        # verify
        d2 = json.loads(open(JOBS, "rb").read().decode("utf-8-sig"))
        j2 = {x["id"]: x for x in d2["jobs"]}[TARGET]
        ok = j2.get("next_run_at") == now and j2.get("manual_run_at") == now
        print("%s RE-TRIGGERED old_next=%s -> next_run_at=%s verified=%s" % (TARGET, old_next, now, ok))
        return 0 if ok else 3
    finally:
        release_lock(lock_fd)

if __name__ == "__main__":
    sys.exit(main())
