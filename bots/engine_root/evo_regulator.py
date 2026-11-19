# -*- coding: utf-8 -*-
"""
evo_regulator.py — 进化监督器「独立监管哨兵」(2026-11-08 监管强化章程 R29)

职责（与 evo_24x7_supervisor 双保险，杜绝单点失效）：
  监督器自身有自修复 + Windows 计划任务 10 分钟看门狗；但若监督器**进程活着却假死**
  （心跳长时间不刷新，进化卡住），计划任务（按 PID 存活判断）无法察觉。本哨兵独立读
  心跳文件，做「进程存活 + 心跳新鲜」双判，超时即强杀陈旧实例并强制重启 + 升级记日志。

判活标准：
  - 心跳文件存在、status=="running"、且距上次写盘 < STALE_GRACE 秒  → 健康
  - 否则 → 不健康：杀陈旧 PID + 清锁 + 经 GoldEvo24x7 任务（兜底直接拉起）重启

红线（与监督器一致）：
  - 绝不初始化/登录 MT5，不碰 Hermes 实盘；本脚本只读心跳/锁 + 启停监督器进程。
  - 重启只触发已注册的合法进程，不改变任何策略参数、不投产、不开单。

用法：
  python evo_regulator.py            # 一次巡检（默认每 5 分钟由 GoldEvoRegulator 任务调用）
  python evo_regulator.py --check    # 仅报告不重启（用于人工核验）
  python evo_regulator.py --status   # 打印当前健康快照后退出
"""
import os
import sys
import json
import time
import subprocess

ROOT = r"E:\GoldstrategyEngine"
STATE_DIR = os.path.join(ROOT, "data", "continuous_evolution")
HEARTBEAT = os.path.join(STATE_DIR, "evo_heartbeat.json")
LOCK = os.path.join(STATE_DIR, "evo_supervisor.lock")
REG_LOG = os.path.join(STATE_DIR, "evo_regulator.log")
REG_STATE = os.path.join(STATE_DIR, "evo_regulator_state.json")
TASK_NAME = "GoldEvo24x7"
PY = r"D:\workbuddy\binaries\python\versions\3.13.12\python.exe"
SUPERVISOR = os.path.join(ROOT, "evo_24x7_supervisor.py")

# 心跳超过此秒数视为假死（与 10 分钟看门狗对齐，避免误杀正常长周期）
STALE_GRACE = 600

NOW = time.time()


def _log(level, msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = "[%s] %s %s" % (ts, level, msg)
    try:
        with open(REG_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line)


def _read_heartbeat():
    try:
        with open(HEARTBEAT, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _read_lock_pid():
    try:
        with open(LOCK, encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None


def _pid_alive(pid):
    if not pid:
        return False
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "PID eq %d" % pid, "/NH", "/FO", "CSV"],
            capture_output=True, text=True, timeout=15)
        return str(pid) in (out.stdout or "")
    except Exception:
        return False


def _assess():
    """返回 (healthy:bool, detail:dict)。"""
    hb = _read_heartbeat()
    if hb is None:
        return False, {"reason": "no_heartbeat", "heartbeat": None}
    ts = hb.get("ts")
    if not isinstance(ts, (int, float)):
        return False, {"reason": "bad_heartbeat_ts", "heartbeat": hb}
    age = NOW - ts
    status = hb.get("status")
    if status == "running" and age < STALE_GRACE:
        return True, {"reason": "ok", "age_s": round(age), "heartbeat": hb}
    return False, {"reason": "stale_or_down", "age_s": round(age), "status": status, "heartbeat": hb}


def _force_restart():
    """强杀陈旧实例 + 清锁 + 触发 GoldEvo24x7 重启；失败则直接拉起。写 evo_regulator_state。"""
    pid = _read_lock_pid()
    killed = False
    if pid and _pid_alive(pid):
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, text=True, timeout=15)
            killed = True
            _log("INFO", "监管哨兵强杀陈旧监督器 PID=%d" % pid)
        except Exception as e:
            _log("WARN", "强杀 PID=%d 失败: %s" % (pid, e))
    # 清锁，让新实例能拿到锁
    try:
        if os.path.exists(LOCK):
            os.remove(LOCK)
    except Exception:
        pass
    # 优先经已注册任务重启
    restarted = False
    try:
        r = subprocess.run(["schtasks", "/Run", "/TN", TASK_NAME],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            restarted = True
            _log("INFO", "已触发计划任务 %s 重启监督器" % TASK_NAME)
    except Exception as e:
        _log("WARN", "schtasks /Run 异常: %s" % e)
    # 兜底：任务触发失败则直接拉起
    if not restarted:
        try:
            env = os.environ.copy()
            env["TMPDIR"] = r"E:\workbuddy\tmp"
            env["TEMP"] = r"E:\workbuddy\tmp"
            env["TMP"] = r"E:\workbuddy\tmp"
            logf = os.path.join(STATE_DIR, "evo_console.log")
            subprocess.Popen(
                [PY, SUPERVISOR],
                cwd=ROOT, env=env,
                stdout=open(logf, "a", encoding="utf-8"),
                stderr=subprocess.STDOUT,
                creationflags=0x00000008)  # DETACHED_PROCESS
            restarted = True
            _log("INFO", "兜底：直接分离式拉起监督器")
        except Exception as e:
            _log("ERROR", "兜底拉起失败: %s" % e)
    # 等恢复（最多 30s）
    recovered = False
    for _ in range(30):
        time.sleep(1)
        ok, det = _assess()
        if ok:
            recovered = True
            break
    state = {
        "last_action": "force_restart",
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "killed_pid": pid if killed else None,
        "via_task": restarted,
        "recovered": recovered,
        "detail": det,
    }
    try:
        with open(REG_STATE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    if not recovered:
        _log("ALERT", "强制重启后 30s 仍未恢复 → 升级通知 chief/Hermes（监督器持续异常）")
    return recovered


def run(check_only=False):
    ok, det = _assess()
    if ok:
        _log("OK", "监督器健康 | 心跳age=%ss cycle=%s tactic=%s"
             % (det.get("age_s"), det.get("heartbeat", {}).get("cycle"),
                det.get("heartbeat", {}).get("tactic")))
        # 写监管自身心跳
        try:
            with open(REG_STATE, "w", encoding="utf-8") as f:
                json.dump({"status": "regulator_ok", "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                           "supervisor_age_s": det.get("age_s"),
                           "supervisor_cycle": det.get("heartbeat", {}).get("cycle")},
                          f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return 0
    # 不健康
    _log("WARN", "监督器不健康: %s" % json.dumps(det, ensure_ascii=False))
    if check_only:
        _log("INFO", "--check 模式：仅报告不重启")
        return 1
    rec = _force_restart()
    return 0 if rec else 2


def status():
    ok, det = _assess()
    print(json.dumps({"healthy": ok, **det}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--status":
        sys.exit(status())
    if arg == "--check":
        sys.exit(run(check_only=True))
    sys.exit(run())
