#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sentry finalization:
- flip last_status of the re-delivered delivery_failed job(s) -> 'delivery_resupplied'
  (with a jobs.json backup) so the 24h scanner doesn't re-queue them;
- append a rerun_log entry + reset the 30-min storm window (last_retry=now) for every
  job this run acted on, in rerun_state.json.
Preserves all existing content in both files. Atomic + contended-retry writers."""
import json, os, sys, time, datetime as dt, tempfile, shutil

CRON   = "E:/workbuddy/国外模型/hermes/cron"
JOBS   = os.path.join(CRON, "jobs.json")
LOCK   = os.path.join(CRON, ".jobs.lock")
STATE  = "E:/GoldstrategyEngine/data/rerun_state.json"
TZ     = dt.timezone(dt.timedelta(hours=8))

FLIP_TO_RESUPPLIED = ["7be97e98563b"]      # currently delivery_failed; we re-delivered its report
HANDLED = ["9077aa0e157a","9124906cea98","6f3d24b639c0","7be97e98563b","257b46fb9937","273e13f500f3","cd863fdae55c"]

def now_iso(): return dt.datetime.now(TZ).isoformat()

def lock(timeout=15.0):
    try: import msvcrt
    except ImportError: return None
    fd = open(LOCK,"a+",encoding="utf-8"); dl=time.time()+timeout
    while time.time()<dl:
        try: msvcrt.locking(fd.fileno(),msvcrt.LK_LOCK,1); return fd
        except OSError: time.sleep(0.2)
    return fd

def unlock(fd):
    if fd is None: return
    try: import msvcrt; msvcrt.locking(fd.fileno(),msvcrt.LK_UNLCK,1)
    except Exception: pass
    try: fd.close()
    except Exception: pass

def contended(e): return getattr(e,"winerror",None) in (5,32,33)

def atomic_write(path, payload_str):
    d=os.path.dirname(path)
    fd,tmp=tempfile.mkstemp(prefix=".tmp_",dir=d)
    with os.fdopen(fd,"w",encoding="utf-8") as fh:
        fh.write(payload_str); fh.flush(); os.fsync(fh.fileno())
    for a in range(1,9):
        try: os.replace(tmp,path); return
        except OSError as e:
            if not contended(e): raise
            time.sleep(0.2*a)

# ---- 1) jobs.json: backup + flip ----
ts=dt.datetime.now(TZ).strftime("%m%d_%H%M")
bak=os.path.join(CRON, f"jobs.json.bak_rerunsentry_{ts}")
shutil.copy2(JOBS, bak)
lj=lock()
try:
    d=json.loads(open(JOBS,"rb").read().decode("utf-8-sig"))
    by={j.get("id"):j for j in d["jobs"]}
    for tid in FLIP_TO_RESUPPLIED:
        if tid in by:
            by[tid]["last_status"]="delivery_resupplied"
            by[tid]["delivery_resupplied_at"]=now_iso()
    d["updated_at"]=now_iso()
    atomic_write(JOBS, json.dumps(d, ensure_ascii=False, indent=2))
    print("jobs.json: flipped -> delivery_resupplied:", FLIP_TO_RESUPPLIED, "| backup:", os.path.basename(bak))
finally:
    unlock(lj)

# ---- 2) rerun_state.json: rerun_log entry + last_retry reset ----
st=json.load(open(STATE, encoding="utf-8"))
now=time.time()
for tid in HANDLED:
    e=st.setdefault(tid, {})
    e["last_retry"]=now
    e.setdefault("reason","handled")
st.setdefault("rerun_log", [])
if not isinstance(st["rerun_log"], list):
    st["rerun_log"]=[st["rerun_log"]]
entry={
  "ts": dt.datetime.now(TZ).strftime("%F %H:%M"),
  "kind":"fail-task-immediate-rerun-sentry",
  "consumed_request":"2026-11-18 20:30:30 窗(4件: 9077aa0e157a/cd863fdae55c error + 257b46fb9937/273e13f500f3 delivery_failed) + 20:47:29 窗(3件: 7be97e98563b delivery_failed + 9124906cea98/6f3d24b639c0 error). 两窗并集处置.",
  "reran":["9077aa0e157a","9124906cea98","6f3d24b639c0"],
  "self_healed":["cd863fdae55c"],
  "delivery_only":["257b46fb9937","273e13f500f3","7be97e98563b"],
  "mt5_relogin":"无. 本窗无 error/429 类 MT5 补跑对象(3件 error 类=验尸官周报/晨学哨/strategy-rd深督, 均被 gateway update-drain 或 interrupted 打断, 非 MT5 终端问题). MT5 numpy ABI 断链=已知 venv 工单(rd_queue), 不在本哨修复范围.",
  "outcomes":{
    "ok":["9077aa0e157a (20:56:42 重跑成功 last_status=ok)","6f3d24b639c0 (21:02:57 二次触发重跑成功 last_status=ok)"],
    "in_flight":["9124906cea98 (20:57:48 触发, LLM agent 运行中, 下窗确认)"],
    "re_delivered":["257b46fb9937(20-33-44.md)","273e13f500f3(20-33-46.md)","7be97e98563b(20-46-24.md)"],
    "flag_repaired":["7be97e98563b (jobs.json last_status->delivery_resupplied, 备份 jobs.json.bak_rerunsentry_%s)"%ts]
  },
  "root_cause_note":"(1) 3件 error 类(验尸官周报/晨学哨/strategy-rd) 均因 gateway 'update drain'(Gateway draining: update_paused) 或 agent 'interrupted' 被打断. 触发器机制: hermes CLI 被中断的 `hermes update` git 恢复卡死(_early_recovery.restore_interrupted_pull), 故哨改用 jobs.json 直接写 trigger_job 字段(next_run_at=now+manual_run_at+manual_run_restore_at) 由活体 gateway 下一 tick 认领. (2) 首触发批 6f3d24b639c0 撞上 os.replace 与 gateway 读 jobs.json 竞争 -> 瞬时 EACCES(Permission denied), 用带 contended-retry 的写器二次触发恢复. (3) 投递失败根因=已知: iLink weixin 会话 not ready(ret=-2) + 参数表 sl4.5/tp7.0 漂移(规格 sl0.8/tp3.0) + 3.13.12 venv numpy._core.multiarray ABI 断链(MT5冒烟/BTC feed 导入败), 均 05:01 起持续已知问题, 非新危机.",
  "note":"本哨处置 7 件并集: 3 件 error 类重跑(9077aa0e157a 已 ok 恢复 + 6f3d24b639c0 已 ok 恢复; 9124906cea98 触发中 LLM 运行, 下窗 30min 确认, 若仍败扫描器 30min 后自动再入队), 1 件=本哨自身 cd863fdae55c(本运行即其恢复), 3 件 delivery_failed 报告以 [supplemental-delivery] 补投(任务本身不重跑), 其中 7be97e98563b 翻 delivery_resupplied 防 24h 重复入队. 预防: ① 中断的 hermes update git 恢复需人工/单独任务收尾(修好则 CLI 不再卡死, 哨可回退用 hermes cron run); ② gateway update-drain 反复打断 agent 任务=系统性隐患, 建议把 update 窗口与 6 节点/深督任务错开; ③ 哨写 jobs.json 一律带 msvcrt 锁 + contended-retry + 原子 replace(已固化 jince_sentry_trigger*.py)."
}
st["rerun_log"].append(entry)
if len(st["rerun_log"])>200:
    st["rerun_log"]=st["rerun_log"][-200:]
atomic_write(STATE, json.dumps(st, ensure_ascii=False, indent=1))
print("rerun_state.json: appended rerun_log entry + reset last_retry for", len(HANDLED), "jobs")
print("DONE")
