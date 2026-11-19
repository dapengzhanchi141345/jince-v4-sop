# -*- coding: utf-8 -*-
"""
金策系统 · 重启防御守卫 (Boot Guardian)  — 2026-10-25 定稿（进程级真实守护，PEB 直读命令行）
==================================================================
使命：电脑重启/登录后，自动把整套金策系统"复活"并持续看护，绝不假死。

关键认知（2026-10-25 实跑进程复核）：
  1) 真正在跑的交易体是  jince_bot\\runner.py --equity <净值>  （不是 run_trader.py）。
  2) 所有金策进程均为无窗口 pythonw.exe（不是 python.exe），检测必须枚举两者。
  3) 各组件由"计划任务"托管，守卫采用【进程探测 + 必要时 Start-ScheduledTask】双保险：
     进程在 -> 不动作（绝不重复拉起，避免双交易循环）；
     进程死 + 任务在 -> 触发任务（任务内的自愈看门狗会复拉真实交易体）；
     进程死 + 任务也死 -> 直接兜底复拉真实交易体（仅最后一手，带重试上限）。
  4) MT5 终端没有任何任务托管 -> 守卫独家负责拉起 + 自动登录开关。
  5) 命令行探测用 NtQueryInformationProcess(class=60) 直读 PEB，不依赖 WMI/CIM 权限，
     在登录会话与受限上下文均可工作（避免"探测失败 -> 误判全死 -> 误拉起"的灾难）。
  6) 任何路径/凭据一律不动（Key 铁律），只看护本地进程与拉起。

路径铁律（双副本）：本脚本守护【实时副本 E:/GoldstrategyEngine】。
"""
import os
import sys
import time
import json
import glob
import struct
import atexit
import datetime
import subprocess
import ctypes
import ctypes as _ct
from ctypes import wintypes, c_char, c_ulong, c_ulonglong, byref, c_void_p

WORKDIR = r"E:\GoldstrategyEngine"
PY = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/pythonw.exe"
MT5_EXE = r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe"
# 真实交易体：jince_bot（实跑命令行已核实）
JINCE_BOT_DIR = r"E:\workbuddy\内容中心\交付\AI交易bot方案_20261019\jince_bot"
JINCE_BOT_RUNNER = os.path.join(JINCE_BOT_DIR, "runner.py")
JINCE_BOT_PY = r"C:\Users\ASUS\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none\pythonw.exe"
WATCHDOG_SCRIPT = os.path.join(WORKDIR, "_guardian_watchdog.py")
DATA = os.path.join(WORKDIR, "data")
LOGDIR = os.path.join(DATA, "logs")
os.makedirs(LOGDIR, exist_ok=True)
ALERT_LOG = os.path.join(DATA, "boot_guardian_alerts.log")
STATUS_MD = os.path.join(DATA, "boot_guardian_status.md")
STARTUP_MD = os.path.join(DATA, "boot_guardian_startup_report.md")
LOCK_FILE = os.path.join(DATA, "boot_guardian.lock")
DETACHED = 0x00000008
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CHECK_INTERVAL = 60          # 主巡检周期（秒）
MT5_FRESH_SEC = 900         # 行情实时数据新鲜阈值（15 分钟）
ANALYSIS_MAX_AGE = 12 * 3600  # 行情分析链最大间隔（12h，错过则提示补跑）
SELF_HEAL_LIMIT = 5         # 单组件连续自愈上限（防抖动死循环）

SELF_HEAL_WINDOW = 10 * 60  # [11-14根治] 连续失败计数按10min滑动窗: 超窗无新失败自动清零, 瞬态卡死(如MT5终端重启窗)不再锁死自愈能力

_heal_count = {}             # 组件 -> 连续自愈次数

# 关键计划任务（实时副本调度矩阵）
CRITICAL_TASKS = [
    "JinCeAutoCycle", "JinCeBotSelfHeal", "JinCeWatchdog", "JinCeEventGuard",
    "JinCeMarketAnalysisCycle", "Hermes_Gateway", "JinCeGitSync",
]

