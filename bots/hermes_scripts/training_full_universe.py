#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策·训练机制·全宇宙回测后台跑 (每日 00:10 起, 不占 01:30 验收枪).
no_agent 0 LLM, 429-proof. 跑 backtest_engine.py 全宇宙 -> backtest_edge.json
末尾写 backtest_edge_run_stamp.json(生成时戳+品种数+耗时), 供 01:30 验收枪判'有没有新产物'.
另加 引擎自检哨兵: 全宇宙里 胜率>0.9 且 n>500 的腿数 记入 sentinels 字段,
供验收枪判'引擎虚高'事故(>3 条即引擎口径有问题, 验收自动打回).
红线: 历史回测≠未来收益; 只产数据不碰实盘.
"""
import os, json, time, subprocess, datetime, sys
# [2026-10-13 L5-fix] 内核级排他文件锁(msvcrt.locking) 替代 O_EXCL:
#   三次双发实锤 06:50/12:50/13:25 — 我手动补卷 撞 JinCeWatchdog 看门狗周期枪(见 backtest_edge
#   停 06:50 空卷 breadth_pass=False 就自动追打), 两趟 training 相差 25~29ms 各起一个 backtest_engine
#   -> 双引擎霸 IPC copy_rates_from_pos -> 全币 TIMECAP 必空卷. O_EXCL 文件锁有毫秒级 TOCTOU 竞态
#   (两个 wrapper 同窗过锁判), 治不了. 改内核级排他锁: 跨进程互斥、无 TOCTOU、持锁进程死了内核
#   自动释放句柄(彻底免 O_EXCL 的陈旧锁/僵尸锁问题).
try:
    import msvcrt
    _HAS_MSVCRT = True
except ImportError:
    _HAS_MSVCRT = False
# [2026-10-09 修] cron 运行器 reader 按 UTF-8 读本脚本 stdout, 而 cron 环境 locale=GBK ->
#   中文 print 出 0xd3(GBK 字节) 崩 reader 线程(UnicodeDecodeError). 强制 UTF-8 出字节流, 根除.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
ATE = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/pythonw.exe"
ROOT = r"E:\GoldstrategyEngine"
DATA = ROOT + "/data"

# [2026-10-13 L5-fix] 单实例原子锁(治本): taskeng 自动枪/看门狗追打/手动补卷 三个发起方各自探活,
#   12:50 实锤双发(32040 手动 + 4296 自动, 创建差 29ms, 各起一个 backtest_engine -> 双引擎霸 IPC
#   -> 全币 TIMECAP 空卷, 与 06:50 同机制). 锁文件 O_EXCL 原子创建 + PID 验活:
#   - 锁新鲜(<8h) 且持锁 pid 活着 = 有另一枪在跑, 本枪静默让位退出(exit 0, 留痕 log, 不并启);
#   - 锁陈旧(pid 已死或 >8h) = 接管(写新锁). 防竞写探活(wmic 查引擎子进程)仍保留做二次闸.
_LOCK = os.path.join(DATA, "training_full_universe.lock")
_LOCK_META = os.path.join(DATA, "training_full_universe.lock.meta")
_LOCK_TTL_S = 8 * 3600  # 仅非 Windows O_EXCL 回退路径用(内核锁无需 TTL)
_lock_fd = None  # 内核锁须全程持句柄, 关句柄=释放锁; 存全局

def _pid_alive(pid):
    try:
        out = subprocess.run('tasklist /fi "pid eq %d" /fo csv' % pid, shell=True,
                             capture_output=True, timeout=15, creationflags=0x08000000)
        text = (out.stdout or b"").decode("gbk", errors="replace")
        return (str(pid) in text)
    except Exception:
        return True  # 验活失败按活着处理(宁可让位, 不并启)

def _acquire_lock():
    """返回 True=拿到锁, False=有活枪在跑本枪退出."""
    global _lock_fd
    me_pid = os.getpid()
    if _HAS_MSVCRT:
        # [内核级排他锁] msvcrt.locking LK_NBLCK 非阻塞: 抢锁是原子系统调用, 无 O_EXCL 的毫秒 TOCTOU;
        #   持锁进程崩/被杀 -> 内核自动释放句柄 -> 无陈旧锁/僵尸锁, 不需 TTL 验活.
        try:
            fd = os.open(_LOCK, os.O_CREAT | os.O_RDWR)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)  # 抢 1 字节排他锁, 被占立即抛 OSError
        except OSError:
            try:
                os.close(fd)
            except OSError:
                pass
            print("[单实例锁] 内核锁已被占(另一枪在跑), 本枪(pid=%d)让位退出, 不并启第二引擎"
                  "(防双发 TIMECAP 空卷, 06:50/12:50/13:25 教训)" % me_pid)
            return False
        _lock_fd = fd
        try:
            with open(_LOCK_META, "w", encoding="utf-8") as f:
                f.write(json.dumps({"pid": me_pid, "ts": datetime.datetime.now().isoformat(),
                                    "origin": os.environ.get("JINCE_LOCK_ORIGIN", "manual")}))
        except Exception:
            pass
        print("[单实例锁] 内核排他锁已获取 pid=%d origin=%s (锁文件=%s)"
              % (me_pid, os.environ.get("JINCE_LOCK_ORIGIN", "manual"), _LOCK))
        return True
    # [非 Windows 回退] O_EXCL 文件锁 + PID 验活(有 TOCTOU 竞态窗, 仅移植兼容用)
    while True:
        try:
            fd = os.open(_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps({"pid": me_pid, "ts": datetime.datetime.now().isoformat(),
                                    "origin": os.environ.get("JINCE_LOCK_ORIGIN", "manual")}))
            print("[单实例锁] 已获取锁(O_EXCL) pid=%d" % me_pid)
            return True
        except FileExistsError:
            try:
                old = json.load(open(_LOCK, encoding="utf-8"))
                ts0 = datetime.datetime.fromisoformat(old.get("ts", ""))
                age = (datetime.datetime.now() - ts0).total_seconds()
                if age < _LOCK_TTL_S and _pid_alive(old.get("pid", -1)):
                    print("[单实例锁] 已有活枪在跑(O_EXCL), 本枪让位退出")
                    return False
                os.remove(_LOCK)
            except Exception:
                try:
                    os.remove(_LOCK)
                except OSError:
                    pass

def _release_lock():
    global _lock_fd
    if _HAS_MSVCRT and _lock_fd is not None:
        try:
            msvcrt.locking(_lock_fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        try:
            os.close(_lock_fd)
        except OSError:
            pass
        _lock_fd = None
        try:
            os.remove(_LOCK_META)
        except OSError:
            pass
        print("[单实例锁] 已释放(内核锁)")
        return
    try:
        os.remove(_LOCK)
        print("[单实例锁] 已释放")
    except OSError:
        pass

def main():
    t0 = time.time()
    if not _acquire_lock():
        raise SystemExit(0)  # 有活枪在跑, 让位(非失败, 不 fail-loud)
    import os as _os
    # [2026-10-12 修] 每日默认 6腿池 keep_symbols (XAUUSD/XAGUSD/BTCUSD/ETHUSD/EURUSD/GBPUSD,
    #   来源 master_coordinator L431), 不再 SMOKE 3品种: chief 10-12 rd_queue#20 点名"全宇宙名不副实".
    #   3品种卷 12:57 全 TIMECAP fail-open=空卷, 不得再当双闸销账依据 (验收标准见 rd_ledger #universe_empty_volume).
    #   SMOKE 仅留 env JINCE_BT_MODE=SMOKE 手动; FULL(全63品种) 仍 env 手动触发(引擎提速后再排周日).
    mode = _os.environ.get("JINCE_BT_MODE", "PO6")
    PO6 = "XAUUSD,XAGUSD,BTCUSD,ETHUSD,EURUSD,GBPUSD"   # 逗号拼成单argv, 引擎 __main__ 按 ',' split
    argv = [PO6] if mode == "PO6" else ([mode] if mode == "SMOKE" else [])
    # [2026-10-09 根因修复] 剥掉父(cron运行器)的 PYTHONPATH/PYTHONHOME, 否则其不兼容 numpy 被继承
    #   -> 子进程 ATE 报 No module named 'numpy._core._multiarray_umath' 0.2s 崩. 干净环境才用 ATE venv 自带 numpy.
    child_env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    # [2026-10-10 L5 修复] 引擎 stderr -> 文件 (崩点 traceback 落盘, 不再 0 日志):
    #   rc=1 且 stderr 空 = 之前 4 起连挂全哑巴, 现重定向到 backtest_engine_stderr.log, 崩因可 grep.
    _err_log = os.path.join(DATA, "backtest_engine_stderr.log")
    # [2026-10-09 防复发闸①] 开跑前快检(10s): 干净环境验 numpy/pandas/MT5 可 import+初始化,
    #   坏 fail-fast 秒报, 不浪费 6.7h 长跑. 治根子: cron 运行器 PYTHONPATH 污染 -> 子进程
    #   numpy 0.2s 崩 (No module named 'numpy._core._multiarray_umath'), 之前 01:30 枪空转 3 个月.
    # [2026-11-04 L5③B-fix] t0 先落 stage=started stamp(治 wrapper 卡半途 -> stamp 冻结旧卷, 04:26 160s 没新戳实锤)
    #   + 各段计时(定位 precheck/wmic/powershell 各占多少, 哪段可砍). 中途被杀, 验收枪读 stage 知卡哪段.
    _seg_ms = {}
    try:
        json.dump({"ts": datetime.datetime.now().isoformat(), "stage": "started", "mode": mode,
                   "note": "wrapper started; 若 stamp 仍 stage=started = 卡 precheck/guard/powershell, 看 seg_ms 定位(治 04:26 冻结)"},
                  open(os.path.join(DATA, "backtest_edge_run_stamp.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception as _e0:
        print("[t0-stamp] 写 started stamp 失败: %s" % _e0)
    _t_pre = time.time()
    pre = subprocess.run([ATE, "-c", "import numpy,pandas,MetaTrader5 as m; _=m.initialize(); print('PRECHECK_OK', numpy.__version__)"],
                         capture_output=True, text=True, timeout=60, cwd=ROOT, env=child_env)
    _seg_ms["precheck"] = int((time.time() - _t_pre) * 1000)
    if "PRECHECK_OK" not in (pre.stdout or ""):
        # [2026-10-13 L5-fix] fail-fast 也写 stamp: 快检崩在写戳之前 -> stamp 冻结 10-09 旧哨兵,
        #   01:30 验收枪误报"哨兵3腿"连报 3 天. 现: 快检不过先落 fail-fast stamp(precheck_fail=True),
        #   再 raise; 验收枪读 precheck_fail/rc 报真因(环境/终端没起), 不再拿旧哨兵顶锅.
        _err_tail = (pre.stderr or pre.stdout or "")[-500:]
        _ff_stamp = {"ts": datetime.datetime.now().isoformat(), "rc": 2, "mode": mode,
                     "elapsed_s": round(time.time()-t0, 1), "precheck_fail": True,
                     "stdout_tail": "", "stderr_tail": _err_tail, "stderr_log": _err_log,
                     "engine_selfcheck_pass": True, "sentinels_high_wr_legs": 0,
                     "note": "PRECHECK_FAIL: 未开跑, 无新卷; 哨兵口径不适用(沿用上一卷口径, 不作验收依据)"}
        try:
            json.dump(_ff_stamp, open(os.path.join(DATA, "backtest_edge_run_stamp.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        except Exception as _e:
            print("[precheck-fail-stamp] 写 stamp 失败: %s" % _e)
        _release_lock()
        raise SystemExit("快检不过(环境污染/依赖缺失/MT5未起), 不开 6.7h 长跑, fail-fast: %s" % ((pre.stderr or pre.stdout or "")[-300:]))
    print("快检过(干净环境 numpy/pandas/MT5), 开跑 mode=%s" % mode)
    # [2026-10-09 L5-fix] 竞写防: 启子进程前先探活, 已有 backtest_engine SMOKE 在跑就等它收工复用产物, 不并启第二枪
    #   (同参双进程写同一真源=4185式脏痕, L4@risk-officer 点名焊死; 探活=wmic 查命令行含 backtest_engine 的活进程)
    import re as _re
    def _wmic_pids():
        # [2026-10-13 L5-fix] wmic 输出含中文路径(GBK 字节), text=True 按 utf-8 解出
        #   UnicodeDecodeError 0xd3 掉降级分支(12:50 实锤); 改 bytes 读 + gbk 容错解.
        try:
            chk = subprocess.run("wmic process where \"name like 'python%' and commandline like '%backtest_engine%'\" get ProcessId,CommandLine /format:list",
                                 shell=True, capture_output=True, env=child_env, timeout=30, creationflags=0x08000000)
            txt = (chk.stdout or b"").decode("gbk", errors="replace")
            # [2026-10-13 L5-fix] SMOKE 不当 PO6 引擎等: SMOKE=3币小冒烟(测试枪), 它霸着引擎入口锁时
            #   PO6 自起引擎会立即让位 exit 3(诚实失败, SMOKE 一清重跑即好), 不该让 PO6 傻等 7h 再
            #   reuse 旧卷假收工. 17:07 v7 实锤: 探活把 SMOKE(41424/13868) 当"引擎在跑" -> 等 ~80min
            #   后 reuse 旧 06:50 空卷, edge_fresh=false 假销账. 只等"非 SMOKE"的真回测枪;
            #   判据=命令行不含 'SMOKE'; 查不到命令行的保守按真枪处理(宁可等, 不假复用).
            pids = [l.strip().split("=", 1)[1] for l in txt.splitlines()
                   if l.strip().startswith("ProcessId=")]
            if pids:
                chk2 = subprocess.run("wmic process where \"name like 'python%'\" get ProcessId,CommandLine /format:list",
                                      shell=True, capture_output=True, env=child_env, timeout=30, creationflags=0x08000000)
                t2 = (chk2.stdout or b"").decode("gbk", errors="replace")
                pid_of_cmd, _last_pid = {}, None
                for l in t2.splitlines():
                    ls = l.strip()
                    if ls.startswith("ProcessId="):
                        _last_pid = ls.split("=", 1)[1].strip()
                    elif ls.startswith("CommandLine=") and _last_pid:
                        pid_of_cmd[_last_pid] = ls.split("=", 1)[1]
                sm_n = sum(1 for p in pids if "SMOKE" in pid_of_cmd.get(p, ""))
                if sm_n:
                    print("[防竞写] 检测到 SMOKE 测试枪 %d 个, 不傻等: PO6 自起引擎, 若引擎锁被霸则让位 exit 3 诚实失败(清 SMOKE 后重跑)" % sm_n)
                pids = [p for p in pids if "SMOKE" not in pid_of_cmd.get(p, "")]
            return pids
        except Exception:
            return []
    # [2026-11-04 L5③, hermes 三重根因③] detached 启动方案: 引擎 ~2.6h(9372s) > cron 全局 script_timeout(3600s)
    #   -> 旧阻塞 subprocess.run 让 wrapper 挂 2.6h, 必被 3600s 杀(00:10 连崩6次根因). 改:
    #   (a) 有竞写引擎在跑 -> 不并启(双引擎霸IPC=TIMECAP空卷根因①), 写 in-progress stamp, 快速退出;
    #   (b) 无竞写 -> Popen 引擎 detached(DETACHED_PROCESS|CREATE_BREAKAWAY_FROM_JOB, 可被 cron kill 幸存),
    #       立即写 launched stamp, 本枪 ~60s 收工(远<3600s, 不触发超时). 引擎自跑 2.6h 写 backtest_edge.json,
    #       01:30 验收枪 training_run.py 读真产物验新卷. 产品侧 sentinel/breadth 自检移到验收枪.
    def _pid_alive(pid):
        if not pid or pid <= 0:
            return False
        try:
            import ctypes
            _h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
            if _h:
                ctypes.windll.kernel32.CloseHandle(_h)
            return bool(_h)
        except Exception:
            return True  # 判不了活死 -> 保守当活着(不并启, 宁可复用)
    def _lock_engine_state():
        # [2026-11-04 L5③A-fix] 可靠判"有引擎在跑": 引擎 __main__ 用 O_EXCL 独占锁文件 data/backtest_engine.lock + 写 pid.
        #   治根: wmic CommandLine 对窗口/分离进程常返回 NULL -> 'commandline like' 漏判 117604(04:24 实锤漏) -> 误并启.
        #   改文件系统级锁: lock 文件存在且 owner pid 活 -> 有引擎在跑. 返回 (running, owner_pid).
        _lp = os.path.join(DATA, "backtest_engine.lock")
        if not os.path.exists(_lp):
            return False, 0
        try:
            _own = int(open(_lp).read().strip() or 0)
        except Exception:
            return False, 0
        if _pid_alive(_own):
            return True, _own
        return False, _own  # owner 死(stale) -> 不算在跑(引擎下次会清重建)
    edge_stamp = os.path.join(DATA, "backtest_edge_run_stamp.json")
    now_iso = datetime.datetime.now().isoformat()
    _err_log = os.path.join(DATA, "backtest_engine_stderr.log")
    _out_log = os.path.join(DATA, "backtest_engine_stdout.log")
    # [2026-11-04 L5③] expected_pool: 广度验收的期望池=本 job argv 品种(PO6=6腿池), 不是全宇宙tradable.
    _expected_pool = (argv[0].split(",") if (argv and argv[0]) else [])
    # [2026-11-04 L5③] 竞写双保险: 主判=引擎 O_EXCL 锁文件(pid 存活), 次判=wmic CommandLine(兜底老引擎没写 pid 时还能看到).
    _t_g = time.time()
    _l_run, _l_own = _lock_engine_state()
    _wm_pids = _wmic_pids()
    _seg_ms["guard"] = int((time.time() - _t_g) * 1000)
    _running_pid = _l_own if _l_run else (_wm_pids[0] if _wm_pids else 0)
    if _l_run:
        print("[防竞写] 引擎 O_EXCL 锁文件生效 pid=%s 在跑, 本枪复用(不并启)" % _l_own)
    if _wm_pids:
        print("[防竞写] wmic 兜底见引擎: %s" % _wm_pids)
    if _l_run or _wm_pids:
        _eff = _running_pid
        _stamp = {"launched": False, "in_progress": True, "reusing_engine_pid": _eff, "ts": now_iso,
                  "mode": mode, "precheck_ok": True, "detach": False,
                  "guard": "lockfile(O_EXCL)+wmic", "lock_pid": _l_own, "wmic_pids": _wm_pids,
                  "expected_pool": _expected_pool, "seg_ms": _seg_ms,
                  "note": "引擎 pid=%s 在跑(锁文件/wmic 双保险命中), 本枪不并启(双引擎霸IPC=TIMECAP空卷), 等其收工, 01:30 验收枪读真产物" % _eff}
        json.dump(_stamp, open(edge_stamp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("[防竞写] 已有引擎 pid=%s 在跑, 本枪不并启, 写 in-progress stamp, %.0fs 收工(远<3600s)" % (_eff, time.time() - t0))
        _release_lock()
        raise SystemExit(0)
    # 无竞写 -> 用 PowerShell Start-Process 把引擎父化到系统(比 Popen detached 更稳: 实测跨 shell/wrapper 拆卸仍存活),
    #   立即写 launched stamp, 本枪 ~60s 收工(远<3600s 不触发超时). 引擎自跑 ~2.6h 写 backtest_edge.json.
    # [2026-11-04 L5③ v2] Popen(DETACHED|BREAKAWAY) 实测在 MSYS/树拆卸时子进程被回收(marker 未落),
    #   改独立 powershell Start-Process 起 -> 引擎 parent 落回系统, 幸存任何 wrapper 杀.
    _engine_py = os.path.join(ROOT, "backtest_engine.py")
    open(_out_log, "w", encoding="utf-8").close()
    open(_err_log, "w", encoding="utf-8").close()
    _args_ps = ",".join('"%s"' % str(a).replace('"', '""') for a in ([_engine_py] + list(argv)))
    _ps_cmd = ('$env:PYTHONPATH=$null; $env:PYTHONHOME=$null; '
               '$p = Start-Process -FilePath "%s" -ArgumentList %s -WorkingDirectory "%s" '
               '-RedirectStandardOutput "%s" -RedirectStandardError "%s" -PassThru; Write-Output $p.Id'
               % (ATE, _args_ps, ROOT, _out_log, _err_log))
    _t_ps = time.time()
    try:
        _r = subprocess.run(["powershell", "-NoProfile", "-Command", _ps_cmd],
                            capture_output=True, text=True, timeout=45, cwd=ROOT, env=child_env)   # [L5③B] 120->45: Start-Process 正常<10s(不等引擎跑完), 45s 宽裕; 治卡 160s 冻结
        _so = (_r.stdout or "").strip()
        _pid = int(_so.splitlines()[-1]) if _so else 0
        _seg_ms["powershell"] = int((time.time() - _t_ps) * 1000)
        if _r.returncode != 0 or not _pid:
            raise RuntimeError("Start-Process 引擎启动失败 rc=%s out=%r err=%r" % (_r.returncode, _so[:200], (_r.stderr or "").strip()[:300]))
        _stamp = {"launched": True, "in_progress": False, "engine_pid": _pid, "ts": now_iso, "launch_ts": now_iso,
                  "mode": mode, "precheck_ok": True, "detach": True, "launch_via": "powershell Start-Process (system-reparented, survives wrapper kill)",
                  "expected_pool": _expected_pool, "seg_ms": _seg_ms,
                  "note": "引擎已用 Start-Process 父化到系统启动 pid=%s (幸存任何 wrapper/shell 拆卸), 本枪 %.0fs 收工; 引擎 ~2.6h 后写 backtest_edge.json, 01:30 验收枪读真产物验新卷" % (_pid, time.time() - t0)}
        json.dump(_stamp, open(edge_stamp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("[detached] 引擎已用 Start-Process 启动 pid=%s (父化到系统, 幸存任何 kill), launched stamp 已写 seg_ms=%s, 本枪 %.0fs 收工" % (_pid, _seg_ms, time.time() - t0))
    except Exception as _pe:
        _seg_ms["powershell"] = int((time.time() - _t_ps) * 1000)
        _stamp = {"launched": False, "in_progress": False, "launch_failed": True, "ts": now_iso, "mode": mode,
                  "seg_ms": _seg_ms, "note": "引擎 Start-Process 启动失败: %s" % _pe}
        json.dump(_stamp, open(edge_stamp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("[detached] 启动失败: %s seg_ms=%s" % (_pe, _seg_ms))
        _release_lock()
        raise SystemExit(1)
    _release_lock()
    raise SystemExit(0)


if __name__ == "__main__":
    main()
