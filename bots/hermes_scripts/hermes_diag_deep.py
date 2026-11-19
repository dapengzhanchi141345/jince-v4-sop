#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Hermes 桌面端打不开对话 —— 深度诊断脚本（只读）"""
import os, sys, time, json, sqlite3, collections, psutil, urllib.request

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
HOME = r"E:\workbuddy\国外模型\hermes"


def line(t):
    print(t, flush=True)


def health(port, timeout=4):
    t = time.time()
    try:
        with OPENER.open("http://127.0.0.1:%d/api/health" % port, timeout=timeout) as r:
            return r.status, round(time.time() - t, 2), r.read(200).decode("utf-8", "ignore")
    except Exception as e:
        return 0, round(time.time() - t, 2), type(e).__name__


line("=" * 72)
line("【1】内存占用 TOP 20")
line("=" * 72)
vm = psutil.virtual_memory()
line("  物理内存 total=%.1fGB used=%.1f%% avail=%.1fGB" % (
    vm.total / 1073741824, vm.percent, vm.available / 1073741824))
mems = []
for p in psutil.process_iter(["pid", "name", "cmdline", "memory_info"]):
    try:
        mm = p.info["memory_info"]
        if not mm:
            continue
        rss = mm.rss / 1048576
        cl = " ".join(p.info["cmdline"] or [])
        tag = ""
        low = cl.lower()
        if "hermes" in low or (p.info["name"] or "").lower() == "hermes.exe":
            tag = "  <<< HERMES"
        elif "python" in (p.info["name"] or "").lower():
            tag = "  (python)"
        mems.append((rss, p.pid, p.info["name"], tag))
    except Exception:
        pass
mems.sort(reverse=True)
hermes_total = 0.0
for rss, pid, nm, tag in mems[:20]:
    line("  %8.0fMB  pid=%-7d %-18s%s" % (rss, pid, nm, tag))
hermes_sum = sum(r for r, pid, nm, tag in mems if tag.strip() in ("<<< HERMES", "(python)"))
line("  ---- 所有 Hermes/python 相关进程合计 RSS: %.0f MB (%.1f GB)" % (
    hermes_sum, hermes_sum / 1024))

line("")
line("=" * 72)
line("【2】state.db 空间去向 (dbstat)")
line("=" * 72)
db = os.path.join(HOME, "state.db").replace("\\", "/")
line("  文件大小 %.1f MB" % (os.path.getsize(db.replace("/", os.sep)) / 1048576))
try:
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=60)
    rows = con.execute(
        "SELECT name, SUM(pgsize)/1048576.0 mb FROM dbstat "
        "GROUP BY name ORDER BY SUM(pgsize) DESC LIMIT 18").fetchall()
    for n, mb in rows:
        line("  %-36s %8.1f MB" % (n, mb or 0))
    tot = con.execute("SELECT SUM(pgsize)/1048576.0 FROM dbstat").fetchone()[0]
    line("  ---- dbstat 合计 %.1f MB" % tot)
    line("  freelist_count = %d" % con.execute("PRAGMA freelist_count").fetchone()[0])
    line("  page_size      = %d" % con.execute("PRAGMA page_size").fetchone()[0])
    con.close()
except Exception as e:
    line("  dbstat 失败: %r" % (e,))

line("")
line("=" * 72)
line("【3】state.db 关键查询耗时（模拟桌面端 sidebar/resume）")
line("=" * 72)
try:
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=60)
    con.row_factory = sqlite3.Row
    cols = [r[1] for r in con.execute("PRAGMA table_info(sessions)")]
    line("  sessions 表列: %s" % ", ".join(cols))
    prof_col = "profile" if "profile" in cols else ("source" if "source" in cols else cols[0])
    q = "SELECT id FROM sessions ORDER BY started_at DESC LIMIT 100"
    t = time.time()
    con.execute(q).fetchall()
    line("  ORDER BY started_at LIMIT 100 : %.3fs" % (time.time() - t))
    t = time.time()
    con.execute("SELECT chat_id, COUNT(*) FROM sessions GROUP BY chat_id").fetchall()
    line("  GROUP BY chat_id              : %.3fs" % (time.time() - t))
    t = time.time()
    n = con.execute("SELECT COUNT(*) FROM messages WHERE session_id=(SELECT id FROM sessions ORDER BY started_at DESC LIMIT 1)").fetchone()[0]
    line("  最近会话消息数=%d, 查询 %.3fs" % (n, time.time() - t))
    t = time.time()
    con.execute("SELECT COUNT(*) FROM messages_fts WHERE messages_fts MATCH 'a'").fetchall()
    line("  FTS MATCH 查询               : %.3fs" % (time.time() - t))
    con.close()
except Exception as e:
    line("  查询失败: %r" % (e,))

line("")
line("=" * 72)
line("【4】网关并发响应曲线（桌面端启动瞬间会并发打 30 个 profile）")
line("=" * 72)
gw = None
for p in psutil.process_iter(["pid", "cmdline"]):
    try:
        cl = " ".join(p.info["cmdline"] or [])
        if "hermes_cli.main" in cl and "gateway run" in cl:
            gw = p
            break
    except Exception:
        pass
if gw is None:
    line("  !! 未找到 gateway 进程")
else:
    ports = sorted({c.laddr.port for c in gw.net_connections(kind="inet")
                    if c.status == "LISTEN"})
    line("  gateway pid=%d 监听端口=%s" % (gw.pid, ports))
    for pt in ports:
        code, dt, body = health(pt, timeout=6)
        line("    端口 %-6d -> %s %.2fs  %s" % (pt, code or "FAIL", dt, body[:70].replace("\n", " ")))
    good = [pt for pt in ports if health(pt, timeout=6)[0] == 200]
    if good:
        pt = good[0]
        import threading
        res = []
        lock = threading.Lock()

        def worker(i):
            c, d, b = health(pt, timeout=20)
            with lock:
                res.append((c, d))

        ths = [threading.Thread(target=worker, args=(i,)) for i in range(30)]
        t0 = time.time()
        for t in ths:
            t.start()
        for t in ths:
            t.join()
        ok = sum(1 for c, d in res if c == 200)
        worst = max(d for c, d in res)
        line("  30 并发 /api/health: 成功 %d/30, 最慢 %.2fs, 总耗时 %.2fs" % (
            ok, worst, time.time() - t0))
        line("  延迟分布: %s" % sorted(d for c, d in res))

line("")
line("=" * 72)
line("【5】supervisor 巡检误判分析")
line("=" * 72)
sup = os.path.join(HOME, "logs", "hermes-supervisor.log")
if os.path.exists(sup):
    txt = open(sup, encoding="utf-8", errors="replace").read()
    tail = txt.splitlines()[-400:]
    restarts = [l for l in tail if "触发自愈重启" in l]
    line("  最近 400 行内自愈重启次数: %d" % len(restarts))
    for l in restarts[-8:]:
        line("    %s" % l[:120])
    kills = [l for l in tail if "停止 desktop" in l]
    line("  被杀的 desktop 进程次数: %d" % len(kills))
else:
    line("  无 supervisor 日志")
line("")
line("  [诊断结束]")