# ---------- ctypes 进程命令行直读（NtQueryInformationProcess class=60） ----------
_k32 = ctypes.windll.kernel32
_ntdll = ctypes.windll.ntdll
_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.CloseHandle.argtypes = [wintypes.HANDLE]
_k32.CloseHandle.restype = wintypes.BOOL
_k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, c_void_p, c_void_p, c_ulonglong, _ct.POINTER(c_ulonglong)]
_k32.ReadProcessMemory.restype = wintypes.BOOL
_ntdll.NtQueryInformationProcess.argtypes = [wintypes.HANDLE, c_ulong, c_void_p, c_ulong, _ct.POINTER(c_ulong)]
_ntdll.NtQueryInformationProcess.restype = c_ulong
_k32.GetProcessVersion.argtypes = [c_ulong]
_k32.GetProcessVersion.restype = c_ulong

PROCESS_QUERY_INFORMATION = 0x0400


def get_cmdline(pid):
    """用 NtQueryInformationProcess(ProcessCommandLineInformation=60) 直读 PEB 命令行。
    不依赖 WMI/CIM 权限，对同会话进程稳定可用。失败返回空串。"""
    h = _k32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        size = 16384
        buf = (c_char * size)()
        retlen = c_ulong()
        status = _ntdll.NtQueryInformationProcess(h, 60, buf, size, byref(retlen))
        if status != 0:
            return ""
        length = struct.unpack_from("<H", buf, 0)[0]   # UNICODE_STRING.Length（字节）
        if length <= 0:
            return ""
        buf_ptr = struct.unpack_from("<Q", buf, 8)[0]  # UNICODE_STRING.Buffer（x64 偏移 8）
        buf_addr = _ct.addressof(buf)
        offset = buf_ptr - buf_addr
        if not (0 <= offset < size):
            offset = 12
        raw = bytes(buf[offset:offset + length])
        return raw.decode("utf-16-le", "replace")
    except Exception:
        return ""
    finally:
        _k32.CloseHandle(h)


def _enum_pids():
    try:
        r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                           capture_output=True, creationflags=NO_WINDOW, timeout=30)
        pids = []
        for ln in (r.stdout or b"").decode("utf-8", "replace").splitlines():
            parts = [p.strip('"') for p in ln.split(",")]
            if len(parts) >= 2 and parts[1].isdigit():
                pids.append(int(parts[1]))
        return pids
    except Exception:
        return []


def enum_all_cmdlines():
    """返回 [(pid, cmdline), ...] 覆盖全部进程（含 MT5/hermes.exe/pythonw）。"""
    res = []
    for pid in _enum_pids():
        cl = get_cmdline(pid)
        if cl:
            res.append((str(pid), cl))
    return res


def pid_alive(pid):
    try:
        pid = int(pid)
        if pid <= 0:
            return False
        return _k32.GetProcessVersion(pid) != 0
    except Exception:
        return False


def alive_in(procs, matchers):
    for pid, cl in procs:
        if all(m in cl for m in matchers) and pid_alive(pid):
            return True
    return False


def proc_alive(matchers):
    return alive_in(enum_all_cmdlines(), matchers)


def count_procs(procs, matchers):
    n = 0
    for pid, cl in procs:
        if all(m in cl for m in matchers) and pid_alive(pid):
            n += 1
    return n


# ---------- 计划任务触发（PowerShell，仅取 returncode/State，不解析命令行） ----------
def run_ps(script):
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                           capture_output=True, creationflags=NO_WINDOW, timeout=40)
        out = (r.stdout or b"").decode("utf-8", "replace") if r.stdout else ""
        return r.returncode, out
    except Exception:
        return -1, ""


def start_task(name):
    rc, _ = run_ps(f"Start-ScheduledTask -TaskName '{name}'")
    log(f"start_task({name}) rc={rc}")
    return rc == 0


def task_ready(name):
    rc, out = run_ps(f"(Get-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue).State")
    s = out.strip()
    return s in ("Ready", "Running") or "Ready" in s


def ensure_mt5_autologin():
    try:
        base = r"C:\Users\ASUS\AppData\Roaming\MetaQuotes\Terminal"
        for ini in glob.glob(os.path.join(base, "*", "config", "terminal.ini")):
            txt = open(ini, encoding="utf-8", errors="ignore").read()
            if "Login=60137964" in txt or "Login=60043976" in txt:
                if "AutoLogin=1" in txt:
                    continue
                if "[Common]" in txt:
                    txt = txt.replace("[Common]\n", "[Common]\nAutoLogin=1\n", 1)
                else:
                    txt += "\n[Common]\nAutoLogin=1\n"
                open(ini, "w", encoding="utf-8").write(txt)
                log(f"MT5 auto-login enabled in {ini}")
    except Exception as e:
        log(f"ensure_mt5_autologin err: {e}")


