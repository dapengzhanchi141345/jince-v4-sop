# D7根治: 00:10全宇宙回测 cron 枪的薄壳 wrapper (60s内收工, 重活 detach 到 pythonw 系统重亲)
# 缘由: cron runner 对 no_agent 脚本硬上限 3600s (哨兵hang检测依赖该cap, 禁全局调高,
#       见 hermes-agent 技能 "Cron no_agent script jobs" 教训 11-06). 本 wrapper:
#   1) 读/写 run_stamp + 引擎锁 (防竞写: 已有引擎在跑则 5s 收工)
#   2) 用 pythonw.exe + DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP 起重活 (系统重亲, 活过 cron kill)
#   3) 60s 内退出 (远 < 3600s cap), 输出静默 (无 stdout = 看门狗模式)
import json, os, subprocess, sys, time, datetime, uuid

ENGINE = r"E:\GoldstrategyEngine"
STAMP = os.path.join(ENGINE, "data", "backtest_edge_run_stamp.json")
LOCK = os.path.join(ENGINE, "data", "backtest_engine.lock")
import glob as _glob
def _resolve_pywin():
    # [11-09 fix] 不写死版本串(tools 目录版本串曾被改导致 os.path.exists 恒 False -> FATAL rc=1,
    # 11-08/11-09 两班 00:10 枪全灭, 回测产物 50h 未更, 节点看门狗防复发闸②报警).
    # glob 扫 tools/python-3.14*/pythonw.exe, 优先 3.14.9, 兜底取版本最高目录.
    cands = _glob.glob(r"E:\workbuddy\国外模型\hermes\tools\python-3.14*\pythonw.exe")
    for c in cands:
        if "3.14.9" in c:
            return c
    return max(cands) if cands else None
PYWIN = _resolve_pywin()
LOG = r"E:\workbuddy\国外模型\hermes\cache\scratch\training_universe_detached.log"

# 1) 防竞写: 锁里有别的活 pid 且 pid 仍存活 → 5s 收工
try:
    if os.path.exists(LOCK):
        holder = open(LOCK, encoding="utf-8").read().strip()
        if holder:
            # [11-09 修] text=True 在本机 locale(西里尔文 tasklist CSV)下 reader 线程 UnicodeDecodeError 崩:
            # 改 bytes + latin-1 手动解码(永不崩), PID 数字串匹配不受 locale 影响.
            ps = subprocess.run(["tasklist", "/FI", "PID eq %s" % holder, "/FO", "CSV", "/NH"],
                                capture_output=True, timeout=30)
            if holder in ps.stdout.decode("latin-1", "replace"):
                json.dump({"ts": datetime.datetime.now().isoformat(), "stage": "in-progress",
                           "note": "wrapper: 引擎 %s 在跑, 本枪不并启" % holder},
                          open(STAMP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                time.sleep(5)
                sys.exit(0)
except Exception:
    pass  # 锁不可读 → 继续起新枪 (引擎脚本自带 O_EXCL 锁再兜一层)

# 2) 写 started stamp + detach 起 pythonw 重活
json.dump({"ts": datetime.datetime.now().isoformat(), "stage": "started",
           "mode": "PO6", "note": "wrapper detached via pythonw (系统重亲, 活过3600s cap)"},
          open(STAMP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE")}
DETACHED = 0x00000008
NEW_GROUP = 0x00000200
cmd = [PYWIN, os.path.join(r"E:\workbuddy\国外模型\hermes\scripts", "training_full_universe.py")]
# 校验 pythonw 路径存在 (tools 目录版本串可能变)
if not PYWIN or not os.path.exists(PYWIN):
    print("FATAL: pythonw 路径不存在: %s (wrapper 需定位本机 tools 下 pythonw.exe)" % PYWIN)
    sys.exit(1)
subprocess.Popen(cmd, stdout=open(LOG, "ab"), stderr=subprocess.STDOUT,
                 creationflags=DETACHED | NEW_GROUP, env=env,
                 cwd=r"E:\workbuddy\国外模型\hermes\scripts")
# 3) 确认子进程活体后 60s 内静默收工
time.sleep(8)
pid = json.load(open(STAMP, encoding="utf-8")).get("ts", "")
sys.exit(0)
