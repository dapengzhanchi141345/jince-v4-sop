#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策·任务续跑检测器 (no_agent, 0 LLM, 429-proof, 稳定输出)
配合 hermes cron 的 --monitor-script: 每 tick 先跑本脚本, 输出"到点该续跑的任务"签名。
  输出字节不变 → 该 agent 运行被完全抑制(不烧 LLM、不撞 429);
  输出变了(有任务到点/该跑没跑) → 才叫醒执行器"从断点接着干"。

治"工作被 429/崩溃/超时打断就停"的核心:
  台账 task_ledger.json 记每个任务 state + checkpoint + next_retry_at + retries + period。
  本脚本每 tick 扫台账, 两类"该续":
    A. 阻断态(blocked_429/blocked/paused/pending_resume) 且 next_retry_at<=now 且 未超重试上限
    B. 正常 running 但 超周期没更新 last_done 戳(=该跑没跑/静默漏跑)
  输出=到点任务的确定签名(排序、无时间戳) → 连续 tick 不变则被抑制。

执行器(agent cron, 带本脚本作 monitor)续跑后:
  成功→state=done, last_done=now, retries=0;
  再断→state=blocked, next_retry_at=now+指数退避(10min*2^retries), retries+1;
  retries>=MAX_RETRY=3 → state=needs_human(停止自动续, 只投群报"卡死需你")。

用法:
  python jince_task_resume_monitor.py           # 打稳定签名(供 cron --monitor-script, 无时间戳)
  python jince_task_resume_monitor.py --due     # 人读: 列到点/漏跑任务
输出铁律: 稳定、无时间戳、无随机, 保证"不变则抑制"。trading 类任务: 检测器照报, 但执行器只更新台账+投群, 不真挂单(仍走P4闸)。
"""
import os, json, sys, time, datetime, zoneinfo

LEDGER = r"E:/GoldstrategyEngine/data/task_ledger.json"
BJT = zoneinfo.ZoneInfo("Asia/Shanghai")
MAX_RETRY = 3
# 2026-10-06 用户令"打断的任务没说不做必须有重启机制": interrupted=被新指令打断且未明确说"不做了",
# 一律登记此状态, 执行器按 next_retry_at 自动重启(默认=被断时刻+10min, 用户回来可改)。
BLOCKED_STATES = ("blocked_429", "blocked", "paused", "pending_resume", "interrupted")


def load():
    try:
        d = json.load(open(LEDGER, encoding="utf-8"))
        return d.get("tasks", []), d.get("meta", {})
    except Exception:
        return [], {}


def ts_epoch(s):
    if not s:
        return 0
    try:
        return datetime.datetime.fromisoformat(s).timestamp()
    except Exception:
        return 0


def is_due_blocked(t, now_epoch):
    if t.get("state") not in BLOCKED_STATES:
        return False
    if t.get("retries", 0) >= MAX_RETRY:
        return False  # 已转 needs_human 处理
    nr = t.get("next_retry_at")
    return nr is not None and ts_epoch(nr) <= now_epoch


def is_overdue_running(t, now_epoch):
    """running 但超周期(last_done + period_min)没更新戳 = 漏跑该续。
    仅对 auto_ok class 报(如 research/ops/content/infra); trading 由全链30min自管。"""
    if t.get("state") != "running":
        return False
    period_min = t.get("period_min")
    if not period_min:
        return False
    last = ts_epoch(t.get("last_done"))
    if last <= 0:
        return True  # 从没跑成 → 该续
    return (now_epoch - last) > period_min * 60


def due_list(tasks, now_epoch):
    out = []
    for t in tasks:
        why = []
        if is_due_blocked(t, now_epoch):
            why.append("blocked_due")
        if is_overdue_running(t, now_epoch):
            why.append("overdue")
        if why:
            out.append((t, why))
    return out


def signature(tasks, now_epoch):
    dt = due_list(tasks, now_epoch)
    if not dt:
        return "READY=0"
    sig = []
    for t, why in sorted(dt, key=lambda x: str(x[0].get("task_id"))):
        sig.append("%s|%s|%s|%s|%s" % (
            t.get("task_id"), t.get("class", "?"),
            ",".join(why), t.get("retries", 0), t.get("checkpoint", "-")))
    return "READY=%d\n" % len(sig) + "\n".join(sig)


def main():
    tasks, meta = load()
    now_epoch = time.time()
    if "--due" in sys.argv:
        dt = due_list(tasks, now_epoch)
        now_iso = datetime.datetime.now(BJT).replace(microsecond=0).isoformat()
        print("[金策任务续跑] BJT=%s 该续=%d (台账任务共 %d)" % (now_iso, len(dt), len(tasks)))
        for t, why in sorted(dt, key=lambda x: str(x[0].get("task_id"))):
            print("  - %s [%s] %s 断点=%s 重试=%s last_done=%s" % (
                t.get("task_id"), t.get("class"), "/".join(why),
                t.get("checkpoint"), t.get("retries", 0), t.get("last_done")))
        return
    print(signature(tasks, now_epoch))


if __name__ == "__main__":
    main()