# ---------- 自愈拉起 ----------
def launch_mt5():
    if alive_in(enum_all_cmdlines(), ["terminal64.exe"]) or alive_in(enum_all_cmdlines(), ["terminal.exe"]):
        return True
    try:
        subprocess.Popen([MT5_EXE], cwd=os.path.dirname(MT5_EXE),
                         creationflags=DETACHED, close_fds=True)
        log("MT5 terminal launched")
        return True
    except Exception as e:
        alert(f"MT5 launch FAILED: {e}")
        return False


def read_daystate_equity():
    p = os.path.join(DATA, "jince_bot_daystate.json")
    try:
        v = json.load(open(p, encoding="utf-8")).get("start_equity")
        if isinstance(v, (int, float)) and 100 < v < 100000:
            return float(v)
    except Exception:
        pass
    return 893.95  # 当前实跑净值锚（兜底）


def launch_jince_bot_direct():
    eq = read_daystate_equity()
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        subprocess.Popen([JINCE_BOT_PY, JINCE_BOT_RUNNER, "--equity", str(eq),
                          "--execute", "--poll", "15", "--signal-refresh", "60"],
                         cwd=JINCE_BOT_DIR, creationflags=DETACHED, close_fds=True, env=env)
        log(f"jince_bot runner DIRECT backstop launched (equity={eq})")
        return True
    except Exception as e:
        alert(f"jince_bot direct launch FAILED: {e}")
        return False


def ensure_jince_bot(procs):
    if alive_in(procs, ["runner.py", "--equity"]):
        return
    log("jince_bot runner absent -> ensure selfheal task")
    if not alive_in(procs, ["jince_selfheal_watchdog.py"]):
        start_task("JinCeBotSelfHeal")
    time.sleep(10)
    procs2 = enum_all_cmdlines()
    if alive_in(procs2, ["runner.py", "--equity"]):
        log("jince_bot runner revived by selfheal task")
        return
    log("selfheal did not revive runner -> DIRECT backstop")
    launch_jince_bot_direct()


def ensure_auto_run_cycle(procs):
    if alive_in(procs, ["auto_run_cycle.py"]):
        return
    log("auto_run_cycle absent -> start_task JinCeAutoCycle")
    start_task("JinCeAutoCycle")
    time.sleep(6)
    if alive_in(enum_all_cmdlines(), ["auto_run_cycle.py"]):
        return
    try:
        subprocess.Popen([PY, "-u", "auto_run_cycle.py"], cwd=WORKDIR,
                         creationflags=DETACHED, close_fds=True)
        log("auto_run_cycle DIRECT backstop launched")
    except Exception as e:
        alert(f"auto_run_cycle direct launch FAILED: {e}")


def ensure_by_task(label, procs, matchers, task):
    if alive_in(procs, matchers):
        return
    log(f"{label} absent -> start_task {task}")
    start_task(task)


def self_heal(component, fn):
    global _heal_count
    now = time.time()
    n, last_fail = _heal_count.get(component, (0, 0.0))
    if n and now - last_fail > SELF_HEAL_WINDOW:
        n, last_fail = 0, 0.0   # 超窗无新失败 -> 瞬态episode清除, 自愈能力恢复(不再永久latch)
        log(f"[HEAL-UNLATCH] {component} 10min无新失败, 计数清零")
    if n >= SELF_HEAL_LIMIT:
        alert(f"[SELF-HEAL LIMIT] {component} 10min内连续自愈 {n} 次仍失败, 暂停自动拉起(10min无新失败自动恢复)")
        _heal_count[component] = (n, last_fail)
        return
    ok = fn()
    if ok is None:
        _heal_count[component] = (n, last_fail)   # ensure_*类无返回值: 视为已尝试, 不误计失败(下轮60s后liveness复检兜底)
    elif ok:
        _heal_count[component] = (0, 0.0)
        log(f"[HEALED] {component}")
    else:
        _heal_count[component] = (n + 1, now)


