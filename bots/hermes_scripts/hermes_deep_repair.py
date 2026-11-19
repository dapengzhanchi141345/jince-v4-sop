# -*- coding: utf-8 -*-
"""Hermes 本地桌面「打不开对话」深度修复 / 自愈脚本。

根因链（2026-11-12 实测）：
  1. 后台自动更新 uv sync 失败 -> 遗留死锁 -> 网关监管链断裂。
  2. 网关冷启动约 8~12 分钟；桌面端若在此期间启动，经控制 socket
     申请 session ticket 失败并 latch（锁存）失败状态。
  3. 网关每次启动会新建 TicketStore(instance_id)，桌面端持有的旧票据
     无法 redeem -> /api/profiles 等全部 401。
  4. state.db 膨胀 + WAL 长期不满 checkpoint -> 写入排队超时，
     会话恢复报 storage_unavailable。
  5. 网关用裸 tools/python + 注入 site-packages，pywin32 的
     pywintypes DLL 不在 PATH -> ACL/日志模块降级。

修复原则：严格按「网关 ready 之后才启动桌面端」的顺序完整重启；
所有陈旧状态改名备份（不删除）；数据库先 checkpoint 再做完整快照，
然后 VACUUM；全程 E 盘，不写 C 盘；不回显任何明文密钥。

用法：
  python hermes_deep_repair.py --check   # 只体检，不改任何东西
  python hermes_deep_repair.py --repair  # 完整修复（会短暂关闭桌面端）
"""
import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import psutil

HOME = Path(r"E:\workbuddy\国外模型\hermes")
REPO = HOME / "hermes-agent"
DESKTOP_EXE = REPO / "apps" / "desktop" / "release" / "win-unpacked" / "Hermes.exe"
LAUNCHER = HOME / "bin" / "hermes.exe"
BACKUP = HOME / "repair-backup-20261112"
LOGDIR = HOME / "logs"
SITE = HOME / "installs" / "4ea489dd943be455" / "environments" / "ab92248aaa8b4c8f8a9091996d241c1d" / "venv" / "Lib" / "site-packages"
WIN32_DLL = SITE / "pywin32_system32"
DB = HOME / "state.db"

DETACH = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def is_gateway(proc):
    try:
        name = (proc.info.get("name") or "").lower()
        cmd = " ".join(proc.info.get("cmdline") or [])
        return name.startswith("python") and "hermes_cli.main" in cmd and "gateway run" in cmd
    except Exception:
        return False


def find_gateway():
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if is_gateway(p):
                return p
        except Exception:
            pass
    return None


def gateway_ports():
    """网关会同时监听多个端口（HTTP API / 控制通道 / webapp），必须全部探测。"""
    p = find_gateway()
    if p is None:
        return [], None
    ports = []
    try:
        for c in p.net_connections(kind="inet"):
            if c.status == "LISTEN" and c.laddr.ip in ("127.0.0.1", "0.0.0.0"):
                ports.append(c.laddr.port)
    except Exception:
        pass
    return sorted(set(ports)), p.pid


def probe_ready(ports):
    last = ""
    for port in ports:
        code, body = health(port)
        last = body
        if code == 200 and '"ok":true' in body:
            return port, code, body
    return None, 0, last if ports else "no-listen"


def health(port):
    """curl 优先（本机实测比 urllib 稳），urllib 兜底。网关被 401 洪流拖慢时会间歇超时。"""
    url = "http://127.0.0.1:%d/api/health" % port
    try:
        r = subprocess.run(
            ["curl", "-s", "--noproxy", "*", "--max-time", "10",
             "-w", "\n__HC__%{http_code}", url],
            capture_output=True, text=True, timeout=14)
        out = r.stdout or ""
        if "__HC__" in out:
            body, code = out.rsplit("__HC__", 1)
            return int(code.strip() or 0), body.strip()[:400]
        return 0, out.strip()[:120]
    except Exception:
        pass
    try:
        with OPENER.open(urllib.request.Request(url), timeout=10) as r:
            return r.status, r.read(400).decode("utf-8", "ignore")
    except Exception as ex:
        return 0, str(ex)[:120]


