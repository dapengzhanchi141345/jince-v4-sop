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

# [2026-10-23 根治] OpenBLAS 线程限: 系统 16GB 常 95% 吃紧, ATE 子代 import numpy/OpenBLAS
# 期默认起满线程池 -> 内存分配失败 -> fork 崩 -> 误报"MT5 握手降级/ATE 连不上/IPC 冻死".
# auto_run_cycle.py 已用同款 OMP/OPENBLAS_NUM_THREADS=2 护住(17-18行); 巡检起 ATE 子代没继承.
# 限定 BLAS 线程=2, 只减线程内存、不碰任何挂单/交易闸. 纯 infra 加固.
def _ate_child_env():
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    env["OMP_NUM_THREADS"] = "2"
    env["OPENBLAS_NUM_THREADS"] = "2"
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
        # [2026-10-23 后台化] CREATE_NO_WINDOW: 瞬时子进程不再闪黑框(逻辑不变, 保留 stdout 捕获).
        res = subprocess.run([ATE_PY, "-c", code], capture_output=True, text=True,
                             timeout=90, cwd=r"E:/GoldstrategyEngine",
                             env=_ate_child_env(), creationflags=0x08000000)
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
        r = subprocess.run("tasklist /FI \"IMAGENAME eq terminal64.exe\" 2>nul", shell=True,
                           capture_output=True, text=True, timeout=20,
                           creationflags=0x08000000)
        if "terminal64.exe" not in r.stdout:
            problems.append("MT5 终端 (terminal64.exe) 未运行")
    except Exception:
        pass
    return problems

# ---------- 检查4: 节点脚本自身没被改坏 (语法) ----------
def check_node_script():
    try:
        r = subprocess.run([ATE_PY, "-m", "py_compile", NODE_SCRIPT], capture_output=True,
                           text=True, timeout=30, creationflags=0x08000000)
        if r.returncode != 0:
            return [f"jince_node.py 语法坏: {(r.stderr or r.stdout)[:100]}"]
    except Exception as e:
        return [f"节点脚本语法检查异常: {e}"]
    return []

def check_chief_queue():
    """[2026-10-06] chief 主持任务队列: 读 E:\\workbuddy\\金策宗师团\\chief_主持任务队列.jsonl 的 PENDING 项,
    有 PENDING 就点名报(让主持活不漏), 已 DONE 的静默. 只点名不代执行(执行归 chief LLM 回话后)."""
    q = r"E:\workbuddy\金策宗师团\chief_主持任务队列.jsonl"
    if not os.path.exists(q):
        return []
    pending = []
    try:
        for line in open(q, encoding="utf-8", errors="ignore"):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("status") == "PENDING":
                pending.append(rec)
    except Exception as e:
        return [f"chief_主持任务队列 读取失败: {e}"]
    if not pending:
        return []
    msgs = []
    for rec in pending:
        tasks = rec.get("tasks", [])
        msgs.append(f"chief 主持任务队列有 {len(tasks)} 项 PENDING({rec.get('beijing','?')}): " + "; ".join(str(t)[:40] for t in tasks[:4]))
    return msgs

