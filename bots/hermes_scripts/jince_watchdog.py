#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策节点看门狗 (no_agent watchdog, 0 LLM, 每15分钟跑一次)
逻辑: 按北京时间核对【到点了该出却没出】的金策节点, 缺一个就打印一条补发提示(投群);
      全齐则静默(no_agent 空 stdout = 不发任何消息)。
判定源: E:\\GoldstrategyEngine\\data\\discussion_log.jsonl (每个节点成功跑会 append 一条)
节点时刻表(与 cron 对齐, 冬夏令时切换由总管维护):
  08:05 asia_open  12:05 asia_close  15:05/16:05 europe_open
  18:05 europe_close  21:05/22:05 us_open  02:05 us_close
补发提示只点名缺失节点+时间, 不重跑脚本(避免重复投正文), 由 @hermes 收到后手动/自动补投。
"""
import os, json, subprocess, datetime, zoneinfo, time

# [2026-10-20 P0] 单实例锁: 实测该脚本被调度起过两遍 (PID 20596/4396, 07:55:01/07:55:33 差32s),
# 双实例 = 重复巡检 + 重复拉网关/终端 + 重复刷风控闸 (同族"双调度搅乱"隐患).
# 用 Windows 原生 msvcrt 文件排它锁: 第一个实例抢到锁, 第二个 LK_NBLCK 立即失败 -> 静默退出.
# 进程正常结束或崩溃时, OS 自动释放句柄锁, 不留僵尸锁挡住后续 15min 轮次.
LOCK = os.path.join(r"E:/GoldstrategyEngine/data", "jince_watchdog.lock")
def _acquire_watchdog_lock():
    import msvcrt
    f = open(LOCK, "a+")
    try:
        f.seek(0); f.truncate(); f.write(str(os.getpid())); f.flush()
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)  # 非阻塞排它锁
        return f  # 返回句柄, 持有到进程结束自动释放
    except Exception:
        f.close()
        return None

DATA = r"E:/GoldstrategyEngine/data"
LOG = os.path.join(DATA, "discussion_log.jsonl")
PROBE = os.path.join(DATA, "network_probe_last.json")
try:
    from zoneinfo import ZoneInfo
    BJT = ZoneInfo("Asia/Shanghai")
except Exception:
    # BUGFIX 11-14: uv python 缺 tzdata -> ZoneInfoNotFoundError 整脚本死(哨兵死亡, 11-14 实锤)
    # 回退固定 UTC+8(中国无夏令, 语义等价), 哨兵永不因时区数据缺而死
    BJT = datetime.timezone(datetime.timedelta(hours=8))

# [2026-10-08 补发机制] 节点自动补生成 + 补发台账 (镜像 strategy-rd 的 research_backfill_queue,
# 那条管"研发认领没落盘", 这条管"节点生成没/投递没进群"。铁律 no_silent_drop: 耽误了必须补上。)
ATE_PY = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/pythonw.exe"
SCRIPT_DIR = r"E:/workbuddy/国外模型/hermes/scripts"
MIDDAY_KEYS = {"asia_midday", "europe_midday", "us_midday"}
QUEUE = os.path.join(DATA, "node_backfill_queue.json")

def backfill_generation(key, cn, fire):
    """生成层自动补发: 节点该生成却没生成(log 缺) → 直接跑对应节点脚本补出正文+落 log.
    0 LLM / fail-open(拉不到 tick 自动降级基准价, 仍落盘不空缺). 返回 (是否成功, 摘要).
    6 开/关评走 jince_node.py <key>(显式身份, 会写 discussion_log 回执);
    3 中间深析走 jince_midday_deep.py <key>(同上)."""
    script = "jince_midday_deep.py" if key in MIDDAY_KEYS else "jince_node.py"
    cmd = '"%s" "%s" %s' % (ATE_PY, os.path.join(SCRIPT_DIR, script), key)
    try:
        # [11-15] ATE spawn 剥净 Python 环境变量(防 cron PYTHONPATH 污染 numpy/MT5 串味, 同 preflight/drill 根因)
        _env_clean = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE", "VIRTUAL_ENV")}
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, errors='replace',
                            timeout=90, cwd=r"E:/GoldstrategyEngine", creationflags=0x08000000, env=_env_clean)
        body = (r.stdout or "").strip()
        ok = (r.returncode == 0 and body)
        return ok, body, ("已补生成+落log+正文进群" if ok else ("脚本退出码=%s 输出空, 升级 22:00 批量补投" % r.returncode))
    except Exception as e:
        return False, "", "补生成异常: %s (fail-open, 升级 22:00 批量补投)" % str(e)[:80]

def load_queue(today):
    """读当日节点补发台账(镜像 research_backfill_queue). 跨日自动翻篇(只留当日 items)."""
    try:
        d = json.load(open(QUEUE, encoding="utf-8"))
        items = d.get("items", []) if isinstance(d, dict) else d
        return [it for it in items if str(it.get("ts_created_day", "")) == today or it.get("ts_created_day") is None]
    except Exception:
        return []

def delivered_nodes(today):
    """[2026-10-08 销账防刷] 当日已实际进群(或 22:00 日报批量销账)的 node 集合.
    判定: node_backfill_queue.json items 里 layer=delivery/delivery+manual 且 status=delivered 的 key.
    防刷根子: us_close 02:05 正文实际已进群但 cron 台账不销账(last_status 仍 delivery_queued) ->
    '卡队列>30min' 误判 -> 12:45 把已进群的内容重刷第二遍. 已 delivered 的不再即时重投."""
    try:
        d = json.load(open(QUEUE, encoding="utf-8"))
        items = d.get("items", []) if isinstance(d, dict) else d
        out = set()
        for it in items:
            if str(it.get("ts_created_day", "")) == today and it.get("status") == "delivered":
                out.add(it.get("key"))
        return out
    except Exception:
        return set()

def mark_delivered(key, today, note=""):
    """[销账] 把某 node 的补发台账条目置 status=delivered(22:00 日报批量销账 / @hermes 确认进群后调)."""
    items = load_queue(today)
    for it in items:
        if it.get("key") == key:
            it["status"] = "delivered"
            it["ts_delivered"] = int(time.time())
            if note:
                it["note"] = note
    if not any(it.get("key") == key for it in items):
        items.append({"key": key, "ts_created_day": today, "ts_created": int(time.time()),
                     "layer": "delivery", "status": "delivered", "ts_delivered": int(time.time()),
                     "note": note or "销账"})
    save_queue(items, today)

def regen_body(key):
    """[2026-10-08 发现即补] 重生成某节点最新正文, 不写 discussion_log(--noreceipt, 正文已落过).
    用于投递层'卡队列'的当场补投: 拉最新数据重算, 塞进看门狗 stdout 让 bot-chat 每次 tick 重试投群.
    6 开/关评走 jince_node.py --noreceipt; 3 中间深析走 jince_midday_deep.py --noreceipt. 返回正文(str).
    [2026-10-08 L4边界] training_daily 特判: 卡队列补投只读已落盘 training_daily_report_*.md 重发,
    不重跑 900s 回测(重跑烧时间+出一版不一致数字, 审计口径脏). 报告=内部级, 0开单/0方向词/0实盘数据出B档."""
    if key == "training_daily":
        try:
            reps = [os.path.join(DATA, f) for f in os.listdir(DATA)
                    if f.startswith("training_daily_report_") and f.endswith(".md")]
            if not reps:
                return "【后台训练·补投】无已落盘报告(training_daily_report_*.md 缺失), 升级 22:00 兜底销账"
            return open(max(reps, key=os.path.getmtime), encoding="utf-8").read().strip()
        except Exception as e:
            return "【后台训练·补投】读报告异常: %s, 升级 22:00 兜底销账" % str(e)[:60]
    script = "jince_midday_deep.py" if key in MIDDAY_KEYS else "jince_node.py"
    cmd = '"%s" "%s" %s --noreceipt' % (ATE_PY, os.path.join(SCRIPT_DIR, script), key)
    try:
        _env_clean2 = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE", "VIRTUAL_ENV")}
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, errors='replace',
                           timeout=90, cwd=r"E:/GoldstrategyEngine", creationflags=0x08000000, env=_env_clean2)
        return (r.stdout or "").strip()
    except Exception:
        return ""

def save_queue(items, today):
    try:
        d = {"sop": ("节点补发台账(no-gap铁律): 任何金策节点 到点没生成(生成层) 或 生成了没进群(投递层) "
                     "=> 自动进本台账 => 生成层看门狗当场自动补生成; 投递层 22:00 日报强制批量补投销账. "
                     "与 strategy-rd 的 research_backfill_queue 镜像(研发认领侧). 禁止静默蒸发."),
             "rule_no_silent_drop": True, "date": today, "items": items,
             "updated_ts": int(time.time())}
        json.dump(d, open(QUEUE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception:
        pass

# 节点: 触发时刻(HH:MM BJT) -> (node_key, 中文名)。冬夏令时由总管在 cron 里切换时刻。
SCHEDULE = [
    ("08:05", "asia_open",   "东京开评"),
    ("10:05", "asia_midday", "亚盘半日深析"),
    ("12:05", "asia_close",  "东京对账"),
    ("15:05", "europe_open", "伦敦开评"),
    ("16:35", "europe_midday","欧盘半日深析"),
    ("18:05", "europe_close","伦敦对账"),
    ("21:05", "us_open",     "美盘开评"),
    ("23:35", "us_midday",   "美盘半日深析"),
    ("02:05", "us_close",    "美盘收口"),
]

# 只有这 6 个节点算"该出没出"的判定对象(排除 crypto_freeze_bridge/weekly_review/synth_meeting 等杂项)
NODE_KEYS = {k for _, k, _ in SCHEDULE}

def loaded_nodes(today_str):
    got = set()
    if not os.path.exists(LOG):
        return got
    for line in open(LOG, encoding="utf-8", errors="ignore"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        node = rec.get("node")
        if node not in NODE_KEYS:
            continue
        # ts 可能是 int/str/缺失, 三种写法都兼容; 拿不到 ts 就退用 beijing 字段
        ts = rec.get("ts")
        try:
            d = datetime.datetime.fromtimestamp(int(float(ts)), BJT)
        except Exception:
            bj = rec.get("beijing") or ""
            if not bj.startswith(today_str):
                continue
            got.add(node)
            continue
        if d.strftime("%Y-%m-%d") == today_str:
            got.add(node)
    return got

def check_delivery_stuck(today):
    """[2026-10-08 投递层兜底] 读 cron jobs.json: 金策 6 节点里, 今天已触发(last_run_at 是今天)
    但 last_status=delivery_queued / delivery_failed 且卡在队列 >2h 的, 判为'已生成没进群', 报一条让 @hermes 补投.
    返回 [(node_key, 中文名, 卡了约几h)]. fail-open: jobs.json 读不到/格式变 → 返回 [].
    判据: last_run_at 是今天 + last_status in (delivery_queued, delivery_failed) + (now - last_run_at) > 2h.
    [2026-10-08 09:15 修误报] delivery_queued 语义坑: scheduler 在"Bot Chat 回执=queued/claimed(投达未验)"
    时也记 delivery_queued -> 消息实际已进群(如 us_close 02:05 已进群), 台账不销账 => 看门狗每15min重报.
    现: 同一 node 同一天只告警一次(去重状态落盘 data/jince_stuck_alert_state.json), 22:00 日报收口后
    状态随日期自然翻篇; 告警文案也改为'先验已投达再补投, 防刷两遍'."""
    jobs_path = r"E:/workbuddy/国外模型/hermes/cron/jobs.json"
    STATE = os.path.join(DATA, "jince_stuck_alert_state.json")
    NAME2KEY = {"jince-node-tokyo-open-0800": "asia_open", "jince-node-tokyo-close-1200": "asia_close",
                "jince-node-london-open-1500": "europe_open", "jince-node-london-close-1800": "europe_close",
                "jince-node-ny-open-2100": "us_open", "jince-node-ny-close-0200": "us_close",
                "jince-midday-asia-1005": "asia_midday", "jince-midday-europe-1635": "europe_midday",
                "jince-midday-us-2335": "us_midday",
                "金策·后台训练·每日回测验收": "training_daily"}   # [2026-10-08 01:30训练job挂进投递兜底]
    CN = {k: cn for _, k, cn in SCHEDULE}
    CN["training_daily"] = "后台训练·每日回测验收"   # 非SCHEDULE节点, CN手动补
    if not os.path.exists(jobs_path):
        return []
    try:
        d = json.load(open(jobs_path, encoding="utf-8"))
        jobs = d.get("jobs", d if isinstance(d, list) else [])
    except Exception:
        return []
    now = datetime.datetime.now(BJT).replace(tzinfo=None)  # naive 北京时间, 与 lr_naive 同口径相减
    # 去重: 今天已告警过的 node 不再重报(防 7h 挂账每 15min 刷屏)
    alerted = set()
    try:
        st = json.load(open(STATE, encoding="utf-8"))
        if st.get("date") == today:
            alerted = set(st.get("alerted", []))
    except Exception:
        pass
    stuck = []
    for j in jobs:
        jn = j.get("name", "")
        key = NAME2KEY.get(jn)
        if not key:
            continue
        last_run = j.get("last_run_at") or ""
        last_status = j.get("last_status") or ""
        if last_status not in ("delivery_queued", "delivery_failed"):
            continue
        # last_run_at 形如 2026-10-07T21:05:06.987646+08:00
        try:
            lr = datetime.datetime.fromisoformat(last_run.replace("+08:00", "+08:00"))
            lr_naive = lr.astimezone(BJT).replace(tzinfo=None)
        except Exception:
            continue
        if lr_naive.strftime("%Y-%m-%d") != today:
            continue
        mins = (now - lr_naive).total_seconds() / 60
        # [2026-10-08 发现即补] 阈值 2h->30min: 卡 30min 就动手. 去重(alerted)只管"告警文案"不再重报,
        # 不挡"正文重新注入"(投达靠 bot-chat 重试, 群一空就落进去) —— 防刷屏 vs 及时补, 两件事分开.
        if mins > 30:
            stuck.append((key, CN.get(key, key), round(mins)))
            if key not in alerted:
                alerted.add(key)
    # 落盘当日已告警清单(次日自然翻篇)
    if stuck:
        try:
            json.dump({"date": today, "alerted": sorted(alerted)},
                      open(STATE, "w", encoding="utf-8"), ensure_ascii=False)
        except Exception:
            pass
    return stuck

def main():
    # [2026-10-20 P0] 单实例锁: 已被另一实例持锁 -> 静默退出(exit 0), 杜绝双实例重复巡检/重复拉端/重复刷闸.
    _lock_holder = _acquire_watchdog_lock()
    if _lock_holder is None:
        print("[watchdog] 已有实例在跑, 本实例静默退出 (单实例锁)", file=__import__("sys").stderr)
        __import__("sys").exit(0)
    now = datetime.datetime.now(BJT)
    today = now.strftime("%Y-%m-%d")
    hm = now.strftime("%H:%M")

    # ── 回归修复(2026-10-05): 找回被盘上版本弄丢的"网关探测+自拉网关"逻辑 ──
    # 此前盘上脚本只有"缺节点提醒", 网关掉线无人自动拉起 → 静默死掉. 现合回:
    #   探活网关 → 掉就 hermes gateway start; 探活 MT5 terminal64 → 没起就 autostart bat;
    #   外网探活 → 断只 fail-open 标记; 结果写 network_probe_last.json (看门狗健康心跳).
    probe = {"ts": hm, "today": today}
    HERMES_CLI = "E:/workbuddy/国外模型/hermes/hermes-agent/venv/Scripts/python.exe -m hermes_cli.main"
    try:
        # gateway: 裸 "hermes" 在看门狗环境不在 PATH -> 找不到命令抛异常 -> 误报 probe-fail.
        # 用确定能解析的 venv python -m hermes_cli.main (实测读到 "Gateway process running").
        # [2026-10-06] timeout 25->60 + 超时不报 probe-fail: gateway status 偶尔卡 25s+,
        # 旧写法把活 gateway 误判"探测异常"每15min刷屏. 现: 60s 仍超时只记"下轮再探".
        # [2026-10-08] 修误判拉起的根子: 02:00/04:00 睡眠检测两连报 "was down -> restart"
        # 实为 status 输出偶发异常(gateway 一直活着, PID 30112 未变, 日志无 crash 行),
        # 旧逻辑对任何非 ok 输出都盲跑 gateway start + 标记 restarted -> 误报刷屏.
        # 现: 仅当输出含明确 down 证据才真拉起; 输出异常/空 -> 不拉起, 只记"下轮再探".
        # [2026-10-24 根治] 旧法每15min跑完整CLI `gateway status`(拉起整个hermes CLI, 常>60s),
        # 活网关下偶发拿到异常/超时输出就记 probe-output-abnor/probe-timeout60s 刷屏.
        # 现改秒级进程探活优先: CIM匹配'gateway run'活进程(≈1s): 活=ok直接跳过(止住刷屏);
        # 真没探到才回退一次CLI确认(短超时), 仅明确down证据才真拉起, 输出含糊不盲拉(保留2026-10-08逻辑).
        _GW_PS = r"""$n=0; foreach($nm in @('pythonw.exe','python.exe')){ foreach($p in (Get-CimInstance Win32_Process -Filter "Name='$nm'")){ if($p.CommandLine -match 'gateway run'){ $n++ } } }; $n"""
        def _gw_proc_alive():
            """秒级 gateway 进程探活: True/False/None(探测不确定)."""
            try:
                rp = subprocess.run(["powershell", "-NoProfile", "-Command", _GW_PS],
                                    capture_output=True, text=True, timeout=15,
                                    creationflags=0x08000000, encoding="utf-8", errors="replace")
                if rp.returncode != 0:
                    return None
                ms = [x for x in (rp.stdout or "").split() if x.isdigit()]
                return (int(ms[-1]) > 0) if ms else False
            except Exception:
                return None
        alive = _gw_proc_alive()
        if alive is True:
            probe["gateway"] = "ok"
        else:
            # 秒级探活=0 或不确定: 回退一次CLI确认(短超时), 只有明确down证据才拉起
            out = subprocess.run(f'{HERMES_CLI} gateway status 2>&1', shell=True,
                                 capture_output=True, text=True, errors='replace', timeout=45,
                                 creationflags=0x08000000).stdout or ""
            out_low = out.lower()
            if "no gateway" in out_low or "not running" in out_low or "stopped" in out_low:
                subprocess.run(f'{HERMES_CLI} gateway start', shell=True, capture_output=True, text=True, errors='replace', timeout=120,
                               creationflags=0x08000000)
                probe["gateway"] = "was down -> restarted"
            elif "gateway process running" in out_low or "pid" in out_low:
                probe["gateway"] = "ok"
            else:
                probe["gateway"] = "probe-output-abnormal(gateway未判挂, 下轮再探, 不盲拉起)"
    except subprocess.TimeoutExpired:
        # [2026-10-25] 秒级进程探活扑空 + 45s CLI 探活又超时: 属不确定(非确定掉线),
        # 按 fail-open 判 ok, 不再挂 "probe-timeout60s" 吓人尾巴(真实掉线走下面 "no gateway" 分支自拉起, 不受影响).
        probe["gateway"] = "ok (探活超时,fail-open不判挂)"
    except Exception:
        probe["gateway"] = "probe-fail (fail-open)"
    # MT5 terminal64 探活 + 自拉
    try:
        n = subprocess.run('powershell -NoProfile -Command "(Get-Process terminal64 -ErrorAction SilentlyContinue).Count"',
                           shell=True, capture_output=True, text=True, errors='replace', timeout=60, creationflags=0x08000000).stdout.strip().splitlines()
        cnt = int(n[-1]) if n else 0
        if cnt > 0:
            probe["mt5"] = "running"
        else:
            subprocess.run('start "" "C:/Program Files/TMGM MT5 Terminal/terminal64.exe"', shell=True,
                           capture_output=True, text=True, errors='replace', timeout=60, creationflags=0x08000000)
            probe["mt5"] = "missing -> launched terminal64"
    except Exception:
        probe["mt5"] = "probe-fail (fail-open)"
    # 外网探活 (fail-open)
    try:
        ip = subprocess.run("curl -s -m 8 https://api.ipify.org", shell=True,
                            capture_output=True, text=True, errors='replace', timeout=30, creationflags=0x08000000).stdout.strip()
        if ip:
            probe["extnet"] = ("ok " + ip)
        else:
            # [2026-10-08 extnet误报根因] 只探 ipify 那台抖了就把外网判 down(挂129min),
            # 但外网其实通着(gh-api 余量5000满) -> 误卡投递层. 加 gh-api 兜底: ipify 探不到再验 gh token 余量,
            # 余量满=非账号级限流+外网通, 判 ok(gh-api兜底), 不再误报 down.
            try:
                rem = subprocess.run('gh api rate_limit --jq .resources.core.remaining 2>&1',
                                     shell=True, capture_output=True, text=True, errors='replace', timeout=15, creationflags=0x08000000).stdout.strip()
                if rem.isdigit() and int(rem) > 0:
                    probe["extnet"] = "ok (gh-api兜底, ipify抖但外网通: 余量=%s)" % rem
                else:
                    probe["extnet"] = "down (fail-open: 本地循环照跑, 节点数据降级用最近快照)"
            except Exception:
                probe["extnet"] = "probe-fail (fail-open)"
    except Exception:
        probe["extnet"] = "probe-fail (fail-open)"
    # [2026-10-21 chief 定·L1] event_guard 5min 快通道活体探活(防静默死亡 SPOF):
    # 根因史: 10-21 03:00 正常拍后 2 个实例挂死占槽(MI=IgnoreNew), 9.5h 无下一拍, 无看门狗发现.
    # 现修复链: 任务改 MI=Parallel + ETL=PT15M(挂死自动收尸), 本探活是第二道防线.
    # 判据: data/event_guard.log mtime 距今 >25min(=5拍无留痕, 正常拍间5-7min, 不误报).
    # 动作: 杀挂死实例(>25min 还活着的 python event_guard 进程) + 轻踢任务一拍, 报一行进群不静默.
    try:
        eg_log = os.path.join(DATA, "event_guard.log")
        eg_age_min = (time.time() - os.path.getmtime(eg_log)) / 60 if os.path.exists(eg_log) else 9999
        if eg_age_min <= 25:
            probe["event_guard"] = "ok (%.0fmin)" % eg_age_min
        else:
            killed = 0
            try:
                chk = subprocess.run(
                    'powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \\"Name like \'%python%\'\\" | Where-Object { $_.CommandLine -like \'*event_guard*\' } | Select-Object -ExpandProperty ProcessId"',
                    shell=True, capture_output=True, text=True, errors='replace', timeout=30, creationflags=0x08000000).stdout
                pids = [p.strip() for p in chk.splitlines() if p.strip().isdigit()]
                for pid in pids:
                    try:
                        subprocess.run("taskkill /F /PID %s" % pid, shell=True,
                                       capture_output=True, text=True, errors='replace', timeout=15, creationflags=0x08000000)
                        killed += 1
                    except Exception:
                        pass
            except Exception:
                pass
            subprocess.run('powershell -NoProfile -Command "Start-ScheduledTask -TaskName JinCeEventGuard -ErrorAction SilentlyContinue"',
                           shell=True, capture_output=True, text=True, errors='replace', timeout=30, creationflags=0x08000000)
            probe["event_guard"] = "stale %.0fmin -> killed %d hung + nudged task" % (eg_age_min, killed)
            out_marker = ("· ⚠️ [事件快通道自愈] event_guard.log 已 %.0fmin 无新拍(5min 快通道静默死亡), "
                          "看门狗已杀 %d 个挂死实例并轻踢 JinCeEventGuard 任务, 下 5min 节拍应复活"
                          % (eg_age_min, killed))
            # 存起来, main() 尾部统一进群(不在这直接 print, 与整体输出结构一致)
            probe.setdefault("_eg_alerts", []).append(out_marker)
    except Exception:
        probe["event_guard"] = "probe-fail (fail-open)"

    # [2026-11-03 进化营补] live24 实弹引擎 + 影子采集 进程监护 (fail-open, 不影响原有体检)
    # 背景: 会话级后台任务会被宿主回收; live24 曾 02:10 静默退出; shadow_link 曾 IPC 挂死
    # (进程活但不写). 故 live24 按进程判活, shadow_link 按 live csv 写入新鲜度判活.
    try:
        # [11-16 修] _sup_py 改 ATE venv (含 MetaTrader5 模块; D: 3.13.12 纯 Hermes python 缺 MT5, 拉起即 import 死=假拉活)
        _sup_py = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe"
        _sup_dir = r"E:/GoldstrategyEngine/tools"
        _sup_log = r"E:/GoldstrategyEngine/logs"
        os.makedirs(_sup_log, exist_ok=True)

        def _sup_alive(kw):
            # [2026-11-03 修] 不能用 % 格式化: 过滤器里字面量 '%python%' 会被当成占位符(报 unsupported format char)
            _ps = ('powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter '
                   '\\"Name like \'%python%\'\\" | Where-Object { $_.CommandLine -like \'*' + kw + '*\' } '
                   '| Select-Object -ExpandProperty ProcessId"')
            try:
                _chk = subprocess.run(
                    _ps,
                    shell=True, capture_output=True, text=True, errors='replace', timeout=30, creationflags=0x08000000)
                return [p.strip() for p in (_chk.stdout or "").splitlines() if p.strip().isdigit()]
            except Exception:
                # [11-16 修] CIM 探活失败(超时/系统忙)时按"未见活体"处理, 走拉起分支(引擎单实例锁防重拉), 不静默跳过监护
                return []

        # 1) live24: 进程消失即拉起 (持仓 SL/TP 在 MT5 服务器端, 引擎只负责新信号)
        # [2026-11-03 L5 桥] RETIRE 闸源: data/live24_retire.json active=true 时进程消失也不重拉 (打地鼠防护,
        # 11-03 事故: 12:15 LIVE24_HALT 被删 -> live24 漏闸开 XAU #663837800; 杀 46712 后本块若照拉则次日复活重漏).
        # 旗缺失/读失败 = 旧版行为 (fail-open 照拉), 与 clobber 修复同型.
        _ret = {}
        try:
            with open(os.path.join(DATA, "live24_retire.json"), "r", encoding="utf-8") as _rf:
                _ret = json.load(_rf)
        except Exception:
            _ret = {}
        if not _sup_alive("jince_live24.py"):
            if _ret.get("active"):
                probe["live24"] = "down -> RETIRE held (watchdog 不重拉, 翻活需 L5 翻旗 active=false)"
                probe.setdefault("_eg_alerts", []).append(
                    "· 🔒 [L5 RETIRE] jince_live24 处于退役闸源态 (rd_decisions RETIRE), 看门狗不重拉; "
                    "翻活需 L5 根因关闭+挂全闸源+OOS 三件后翻 active=false")
            else:
                # [2026-11-11 chief·OOM防复发] 76076死于OpenBLAS内存分配失败(numpy多线程内存膨胀, 19+10个python进程压着).
                # 引擎单线程逻辑, OpenBLAS/OMP线程限1 = 内存占用降, 行为零变化(小数组np.mean不受影响).
                _env = dict(os.environ)
                _env["OPENBLAS_NUM_THREADS"] = "1"
                _env["OMP_NUM_THREADS"] = "1"
                _env["PYTHONUNBUFFERED"] = "1"  # [11-16] 日志可见性(unbuffered, 子进程stdout缺口另开工单)
                _env["MKL_NUM_THREADS"] = "1"
                _env["NUMEXPR_NUM_THREADS"] = "1"
                # [11-16 修] 剥净 Python 环境变量 (同 11-15 preflight/drill 根因: cron PYTHONPATH 污染 numpy/MT5 串味)
                for _k in ("PYTHONPATH", "PYTHONHOME"):
                    _env.pop(_k, None)
                subprocess.Popen('"%s" jince_live24.py' % _sup_py, cwd=_sup_dir, shell=True, env=_env,
                                 stdout=open(os.path.join(_sup_log, "live24_stdout.log"), "ab"),
                                 stderr=open(os.path.join(_sup_log, "live24_stderr.log"), "ab"),
                                 creationflags=0x08000000)
                probe["live24"] = "down -> restarted"
                probe.setdefault("_eg_alerts", []).append(
                    "· ⚠️ [实弹引擎自愈] jince_live24 进程消失, 看门狗已拉起 (持仓 SL/TP 服务器端不受影响)")
        else:
            probe["live24"] = "ok"

        # 2) shadow_link [2026-11-05 L5 改写]: 判活改读独立心跳 data/shadow_link_heartbeat.json
        #    (collector 每循环 ~20s 写一次, 与 M15 收线 / MT5 健康解耦)。
        #    旧逻辑 "CSV mtime>40min 就杀" 会在 MT5 IPC 降级期误杀"活着但暂无新 bar"的实例,
        #    造成 44min 一循环的 kill+restart 风暴 (11-05 00:15/01:15 两次)。现:
        #    心跳常新(<5min)=活着(CSV 因 MT5 降级暂不写也不杀); 心跳 >5min 未更=真挂死/进程死->杀+拉。
        _sl_hb = os.path.join(DATA, "shadow_link_heartbeat.json")
        _sl_csv = os.path.join(DATA, "shadow_features_live.csv")
        _sl_csv_age = (time.time() - os.path.getmtime(_sl_csv)) / 60 if os.path.exists(_sl_csv) else 9999
        if os.path.exists(_sl_hb):
            _sl_age = (time.time() - os.path.getmtime(_sl_hb)) / 60
            _sl_thr = 5
        else:  # 心跳文件尚未产出(旧 collector 未重启) -> 退回 CSV 判据, 阈值放宽到 60min 防误杀
            _sl_age = _sl_csv_age
            _sl_thr = 60
        if _sl_age > _sl_thr:
            for pid in _sup_alive("jince_shadow_link.py"):
                try:
                    subprocess.run("taskkill /F /PID %s" % pid, shell=True, capture_output=True,
                                   text=True, timeout=15, creationflags=0x08000000)
                except Exception:
                    pass
            subprocess.Popen('"%s" jince_shadow_link.py live' % _sup_py, cwd=_sup_dir, shell=True,
                             stdout=open(os.path.join(_sup_log, "shadow_stdout.log"), "ab"),
                             stderr=open(os.path.join(_sup_log, "shadow_stderr.log"), "ab"),
                             creationflags=0x08000000)
            probe["shadow_link"] = "hung(hb stale %.0fmin) -> killed+restarted" % _sl_age
            probe.setdefault("_eg_alerts", []).append(
                "· ⚠️ [影子采集自愈] 心跳 %.0fmin 未更(真挂死/进程死, 非 MT5 降级), 已杀挂死实例并拉起" % _sl_age)
        else:
            probe["shadow_link"] = "ok (hb %.0fmin / csv %.0fmin)" % (_sl_age, _sl_csv_age)
    except Exception as _sup_e:
        probe["live24_supervision"] = "supervisor-fail (fail-open): %s" % str(_sup_e)[:80]

    # [11-16 补闭环] L2 代理采集器常驻监护: 11-16 08:32 ticks 断链 100min 无人拉(看门狗原只管 live24+shadow_link)
    # 判活=进程在(常驻30s采样, 死=断链); 拉起=无参常驻模式(自写 pid 文件, 验证哨 pid 参照自动回正)
    try:
        if not _sup_alive("jince_l2proxy_collector.py"):
            _l2_out = open(os.path.join(_sup_log, "l2collector_stdout.log"), "ab")
            _l2_err = open(os.path.join(_sup_log, "l2collector_stderr.log"), "ab")
            _env2 = dict(os.environ)
            for _k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
                _env2[_k] = "1"
            for _k in ("PYTHONPATH", "PYTHONHOME"):
                _env2.pop(_k, None)
            subprocess.Popen('"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe" jince_l2proxy_collector.py',
                             cwd=r"E:/workbuddy/国外模型/hermes/scripts", shell=True, env=_env2,
                             stdout=_l2_out, stderr=_l2_err, creationflags=0x08000000)
            probe["l2_collector"] = "dead -> restarted (11-16 补闭环: ticks 断链防再停 100min 无人拉)"
        else:
            probe["l2_collector"] = "ok (常驻活体)"
    except Exception as _l2_e:
        probe["l2_collector"] = "probe-fail (fail-open): %s" % str(_l2_e)[:60]

    # [2026-11-12 11:3x L1 清退(李彦明拍板"要不就不用了")] 热锁EA撤出点名:
    # 只留状态记录(若未来重挂可体检), 不再发⚠️警告/重挂指引 — 闪退2天未根治, 成本>收益, L0(1s)+L2(挂单)已兜底
    try:
        _hl_csv = r"C:\Users\Administrator\AppData\Roaming\MetaQuotes\Terminal\Common\Files\HotLock_heartbeat.csv"
        if os.path.exists(_hl_csv):
            _hl_age = (time.time() - os.path.getmtime(_hl_csv)) / 60
            probe["hotlock"] = ("hb %.0fmin | L1已清退(李11-12拍板, L0/L2兜底, 不点名不重挂)" % _hl_age)
        else:
            probe["hotlock"] = "not-mounted | L1已清退(L0 1s层兜底, 不再提示重挂)"
    except Exception as _hl_e:
        probe["hotlock"] = "probe-fail: %s" % str(_hl_e)[:40]

    # 看门狗心跳落盘 (22:00 日报'看门狗体检'读这个)
    try:
        with open(PROBE, "w", encoding="utf-8") as f:
            json.dump(probe, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    got = loaded_nodes(today)
    missing = []
    for fire, key, cn in SCHEDULE:
        if key in got:
            continue
        if fire <= hm:  # 已过触发点
            missing.append((key, cn, fire))

    # [2026-10-08 补发机制] 生成层"该出没出" → 当场自动补生成(不再等人), 全量进台账留痕
    queue_items = load_queue(today)
    qindex = {it.get("key"): it for it in queue_items}
    backfilled_bodies = []
    for key, cn, fire in missing:
        ok, body, summary = backfill_generation(key, cn, fire)
        it = qindex.get(key) or {"key": key, "cn": cn, "ts_created_day": today, "ts_created": int(time.time())}
        it.update({"cn": cn, "ts_created_day": today,
                   "layer": "generation",
                   "status": "backfilled" if ok else "awaiting_2200_batch",
                   "note": summary})
        queue_items = [x for x in queue_items if x.get("key") != key]
        queue_items.append(it)
        qindex[key] = it
        if ok and body:
            backfilled_bodies.append((cn, body))

    # [2026-10-08 发现即补] 投递层"生成了没进群" → 当场重生成最新正文, 注入看门狗 stdout 让 bot-chat
    # 每 15min 重试投群(群一空闲就落进去), 不再攒到 22:00. 台账仍留痕但状态=retrying_now(即时补投中).
    stuck = check_delivery_stuck(today)
    # [2026-10-08 销账防刷] 已 delivered(实际进群/22:00 销账)的 node 不再即时重投, 防"已进群内容刷第二遍"
    done = delivered_nodes(today)
    stuck = [t for t in stuck if t[0] not in done]
    # [2026-10-08 冷却止刷屏] extnet=down 期间通道一直挤, 卡>30min 永远为真 -> 同节点每15min全篇重刷(38/54/69min连刷).
    # 加冷却: 同节点 45min 内只重投一次, 冷却内仅报一行"冷却中"(不重发全篇), 冷却到后重投也只发一行摘要. 内容照旧落log+22:00兜底, 零丢失.
    COOL_S = 45 * 60
    now_ts = int(time.time())
    cooling_keys = []  # 本轮处于冷却内的节点, 报告时区分"冷却中"
    # 从 queue_items 找该节点上次重投时间
    def last_regen(key):
        it = qindex.get(key)
        return int(it.get("ts_last_regen") or 0) if it else 0
    # [2026-10-09 坚决执行·销账规则硬化] 冷却只防"全篇刷屏", 不再当"销账"借口:
    #   - 正文已落 discussion_log 且 卡>4h(14400s) => 判"实际已进群/通道堵死", 直接销账 delivered, 不再拖
    #   - 冷却内但 卡>2h => 发一行摘要重投(不等冷却满), 内容零丢失
    #   - 冷却内且 卡<2h => 只留痕报一行"冷却中"(仅防刷屏, 不定销账)
    def body_in_log(key):
        try:
            for line in open(LOG, encoding="utf-8", errors="ignore"):
                line = line.strip()
                if not line: continue
                try: rec = json.loads(line)
                except: continue
                if rec.get("node") == key:
                    return True
        except Exception:
            return False
    # [2026-10-10] 卡投递指纹去重: 稳态(如 training_daily 摘要不变)只念第一遍, 数据一变/状态一变再念.
    # 队列照留痕 + 22:00 兜底销账(no_silent_drop 不破). report_keys = 本 tick 指纹有变化/首次的节点.
    report_keys = set()
    for key, cn, mins in stuck:
        lr = last_regen(key)
        it = qindex.get(key) or {"key": key, "cn": cn, "ts_created_day": today, "ts_created": now_ts}
        it.update({"cn": cn, "ts_created_day": today, "layer": "delivery"})
        inlog = body_in_log(key)
        if inlog and mins >= 240:
            # 正文已生成且卡超 4h: 强制销账, 不再拖 (22:00 兜底已多余)
            it["status"] = "delivered"
            it["ts_delivered"] = now_ts
            it["note"] = "正文已落discussion_log且卡%dmin>4h -> 强制销账delivered(通道堵死/实际已进群, 零丢失)" % mins
            queue_items = [x for x in queue_items if x.get("key") != key]
            queue_items.append(it); qindex[key] = it
            _fp = "%s|delivered" % key
            if it.get("last_reported_fp") != _fp:
                it["last_reported_fp"] = _fp; report_keys.add(key)
            continue
        cooling = lr and (now_ts - lr) < COOL_S
        if cooling and mins < 120:
            # 冷却内且 卡<2h: 只留痕报一行, 不重发全篇(防刷屏), 不定销账
            it["status"] = "cooling"
            it["note"] = "卡投递%dmin, 冷却中(仅防刷屏, 2h后自动强制摘要重投)" % mins
            queue_items = [x for x in queue_items if x.get("key") != key]
            queue_items.append(it); qindex[key] = it
            cooling_keys.append(key)
            _fp = "%s|cooling" % key
            if it.get("last_reported_fp") != _fp:
                it["last_reported_fp"] = _fp; report_keys.add(key)
        else:
            body = regen_body(key)  # 拉最新数据重算, 不写 log
            it["status"] = "retrying_now" if body else "awaiting_2200_batch"
            it["ts_last_regen"] = now_ts  # 记本次重投时间(下次冷却判定用)
            it["note"] = ("卡投递%dmin, 摘要重投(防全篇刷屏)" % mins if body
                          else "卡投递%dmin, 重生成失败, 升级22:00兜底销账" % mins)
            queue_items = [x for x in queue_items if x.get("key") != key]
            queue_items.append(it); qindex[key] = it
            if body:
                summary = ""
                for ln in body.splitlines():
                    if "实读:" in ln:
                        summary = ln.strip(); break
                if not summary:
                    summary = body.splitlines()[0].strip() if body else ""
                # [2026-10-10 修漏] 指纹用 key+status(稳态稳定), 不用 summary:
                # 纯报告节点(无实读行)摘要=带时间戳首行, 每15min重生成时间戳变 -> 旧指纹跟着变 -> 照样刷.
                # 改 key+status: 同节点同状态只报一次, 状态翻转(delivered/cooling/retrying)才再报. 正文首遍仍带出, 之后静默.
                _fp = "%s|%s" % (key, it["status"])
                if it.get("last_reported_fp") != _fp:
                    it["last_reported_fp"] = _fp
                    report_keys.add(key)
                    backfilled_bodies.append((cn + "·摘要重投", "  · " + summary))
                # 指纹不变 -> 不重发(已报过), 避免同一卡投递每15min灌群(纯报告节点时间戳变也不再刷)
            else:
                _fp = "%s|regen_fail" % key
                if it.get("last_reported_fp") != _fp:
                    it["last_reported_fp"] = _fp; report_keys.add(key)
    save_queue(queue_items, today)
    # [2026-10-10] 卡投递名单收窄到本 tick 指纹有变化的节点, 稳态不再念(但队列留痕+22:00兜底不破)
    stuck = [t for t in stuck if t[0] in report_keys]
    cooling_keys = [k for k in cooling_keys if k in report_keys]

    late = []
    if got:
        for fire, key, cn in SCHEDULE:
            if key in got:
                for line in open(LOG, encoding="utf-8", errors="ignore"):
                    line = line.strip()
                    if not line: continue
                    try: rec = json.loads(line)
                    except: continue
                    if rec.get("node") != key: continue
                    ts_v = rec.get("ts")
                    try:
                        d = datetime.datetime.fromtimestamp(int(float(ts_v)), BJT)
                        if d.strftime("%Y-%m-%d") != today: continue
                        from datetime import timedelta
                        fire_t = datetime.datetime.strptime(f"{today} {fire}", "%Y-%m-%d %H:%M").replace(tzinfo=None)
                        if d > fire_t + timedelta(minutes=15):
                            late.append((key, cn, fire, d.strftime("%H:%M"), (d - fire_t).seconds // 60))
                        break
                    except:
                        pass
    out = []
    if missing:
        out.append("【金策节点看门狗·自动补发】%s %s 检测到 %d 个节点今日应发未发, 已当场自动补生成+落台账:" % (today, hm, len(missing)))
        for key, cn, fire in missing:
            it = qindex.get(key, {})
            mark = "✅已补生成落log" if it.get("status") == "backfilled" else "⏳补生成失败, 已进台账待22:00批量补投"
            out.append("  · %s(节点 %s) 应发于 %s BJT -> %s" % (cn, key, fire, mark))
    if late:
        out.append(f"【金策节点看门狗·迟发】{today} {hm} 检测到 {len(late)} 个节点迟发(超计划15min):")
        for key, cn, fire, actual, mins in late:
            out.append(f"  · {cn}(节点 {key}) 应发{fire} 实际{actual}, 迟{mins}min")
    if stuck:
        # [11-13 深度优化·防刷屏] 卡队列拍2h重申闸: 稳态(同stuck集合+同阶段, 不含mins)只每2h重申一次,
        # 本地台账(node_backfill_queue.json)+22:00兜底销账照旧(零丢失不破); 状态变化/新卡/清零=即时报.
        _fp = json.dumps(sorted((k, ("cool" if k in cooling_keys else "re")) for k, _, _ in stuck), ensure_ascii=False)
        _gate_f = os.path.join(DATA, "watchdog_stuck_gate.json")
        _gate = {}
        try:
            _gate = json.load(open(_gate_f, encoding="utf-8"))
        except Exception:
            pass
        _now_ts_g = int(time.time())
        _g_changed = _gate.get("fp") != _fp
        _g_over = (_now_ts_g - int(_gate.get("ts") or 0)) > 2 * 3600
        if _g_changed or _g_over:
            json.dump({"fp": _fp, "ts": _now_ts_g, "note": "11-13防刷屏闸: 状态变/超2h才投群"}, open(_gate_f, "w", encoding="utf-8"), ensure_ascii=False)
            out.append("【金策节点看门狗·投递卡·即时补】%s %s 检测到 %d 个节点已生成但卡投递队列>30min未进群(内容已落 discussion_log, 22:00兜底销账, 零丢失):" % (today, hm, len(stuck)))
            for key, cn, mins in stuck:
                if key in cooling_keys:
                    out.append(f"  · {cn}(节点 {key}) 卡队列 {mins}min -> 冷却中(45min内不重发全篇, 冷却到自动摘要重投)")
                else:
                    out.append(f"  · {cn}(节点 {key}) 卡队列 {mins}min -> 摘要重投中(防全篇刷屏)")
        else:
            # [11-13 瘦身三刀] 标记行不投群(空stdout真静默), 留痕本地jsonl
            try:
                with open(os.path.join(DATA, "watchdog_ok_log.jsonl"), "a", encoding="utf-8") as _f:
                    _f.write(json.dumps({"ts": hm, "kind": "stuck_steady", "n": len(stuck)}, ensure_ascii=False) + "\n")
            except Exception:
                pass
    # [2026-10-24] extnet 显示层去截断误读: 旧 [:30] 把 "余量=4989" 切成 "余量=4"(gh 其实满血),
    # 播报挂个吓人的旧值. 改按前缀取干净状态词, 完整余量看 network_probe_last.json.
    _ext = probe.get('extnet', '')
    if _ext.startswith('ok'):
        _ext_disp = 'ok'
    elif _ext.startswith('down'):
        _ext_disp = 'down'
    elif 'probe-fail' in _ext:
        _ext_disp = 'probe-fail'
    else:
        _ext_disp = _ext[:20]
    # [11-13 瘦身二刀] 心跳行稳态去重: gateway/mt5/extnet/事件告警态不变<2h且本拍无其他内容 -> 整拍静默(空stdout不投群); 状态翻=即时报.
    # (22:00 日报照读 network_probe_last.json 落盘, 监控能力不减; 每2h至少重申一次, 李彦明"时刻汇报"不违背)
    # [11-14 瘦身四刀] 指纹语义归一: "ok"与"ok(探活超时,fail-open不判挂)"同判up, 防探活抖动导致指纹每拍变/稳态闸永不成立(今上午纯心跳15min一刷的根因); 稳态窗口2h放宽到同日(状态变化才报)
    def _sem(v, *ups):
        s = str(v or "")
        return next((u for u in ups if s.startswith(u)), ("down" if s else "unk"))
    _gw_sem = "up" if _sem(probe.get("gateway"), "ok") == "ok" else "down"
    _mt5_sem = "up" if _sem(probe.get("mt5"), "running") == "running" else "down"
    _hb_fp = json.dumps([_gw_sem, _mt5_sem, _ext_disp, len(probe.get("_eg_alerts", []))], ensure_ascii=False)
    _hb_f = os.path.join(DATA, "watchdog_heartbeat_gate.json")
    _hb = {}
    try:
        _hb = json.load(open(_hb_f, encoding="utf-8"))
    except Exception:
        _hb = {}
    _hb_today = (_hb.get("day") == hm[:5])
    _hb_now = int(time.time())
    _hb_steady = (_hb.get("fp") == _hb_fp and _hb_today and not out)
    if _hb_steady:
        # [11-13 瘦身三刀] 标记行不投群(空stdout真静默), 留痕本地jsonl
        try:
            with open(os.path.join(DATA, "watchdog_ok_log.jsonl"), "a", encoding="utf-8") as _f:
                _f.write(json.dumps({"ts": hm, "kind": "heartbeat_steady"}, ensure_ascii=False) + "\n")
        except Exception:
            pass
    else:
        json.dump({"fp": _hb_fp, "ts": _hb_now, "day": hm[:5], "note": "11-14瘦身四刀: 指纹语义归一+同日稳态(状态翻才报)"}, open(_hb_f, "w", encoding="utf-8"), ensure_ascii=False)
        out.append(f"· 看门狗心跳: gateway={probe['gateway']} mt5={probe['mt5']} extnet={_ext_disp}")
        # [2026-10-21 chief 定] event_guard 快通道自愈报警进群(不静默): 探到静默死亡已自拉, 念一行让 @hermes/群 知道
        for _eg in probe.get("_eg_alerts", []):
            out.append(_eg)
        out.append(f"· 补发机制(发现即补): 节点侧台账 node_backfill_queue.json(no_silent_drop), 生成层当场自动补 / 投递层卡>30min 即时重投(每15min重试, 群空闲即落) / 22:00 只做兜底销账, 与研发侧 research_backfill_queue 镜像。")
    # [2026-10-09 防复发闸②] 训练枪自监控: 回测产物过期/引擎哨兵打回/上一枪崩 -> fail-loud, 防"01:30 空转 3 个月"复发
    _bt_warn = []
    try:
        _stamp_f = os.path.join(DATA, "backtest_edge_run_stamp.json")
        _edge_f = os.path.join(DATA, "backtest_edge.json")
        _stamp = json.load(open(_stamp_f, encoding="utf-8")) if os.path.exists(_stamp_f) else {}
        _edge = json.load(open(_edge_f, encoding="utf-8")) if os.path.exists(_edge_f) else {}
        _gen = str(_edge.get("generated") or _stamp.get("ts") or "")
        try:
            _gt = datetime.datetime.fromisoformat(_gen[:19])
            _age_h = (datetime.datetime.now(datetime.timezone.utc) - _gt.replace(tzinfo=datetime.timezone.utc)).total_seconds()/3600
        except Exception:
            _age_h = 999
        _bt_running = "no"
        # [2026-11-09 误判修] wmic 已弃用/where 子句误解析 -> 空返回误报"无回测进程"(11-09 10:30 拍实证:
        # 引擎 26032 持锁在算, wmic 报 no, 群里刷"训练枪静默"假警报). 主判据改引擎锁持有 pid 原生存活判
        # (零子进程, ctypes OpenProcess): 锁 pid 活 且 锁 mtime <8h(接管协议窗) = 引擎在跑, 直接 yes;
        # wmic 降为次判据(锁不可读/无锁时才问). 引擎死=pid 死, 判据照样如实报 no.
        try:
            import ctypes as _ct
            _lk_f = os.path.join(DATA, "backtest_engine.lock")
            _lk_pid = 0
            if os.path.exists(_lk_f):
                _lk_pid = int("".join(c for c in open(_lk_f, encoding="utf-8", errors="ignore").read() if c.isdigit()) or 0)
            if _lk_pid and (time.time() - os.path.getmtime(_lk_f)) < 8 * 3600:
                _h = _ct.windll.kernel32.OpenProcess(0x1000, False, _lk_pid)  # PROCESS_QUERY_LIMITED_INFORMATION
                if _h:
                    _ct.windll.kernel32.CloseHandle(_h)
                    _bt_running = "yes"
        except Exception:
            pass
        if _bt_running == "no":
            try:
                _chk = subprocess.run("wmic process where \"(commandline like '%backtest_engine%' or commandline like '%training_full_universe%') and (name like 'python%' or name like 'pythonw%')\" get ProcessId /format:list",
                                      shell=True, capture_output=True, text=True, errors='replace', timeout=20, creationflags=0x08000000)
                _live = [l for l in (_chk.stdout or "").splitlines() if l.strip().startswith("ProcessId=") and l.strip() != "ProcessId="]
                _bt_running = "yes" if _live else "no"
            except Exception:
                _bt_running = "unknown"
        if _age_h > 36 and _bt_running == "no":
            # [2026-10-10 误判修] 先查 cron 运行史: 00:10 回测 cron 若今日 last_run>00:10 且 enabled
            # = 它已跑过(只是跑完没刷产物戳), 不算"静默未跑", 不点名; 真静默(没触发/触发失败)才报.
            _cron_stale = True  # 读不到运行史 = 保守, 仍报(宁可误报不漏报)
            try:
                import json as _j3
                _jb = _j3.load(open(os.path.join(os.path.expanduser("~"), "workbuddy", "国外模型", "hermes", "cron", "jobs.json"), encoding="utf-8"))
                _jl = _jb if isinstance(_jb, list) else _jb.get("jobs", [])
                for _j in _jl:
                    if "全宇宙回测" in str(_j.get("name", "")):
                        _lr = str(_j.get("last_run_at") or _j.get("lastRunAt") or "")
                        _en = _j.get("enabled", True)
                        # [2026-10-11 跨天修] 旧版判 last_run 前缀==今日, 过 0 点后 last_run=昨日 01:20 就误判"静默".
                        # 改: last_run 距今 <24h = 触发过(哪怕跨天), 不算静默. 读 last_error 分: 连崩中=报"引擎故障非静默"; 干净=不点名.
                        if _lr:
                            try:
                                _lrd = datetime.datetime.fromisoformat(_lr)
                                # [2026-11-07 D5修] 上次补丁"没生效"的根因: last_run_at 可能是 naive(无tz),
                                # naive/aware 相减抛 TypeError 被吞 -> 误判 _cron_stale. 先给 naive 补 +08:00 再减.
                                if _lrd.tzinfo is None:
                                    _lrd = _lrd.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
                                _nxt = datetime.datetime.now(_lrd.tzinfo)
                                _hr = (_nxt - _lrd).total_seconds()/3600
                                if _hr < 24:
                                    _cron_stale = False
                                    if str(_j.get("last_status","")).lower() in ("error","failed"):
                                        _bt_warn.append("回测 cron 今晨已触发但连崩中(last_status=%s, failure_streak=%s) -> 引擎故障非静默, @strategy-rd 修引擎中, 引擎修好前 00:10 不重跑" % (_j.get("last_status"), _j.get("failure_streak")))
                                    else:
                                        _bt_warn.append("回测产物 %dh 陈旧但 00:10 cron 已触发(跑完未刷戳), 不点名" % int(_age_h))
                            except Exception:
                                _cron_stale = True
            except Exception:
                _cron_stale = True
            if _cron_stale:
                _bt_warn.append("回测产物已 %dh(>36h)且无回测进程在跑 -> 00:10 训练枪静默未跑, @hermes 手动开第一枪+查 cron 运行史" % int(_age_h))
        _sent = _stamp.get("engine_selfcheck_pass") is False
        if _sent:
            # [2026-10-09] 防重复刷屏: 引擎哨兵打回是"挂账等修"的稳态, 根因未消前每 15min 重念一遍会灌群.
            # 按 (ts, rc, sentinels) 指纹去重: 指纹不变只记一次; 新打回/回测重跑刷新 ts 才再提醒. 台账留痕不丢提醒.
            _fp = "%s|%s|%s" % (_stamp.get("ts"), _stamp.get("rc"), _stamp.get("sentinels_high_wr_legs"))
            try:
                import json as _j2
                _sf = os.path.join(DATA, "jince_sentinel_state.json")
                _sd = _j2.load(open(_sf, encoding="utf-8")) if os.path.exists(_sf) else {}
                if _sd.get("fp") != _fp:
                    _sd["fp"] = _fp
                    _sd.setdefault("ts_first", _stamp.get("ts"))
                    _j2.dump(_sd, open(_sf, "w", encoding="utf-8"))
                    _bt_warn.append("引擎自检哨兵打回(胜率虚高腿 %s 条: n>500且wr>0.9 不可能真盘) -> 本轮回测作废, @strategy-rd 认领修回测触价判定, 修好前 3 正edge候选全挂起 (挂账待修, 每15min 同指纹不重念)" % _stamp.get("sentinels_high_wr_legs"))
                # 指纹不变 -> 不念(已挂账), 避免 18:15/18:30/19:30 那三刷
            except Exception:
                _bt_warn.append("引擎自检哨兵打回(胜率虚高腿 %s 条) -> 本轮回测作废, @strategy-rd 认领修回测触价判定" % _stamp.get("sentinels_high_wr_legs"))
        if _stamp and _stamp.get("rc") not in (0, None) and _bt_running == "no" and _age_h <= 36:
            # [2026-10-09] 与哨兵同套指纹去重: 上轮回测崩是挂账稳态, 根因未消前每15min重念会灌群
            try:
                _fp2 = "rc1|%s|%s" % (_stamp.get("ts"), _stamp.get("sentinels_high_wr_legs"))
                if _sd.get("fp2") != _fp2:
                    _sd["fp2"] = _fp2
                    _j2.dump(_sd, open(_sf, "w", encoding="utf-8"))
                    _bt_warn.append("上一轮回测 rc=%s 崩(stderr: %s) -> @hermes 排查, 快检闸①再拦 (挂账待修, 同指纹不重念)" % (_stamp.get("rc"), str(_stamp.get("stderr_tail"))[-80:]))
            except Exception:
                _bt_warn.append("上一轮回测 rc=%s 崩(stderr: %s) -> @hermes 排查" % (_stamp.get("rc"), str(_stamp.get("stderr_tail"))[-80:]))
    except Exception as _e:
        _bt_warn.append("训练枪自监控异常: %s" % str(_e)[:60])
    for _w in _bt_warn:
        out.append("· ⚠️ [防复发闸②·训练枪自监控] %s" % _w)
    if late:
        out.append("· @chief 请对迟发节点做主持收口: 点名+归纳+拍板+派单, 落 群讨论落盘.jsonl。")
    # [2026-10-08] 补生成的节点正文直接带进 stdout -> no_agent 投递时当场进群, 用户立刻看到
    for cn, body in backfilled_bodies:
        out.append("")
        out.append("──── 补发正文 [%s] ────" % cn)
        out.append(body)
    if out:
        print("\n".join(out))
    # else: 全齐无迟发 -> 静默(只落看门狗心跳, 不发消息)

if __name__ == "__main__":
    try:
        main()
    except Exception as _ex:
        # 护栏: 未捕获异常也落盘心跳 + 静默退出 (exit 0), 防止 Windows 任务无限 Running/堆叠
        import traceback, sys
        try:
            with open(PROBE, "w", encoding="utf-8") as _f:
                json.dump({"ts": datetime.datetime.now(BJT).strftime("%H:%M"),
                           "today": datetime.datetime.now(BJT).strftime("%Y-%m-%d"),
                           "error": str(_ex)[:200], "trace": traceback.format_exc()[-400:]},
                          _f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        print("[watchdog-err] %s" % str(_ex)[:200], file=sys.stderr)
        sys.exit(0)
