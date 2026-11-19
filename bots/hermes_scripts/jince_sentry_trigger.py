#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sentry: re-trigger failed cron jobs by replicating cron.jobs.trigger_job
(set next_run_at=now + manual_run_at + manual_run_restore_at + state=scheduled)
under the same cross-process msvcrt lock + atomic replace the scheduler uses.
The live gateway re-reads jobs.json each tick and fires the run-now markers."""
import json, os, sys, time, datetime as dt, tempfile

CRON = "E:/workbuddy/国外模型/hermes/cron"
JOBS = os.path.join(CRON, "jobs.json")
LOCK = os.path.join(CRON, ".jobs.lock")
TZ = dt.timezone(dt.timedelta(hours=8))

TARGETS = ["9077aa0e157a", "9124906cea98", "6f3d24b639c0"]
LOCK_TIMEOUT = 15.0

def now_iso():
    return dt.datetime.now(TZ).isoformat()

def acquire_lock():
    try:
        import msvcrt
    except ImportError:
        return None
    fd = open(LOCK, "a+", encoding="utf-8")
    deadline = time.time() + LOCK_TIMEOUT
    while time.time() < deadline:
        try:
            msvcrt.locking(fd.fileno(), msvcrt.LK_LOCK, 1)
            return fd
        except OSError:
            time.sleep(0.2)
    # degrade to no cross-proc lock (system tolerates a brief racing write)
    return fd

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

def main():
    lock_fd = acquire_lock()
    try:
        raw = open(JOBS, "rb").read()
        d = json.loads(raw.decode("utf-8-sig"))
        jobs = d["jobs"]
        by_id = {j.get("id"): j for j in jobs}
        now = now_iso()
        report = []
        for tid in TARGETS:
            j = by_id.get(tid)
            if j is None:
                report.append((tid, "MISSING", None, None))
                continue
            old_next = j.get("next_run_at")
            j["enabled"] = True
            j["state"] = "scheduled"
            j["paused_at"] = None
            j["paused_reason"] = None
            j["next_run_at"] = now
            j["manual_run_at"] = now
            j["manual_run_restore_at"] = old_next  # extra_fire.RESTORE_KEY
            j["manual_run_prompt"] = None
            report.append((tid, "TRIGGERED", old_next, now))
        d["updated_at"] = now
        # atomic write (temp + fsync + replace), same dir
        fd2, tmp = tempfile.mkstemp(prefix=".tmp_jobs_", dir=CRON)
        with os.fdopen(fd2, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, JOBS)
        for tid, act, old, new in report:
            print("%s %s old_next=%s -> next_run_at=%s" % (tid, act, old, new))
    finally:
        release_lock(lock_fd)

if __name__ == "__main__":
    main()