def check_crypto_unlock():
    """币系close-only主动监视(李彦明11-08令'不能干等着'): 关着=每轮巡报告知在盯, 放开但没开单=异常报警"""
    import subprocess
    ATE = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe"
    code = (
        "import MetaTrader5 as mt5\n"
        "if not mt5.initialize(): print('OFFLINE'); raise SystemExit\n"
        "tm = {s: mt5.symbol_info(s).trade_mode for s in ['BTCUSD','ETHUSD','SOLUSD','ADAUSD']}\n"
        "pos = len([p for p in (mt5.positions_get() or []) if p.magic == 30261106])\n"
        "print('TM:' + ','.join(str(v) for v in tm.values()), 'POS:', pos)\n"
        "mt5.shutdown()\n"
    )
    try:
        import os as _os
        _env = {k: v for k, v in _os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "PYTHONNOUSERSITE")}
        r = subprocess.run([ATE, "-c", code], capture_output=True, timeout=45, env=_env)
        out = (r.stdout or b"").decode("utf-8", "replace")
        if isinstance(r.stdout, str): out = r.stdout
        out = out.strip().splitlines()
        line = out[-1] if out else ""
        if "OFFLINE" in out[-1] if out else False:
            return []
        tms = [int(x) for x in line.split("TM:")[1].split(" POS:")[0].split(",")[:4]] if "TM:" in line else []
        pos = int(line.split("POS:")[1].strip()) if "POS:" in line else -1
        # [2026-11-12 主持拍币系口径根治] 巡检实时tm结论落盘, 供主持拍(jince_group_host)直读
        # (主持拍此前读静态crypto_freeze_gate.json=我方闸老值, 误报"已放"42连报实证)
        try:
            import json as _json, datetime as _dt
            _syms = ["BTCUSD", "ETHUSD", "SOLUSD", "ADAUSD"]
            _st = {
                "ts": _dt.datetime.now().strftime("%F %T"),
                "closed_only": bool(tms) and all(t == 4 for t in tms),
                "trade_mode": dict(zip(_syms, tms)),
                "magic_pos": pos,
                "src": "mt5 symbol_info real-time read (patrol 30min)",
            }
            with open(os.path.join(DATA, "coin_tm_state.json"), "w", encoding="utf-8") as _f:
                _json.dump(_st, _f, ensure_ascii=False, indent=1)
        except Exception:
            pass
        if any(t == 1 for t in tms) and pos == 0:
            return ["⚠️ 币系已放开(tm=1)但0.01样本腿未开(0张) — 该开没开, 立即手动开4腿!"]
        if all(t == 4 for t in tms) and pos == 0:
            # [11-13 深度优化·防刷屏] close-only长期稳态去重: 同日只报首拍, 后续静默(5min自修复哨通道独立, 翻1即时开4腿报群不受影响)
            import json as _j3, datetime as _dt3
            _dd_f = os.path.join(DATA, "patrol_coin_dedup.json")
            _dd = {}
            try:
                _dd = _j3.load(open(_dd_f, encoding="utf-8"))
            except Exception:
                pass
            _today_s = _dt3.datetime.now().strftime("%F")
            if _dd.get("state") == "close-only" and _dd.get("date") == _today_s:
                return []  # 同日稳态已报过 -> 静默拍
            _j3.dump({"state": "close-only", "date": _today_s, "ts": _dt3.datetime.now().strftime("%F %T")},
                     open(_dd_f, "w", encoding="utf-8"), ensure_ascii=False)
            return ["币系4品种仍close-only(tm=4, 博德未放开) — 5min哨每5min紧盯, 一翻1自动开4腿, 不等 (同日稳态仅报此拍, 之后静默)"]
        return []
    except Exception:
        return []

def check_family_ledger():
    """[11-14 日结提案] 家族盈亏账本新鲜度哨: family_pnl_ledger.jsonl 超24h没更新=断账红报(防断账被读成'今日0盈亏'); 同日断账状态只报首拍防刷屏"""
    try:
        lp = os.path.join(DATA, "family_pnl_ledger.jsonl")
        if not os.path.exists(lp):
            return []  # 账本未建=日结④会建, 不算断账
        age_h = (time.time() - os.path.getmtime(lp)) / 3600
        if age_h <= 24:
            return []
        _today_s = bjt_now().strftime("%F")
        _g_f = os.path.join(DATA, "ledger_stale_gate.json")
        _g = {}
        try:
            _g = json.load(open(_g_f, encoding="utf-8"))
        except Exception:
            _g = {}
        if _g.get("day") == _today_s and _g.get("stale") is True:
            return []  # 同日断账稳态: 首拍已报, 之后静默(修好即恢复, mtime<24h自动销)
        json.dump({"stale": True, "day": _today_s, "age_h": round(age_h, 1), "ts": bjt_now().strftime("%F %T")},
                  open(_g_f, "w", encoding="utf-8"), ensure_ascii=False)
        return [f"家族账本断裂: family_pnl_ledger.jsonl 已 {age_h:.0f}h 未更新(>24h) — 断账不等于'今日0盈亏', 补账提案进日进化(11-14 日结⑨首案: 11-13/14 引擎账本断两日实收R未入账)"]
    except Exception:
        return []

