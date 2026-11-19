# -*- coding: utf-8 -*-
r"""金策·全链路验证哨 (确定性 0LLM, no_agent cron 每30min, 全绿静默/红报一行)
验证"代码优化真的在执行"——防旧码复活/进程僵尸/数据断链/闸失效。
检查项: ①引擎: magic锁pid活+启动时间>代码mtime(新码在跑)+源码三标记(B0_VOL_K/_regime_gate/per修复)+日志<10min
②L2采集器pid活+tick<5min ③regime/zones 新鲜(<45min) ④MC/VaR 哨产物(<26h, 日频07:45一次) ⑤kill_switch 非TRIGGERED
⑥夜间深研产物存在。红报=stdout一行(投群); 全绿=stdout空。
"""
import json
import os
import subprocess
import time

DATA = "E:/GoldstrategyEngine/data"
TOOLS = "E:/GoldstrategyEngine/tools"
LOGS = "E:/GoldstrategyEngine/logs"
red = []
yellow = []  # [11-16] 黄注: 降级观察项(不红报, 只留痕不进群)


def task(pid):
    r = subprocess.run(["tasklist", "/FI", "PID eq " + str(pid)], capture_output=True, text=True, errors="replace")
    return r.stdout or ""


def main():
    now = time.time()

    def fresh(path, sec):
        try:
            return (now - os.stat(path).st_mtime) < sec
        except Exception:
            return False

    # ① 引擎
    magic_lock = DATA + "/live24_magic_30261103.lock"
    eng_pid = None
    try:
        _lj = json.load(open(magic_lock))
        eng_pid = int(_lj["pid"])
        if now - float(_lj.get("ts_unix", 0)) > 300:
            red.append("引擎心跳>5min(lock ts_unix 过期=主循环假死)")
    except Exception:
        red.append("引擎magic锁读不到(pid缺失)")
    src = open(TOOLS + "/jince_live24.py", encoding="utf-8").read()
    for mk, name in (("B0_VOL_K", "B0量能闸"), ("_regime_gate", "regime门"), ("per = PER_SYMBOL", "per修复")):
        if mk not in src:
            red.append("源码缺%s(优化码被回滚?)" % name)
    if eng_pid:
        alive = "python" in task(eng_pid)
        if not alive:
            red.append("引擎pid=%d 已死(看门狗该拉没拉?)" % eng_pid)
        else:
            st_mtime = os.stat(TOOLS + "/jince_live24.py").st_mtime
            p = subprocess.run(["powershell", "-NoProfile", "-Command",
                                "(Get-Process -Id %d).StartTime" % eng_pid], capture_output=True, text=True, errors="replace")
            out = (p.stdout or "").strip()
            if out:
                try:
                    st_start = time.mktime(time.strptime(out, "%Y-%m-%d %H:%M:%S"))
                    if st_start < st_mtime:
                        red.append("引擎pid=%d 跑旧码(启动%s < 代码改动%s)=热切换未完成" % (
                            eng_pid, time.strftime("%H:%M", time.localtime(st_start)), time.strftime("%H:%M", time.localtime(st_mtime))))
                except Exception:
                    pass
            # [11-15 修] 原判定查 E:/GoldstrategyEngine/logs/live24_stdout.log —— 该文件根本不存在(日志实际在 data/l24_stdout.log, 且引擎静默期合法不写), 每拍必假报.
            # 改三证任一活=引擎在: ①live24 进程在(PID扫描) ②data/l24_stdout.log 30min内写过 ③event_guard.log 10min内写过(事件快通道)
            _eng_alive = False
            try:
                import subprocess as _sp
                _pr = _sp.run('powershell -NoProfile -Command "(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like \'*jince_live24*\' }).Count"', shell=True, capture_output=True, timeout=60)
                if _pr.stdout and _pr.stdout.strip().isdigit() and int(_pr.stdout.strip()) > 0:
                    _eng_alive = True
            except Exception:
                pass
            if not _eng_alive:
                _l24 = DATA + "/l24_stdout.log"
                _evg = DATA + "/event_guard.log"
                _ok_l24 = os.path.exists(_l24) and (time.time() - os.path.getmtime(_l24)) < 1800
                _ok_evg = os.path.exists(_evg) and (time.time() - os.path.getmtime(_evg)) < 600
                if not (_ok_l24 or _ok_evg):
                    red.append("引擎三证全哑: live24进程无/l24_stdout>30min/event_guard>10min (主循环疑似卡死)")
    # ② L2 采集器
    try:
        cp = int(open(DATA + "/l2proxy_collector.pid").read().strip())
        if "python" not in task(cp):
            # [11-16 修] pid 参照陈旧降级: 30min cron 一次性模式 collector 每拍新起子进程, pid 文件常落后一拍;
            # zones/ticks 数据新鲜(<10min)=采集实际正常, 降黄注不红报; 数据也断才是真停摆
            if fresh(DATA + "/l2proxy_zones.json", 600) and fresh(DATA + "/tick_live.json", 40 * 60):
                yellow.append("L2采集器pid=%d 参照陈旧(一次性模式), 数据新鲜=实际正常" % cp)
            else:
                red.append("L2采集器pid=%d 已死 且数据断链(真停摆)" % cp)
        if not fresh(DATA + "/l2proxy_ticks.jsonl", 300):
            red.append("L2 tick流>5min断链")
    except Exception:
        red.append("L2采集器pid文件缺")
    # ③ regime/zones
    if not fresh(DATA + "/regime_state.json", 2700):
        red.append("regime_state>45min未刷新(30min runner哨没跑?)")
    # ④ MC/VaR (日频: 07:45 哨每日一次, 合法静默窗=次日07:45前; 26h=日周期24h+2h容差, 防23:45-07:45误报)
    if not fresh(DATA + "/mc_var_last.json", 26 * 3600):
        red.append("MC/VaR产物>26h(今晨07:45哨没跑?)")
    # ⑤ kill switch
    try:
        ks = json.load(open(DATA + "/kill_switch.json"))
        if ks.get("state") == "TRIGGERED":
            red.append("kill_switch=TRIGGERED 未复位(人工翻ARMED+chief确认?)")
    except Exception:
        pass
    # ⑥ 深研产物(存在性, 缺失=黄但报一行防静默)
    if not os.path.exists(DATA + "/family_deep_study_log.jsonl"):
        red.append("夜间深研log缺失(深研哨没写?)")
    if red:
        print("⚠️ [金策验证哨] " + " | ".join(red))
    if yellow:
        # [11-16] 黄注落留痕不进 stdout(群静默): 降级观察项, 逐条写 sd_guard_run.log
        try:
            with open(DATA + "/sd_guard_run.log", "a", encoding="utf-8") as _f:
                _f.write(__import__("json").dumps({"ts": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"), "kind": "verify哨黄注", "items": yellow}, ensure_ascii=False) + "\n")
        except Exception:
            pass


if __name__ == "__main__":
    main()