def ensure_watchdog():
    """与 _guardian_watchdog.py 互为守护：保证看门狗存活，看门狗负责在守卫
    异常退出时兜底复拉本进程。无需管理员/计划任务权限。"""
    procs = enum_all_cmdlines()
    if alive_in(procs, ["_guardian_watchdog.py"]):
        return
    try:
        subprocess.Popen([PY, WATCHDOG_SCRIPT], cwd=WORKDIR,
                         creationflags=DETACHED, close_fds=True)
        log("guardian watchdog launched (mutual supervision)")
    except Exception as e:
        alert(f"watchdog launch FAILED: {e}")


def ensure_analysis_chain():
    t = latest_mtime(os.path.join(DATA, "group_messages", "analysis_*.md"))
    now = time.time()
    if t is None or (now - t) > ANALYSIS_MAX_AGE:
        lock = os.path.join(DATA, "boot_guardian_analysis.lock")
        if os.path.exists(lock) and (now - os.path.getmtime(lock)) < 6 * 3600:
            return
        try:
            open(lock, "w").write(str(now))
            alert("行情分析链超过 12h 未更新，触发 JinCeMarketAnalysisCycle 补跑")
            start_task("JinCeMarketAnalysisCycle")
        except Exception as e:
            alert(f"analysis chain trigger FAILED: {e}")


# ---------- 数据新鲜度 / 健康度 ----------
def latest_mtime(pattern):
    files = glob.glob(pattern)
    if not files:
        return None
    return max(os.path.getmtime(f) for f in files)


def mt5_fresh():
    t = latest_mtime(os.path.join(DATA, "mt5_live_read_*.json"))
    if t is None:
        return None
    age = time.time() - t
    return age <= MT5_FRESH_SEC, age


def data_source_health():
    csvs = [f for f in glob.glob(os.path.join(DATA, "*.csv")) if "mt5_live_read" not in f]
    have = len(csvs)
    if have < 10:
        light = "🔴红(疑似数据缺失)"
    elif have < 20:
        light = "🟡黄"
    else:
        light = "🟢绿"
    return have, light


def winrate_valid():
    try:
        g = json.load(open(os.path.join(WORKDIR, "evolution", "incumbent_genome.json"),
                          encoding="utf-8"))
        exp_r = [None]
        def dig(o):
            if exp_r[0] is not None:
                return
            if isinstance(o, dict):
                for k, v in o.items():
                    if k == "exp_r" and isinstance(v, (int, float)):
                        exp_r[0] = v
                        return
                    dig(v)
            elif isinstance(o, list):
                for i in o:
                    dig(i)
        dig(g)
        if exp_r[0] is None:
            return None, 0
        return exp_r[0] > 0, exp_r[0]
    except Exception:
        return None, 0


# ---------- 状态报告 ----------
def dup_warning(procs):
    warns = []
    checks = [
        ("auto_run_cycle.py", ["auto_run_cycle.py"]),
        ("jince_watchdog.py", ["jince_watchdog.py"]),
        ("jince_selfheal_watchdog.py", ["jince_selfheal_watchdog.py"]),
        ("jince_bot runner", ["runner.py", "--equity"]),
        ("hermes gateway", ["hermes.exe", "serve"]),
    ]
    for label, m in checks:
        n = count_procs(procs, m)
        if n > 1:
            warns.append(f"{label} 检测到 {n} 个实例（疑似重复，建议人工核查，勿擅自 kill 交易进程）")
    return warns


