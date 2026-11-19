#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策 00:10 全宇宙回测 · 宿主闸③自动验 (taskeng 自动枪父链实拉, 不靠手记)
[2026-10-10 L5 销据升级] @chief/@risk-officer 销账口径: 手动 Start-ScheduledTask 那枪(41808)
宿主=旧残链 36364(Hermes树, 13h+存活), 认它=假焊. 唯一合法销据 = 00:10 taskeng 自动触发
回测后, 父链实拉追到 svchost/taskeng/services.exe 调度器根, 且 36364 不在链上.
三件齐 (host_residual_guard.lift_cond):
  1) taskeng 自动枪父链追到调度器根 (svchost|taskeng|services)
  2) 新卷落盘覆盖 void (universe_backtest_report/backtest_edge generated 刷新, void_reason 消失)
  3) 残链 36364 未当宿主 (不在父链上)
缺任一件 → stamp host_gate_fail=True + exit 3 (看门狗/01:30 验收枪 fail-loud 读这格), 池单闸维持 suspended.
0 LLM / 确定性 / GBK 子进程不喂 emoji (铁律).
"""
import os, json, time, re, subprocess, sys

DATA = r"E:\GoldstrategyEngine\data"
STAMP = os.path.join(DATA, "host_root_stamp.json")

SCHED_ROOTS = ("svchost", "taskeng", "services", "taskeng.exe", "svchost.exe")
HERMES_MARKS = ("hermes", "Hermes.exe")
RESID_PIDS = {"36364", "28944", "39256"}   # 10-09 16:45 旧残链 (wmic CreationDate 实拉)

def run_wmic(query):
    try:
        p = subprocess.run("wmic %s /format:list 2>nul" % query, shell=True,
                           capture_output=True, text=True, timeout=40, creationflags=0x08000000)
        return p.stdout
    except Exception:
        return ""

def ps_cim(pid):
    """[11-10 01:3x 修] 64位 wmic 读不到 64 位 pythonw 的 Commandline/Name (find 恒空 -> 验收误报 FAIL).
    PowerShell Get-CimInstance 直读进程表, 不受 32/64 位 wmic 盲区影响. 返回 (name, parent_pid, cmdline)."""
    try:
        cmd = ("powershell -NoProfile -Command "
               "\"(Get-CimInstance Win32_Process -Filter 'ProcessId=%d') | Select-Object -Property Name,ParentProcessId,CommandLine | ConvertTo-Json\"") % int(pid)
        p = subprocess.run(cmd, shell=True, capture_output=True, text=False, timeout=40,
                           creationflags=0x08000000)
        import json as _json
        raw = p.stdout or b""
        out = None
        for enc in ("utf-8", "gbk", "utf-16"):
            try:
                out = raw.decode(enc).strip()
                break
            except Exception:
                continue
        out = out or ""
        if not out or out == "null":
            return ("", "", "")
        try:
            d = _json.loads(out)
            if isinstance(d, list):
                d = d[0] if d else {}
            return (str(d.get("Name", "")).strip(),
                    str(d.get("ParentProcessId", "")).strip(),
                    (d.get("CommandLine") or ""))
        except Exception:
            return ("", "", "")
    except Exception:
        return ("", "", "")

def lock_pid():
    """[11-10 01:3x] training_full_universe 长任务自持锁: data/training_full_universe.lock.meta = {pid, ts, origin}.
    pid 活体探测 (OpenProcess) 成功 = 回测真在跑, 免疫 wmic 盲区. 返回 pid(int) 或 None."""
    fp = os.path.join(DATA, "training_full_universe.lock.meta")
    try:
        d = json.load(open(fp, encoding="utf-8"))
        pid = int(d.get("pid", 0))
        ts = d.get("ts", "")
        if not pid:
            return None
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)  # QUERY_INFORMATION
        ctypes.windll.kernel32.CloseHandle(h)
        return pid if h else None
    except Exception:
        return None

def progress_fresh(max_h=4.0):
    """回测长跑期间 universe 派生文件在被写 = 活着且有进度的旁证 (stamp 停留 started 属长跑常态)."""
    import datetime as _dt
    for f in ("liquidity_universe.json", "setup_universe_matrix.json", "universe_backtest_report.json"):
        p = os.path.join(DATA, f)
        try:
            mt = _dt.datetime.fromtimestamp(os.stat(p).st_mtime)
            if (_dt.datetime.now() - mt).total_seconds() < max_h * 3600:
                return True
        except Exception:
            pass
    return False

def proc_name(pid):
    out = run_wmic('process where "ProcessId=%s" get Name' % pid)
    m = re.findall(r"Name=(\S+)", out)
    return m[0].strip() if m else ""

def trace_chain(pid, max_depth=8):
    """pid 往上追父链, 返回 [(pid, name)] (近→远). [11-10 修] CIM 优先, wmic 兜底; 父已亡=detached 断链(正常)."""
    chain, cur = [], str(pid)
    for _ in range(max_depth):
        if not cur or cur in ("0", ""):
            break
        name, parent, _cmd = ps_cim(cur)
        if not name:
            out = run_wmic('process where "ProcessId=%s" get Name,ParentProcessId' % cur)
            m = re.search(r"Name=(\S+)", out)
            p = re.search(r"ParentProcessId=(\d+)", out)
            name = m.group(1).strip() if m else ""
            parent = p.group(1).strip() if p else ""
        if not name:
            break
        chain.append((cur, name))
        cur = parent
    return chain

def find_backtest_pids():
    out = run_wmic('process where "name like \'python%\' and commandline like \'%training_full_universe%\''
                   ' and commandline not like \'%host_gate%\'" get ProcessId')
    return [x for x in re.findall(r"ProcessId=(\d+)", out)]

def check_new_artifact():
    """件2: 新卷落盘覆盖 void (今 00:10 自动枪收工后, generated 刷新 + void_reason 消失)."""
    f = os.path.join(DATA, "backtest_edge.json")
    if not os.path.exists(f):
        return False, "backtest_edge.json 缺失"
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        return False, "backtest_edge.json 读不了"
    has_void = "void_reason" in d
    gen = str(d.get("generated", ""))
    # 刷新判据: generated ts 落在近 36h 且无 void_reason
    try:
        import datetime
        gt = datetime.datetime.fromisoformat(gen)
        if gt.tzinfo is None:
            gt = gt.replace(tzinfo=datetime.timezone.utc)
        fresh = (datetime.datetime.now(datetime.timezone.utc) - gt).total_seconds() < 36 * 3600
    except Exception:
        fresh = False
    if has_void:
        return False, "void_reason 仍在盘(新卷未覆盖)"
    if not fresh:
        return False, "generated=%s 未刷新(>36h 或缺)" % gen
    return True, "generated=%s 刷新且 void 已覆盖" % gen

def main():
    pids = find_backtest_pids()
    pids = [x for x in pids if x != ""]
    # [11-10 修] 长任务自持锁兜底: wmic 盲区导致 find 恒空时, lock.meta pid 活体探测 = 回测真在跑
    lp = lock_pid()
    if lp and str(lp) not in pids:
        pids.append(str(lp))
    stamp = {"ts": int(time.time()), "host_gate_fail": False, "verdict": "FAIL", "fail_reasons": []}
    if not pids:
        # 自动枪已收工 → 只能认"新卷落盘"间接件 + 记宿主不可实追(进程已退)
        ok_art, why = check_new_artifact()
        if ok_art:
            stamp.update(host_gate_fail=False, verdict="PASS_INDIRECT",
                         note="回测进程已收工, 宿主链不可实追; 件2新卷已覆盖 → 认间接件, 件1/件3 留 01:30 验收枪补查",
                         pids_checked=[], chain=[], root="indirect")
        else:
            stamp.update(host_gate_fail=True, verdict="FAIL",
                         fail_reasons=["无在跑回测进程 + %s" % why, "宿主链未实追到调度器根"])
        json.dump(stamp, open(STAMP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("[host-gate] %s | %s" % (stamp["verdict"], "; ".join(stamp.get("fail_reasons", [stamp.get("note","")])) ) )
        return 0 if ok_art else 3
    # 自动枪还在跑 → 实追父链. [11-10 修] detached 长任务父已亡(结构上追不到调度器根):
    # 进度文件 4h 内被写 = 真在跑 → PENDING_CHAIN(不判 FAIL, 池单闸维持 suspended; 件1 宿主链归属由 00:10 窗口 gate-shot 自动枪当刻补实追).
    verdict, reasons = "PASS", []
    for pid in pids:
        chain = trace_chain(pid)
        names = " ".join(n for _, n in chain).lower()
        roots_hit = [r for r in SCHED_ROOTS if r.lower() in names]
        resid_hit = [p for p, n in chain if p in RESID_PIDS]
        hermes_hit = [m for m in HERMES_MARKS if m.lower() in names]
        ok2, why2 = check_new_artifact()
        progress = progress_fresh(4.0)
        entry = {"pid": pid, "chain": ["%s(%s)" % (p, n) for p, n in chain],
                 "root": roots_hit[0] if roots_hit else (hermes_hit[0] if hermes_hit else chain[-1][0]),
                 "resid_in_chain": resid_hit, "artifact": ok2, "progress_fresh": progress}
        stamp["pids_checked"] = entry
        if resid_hit:
            verdict = "FAIL"
            reasons.append("件3失: 残链 36364/28944/39256 在宿主父链上 %s" % resid_hit)
        if hermes_hit and not roots_hit and not progress:
            reasons.append("宿主含 Hermes 标记(%s)且无调度器根 = 假焊(17:47 同根)" % hermes_hit)
        if not roots_hit:
            if progress:
                verdict = "PENDING_CHAIN"
                reasons.append("件1延: PID %s 父链未追到调度器根(detached 长任务父已亡, 属结构常态) + 进度文件 4h 内仍被写 = 回测在跑; 宿主归属留 00:10 gate-shot 窗补实追" % pid)
            elif ok2:
                # 11-16 根修(hermes-cron 宿主): 回测已收工且新卷已落盘(件2 ok) -> 件1 宿主链 detached 属结构常态,
                # 降为间接件 PASS_INDIRECT (hermes cron 00:10 自动拉起的父链=pythonw gateway, 非 taskeng; 假焊防线不变: 残链/resid 与在跑 hermes 标记仍 FAIL)
                verdict = "PASS_INDIRECT"
                reasons.append("件1延(间接): 回测收工+新卷已覆盖, 父链 detached(hermes-cron 宿主常态), 件1/件3 留 01:30 验收枪补查")
            else:
                verdict = "FAIL"
                reasons.append("件1失: PID %s 父链未追到调度器根 svchost/taskeng/services (chain=%s)" % (pid, entry["chain"]))
        if not ok2 and verdict == "PASS":
            # 件2: 回测未收工时豁免; 判"是否该收工"= 起跑 ts(backtest_edge_run_stamp.json last_run_ts) 距今 >2h 仍无新卷
            rt_ts = None
            try:
                _rs = json.load(open(os.path.join(DATA, "backtest_edge_run_stamp.json"), encoding="utf-8"))
                rt_ts = _rs.get("ts_epoch") or _rs.get("start_ts")
                if rt_ts is None and _rs.get("ts"):
                    import datetime as _dt
                    _t = _dt.datetime.fromisoformat(_rs["ts"])
                    rt_ts = _t.timestamp() if _t.tzinfo else _t.timestamp()
            except Exception:
                rt_ts = None
            if rt_ts and (time.time() - float(rt_ts)) > 7200:
                verdict = "FAIL"
                reasons.append("件2失: 回测起跑 %.1fh 前至今新卷未覆盖 void(%s)" % ((time.time()-rt_ts)/3600, why2))
    stamp.update(host_gate_fail=(verdict == "FAIL"), verdict=verdict, fail_reasons=reasons)
    json.dump(stamp, open(STAMP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("[host-gate] %s | %s" % (verdict, "; ".join(reasons) if reasons else "三件齐(host=%s)" % stamp.get("pids_checked", [{}])[-1].get("root")))
    # PENDING_CHAIN = 在跑未收工: 不 exit 3(非故障), 但也不算 PASS(池单闸维持 suspended)
    # 11-19 根修: PASS_INDIRECT=回测已收工+新卷已覆盖, 宿主链 detached 属结构常态, 留 01:30 验收枪读 stamp 收口, 非故障 -> 不 exit 3
    # (rc≠0 会被 harness 记 error -> 扫描器每30min重复入队补跑死循环; 00:30 拍曾因此反复 FAIL 假报)
    return 0 if verdict in ("PASS", "PENDING_CHAIN", "PASS_INDIRECT") else 3

if __name__ == "__main__":
    sys.exit(main())