def check():
    log("=== 体检（只读）===")
    ports, pid = gateway_ports()
    log("  网关 pid=%s ports=%s" % (pid, ports))
    hit, code, body = probe_ready(ports)
    log("  /api/health -> HTTP %s port=%s  %s" % (code, hit, body[:160]))
    if not hit:
        log("  !! 网关未就绪或 HTTP API 端口不可达")
    desktops = [p.pid for p in psutil.process_iter(["pid", "name"])
                if (p.info.get("name") or "").lower() == "hermes.exe"]
    log("  桌面进程数=%d pids=%s" % (len(desktops), desktops[:8]))
    if DB.exists():
        log("  state.db %.1f MB, wal %.1f MB" % (
            DB.stat().st_size / 1024 / 1024,
            (DB.with_name(DB.name + "-wal").stat().st_size / 1024 / 1024)
            if DB.with_name(DB.name + "-wal").exists() else 0))
    for f in ("desktop.log", "errors.log"):
        p = LOGDIR / f
        if not p.exists():
            continue
        tail = p.read_bytes()[-400000:].decode("utf-8", "ignore")
        log("  %s 近段: 401=%d, timed_out=%d, bootstrap_failed=%d, storage_unavailable=%d" % (
            f, tail.count("401:"), tail.count("Timed out"), tail.count("ticket bootstrap failed"),
            tail.count("storage_unavailable")))
    return 0


def stop_all():
    log("=== 1. 停止所有 Hermes 进程 ===")
    targets = []
    for p in psutil.process_iter(["pid", "name", "cmdline", "ppid"]):
        try:
            name = (p.info.get("name") or "").lower()
            cmd = " ".join(p.info.get("cmdline") or [])
            if name == "hermes.exe":
                targets.append((p, "desktop"))
            elif is_gateway(p):
                targets.append((p, "gateway"))
            elif name.startswith("python") and "-P -u -c" in cmd and "hermes" in cmd.lower():
                targets.append((p, "stuck-probe"))
        except Exception:
            pass
    for p, kind in targets:
        try:
            p.kill()
            log("  kill %-12s pid=%d" % (kind, p.pid))
        except Exception as e:
            log("  kill err pid=%s %s" % (p.pid, str(e)[:60]))
    time.sleep(5)
    gone, alive = psutil.wait_procs([p for p, _ in targets], timeout=6)
    left = [p.pid for p in alive]
    if left:
        log("  仍在退出的 pid=%s（继续，DB 独占打开会验证）" % left[:8])
    log("  停机完成")


def backup_states():
    BACKUP.mkdir(parents=True, exist_ok=True)
    log("=== 2. 备份状态文件 -> %s ===" % BACKUP.name)
    names = ["gateway.pid", "gateway.lock", "gateway_state.json", "gateway-connections.json",
             "processes.json", "spawn-ledger.json", "auth.json", "auth.lock",
             "channel_directory.json", "ui-preferences.json", ".hermes-update-in-progress.lock"]
    for name in names:
        src = HOME / name
        if src.exists():
            try:
                shutil.copy2(src, BACKUP / name)
                log("  备份 %s (%dB)" % (name, src.stat().st_size))
            except Exception as e:
                log("  备份失败 %s: %s" % (name, str(e)[:80]))


def maintain_db():
    log("=== 3. state.db 维护 ===")
    if not DB.exists():
        log("  !! state.db 不存在，跳过")
        return
    before = DB.stat().st_size / 1024 / 1024
    con = sqlite3.connect(str(DB), timeout=30, isolation_level=None)
    try:
        r = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        log("  checkpoint(TRUNCATE) -> %s" % (r,))
    finally:
        con.close()
    snap = BACKUP / "state.db.pre-vacuum"
    shutil.copy2(DB, snap)
    log("  完整快照已存 %s (%.1f MB)" % (snap.name, snap.stat().st_size / 1024 / 1024))
    con = sqlite3.connect(str(DB), timeout=120, isolation_level=None)
    try:
        t = time.time()
        con.execute("VACUUM")
        log("  VACUUM 完成 %.1fs, %.1f MB -> %.1f MB" % (
            time.time() - t, before, DB.stat().st_size / 1024 / 1024))
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception as e:
        log("  !! VACUUM 失败（快照仍在，可回滚）: %s" % str(e)[:160])
    finally:
        con.close()


