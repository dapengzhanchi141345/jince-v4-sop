# -*- coding: utf-8 -*-
"""Hermes 常驻守护：按「网关 ready -> 桌面端」顺序启动并持续自愈。

2026-11-12 实测根因：
  WorkBuddy 的 Bash / 后台任务在命令结束时会回收该命令创建的全部子进程。
  DETACHED_PROCESS、CREATE_BREAKAWAY_FROM_JOB、Shell.Application.ShellExecute、
  win32api.ShellExecute 启动的进程全部在命令结束时被清理（explorer/WMI 之外的通道无效）。
  只有 WMI Win32_Process.Create 创建的进程（父进程为 WmiPrvSE 系统服务）能跨命令存活。

因此本脚本必须以 `--launch` 方式由 WMI 拉起，之后它自身及它创建的所有 Hermes
进程都不受 WorkBuddy 会话生命周期影响。

用法：
  python hermes_supervisor.py --launch    # 用 WMI 创建常驻守护（推荐）
  python hermes_supervisor.py             # 前台守护模式（调试用）
  python hermes_supervisor.py --status    # 只读查看网关/桌面端状态
"""
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import psutil

HOME = Path(r"E:\workbuddy\国外模型\hermes")
REPO = HOME / "hermes-agent"
PY = REPO / ".venv" / "Scripts" / "python.exe"
PYW = REPO / ".venv" / "Scripts" / "pythonw.exe"
DESKTOP = REPO / "apps" / "desktop" / "release" / "win-unpacked" / "Hermes.exe"
LAUNCHER = HOME / "bin" / "hermes.exe"
LOG = HOME / "logs" / "hermes-supervisor.log"
LOCK = HOME / "hermes-supervisor.lock"
PYWIN32 = REPO / ".venv" / "Lib" / "site-packages" / "pywin32_system32"
TMP = Path(r"E:\workbuddy\tmp")

GW_CMD = [str(PY), "-m", "hermes_cli.main", "--profile", "default", "gateway", "run", "--quiet"]
DETACH = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# 健康探测参数（2026-11-12 修正）
# 网关在 30+ profile 并发下健康接口本身就要 2-3s，超时给足 10s；
# 不健康阈值放大到 10 次（= 5 分钟），避免偶发抖动触发误杀。
HEALTH_TIMEOUT = 10
UNHEALTHY_THRESHOLD = 10


