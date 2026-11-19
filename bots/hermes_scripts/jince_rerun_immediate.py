#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""金策·任务即时启动机制 (李11-16令: 别因一个限流就不干活了)
扫 jobs.json: 任何 last_status in (error, delivery_failed) 且 24h 内失败 的任务
-> 写 rerun_request.json (由 30min 轻量哨消费, 对脚本型任务直接补跑, LLM 型任务经 cron 补跑)
限流: 同任务 30min 内只请求 1 次 (rerun_state.json), 防 429 风暴.
确定性 0 LLM; no_agent stdout 静默=无请求, 有请求=列清单."""
import json, os, time, datetime as dt

JOBS = "E:/workbuddy/国外模型/hermes/cron/jobs.json"
STATE = "E:/GoldstrategyEngine/data/rerun_state.json"
REQ = "E:/GoldstrategyEngine/data/rerun_request.json"
TZ = dt.timezone(dt.timedelta(hours=8))
RETRY_GAP = 1800  # 30min 限流


def main():
    jobs = json.load(open(JOBS, encoding="utf-8"))
    flat = []
    if isinstance(jobs, dict):
        for v in jobs.values():
            if isinstance(v, list):
                flat += v
            else:
                flat.append(v)
    else:
        flat = jobs
    st = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {}
    now = time.time()
    reqs = []
    for j in flat:
        if not isinstance(j, dict):
            continue
        js = str(j.get("id"))
        ls = j.get("last_status")
        if ls not in ("error", "delivery_failed"):
            continue
        lr = j.get("last_run_at") or ""
        try:
            t = dt.datetime.fromisoformat(lr).timestamp()
            if now - t > 86400:
                continue  # 只救 24h 内
        except Exception:
            continue
        last_retry = st.get(js, {}).get("last_retry", 0)
        if now - last_retry < RETRY_GAP:
            continue  # 30min 限流
        st[js] = dict(last_retry=now, reason=ls, err=str(j.get("last_error", ""))[:150], name=j.get("name"))
        reqs.append(dict(id=js, name=j.get("name"), status=ls, err=str(j.get("last_error", ""))[:120],
                         script=j.get("script"), no_agent=j.get("no_agent"), ts=dt.datetime.now(TZ).strftime("%F %T")))
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if reqs:
        json.dump(dict(ts=dt.datetime.now(TZ).strftime("%F %T"), reqs=reqs), open(REQ, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        for r in reqs:
            print("补跑请求: %s (%s) %s" % (r["name"], r["status"], r["err"][:60]))
    # 无请求 = 静默 (watchdog 模式)


if __name__ == "__main__":
    main()