def write_status(procs):
    try:
        now = datetime.datetime.now()
        mt5 = mt5_fresh()
        have, light = data_source_health()
        valid, exp_r = winrate_valid()
        valid_label = "无效(负期望)" if valid is False else ("有效" if valid else "未知")
        dups = dup_warning(procs)

        comp = [
            ("MT5 终端", alive_in(procs, ["terminal64.exe"]) or alive_in(procs, ["terminal.exe"])),
            ("jince_bot 交易体(runner.py)", alive_in(procs, ["runner.py", "--equity"])),
            ("CIO 全链(auto_run_cycle.py)", alive_in(procs, ["auto_run_cycle.py"])),
            ("jince 自愈看门狗(selfheal)", alive_in(procs, ["jince_selfheal_watchdog.py"])),
            ("JinCeWatchdog(jince_watchdog.py)", alive_in(procs, ["jince_watchdog.py"])),
            ("事件守卫(event_guard.py)", alive_in(procs, ["event_guard.py"])),
            ("Hermes 网关(hermes.exe serve)", alive_in(procs, ["hermes.exe", "serve"])),
        ]
        ana_t = latest_mtime(os.path.join(DATA, "group_messages", "analysis_*.md"))
        ana_age = (now.timestamp() - ana_t) / 3600 if ana_t else None

        lines = [
            f"# 金策系统健康日报（{now:%Y-%m-%d %H:%M}）",
            "",
            "> 本文件由 `boot_guardian.py` 自动生成，每 60s 刷新，重启/登录后由启动文件夹 VBS 自动拉起。",
            "",
            "## 核心组件状态",
        ]
        for name, ok in comp:
            lines.append(f"- {name}：{'✅ 存活' if ok else '❌ 缺失（守卫将自愈）'}")
        lines.append(f"- 行情分析链：最新 {('%.1f h 前' % ana_age) if ana_age is not None else '❌ 无'} "
                     f"{'✅' if ana_age is None or ana_age < 12 else '⚠️ 超时'}")
        lines.append("")
        lines.append("## 关键计划任务（State）")
        for t in CRITICAL_TASKS:
            lines.append(f"- {t}：{'✅ Ready/Running' if task_ready(t) else '❌ 异常'}")
        lines.append("")
        lines.append("## 数据源健康度")
        lines.append(f"- MT5 历史 CSV：{have} 个（状态灯 {light}）")
        lines.append(f"- 实时行情 JSON 新鲜度："
                     f"{('✅ 新鲜(%dmin)' % (mt5[1]/60)) if mt5 and mt5[0] else ('⚠️ 超时' if mt5 else '❌ 无数据')}")
        lines.append("")
        lines.append("## 胜率有效性（核心 KPI）")
        lines.append(f"- **当前胜率有效性：{valid_label}**（incumbent exp_r={exp_r:.4f}R）")
        lines.append("")
        if dups:
            lines.append("## ⚠️ 重复进程告警")
            for d in dups:
                lines.append(f"- {d}")
            lines.append("")
        lines.append("---")
        lines.append("异常项详见 data/boot_guardian_alerts.log；本守卫单实例运行，重启后自动复活。")
        with open(STATUS_MD, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception as e:
        log(f"write_status err: {e}")


def write_startup_report(procs):
    try:
        now = datetime.datetime.now()
        lines = [
            f"# 金策守卫 · 启动自检报告（{now:%Y-%m-%d %H:%M:%S}）",
            "",
            "守卫已在登录时自动拉起（启动文件夹 VBS → pythonw 无窗口，PEB 直读命令行探测）。本次启动逐组件复核：",
            "",
        ]
        checks = [
            ("MT5 终端", alive_in(procs, ["terminal64.exe"]) or alive_in(procs, ["terminal.exe"]), "无任务托管，守卫独家拉起"),
            ("jince_bot 交易体", alive_in(procs, ["runner.py", "--equity"]), "由 JinCeBotSelfHeal 自愈看门狗复拉"),
            ("CIO 全链 auto_run_cycle", alive_in(procs, ["auto_run_cycle.py"]), "由 JinCeAutoCycle 任务托管"),
            ("jince 自愈看门狗", alive_in(procs, ["jince_selfheal_watchdog.py"]), "由 JinCeBotSelfHeal 任务托管"),
            ("JinCeWatchdog", alive_in(procs, ["jince_watchdog.py"]), "由 JinCeWatchdog 任务托管"),
            ("事件守卫", alive_in(procs, ["event_guard.py"]), "由 JinCeEventGuard 任务托管"),
            ("Hermes 网关", alive_in(procs, ["hermes.exe", "serve"]), "由 Hermes_Gateway 登录触发器托管"),
        ]
        for name, ok, owner in checks:
            lines.append(f"- {name}：{'✅ 已在跑' if ok else '🔧 缺失，已触发自愈'}（{owner}）")
        lines.append("")
        dups = dup_warning(procs)
        if dups:
            lines.append("⚠️ 发现重复进程：")
            for d in dups:
                lines.append(f"  - {d}")
            lines.append("")
        lines.append("结论：系统已在登录后自动复活并进入持续看护。若某组件缺失，守卫会在 10s 内自愈拉起。")
        with open(STARTUP_MD, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception as e:
        log(f"write_startup_report err: {e}")


# ---------- 单实例锁（PID 锁文件，避免 ctypes mutex 不可靠） ----------
def acquire_single_instance():
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        try:
            old = int(open(LOCK_FILE, "r").read().strip() or "0")
        except Exception:
            old = 0
        if old and pid_alive(old):
            return False
        try:
            os.remove(LOCK_FILE)
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except Exception:
            return False


def release_lock():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception:
        pass


def log(msg, to_alert=False):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} GUARDIAN: {msg}\n"
    try:
        with open(os.path.join(LOGDIR, "boot_guardian.log"), "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    if to_alert:
        try:
            with open(ALERT_LOG, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass


def alert(msg):
    log(msg, to_alert=True)


# ---------- 主循环 ----------
def startup_sequence():
    log("=== 启动序列开始 ===")
    ensure_mt5_autologin()
    launch_mt5()
    time.sleep(15)
    procs = enum_all_cmdlines()
    ensure_by_task("selfheal", procs, ["jince_selfheal_watchdog.py"], "JinCeBotSelfHeal")
    ensure_by_task("watchdog", procs, ["jince_watchdog.py"], "JinCeWatchdog")
    ensure_by_task("event_guard", procs, ["event_guard.py"], "JinCeEventGuard")
    ensure_by_task("gateway", procs, ["hermes.exe", "serve"], "Hermes_Gateway")
    ensure_by_task("auto_run_cycle", procs, ["auto_run_cycle.py"], "JinCeAutoCycle")
    ensure_jince_bot(procs)
    ensure_analysis_chain()
    ensure_watchdog()
    write_startup_report(procs)
    log("=== 启动序列结束 ===")


_onced = {}
def log_once(key, msg):
    now = time.time()
    if now - _onced.get(key, 0.0) > 3600:
        log(f"[LOG-ONCE] {msg}")
        _onced[key] = now


def health_loop():
    write_status(enum_all_cmdlines())
    last_daily = datetime.datetime.now().date()
    while True:
        try:
            procs = enum_all_cmdlines()
            if not (alive_in(procs, ["terminal64.exe"]) or alive_in(procs, ["terminal.exe"])):
                self_heal("mt5", launch_mt5)
            if not alive_in(procs, ["runner.py", "--equity"]):
                log_once("jince_bot", "jince_bot runner 缺席(10-19实盘runner=legacy, 自动拉起涉L5实盘红线已禁, 需李彦明令才复活)")
            if not alive_in(procs, ["auto_run_cycle.py"]):
                log_once("auto_run_cycle", "auto_run_cycle 缺席(legacy计划任务JinCeAutoCycle不存在, 周期链现由主bot哨+21:30学习哨承接, 不自动拉起)")
            if not alive_in(procs, ["jince_selfheal_watchdog.py"]):
                log_once("selfheal", "jince_selfheal_watchdog 缺席(legacy计划任务JinCeBotSelfHeal不存在, 角色由本guardian+主bot哨接管, 不自动拉起)")
            if not alive_in(procs, ["jince_watchdog.py"]):
                log_once("watchdog", "jince_watchdog 缺席(legacy计划任务JinCeWatchdog不存在, 角色由_guardian_watchdog+主bot哨接管, 不自动拉起)")
            if not alive_in(procs, ["event_guard.py"]):
                self_heal("event_guard", lambda: start_task("JinCeEventGuard"))
            if not alive_in(procs, ["hermes_cli.main", "--profile"]):
                self_heal("gateway", lambda: start_task("Hermes_Gateway"))
            ensure_watchdog()
            ensure_analysis_chain()
            write_status(procs)
            now = datetime.datetime.now()
            if now.hour == 9 and now.minute < 5 and now.date() != last_daily:
                write_status(procs)
                last_daily = now.date()
                log("daily report generated")
        except Exception as e:
            alert(f"health_loop error: {e}")
        time.sleep(CHECK_INTERVAL)


def main():
    try:
        if not acquire_single_instance():
            log("another boot_guardian running, exit")
            sys.exit(0)
        atexit.register(release_lock)
        log("boot_guardian started (detached, single-instance, PEB cmdline probe)")
        startup_sequence()
        health_loop()
    except Exception as e:
        try:
            import traceback
            log("FATAL in main loop: %r\n%s" % (e, traceback.format_exc()))
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