def check_livestate_zero():
    """[11-15 新增] live_state 零持仓防呆哨: TMGM终端64约2h自重启窗内, yushi快照会读到'进程活但未登录好'=0持仓假信号(02:04实证: 真实7张被写成0, 共享真值源短暂错档).
    判据: live_state positions_n=0 且 1h内账本(order_lifecycle)无平仓记录 -> 疑似假0 -> 自动重刷快照, 刷回>0则报'已自愈', 仍=0则报'真零仓待核'."""
    try:
        import subprocess
        _ls = "E:/AgentCommons/shared/live_state.json"
        if not os.path.exists(_ls):
            return []
        d = json.load(open(_ls, encoding="utf-8"))
        ps = d.get("positions") or []
        if ps:
            return []  # 有持仓=正常
        # 0持仓: 查1h内账本有无平仓记录
        _oc = os.path.join(DATA, "order_lifecycle.jsonl")
        _recent_close = False
        if os.path.exists(_oc):
            _cut = time.time() - 3600
            for _ln in open(_oc, encoding="utf-8", errors="ignore").readlines()[-400:]:
                try:
                    _e = json.loads(_ln)
                except Exception:
                    continue
                if str(_e.get("event", _e.get("action", ""))).lower() in ("close", "closed", "平仓", "close_partial") and _e.get("ts_epoch", 0) > _cut:
                    _recent_close = True
                    break
        if _recent_close:
            return []  # 有平仓记录=真0仓, 正常
        # 疑似假0(终端重登窗): 自动重刷快照一次
        _g_f = os.path.join(DATA, "livestate_zero_gate.json")
        _today_s = bjt_now().strftime("%F")
        _g = {}
        try:
            _g = json.load(open(_g_f, encoding="utf-8"))
        except Exception:
            _g = {}
        _res = subprocess.run('cmd /c E:/AgentCommons/yushi/bin/snapshot.cmd --shared', shell=True,
                              capture_output=True, text=True, timeout=120, errors='ignore')
        time.sleep(2)
        try:
            d2 = json.load(open(_ls, encoding="utf-8"))
            n2 = len(d2.get("positions") or [])
        except Exception:
            n2 = -1
        _state = "recovered" if n2 > 0 else "still_zero"
        if _g.get("day") == _today_s and _g.get("state") == _state:
            return []  # 同日同态稳态: 静默(修好/恢复即翻态, 下拍自动销)
        json.dump({"day": _today_s, "state": _state, "ts": bjt_now().strftime("%F %T"), "n": n2}, open(_g_f, "w", encoding="utf-8"))
        if n2 > 0:
            return [f"live_state 假零仓自愈: 终端重登窗读到0张(真实{n2}张), 巡检已自动重刷快照恢复共享真值源(同日同态静默, 翻态即报)"]
        return ["live_state 零持仓且重刷后仍=0, 1h内无平仓记录 — 疑似终端/快照故障或真清仓, 待核(同日同态静默, 翻态即报)"]
        return []  # 重刷失败(n2=-1): 下拍再试, 不刷噪声
    except Exception:
        return []

def main():
    problems = []
    p_nodes, got = check_nodes()
    problems += p_nodes
    p_live, _live = check_live_read()
    problems += p_live
    problems += check_infra()
    problems += check_node_script()
    problems += check_chief_queue()
    problems += check_crypto_unlock()
    problems += check_family_ledger()
    problems += check_livestate_zero()  # [11-15] live_state零持仓防呆(终端重登窗假0仓自愈)

    now = bjt_now().strftime("%Y-%m-%d %H:%M")
    if not problems:
        # [11-13 瘦身三刀] 标记行也会被 no_agent 投群 -> 全绿=空stdout(真静默), 留痕改本地jsonl
        try:
            with open(os.path.join(DATA, "patrol_ok_log.jsonl"), "a", encoding="utf-8") as _f:
                _f.write(json.dumps({"ts": now, "nodes": sorted(got) or []}, ensure_ascii=False) + "\n")
        except Exception:
            pass
        return
    print(f"【金策自动巡检·异常 {now}】发现 {len(problems)} 处, 主动报不静默:")
    for i, p in enumerate(problems, 1):
        print(f"  {i}. {p}")
    print(f"· 已发节点: {sorted(got) or '无'}")
    print(f"· 闭环: 巡检每30min自动跑, 有异常自动进群点名, 全绿静默; 历史回测≠未来收益")

if __name__ == "__main__":
    main()