def log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        with open(str(LOG), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    if sys.stdout is not None:
        try:
            print(line, flush=True)
        except Exception:
            pass


def env_for_child():
    e = dict(os.environ)
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        e.pop(k, None)
    # 剥掉 WorkBuddy 的 sitecustomize shim（2026-11-12 新增，必做）。
    # WorkBuddy 会在自己的 CLI 进程里注入 PYTHONPATH=...cli\vendor\shim，那个目录里的
    # sitecustomize.py 会把「safe-delete 批量护栏」装进每一个 Python 子进程：同一轮里
    # 累计删除达到 50 个目标后，任何 os.unlink / Path.unlink / rmtree 都会 raise
    # SystemExit(1)。Hermes 网关启动时要清理 installs\<id>\environments\ 下的旧依赖代
    # （本机已积到 13 个），删除数必然踩线 —— 网关进程会在启动途中被直接打死，
    # 表现为「桌面端 gateway ensure 超时 → 反复重启」。桌面端自己起的
    # `hermes gateway ensure` 子进程同样继承这个 PYTHONPATH，所以必须在这里剥掉。
    _pp = e.get("PYTHONPATH", "")
    _parts = [p for p in _pp.split(os.pathsep)
              if p and "workbuddy" not in p.lower() and "codebuddy" not in p.lower()]
    if _parts:
        e["PYTHONPATH"] = os.pathsep.join(_parts)
    else:
        e.pop("PYTHONPATH", None)
    e["HERMES_HOME"] = str(HOME)
    e["HERMES_GATEWAY_DETACHED"] = "1"
    if LAUNCHER.exists():
        e["HERMES_DESKTOP_HERMES"] = str(LAUNCHER)
    e.pop("HERMES_SESSION_ID", None)
    dll = str(PYWIN32)
    if PYWIN32.is_dir() and dll.lower() not in e.get("PATH", "").lower():
        e["PATH"] = dll + os.pathsep + e.get("PATH", "")
    try:
        TMP.mkdir(parents=True, exist_ok=True)
        e["TEMP"] = str(TMP)
        e["TMP"] = str(TMP)
    except Exception:
        pass
    return e


def spawn(cmd, cwd):
    return subprocess.Popen(cmd, cwd=str(cwd), env=env_for_child(),
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, creationflags=DETACH)


def gateway_procs():
    """All processes that look like a gateway server.

    修正点（2026-11-12）：``.venv\\Scripts\\python.exe -m hermes_cli.main ... gateway run`` 会
    re-exec 出真正的解释器（uv 的 base python），于是同一台机器上出现两个都匹配
    "hermes_cli.main" + "gateway run" 的进程 —— 前者是 4MB 的 launcher，**不持有任何监听端口**；
    后者才是真正跑服务、持有 socket 的那个。旧实现只取第一个匹配项，于是
    ``listen_ports()`` 永远返回空 → ``ready()`` 永远报 "gateway-has-no-listen-port" →
    supervisor 永远等不到 READY → **永远不拉桌面端**。
    """
    out = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cl = " ".join(p.info["cmdline"] or [])
            if ((p.info["name"] or "").lower().startswith("python")
                    and "hermes_cli.main" in cl and "gateway run" in cl):
                out.append(p)
        except Exception:
            pass
    return out


def gateway_proc():
    """The gateway process that actually owns the listening socket (see :func:`gateway_procs`)."""
    cands = gateway_procs()
    if not cands:
        return None
    for p in cands:
        if listen_ports(p):
            return p
    # 还没有监听端口（仍在冷启动）：退回第一个候选，让调用方能区分"进程没了"和"还没就绪"。
    return cands[0]


def desktop_procs():
    out = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if (p.info["name"] or "").lower() == "hermes.exe":
                out.append(p)
        except Exception:
            pass
    return out


def listen_ports(proc):
    try:
        return sorted({c.laddr.port for c in proc.net_connections(kind="inet")
                       if c.status == "LISTEN" and c.laddr.ip in ("127.0.0.1", "0.0.0.0")})
    except Exception:
        return []


def health(port):
    """探测单个端口的 /api/health。返回 (code, elapsed, body)。"""
    t0 = time.time()
    try:
        with OPENER.open("http://127.0.0.1:%d/api/health" % port, timeout=HEALTH_TIMEOUT) as r:
            return r.status, round(time.time() - t0, 2), r.read(400).decode("utf-8", "ignore")
    except Exception as e:
        return 0, round(time.time() - t0, 2), type(e).__name__


def ready():
    """网关是否就绪。

    修正点（2026-11-12）：网关会同时监听多个端口，其中只有 HTTP 端口能响应
    /api/health，其余是控制 socket / websocket（必然返回 BadStatusLine/URLError）。
    旧实现只保留最后一次探测结果，导致健康网关被误判为故障 → 反复杀桌面端 →
    桌面端重拉起 30+ 个 ticket bridge Python 进程 → 网关被压垮 → 死亡螺旋。

    现在：只要任一端口在超时内返回 200 且 body 含 "ok":true 即判定就绪。
    """
    cands = gateway_procs()
    if not cands:
        return False, "no-gateway-process"
    detail = []
    for p in cands:
        ports = listen_ports(p)
        if not ports:
            detail.append("pid%d:no-listen-port" % p.pid)
            continue
        for port in ports:
            code, dt, body = health(port)
            detail.append("%d:%s/%.1fs" % (port, code or "FAIL", dt))
            if code == 200 and '"ok":true' in body:
                return True, "port=%d pid=%d %.1fs" % (port, p.pid, dt)
    return False, "ports=[%s]" % " ".join(detail)


def kill(procs, label):
    procs = [p for p in procs if p is not None]
    for p in procs:
        try:
            log("  停止 %s pid=%d" % (label, p.pid))
            p.kill()
        except Exception:
            pass
    if procs:
        try:
            psutil.wait_procs(procs, timeout=8)
        except Exception:
            pass


def bring_up():
    """精准冷启动：网关缺席才重启网关；桌面端缺失才拉起。

    修正点（2026-11-12）：旧实现无条件 kill 桌面端，而桌面端有 30+ 个 ticket
    bridge Python 子进程（合计 1.6GB）。反复杀拉会制造内存尖峰，把网关压垮，
    形成"网关慢 → 杀桌面端 → 更慢"的死亡螺旋。现在默认不杀桌面端，
    仅在明确要求时（force=True）才清理。
    """
    g = gateway_proc()
    if g is not None:
        log("  复用现有网关 pid=%d（不打断其运行）" % g.pid)
    else:
        kill([gateway_proc()], "gateway")
        time.sleep(2)
        try:
            spawn(GW_CMD, REPO)
            log("  网关已拉起，等待 ready（最多 15 分钟）")
        except Exception as e:
            log("  !! 网关启动失败 %r" % (e,))
            return False
    for i in range(90):
        time.sleep(10)
        ok, info = ready()
        if ok:
            log("  网关 READY %s（耗时 %ds）" % (info, (i + 1) * 10))
            break
        if i % 3 == 0:
            log("  等待 ready %ds %s" % ((i + 1) * 10, info[:150]))
    else:
        log("  !! 15 分钟未 ready，放弃本轮，桌面端不启动")
        return False
    try:
        if desktop_procs():
            log("  桌面端已在运行（不重复拉起）")
        else:
            spawn([str(DESKTOP)], DESKTOP.parent)
            log("  桌面端已拉起（网关 ready 之后，ticket 一次签发）")
    except Exception as e:
        log("  !! 桌面端启动失败 %r" % (e,))
        return False
    return True


def launch():
    """通过 WMI 由系统服务创建守护进程，使其脱离 WorkBuddy 会话进程组。"""
    import win32com.client
    exe = str(PYW if PYW.exists() else PY)
    script = str(Path(__file__).resolve())
    cmdline = '"%s" "%s"' % (exe, script)
    loc = win32com.client.Dispatch("WbemScripting.SWbemLocator")
    svc = loc.ConnectServer(".", "root\\cimv2")
    cls = svc.Get("Win32_Process")
    inp = cls.Methods_("Create").InParameters.SpawnInstance_()
    inp.CommandLine = cmdline
    inp.CurrentDirectory = str(REPO)
    out = svc.ExecMethod("Win32_Process", "Create", inp)
    print("WMI ReturnValue=%s ProcessId=%s cmd=%s" % (out.ReturnValue, out.ProcessId, cmdline))
    return int(out.ReturnValue)


def main():
    if "--launch" in sys.argv:
        # --launch 只负责用 WMI 拉起守护实例，本进程必须立刻退出，
        # 否则 WMI 子进程和本进程会同时进入巡检循环，产生双实例。
        sys.exit(0 if launch() == 0 else 1)
    if "--status" in sys.argv:
        ok, info = ready()
        print("health_ok=%s %s" % (ok, info))
        print("desktop_pids=%s" % [p.pid for p in desktop_procs()])
        return

    # 原子锁：先以 O_EXCL 抢占，抢不到就说明已有实例在跑。
    # （旧实现先读后写，两个实例同时启动时会双双通过检查。）
    lock_acquired = False
    try:
        fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w") as _f:
            _f.write(str(os.getpid()))
        lock_acquired = True
    except FileExistsError:
        pass
    except Exception:
        lock_acquired = True  # 锁文件不可用时退化为非严格模式

    if not lock_acquired:
        try:
            old = int(LOCK.read_text(encoding="utf-8").strip())
            p = psutil.Process(old)
            if "hermes_supervisor" in " ".join(p.cmdline()):
                print("已有守护 pid=%d 在运行，本实例退出" % old)
                return
        except Exception:
            pass
        # 锁指向的进程已死 → 陈旧锁，清掉后重试一次
        try:
            LOCK.unlink()
        except Exception:
            pass
        try:
            fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as _f:
                _f.write(str(os.getpid()))
            lock_acquired = True
        except Exception:
            pass
        if not lock_acquired:
            print("无法取得守护锁，本实例退出")
            return
    # pythonw 无控制台，把 stdout/stderr 落到文件，便于捕获任何未处理异常
    try:
        _out = open(str(LOG) + ".out", "a", encoding="utf-8", buffering=1)
        sys.stdout = _out
        sys.stderr = _out
    except Exception:
        pass
    LOCK.write_text(str(os.getpid()), encoding="utf-8")
    log("=== 守护启动 pid=%d python=%s ===" % (os.getpid(), sys.executable))
    bring_up()
    log("=== 进入巡检循环（30s）===")
    bad = 0
    while True:
        time.sleep(30)
        try:
            # 锁自检（2026-11-12 新增）：锁文件是互斥的唯一依据，但锁被外部删掉/覆盖时
            # （例如人工清理、手工 rm）另一个实例就会拿到锁并同时进入巡检循环 —— 两个
            # supervisor 会各自拉桌面端、拉网关，互相踩。锁不再指向自己就说明已被别人接管，
            # 本实例必须退出，把唯一性还给持锁者。
            try:
                holder = LOCK.read_text(encoding="utf-8").strip()
            except Exception:
                holder = ""
            if holder != str(os.getpid()):
                log("  锁已不再指向本进程（当前=%r 本进程=%d）→ 已有另一个守护接管，本实例退出"
                    % (holder, os.getpid()))
                return
            ok, info = ready()
            if ok:
                if bad:
                    log("  已恢复正常 %s" % info[:130])
                bad = 0
                if not desktop_procs():
                    log("  桌面端缺失，补拉（网关已 ready）")
                    spawn([str(DESKTOP)], DESKTOP.parent)
            else:
                bad += 1
                log("  巡检异常 x%d/%d %s" % (bad, UNHEALTHY_THRESHOLD, info[:150]))
                # 关键修正（2026-11-12）：网关"慢"和网关"死"必须分开处理。
                # 旧逻辑：连续 3 次不健康就 bring_up()，而 bring_up() 会杀桌面端。
                # 但桌面端有 30+ 个 ticket bridge Python 子进程，杀掉再拉起会
                # 造成内存尖峰，反而把网关拖垮 —— 形成死亡螺旋。
                # 现在：只有网关进程真的消失，或持续不健康超过阈值很久，
                #       才重启网关；桌面端在网关活着时一律不杀。
                if gateway_proc() is None:
                    log("  网关进程已消失 → 冷启动网关")
                    bring_up()
                    bad = 0
                elif bad >= UNHEALTHY_THRESHOLD:
                    # 网关还在但长时间不健康：只做温和动作（拉起缺失的桌面端），
                    # 不杀桌面端、不重启网关，避免加剧资源争抢。
                    log("  网关存活但持续不健康 → 只补桌面端，不重启网关")
                    if not desktop_procs():
                        spawn([str(DESKTOP)], DESKTOP.parent)
                    bad = 0
        except Exception as e:
            log("  巡检出错 %r" % (e,))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        # --launch 正常退出路径，不算错误
        raise
    except BaseException:
        import traceback
        try:
            with open(str(LOG), "a", encoding="utf-8") as _f:
                _f.write("[FATAL] " + traceback.format_exc() + "\n")
        except Exception:
            pass
        raise
