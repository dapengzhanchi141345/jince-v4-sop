#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策宗师团 · 自动巡检 (no_agent 确定性, 0 LLM, 429-proof)
每 30min 跑一次: 全量核今日 6 节点是否落记 + 实盘实读 + gateway/L3/MT5 三件套.
全绿 -> 静默 (不投递, 打印一行 [巡检OK] 留痕);
有异常 -> 投递到群 (bot-chat) 点名, 附根因+已做动作.
根治目标: 不再靠人工"盯下一节点", 缺发/降级/三件套挂 = 自动报警.
用法: python jince_auto_patrol.py   (Hermes cron no_agent 调, stdout 投递)
"""
import os, sys, json, time, subprocess, datetime, zoneinfo, glob

DATA = r"E:/GoldstrategyEngine/data"
ATE_PY = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/pythonw.exe"
BJT = zoneinfo.ZoneInfo("Asia/Shanghai")
NODE_SCRIPT = r"E:/workbuddy/国外模型/hermes/scripts/jince_node.py"
WATCHDOG_PY = r"E:/workbuddy/国外模型/hermes/scripts/jince_watchdog.py"
RECEIPT = os.path.join(DATA, "delivery_receipt.jsonl")   # {node,day,ts,by=patrol} 巡检补投回执
PATROL_REINVEST_LIMIT = 1      # 每节点每日补投上限(幂等, 防30min循环刷屏)
PATROL_GRACE_S = 30 * 60      # 节点生成后宽限30min: 正常路径(cron秒投)先投, 超30min没进群才兜底补

# [2026-10-23 根治] OpenBLAS 线程限: 系统 16GB 常 95% 吃紧, ATE 子代 import numpy/OpenBLAS
# 期默认起满线程池 → 内存分配失败 → fork 崩 → 误报"MT5 握手降级/ATE 连不上/IPC 冻死".
# auto_run_cycle.py 已用同款 OMP/OPENBLAS_NUM_THREADS=2 护住(17-18行); 巡检起 ATE 子代没继承.
# 此处限定 BLAS 线程=2, 只减线程内存、不碰任何挂单/交易闸, 子代 env = os.environ 去掉 PYTHON*
# 再盖上两个 BLAS 限. 纯 infra 加固, 不引入新行为.
def _ate_child_env():
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    # [11-09 加固] 16GB 内存 95% 吃紧时 2 线程仍会 OpenBLAS malloc 失败(22:31 巡检误报根因), 降到 1 线程:
    # 只减子代 BLAS 内存占用, 不碰任何挂单/交易闸, 纯 infra.
    env["OMP_NUM_THREADS"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"
    return env

# 6 节点 -> (job 名关键词, 应发时刻 "HH:MM" 北京时间)
NODES = [
    ("asia_open",    "jince-node-tokyo-open-0800",    "08:05"),
    ("asia_close",   "jince-node-tokyo-close-1200",   "12:05"),
    ("europe_open",  "jince-node-london-open-1500",   "15:05"),
    ("europe_close", "jince-node-london-close-1800",  "18:05"),
    ("us_open",      "jince-node-ny-open-2100",       "21:05"),
    ("us_close",     "jince-node-ny-close-0200",      "02:05"),
]

def bjt_now():
    return datetime.datetime.now(BJT)

def today_str():
    return bjt_now().strftime("%Y-%m-%d")

# ---------- 检查1: 今日 6 节点是否落记 ----------
def check_nodes():
    got = {}
    try:
        for line in open(os.path.join(DATA, "discussion_log.jsonl"), encoding="utf-8", errors="ignore"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if not isinstance(r, dict):
                continue  # 某行不是对象(dict), 跳过, 防 .get 炸
            n = r.get("node")
            if n in ("asia_open","asia_close","europe_open","europe_close","us_open","us_close"):
                try:
                    d = datetime.datetime.fromtimestamp(int(float(r.get("ts"))), BJT)
                except Exception:
                    continue
                if d.strftime("%Y-%m-%d") == today_str():
                    got.setdefault(n, []).append(d.strftime("%H:%M"))
    except Exception as e:
        return [f"discussion_log 读取失败: {e}"], got
    now_hm = bjt_now().strftime("%H:%M")
    problems = []
    # 只核"应发时刻已过"的节点 (未到点不算缺发)
    for key, _job, due in NODES:
        # 跨 02:00 美盘收口特判: 02:05 属于前一自然日 22:00-04:59 窗口
        if key == "us_close":
            # 美盘收口 02:05 归当日凌晨; 当前 04:59 之后才核当日
            if now_hm < "04:59":
                continue  # 当日 02:05 美盘收口还没到/刚过, 看昨日不在此窗口误报
            else:
                pass
        else:
            if now_hm < due:
                continue  # 未到应发时刻, 不核
        if not got.get(key):
            problems.append(f"节点[{key}]应发 {due} 未落记 (截至今日已发节点: {sorted(got) or '无'})")
    return problems, got

# ---------- 检查2: 实盘实读 (根 MT5 import 坏) ----------
def check_live_read():
    code = ("import os,json,sys\n"
            "os.environ.pop('PYTHONPATH',None);os.environ.pop('PYTHONHOME',None)\n"
            "sys.path.insert(0,r'E:/GoldstrategyEngine')\n"
            "import mt5_live_read\n"
            "r=mt5_live_read.live_read()\n"
            "print(json.dumps(r,ensure_ascii=False,default=str))\n")
    try:
        # [2026-10-06 加固] 45s -> 90s: MT5 终端重启/IPC 卡顿窗口内 45s 不够, 会误报
        # "MT5 实读异常: timed out after 45s"(07:01 实例). 90s 容忍窗口; 真卡死仍降级明示.
        res = subprocess.run([ATE_PY, "-c", code], capture_output=True, text=True,
                             timeout=90, cwd=r"E:/GoldstrategyEngine",
                             env=_ate_child_env())
        # [11-09 加固] OpenBLAS 内存分配偶发失败(系统内存峰值)会误报"MT5握手降级": 5s 后重试一次,
        # 重试通过=瞬峰恢复(只留痕不报异常), 两次皆败才报(stderr 根因保留). 纯 infra, 不碰交易闸.
        if res.returncode != 0 and "Memory allocation" in (res.stderr or ""):
            import time as _t
            _t.sleep(5)
            _r2 = subprocess.run([ATE_PY, "-c", code], capture_output=True, text=True,
                                 timeout=90, cwd=r"E:/GoldstrategyEngine",
                                 env=_ate_child_env())
            if _r2.returncode == 0:
                res = _r2  # 瞬峰恢复
            else:
                res = _r2  # 两次皆败, 报
        for line in res.stdout.strip().splitlines():
            line = line.strip()
            if line.startswith("{"):
                r = json.loads(line)
                if r.get("degraded"):
                    return [f"MT5 实读降级(ATE 也连不上, 终端可能挂了): {r.get('errors')}"], r
                return [], r
        return [f"MT5 实读子进程无 JSON: {res.stderr[:80] or res.stdout[:80]}"], {}
    except Exception as e:
        return [f"MT5 实读异常: {e}"], {}

# ---------- 检查3: gateway / L3 / MT5 终端 三件套 ----------
def check_infra():
    problems = []
    # gateway
    # [2026-10-24 根治] 旧法每30min跑完整CLI `gateway status`(拉起整个hermes CLI, 常>60s),
    # 一超时就记"异常"进群刷屏, 而网关其实一直活着. 现改秒级进程探活优先:
    #   ① CIM匹配'gateway run'活进程数(≈1.2s): >0=健康, 跳过(不再每轮跑慢CLI往返→根治刷屏)
    #   ② 探到0个/探测不确定才回退一次完整CLI确认(只有明确No gateway才报, 保留真故障检测)
    _GW_CLI = [r"E:/workbuddy/国外模型/hermes/hermes-agent/venv/Scripts/python.exe",
               "-m", "hermes_cli.main", "gateway", "status"]
    _GW_PS = r"""$n=0; foreach($nm in @('pythonw.exe','python.exe')){ foreach($p in (Get-CimInstance Win32_Process -Filter "Name='$nm'")){ if($p.CommandLine -match 'gateway run'){ $n++ } } }; $n"""
    def _gw_alive():
        """秒级 gateway 进程探活: True/False/None(探测不确定)."""
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", _GW_PS],
                               capture_output=True, text=True, timeout=15,
                               creationflags=0x08000000, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                return None
            ms = re.findall(r"\b\d+\b", r.stdout or "")
            return (int(ms[-1]) > 0) if ms else False
        except Exception:
            return None
    alive = _gw_alive()
    if alive is True:
        pass  # 网关活: 健康, 跳过(不再每轮跑慢CLI往返 → 根治刷屏)
    else:
        # 探到0个/探测不确定: 回退一次完整CLI确认(短超时), 只有明确"没在跑"才报
        try:
            r = subprocess.run(_GW_CLI, capture_output=True, text=True, timeout=45,
                               cwd=r"E:/GoldstrategyEngine", creationflags=0x08000000)
            txt = (r.stdout or "") + (r.stderr or "")
            if "No gateway" in txt or "not running" in txt:
                problems.append("gateway 未运行 (No gateway/not running)")
            # CLI仍卡/输出含糊: 不刷"异常"(活网关CLI卡是已知现象), 静默降级下轮再探
        except Exception:
            pass  # 探测不确定: 保守静默, 不误报
    # MT5 终端
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq terminal64.exe"],
                           capture_output=True, text=True, timeout=20,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if "terminal64.exe" not in r.stdout:
            problems.append("MT5 终端 (terminal64.exe) 未运行")
    except Exception:
        pass
    return problems

# ---------- 检查4: 节点脚本自身没被改坏 (语法) ----------
def check_node_script():
    try:
        r = subprocess.run([ATE_PY, "-m", "py_compile", NODE_SCRIPT], capture_output=True,
                           text=True, timeout=30)
        if r.returncode != 0:
            return [f"jince_node.py 语法坏: {(r.stderr or r.stdout)[:100]}"]
    except Exception as e:
        return [f"节点脚本语法检查异常: {e}"]
    return []

# ---------- 检查5: 投递层兜底 (节点生成了, 有没有真投进群?) ----------
# 根因(2026-10-07 21:05 事故): check_nodes 只验"节点写没写进 discussion_log"(生成层),
# 从不验"投没投进群"(投递层). 节点落记了却卡 cron 队列 12h 没投达, 巡检 30min 兜底漏看这层.
# 兜底: 已生成 + 超宽限30min没投达 + 当日没补投过 -> 巡检补投该节点(--noreceipt 不重复写留痕) + 记回执.
def _due_now(key, now_hm):
    """节点此刻是否"应发已过"(与 check_nodes 同窗口逻辑). us_close 02:05 归凌晨, 04:59 后才核当日."""
    if key == "us_close":
        return now_hm >= "04:59"
    for k, _j, due in NODES:
        if k == key:
            return now_hm >= due
    return False

def _receipt_count_today(key, day):
    try:
        n = 0
        for line in open(RECEIPT, encoding="utf-8", errors="ignore"):
            try:
                r = json.loads(line.strip())
            except Exception:
                continue
            if isinstance(r, dict) and r.get("node") == key and r.get("day") == day:
                n += 1
        return n
    except Exception:
        return 0   # 读不到回执 -> 视为未补投, 宁可补(幂等上限兜底)

def check_delivery():
    """对'已生成但超宽限没投达'的节点做巡检补投. 返回 (problems, reinvested).
    problems 仅列'补投失败'的; 成功补投的不算异常(已进群), 只在 reinvested 留痕. 全绿(无卡)时静默."""
    day = today_str()
    now_hm = bjt_now().strftime("%H:%M")
    # 1. 读 discussion_log 取每节点当日最新生成 ts
    got_ts = {}
    try:
        for line in open(os.path.join(DATA, "discussion_log.jsonl"), encoding="utf-8", errors="ignore"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if not isinstance(r, dict):
                continue
            n = r.get("node")
            if n in ("asia_open","asia_close","europe_open","europe_close","us_open","us_close"):
                ts = r.get("ts")
                try:
                    d = datetime.datetime.fromtimestamp(int(float(ts)), BJT)
                except Exception:
                    continue
                if d.strftime("%Y-%m-%d") == day:
                    cur = got_ts.get(n)
                    if cur is None or ts > cur:
                        got_ts[n] = ts
    except Exception as e:
        return [f"check_delivery 读 discussion_log 失败: {e}"], []
    now_ts = time.time()
    problems, reinvested = [], []
    for key, _job, _due in NODES:
        if not _due_now(key, now_hm):
            continue                       # 未到应发时刻, 不核
        if key not in got_ts:
            continue                       # 未生成 = 生成层缺发, 归 check_nodes 报, 这里不重复
        if now_ts - got_ts[key] < PATROL_GRACE_S:
            continue                       # 生成后30min宽限内, 正常投递路径(cron秒投)优先, 不误补
        if _receipt_count_today(key, day) >= PATROL_REINVEST_LIMIT:
            continue                       # 当日已补投过(幂等), 不再刷
        # 真卡投递: 补投该节点摘要(stdout 由 cron 壳投群), 不重复写留痕
        try:
            r = subprocess.run([ATE_PY, NODE_SCRIPT, key, "--noreceipt"], capture_output=True,
                               text=True, timeout=120, cwd=r"E:/GoldstrategyEngine")
            body = (r.stdout or "").strip()
            if not body:
                problems.append(f"投递兜底[{key}] 补投无输出(rc={r.returncode})")
                continue
            try:
                with open(RECEIPT, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"node": key, "day": day, "ts": int(now_ts), "by": "patrol"},
                                       ensure_ascii=False) + "\n")
            except Exception:
                pass
            reinvested.append(key)
            print(f"【投递兜底·补投 {bjt_now().strftime('%H:%M')}】节点[{key}]生成后>30min未进群, 巡检已补投并记回执(幂等, 每节点每日1次)")
        except Exception as e:
            problems.append(f"投递兜底[{key}] 补投异常: {str(e)[:60]}")
    return problems, reinvested

def main():
    problems = []
    p_nodes, got = check_nodes()
    problems += p_nodes
    p_live, _live = check_live_read()
    problems += p_live
    problems += check_infra()
    problems += check_node_script()
    # 检查5: 投递层兜底(补投卡队列节点), 补投成功不计异常, 只补投失败计入
    p_dlv, reinvested = check_delivery()
    problems += p_dlv

    now = bjt_now().strftime("%Y-%m-%d %H:%M")
    if not problems:
        tail = f" | 投递兜底补投{reinvested}" if reinvested else ""
        print(f"[巡检OK {now}] 6节点已发{sorted(got) or '无'} | MT5实读通 | gateway/MT5终端全活 | 节点脚本语法OK{tail}")
        return
    print(f"【金策自动巡检·异常 {now}】发现 {len(problems)} 处, 主动报不静默:")
    for i, p in enumerate(problems, 1):
        print(f"  {i}. {p}")
    print(f"· 已发节点: {sorted(got) or '无'}")
    if reinvested:
        print(f"· 投递兜底: 已补投 {reinvested} (生成后>30min未进群, 幂等每节点每日1次)")
    print(f"· 闭环: 巡检每30min自动跑, 有异常自动进群点名, 全绿静默; 历史回测≠未来收益")

if __name__ == "__main__":
    main()
