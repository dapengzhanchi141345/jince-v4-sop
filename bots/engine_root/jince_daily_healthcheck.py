#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策·每日全面深度体检 (no_agent, 0 LLM, 429-proof, 每天 03:00 挂 cron 自转)
用户 2026-10-06 令: "以后每天凌晨3全面深度体检, 建立健全完善机制"。

七项检查(复刻 2026-10-05 人工体检, 固化成自动):
 1) 全链心跳: auto_cycle.log 末行是否 [全链自动运行完成] 且 2h 内(30min 全链周期, 超 2h=静默死)
 2) 节点逐个验: 对 9 个节点 py_compile + 实跑(带 auto_run_cycle 同款真实 cwd), 记录 exit
 3) JSON 全量合法性: data/*.json 逐个 json.load, 坏的=危险
 4) 误归档防线(2026-10-05 踩坑固化): 扫所有 .py 引用的 .json, 凡"实时引用但只在 _archive 里"→自动回血
 5) 坏账本自修(2026-10-05 踩坑固化): 被实时 .py 引用的 json 若不可解析→备份后清成合法空壳(防读取端崩);
    不被引用的历史文件不碰(只列名报告)
 6) 429 委托池体检: 扫最近 24h 委托 live 日志 429 次数, 超限=提醒(池额度问题, 记 task_ledger infra)
 7) 看板生成器 py_compile(防 high_n 那种"子代理留 bug 没人验"再发生)

闭环: 凡是"需要动脑修"的项(节点实跑失败等)→写 task_ledger.json 一条 blocked 任务
      (next_retry_at=now, 每30min 续跑执行器自动接手从断点续); 确定性安全项当场修好。
红线: 不碰挂单真闸/撤单/交易配置; 节点实跑=复刻 30min 全链本来就在跑的动作, 不引入新行为;
      fail-open: 本脚本任何一步崩→整段 try/except, 报告照出, 不静默; GBK 安全: 只 print 汉字+ASCII, 无 emoji。
产出: stdout=一页大白话报告(投群); data/healthcheck_last.json=机读结果(供 2h 效率播报/看板引用)。
"""
import os, sys, json, time, glob, shutil, subprocess, datetime, zoneinfo, re

ROOT = r"E:/GoldstrategyEngine"
DATA = os.path.join(ROOT, "data")
PY = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/pythonw.exe"
LEDGER = os.path.join(DATA, "task_ledger.json")
HC_OUT = os.path.join(DATA, "healthcheck_last.json")
DELEG_LIVE = r"E:/workbuddy/国外模型/hermes/cache/delegation/live"
BJT = zoneinfo.ZoneInfo("Asia/Shanghai")

# 节点表: (名称, 脚本相对路径, 工作目录相对 ROOT, 超时秒) — 与 auto_run_cycle.py 同款真实配置
NODES = [
    ("快照", "mt5_snapshot_write.py", ROOT, 120),
    ("CIO", "multi_agent/cio_orchestrator.py", os.path.join(ROOT, "multi_agent"), 600),
    ("币圈", "multi_agent/trading/crypto_pending.py", os.path.join(ROOT, "multi_agent", "trading"), 600),
    ("股指", "multi_agent/trading/equity_pending.py", os.path.join(ROOT, "multi_agent", "trading"), 600),
    ("总督", "multi_agent/trading/portfolio_governor.py", os.path.join(ROOT, "multi_agent", "trading"), 600),
    ("体温表", "write_risk_state.py", ROOT, 60),
    ("进化", "multi_agent/trading/meta_evolver.py", os.path.join(ROOT, "multi_agent", "trading"), 600),
    ("研判", "multi_agent/trading/daily_advisory.py", os.path.join(ROOT, "multi_agent", "trading"), 900),
    ("事件闸", "event_guard.py", ROOT, 120),
]
ALL_PY = [os.path.join(ROOT, "auto_run_cycle.py")] \
    + [os.path.join(ROOT, n[1]) for n in NODES] \
    + [os.path.join(ROOT, "multi_agent", "trading", "dashboard_gen.py")] \
    + [os.path.join(ROOT, "event_guard.py")]


def now_iso():
    return datetime.datetime.now(BJT).replace(microsecond=0).isoformat()


def scan_json_refs():
    """扫所有实时 .py 引用的 .json 文件名(=实时账本全集, 2026-10-05 归档踩坑的正确判据)。"""
    refs = set()
    pats = [re.compile(r'[\'"]([a-zA-Z0-9_\-\.\/]+\.json)[\'"]')]
    for py in ALL_PY:
        try:
            src = open(py, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for m in pats[0].findall(src):
            refs.add(os.path.basename(m))
    return refs


def _next_fullchain_beat():
    """[2026-11-13 03:0x 根治口径误报·同jince_heartbeat_watch 21:4x同根因]
    全链=金策宗师团·全链扫描 job(cron 45 13,18,21 * * 1-5 工作日三定点, 空窗最长15h),
    旧 chk 拿'120分钟死窗'量 -> 22:31末拍后03:0x体检(4.5h空窗内)必误报异常(11-13 03:01实证).
    动态读该job的cron表达式算下一拍时刻; 读不到fail-open回退120min旧口径(不漏真故障).
    """
    import json as _json
    try:
        jobs = _json.load(open(r"E:/workbuddy/国外模型/hermes/cron/jobs.json", encoding="utf-8"))
        jl = jobs if isinstance(jobs, list) else jobs.get("jobs", [])
        for j in jl:
            if "全链扫描" in str(j.get("name", "")):
                expr = (j.get("schedule") or {}).get("expr") or (j.get("schedule") if isinstance(j.get("schedule"), str) else None) or "45 13,18,21 * * 1-5"
                # cron 5段: [分, 时, 日, 月, 周] -> 分=parts[0], 时=parts[1], 周=parts[4] (parts[2]是"日"字段, 误读致int("*")崩)
                parts = expr.split()
                mins, hrs = int(parts[0]), [int(x) for x in parts[1].split(",")]
                dow = set()
                for part in parts[4].split(","):
                    if "-" in part:
                        a, b = part.split("-"); dow.update(range(int(a), int(b) + 1))
                    else:
                        dow.add(int(part))
                now = datetime.datetime.now(BJT)
                for off in range(0, 9):
                    dd = now + datetime.timedelta(days=off)
                    pyday = dd.isoweekday()  # 1=Mon..7=Sun
                    if dow and pyday not in dow:
                        continue
                    for h in hrs:
                        cand = dd.replace(hour=h, minute=mins, second=0, microsecond=0)
                        if cand > now:
                            return cand
                return None
    except Exception:
        return None


def chk_1_cycle_heartbeat():
    out = {"ok": False, "detail": "auto_cycle.log 不存在"}
    p = os.path.join(DATA, "auto_cycle.log")
    try:
        raw = open(p, encoding="utf-8", errors="replace").read()
        i = raw.rfind("[全链自动运行完成]")
        if i >= 0:
            seg = raw[i:i + 60]
            m = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", seg)
            if m:
                ts = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=BJT)
                age_min = (datetime.datetime.now(BJT) - ts).total_seconds() / 60
                # 动态口径: 全链三定点拍(13/18/21:45工作日), 下一拍+90min容差前不算超窗;
                # 超过下一拍+90min 且该拍后无新完成行 = 真漏拍(点名); fail-open: 排班读不到=旧120min口径
                nb = _next_fullchain_beat()
                if nb is None:
                    ok = age_min <= 120
                    why = "末次全链 %s (距今 %.0f 分, 排班读不到按旧120min口径)" % (m.group(1), age_min)
                elif datetime.datetime.now(BJT) > nb + datetime.timedelta(minutes=90):
                    ok = ts >= nb  # 下一拍时刻之后有新完成行才算没漏
                    why = "末次全链 %s (应拍 %s 后%.0fmin, %s)" % (m.group(1), nb.strftime("%m-%d %H:%M"),
                              (datetime.datetime.now(BJT) - nb).total_seconds() / 60, "补拍在" if ok else "真漏拍")
                else:
                    ok = True
                    why = "末次全链 %s (距今 %.0f 分, 下一拍 %s 未到期, 正常)" % (m.group(1), age_min, nb.strftime("%m-%d %H:%M"))
                out = {"ok": ok, "detail": why}
    except Exception as e:
        out["detail"] = "读日志失败: %s" % str(e)[:60]
    return out


def chk_2_nodes():
    # [2026-10-07 根治] 起 ATE 子进程必须剥 PYTHONPATH/PYTHONHOME: cron 跑体检时父进程
    # 是 gateway(3.11 venv), PYTHONPATH 指向 3.11 site-packages, ATE(3.13) 加载 3.11 的
    # numpy C 扩展就崩(numpy._core.multiarray failed to import) -> 4 节点误报红。
    # 同 jince_node.py "ATE 实读 import 坏" 根治写法: 剥这两个 env var, ATE 用它自带的 numpy。
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    res = []
    for name, rel, cwd, tout in NODES:
        sp = os.path.join(ROOT, rel)
        item = {"name": name, "script": rel, "compile": None, "exit": None, "ok": False}
        try:
            r = subprocess.run([PY, "-m", "py_compile", sp], capture_output=True, text=True,
                               timeout=60, env=env)
            item["compile"] = (r.returncode == 0)
        except Exception as e:
            item["compile"] = False
            item["err"] = "compile: %s" % str(e)[:60]
        if item["compile"]:
            try:
                r = subprocess.run([PY, sp], capture_output=True, text=True, cwd=cwd,
                                    timeout=tout, env=env)
                item["exit"] = r.returncode
                item["ok"] = (r.returncode == 0)
                if r.returncode != 0:
                    tail = ((r.stderr or "") + "\n" + (r.stdout or "")).splitlines()
                    bad = [l for l in tail if re.search(r"Error|Exception|Traceback|File \"|No such file", l)]
                    item["err"] = (bad[-1].strip()[:100] if bad else tail[-1][:100])
            except subprocess.TimeoutExpired:
                item["exit"] = -1
                item["err"] = "实跑超时 >%ds" % tout
        res.append(item)
    return res


def chk_3_json_validity():
    bad = []
    for f in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        try:
            json.load(open(f, encoding="utf-8"))
        except Exception as e:
            bad.append({"file": os.path.basename(f), "err": str(e)[:50]})
    return bad


def chk_4_archive_defense(refs):
    """误归档防线: 实时引用但只在 _archive 里的 json → 自动回血(2026-10-05 踩坑固化)。"""
    healed, missing = [], []
    for fn in sorted(refs):
        lp = os.path.join(DATA, fn)
        ap = os.path.join(DATA, "_archive", fn)
        if os.path.exists(ap) and not os.path.exists(lp):
            try:
                shutil.move(ap, lp)
                healed.append(fn)
            except Exception:
                missing.append(fn)
    return healed, missing


def chk_5_bad_ledger_autofix(refs, bad_json):
    """坏账本自修: 被实时 .py 引用的坏 json → 备份后清成合法空壳(防读取端崩);
    不被引用的坏文件 → 只列名不碰(历史留痕, 无读取端)。"""
    fixed, reported = [], []
    for b in bad_json:
        fn = b["file"]
        if fn in refs:
            p = os.path.join(DATA, fn)
            try:
                bak = p + ".bak_%s" % time.strftime("%Y%m%d%H%M%S")
                shutil.copy(p, bak)
                json.dump({"_cleared": now_iso(), "_reason": b["err"], "_backup": os.path.basename(bak)},
                          open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                fixed.append(fn)
            except Exception:
                reported.append(fn + " (清修失败)")
        else:
            reported.append(fn)
    return fixed, reported


def chk_6_429_pool():
    n429, files = 0, 0
    cutoff = time.time() - 86400
    try:
        for d in glob.glob(os.path.join(DELEG_LIVE, "deleg_*")):
            for f in glob.glob(os.path.join(d, "task-*.log")):
                if os.path.getmtime(f) < cutoff:
                    continue
                try:
                    raw = open(f, encoding="utf-8", errors="replace").read()
                except Exception:
                    continue
                files += 1
                if re.search(r"HTTP 429|used up today's text quota|rate limit", raw, re.I):
                    n429 += 1
    except Exception:
        pass
    return {"n429_24h": n429, "files_scanned": files}


def chk_7_dashboard_gen():
    p = os.path.join(ROOT, "multi_agent", "trading", "dashboard_gen.py")
    r = subprocess.run([PY, "-m", "py_compile", p], capture_output=True, text=True, timeout=60)
    return {"ok": r.returncode == 0, "err": (r.stderr or "").strip()[:120] if r.returncode else ""}


def register_blocked_task(task_id, klass, checkpoint, last_error):
    """需要动脑的失败项 → 登记 task_ledger 一条 blocked 任务, 交给每30min续跑执行器自动接手(不静默)。"""
    try:
        d = json.load(open(LEDGER, encoding="utf-8"))
        tasks = d.setdefault("tasks", [])
        rec = {"task_id": task_id, "class": klass, "state": "blocked",
               "checkpoint": checkpoint, "last_error": str(last_error)[:120],
               "retries": 0, "period_min": None, "last_done": None,
               "next_retry_at": now_iso(), "note": "03:00 每日体检自动登记, 续跑执行器接手"}
        for t in tasks:
            if t.get("task_id") == task_id:
                rec["retries"] = int(t.get("retries", 0))
                break
        else:
            tasks.append(rec)
        tmp = LEDGER + ".tmp"
        json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmp, LEDGER)
        return True
    except Exception:
        return False


def main():
    report = {"ts": now_iso(), "checks": {}, "auto_fixed": [], "registered_tasks": []}
    refs = scan_json_refs()
    c1 = chk_1_cycle_heartbeat()
    nodes = chk_2_nodes()
    bad_json = chk_3_json_validity()
    healed, miss_heal = chk_4_archive_defense(refs)
    fixed5, rep5 = chk_5_bad_ledger_autofix(refs, bad_json)
    c6 = chk_6_429_pool()
    c7 = chk_7_dashboard_gen()
    report["checks"] = {
        "cycle_heartbeat": c1, "nodes": nodes,
        "json_bad_after_autofix": rep5, "archive_misfile_unhealed": miss_heal,
        "pool_429": c6, "dashboard_gen": c7,
    }
    report["auto_fixed"] = sorted(set(healed + fixed5))

    # 需要动脑的项 → 登记 task_ledger(交给 30min 续跑执行器)
    for nd in nodes:
        if not nd["ok"]:
            ok = register_blocked_task("hc_node_" + nd["name"], "infra",
                                       "节点 %s 实跑失败(03:00体检), 断点=修此节点" % nd["name"],
                                       nd.get("err", "exit=%s" % nd.get("exit")))
            if ok:
                report["registered_tasks"].append("hc_node_" + nd["name"])
    if not c1["ok"]:
        ok = register_blocked_task("hc_cycle_heartbeat", "infra",
                                   "全链心跳超 2h 静默, 断点=查 auto_cycle.log+计划任务+gateway",
                                   c1["detail"])
        if ok:
            report["registered_tasks"].append("hc_cycle_heartbeat")
    if c6["n429_24h"] >= 3:
        ok = register_blocked_task("hc_429_pool", "infra",
                                   "24h 内 %d 个委托撞 429, 断点=检查免费池/加错峰/确认 max_concurrent_children=2" % c6["n429_24h"],
                                   "429 超限")
        if ok:
            report["registered_tasks"].append("hc_429_pool")

    # 机读结果落盘
    tmp = HC_OUT + ".tmp"
    json.dump(report, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, HC_OUT)

    # 大白话报告(GBK 安全: 无 emoji)
    ok_nodes = sum(1 for n in nodes if n["ok"])
    lines = ["[金策每日体检 03:00] BJT %s" % now_iso()[11:16]]
    lines.append("- 全链心跳: %s (%s)" % ("正常" if c1["ok"] else "异常", c1["detail"][:40]))
    lines.append("- 节点实跑: %d/%d 绿" % (ok_nodes, len(nodes)))
    for n in nodes:
        if not n["ok"]:
            lines.append("  红: %s -> %s" % (n["name"], n.get("err", "exit=%s" % n.get("exit"))[:80]))
    lines.append("- 数据文件: 实时引用 %d 个 json; 误归档回血 %d 个; 坏账本清修 %d 个; 历史坏文件 %d 个(不碰)"
                 % (len(refs), len(healed), len(fixed5), len(rep5)))
    lines.append("- 委托池: 24h 撞 429 次数=%d" % c6["n429_24h"])
    lines.append("- 看板生成器: %s" % ("编译过" if c7["ok"] else "编译失败 " + c7["err"][:60]))
    lines.append("- 自动登记待修: %s" % (", ".join(report["registered_tasks"]) if report["registered_tasks"] else "无(30min续跑执行器会接手)"))
    all_ok = c1["ok"] and ok_nodes == len(nodes) and c7["ok"] and not rep5 and c6["n429_24h"] < 3
    lines.append("- 总判: " + ("全绿" if all_ok else "有项待修(已登记, 自动续, 交易零影响)"))
    print("\n".join(lines))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # 最外层 fail-open: 体检自己崩也不能静默
        try:
            json.dump({"ts": now_iso(), "fatal": str(e)[:200]},
                      open(HC_OUT + ".tmp", "w", encoding="utf-8"), ensure_ascii=False)
            os.replace(HC_OUT + ".tmp", HC_OUT)
        except Exception:
            pass
        print("[金策每日体检] 脚本自身异常(fail-open, 已记录): %s" % str(e)[:150])
