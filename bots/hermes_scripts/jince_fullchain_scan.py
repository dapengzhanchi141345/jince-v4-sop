#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策全链扫描 (11-14 根治版: no_agent 纯脚本 0 LLM)
背景: LLM 驱动版 11-13 起 3 连 interrupted(provider 中断簇, 18:55/18:58/21:45 三拍全丢).
全链扫描本质=跑确定性 auto_run_cycle.py(DRY-RUN 安全铁律 LIVE_TRADING_ENABLED=False)+读日志出简报,
0 LLM 即可, 改纯脚本后永不被 LLM 链路中断.
跑法: 每 13:45/18:45/21:45(工作日) cron no_agent 直跑, stdout=简报投群(bot-chat).
fail-loud: auto_run_cycle 非 0 退出 -> 报一行异常不静默.
"""
import os, subprocess, sys, datetime

ENGINE = r"E:/GoldstrategyEngine"
ATE = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe"
LOG = os.path.join(ENGINE, "data/auto_cycle.log")
BRIEF = os.path.join(ENGINE, "data/pending_orders_brief.md")

def main():
    now = datetime.datetime.now()
    hm = now.strftime("%H:%M")
    # ① 跑全链(DRY-RUN, 600s 上限)
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "PYTHONNOUSERSITE")}
    r = subprocess.run([ATE, "auto_run_cycle.py"], cwd=ENGINE, capture_output=True, text=True,
                       timeout=600, env=env, creationflags=0x08000000)
    tail = ""
    try:
        with open(LOG, encoding="utf-8", errors="ignore") as f:
            lines = f.read().splitlines()
        tail = "\n".join([l for l in lines[-80:] if l.strip()])
    except Exception as e:
        tail = "auto_cycle.log 读取异常: %s" % str(e)[:60]
    brief = ""
    try:
        brief = open(BRIEF, encoding="utf-8", errors="ignore").read().strip()[:1500]
    except Exception:
        brief = "(pending_orders_brief.md 缺)"
    out = ["【金策全链扫描 %s】0 LLM 纯脚本拍(DRY-RUN 不真实开仓)" % hm]
    if r.returncode != 0:
        out.append("⚠️ auto_run_cycle 退出码=%s, stderr 尾: %s" % (r.returncode, (r.stderr or r.stdout or "")[-200:]))
    else:
        out.append("✅ auto_run_cycle 跑完(全链: 数据→看图→事件→研究→交易→风控→挂单部, 残留单处理+DRY-RUN)")
    out.append("· 全链日志尾:")
    out.append(tail[-1800:])
    out.append("· 挂单简报:")
    out.append(brief)
    out.append("· 安全铁律: LIVE_TRADING_ENABLED=False, 平仓只平 magic=20260902 系统单且点差<100点. 历史回测≠未来收益")
    print("\n".join(out))
    return 0

if __name__ == "__main__":
    sys.exit(main())