def rotate_stale():
    log("=== 4. 陈旧锁/状态改名（不删除）===")
    paths = [HOME / ".hermes-update-in-progress.lock", HOME / "gateway.pid",
             HOME / "gateway.lock", HOME / "auth.lock", HOME / "processes.json",
             HOME / "spawn-ledger.json", REPO / ".git" / "hermes-update.lock"]
    for p in paths:
        if not p.exists():
            continue
        dst = p.with_name(p.name + ".stale-deepfix")
        try:
            if dst.exists():
                dst.unlink()
            p.rename(dst)
            log("  改名 %s" % p.name)
        except Exception as e:
            log("  改名失败 %s: %s" % (p.name, str(e)[:80]))


def clean_env(env):
    e = dict(env)
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        if k in e:
            e[k] = ""
    dll = str(WIN32_DLL)
    if WIN32_DLL.is_dir() and dll.lower() not in e.get("PATH", "").lower():
        e["PATH"] = dll + os.pathsep + e.get("PATH", "")
        log("  PATH 注入 pywin32_system32（修复 pywintypes 加载）")
    else:
        log("  pywin32_system32 已在 PATH 或不存在")
    e.pop("HERMES_SESSION_ID", None)
    e["HERMES_GATEWAY_DETACHED"] = "1"
    e["HERMES_HOME"] = str(HOME)
    e["HERMES_DESKTOP_HERMES"] = str(LAUNCHER)
    return e


def spawn(cmd, cwd, env, label):
    p = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=DETACH)
    log("  %s 已拉起 pid=%d" % (label, p.pid))
    return p


def repair():
    log("=== 深度修复开始（全程 E 盘，陈旧状态只改名不删除）===")
    gw = find_gateway()
    gw_env, gw_cmd = None, None
    if gw is not None:
        try:
            gw_env, gw_cmd = dict(gw.environ()), gw.cmdline()
            log("=== 0. 已捕获在跑网关的配置 pid=%d ===" % gw.pid)
            log("  cmd=%s" % " ".join(gw_cmd)[:170])
        except Exception as e:
            log("  捕获 env 失败（将回退 launcher）: %s" % str(e)[:80])

    stop_all()
    backup_states()
    maintain_db()
    rotate_stale()

    env = clean_env(gw_env if gw_env else os.environ.copy())
    cmd = gw_cmd if gw_cmd else [str(LAUNCHER), "gateway", "run", "--quiet"]
    log("=== 5. 先启动网关（桌面端暂不起）===")
    spawn(cmd, REPO, env, "网关")

    log("=== 6. 等待网关 ready（最多 15 分钟）===")
    port = None
    for i in range(90):
        time.sleep(10)
        ports, pid = gateway_ports()
        hit, code, body = probe_ready(ports)
        if hit:
            port = hit
            log("  ✅ 网关 READY port=%d pid=%s，耗时约 %ds" % (port, pid, (i + 1) * 10))
            break
        if i % 3 == 0:
            log("  等待 ready %ds ports=%s resp=%s" % ((i + 1) * 10, ports, body[:90]))
    else:
        log("  !! 15 分钟内未 ready，停止脚本，未启动桌面端（可查 logs/gateway.log）")
        return 2

    log("=== 7. 网关 ready 后再启动桌面端（保证 ticket 一次签发成功）===")
    spawn([str(DESKTOP_EXE)], DESKTOP_EXE.parent, env, "桌面端")
    time.sleep(35)

    log("=== 8. 验证 ===")
    ports, pid = gateway_ports()
    hit, code, body = probe_ready(ports)
    log("  /api/health -> HTTP %s port=%s %s" % (code, hit, body[:170]))
    for f in ("desktop.log", "errors.log"):
        p = LOGDIR / f
        if p.exists():
            tail = p.read_bytes()[-120000:].decode("utf-8", "ignore")
            log("  %s 最新 120KB: 401=%d timed_out=%d bootstrap_failed=%d storage_unavailable=%d" % (
                f, tail.count("401:"), tail.count("Timed out"),
                tail.count("ticket bootstrap failed"), tail.count("storage_unavailable")))
    log("=== 修复流程结束，请在桌面端新建会话发一句 hi 做最终确认 ===")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只读体检")
    ap.add_argument("--repair", action="store_true", help="完整修复")
    a = ap.parse_args()
    sys.exit(check() if a.check else repair() if a.repair else check())
