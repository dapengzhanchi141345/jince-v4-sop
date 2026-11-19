# -*- coding: utf-8 -*-
"""
event_guard.py — L1事件快通道看门狗 (2026-09-28 升级, 5min Windows 计划任务)
================================================================
背景: 30min 全链 (auto_run_cycle) 之间, HIGH/HALT 突发事最长 25min 无反应 = 风险敞口。
本看门狗只做确定性事件闸, 不跑分析链/不烧 LLM key (拓扑判据: 确定性层保持 Python):
  ① 新鲜度: event_risk.json 的 updated 比上一轮快照新 → 说明 30min 全链已刷新过事件
     → 本次跳过 (防和全链撞车, 也防每 5min 重跑无意义动作)
  ② 新且 level∈{HIGH,HALT} → 撤三个挂单状态机里 趋势/Stop 类挂单 + 写 halt 标记
  ③ 新且 level==LOW → 清 halt 标记 (恢复挂单), 不自动回补 (回补交给下轮 30min 全链)
动作只撤单/标记, 永不加仓 (保险丝原则); 撤单失败开放 (日志留痕); GBK 安全 (纯 ASCII 日志)。
日志: data/event_guard.log | 快照: data/event_guard_last.json
"""
import os, sys, json, time, subprocess, datetime

ROOT = "E:/GoldstrategyEngine"
DATA = os.path.join(ROOT, "data")
LOG = os.path.join(DATA, "event_guard.log")
SNAP = os.path.join(DATA, "event_guard_last.json")
EVENTS = os.path.join(DATA, "event_risk.json")
FEED = os.path.join(DATA, "event_news_feed.json")
RISK_STATE = os.path.join(DATA, "risk_state.json")  # L4 t_a3872914: 组合风险体温表
CALENDAR = os.path.join(DATA, "event_calendar.json")
WIN_OUT = os.path.join(DATA, "event_guard_windows.json")  # 三段式做单时刻表(闸), 30min全链/看板可读
PY = "C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/pythonw.exe"
MAGIC = [20260902, 20260903, 20260904]   # 外汇/币/股指 三状态机 magic

# 三个挂单状态机 (STATE 文件 + 撤单脚本参数)
MACHINES = [
    ("forex", os.path.join(DATA, "pending_orders_state.json"), MAGIC[0]),
    ("crypto", os.path.join(DATA, "crypto_pending_state.json"), MAGIC[1]),
    ("equity", os.path.join(DATA, "equity_pending_state.json"), MAGIC[2]),
]


def log(line):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def now_hms():
    return datetime.datetime.now().strftime("%H:%M:%S")


def read_last_updated():
    try:
        d = json.load(open(EVENTS, encoding="utf-8"))
        return int(d.get("updated", 0)), d
    except Exception:
        return 0, {}


def read_feed_freshness():
    """读 event_news_feed.json 新鲜度 + fail_open 标记.
    fail-open 口径: 抓取失败 (fail_open=True) 沿用上一份定级 + 从保守 (MED),
    留痕 event_guard.log, 不阻塞交易。
    返回 (feed_ts, fail_open, level_inherit, n_hits).
    """
    try:
        f = json.load(open(FEED, encoding="utf-8"))
        return (
            int(f.get("updated", 0)),
            bool(f.get("fail_open")),
            str(f.get("level_auto", "MED")).upper(),
            int(f.get("auto_source", {}).get("n_hits", 0) if isinstance(f.get("auto_source"), dict) else 0),
        )
    except Exception:
        return 0, True, "MED", 0


def _feed_hits(f):
    """feed 顶层级联: auto_source.n_hits → 三类目 items.hits 展平计数. 返回 int."""
    if isinstance(f.get("auto_source"), dict):
        try:
            return int(f["auto_source"].get("n_hits", 0) or 0)
        except Exception:
            pass
    try:
        return sum(len(it.get("hits", [])) for blk in f.get("categories", {}).values()
                   for it in blk.get("items", []))
    except Exception:
        return 0


def read_feed_level():
    """读 event_news_feed.json 自动源定级 (level_auto/halt_auto/fail_open/n_hits).
    fail-open 口径: 抓取失败 (fail_open=True 或文件缺失/损坏) 沿用上一份定级 + 从保守 (MED),
    留痕 event_guard.log, 不阻塞交易。返回 (feed_ts, fail_open, level, n_hits, halt)."""
    try:
        f = json.load(open(FEED, encoding="utf-8"))
        return (
            int(f.get("updated", 0)),
            bool(f.get("fail_open")),
            str(f.get("level_auto", "MED")).upper(),
            _feed_hits(f),
            bool(f.get("halt_auto")),
        )
    except Exception:
        return 0, True, "MED", 0, False


def run_cancel_script():
    """撤单: 三个状态机里 趋势(regime=trending) 挂单 + 未跟踪的 Stop 类挂单一并撤,
    撤成功的票号清出 st['pending'] (防下轮 reevaluate 重挂)。GBK 安全, fail-open。"""
    script = '''
import MetaTrader5 as mt5, json, time, os
PAIRS = [
    (r"E:\\\\GoldstrategyEngine\\\\data\\\\pending_orders_state.json", 20260902),
    (r"E:\\\\GoldstrategyEngine\\\\data\\\\crypto_pending_state.json", 20260903),
    (r"E:\\\\GoldstrategyEngine\\\\data\\\\equity_pending_state.json", 20260904),
]
ok0 = mt5.initialize()
mt5.login(60137964, password="Lym141345$", server="TradeMaxGlobal-Demo")
out = {"cancelled": [], "failed": []}
for stpath, magic in PAIRS:
    st = json.load(open(stpath, encoding="utf-8")) if os.path.exists(stpath) else {}
    pend = st.get("pending", {})
    for tk, p in list(pend.items()):
        regime = p.get("regime", p.get("layer", "trend"))
        ptype = p.get("ptype", p.get("type", ""))
        is_trend = (regime == "trending") or ("STOP" in str(ptype).upper())
        if not is_trend:
            continue    # 事件高危只撤趋势/Stop, 震荡 Limit 腿保留 (反向对冲价值)
        r = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": int(tk)})
        # build6182 撤单: 挂单请求只需要 order ticket (带 symbol/type 等旧字段会 10013)
        rc = r.retcode if r else -1
        if rc in (mt5.TRADE_RETCODE_DONE, 10007, 10027):
            out["cancelled"].append({"sym": p.get("sym"), "ticket": int(tk), "ret": rc})
            del pend[tk]
        else:
            out["failed"].append({"sym": p.get("sym"), "ticket": int(tk), "ret": rc})
    st["pending"] = pend
    json.dump(st, open(stpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
mt5.shutdown()
print("[event_guard]", json.dumps(out, ensure_ascii=False))
'''
    r = subprocess.run([PY, "-c", script], capture_output=True, text=True, cwd=ROOT, timeout=180)
    for l in (r.stdout or "").strip().splitlines():
        log("  [撤单] " + l)
    if r.returncode != 0:
        log("  [撤单] 异常: " + (r.stderr or "").strip()[:300])
    return r


def run_xau_gate_cancel(dry_run: bool = False):
    """[2026-10-14 L5 hook · chief派单] XAUUSD 破位撤单闸源 (L4 建 xau_break_cancel_gate.json):
    active 且 live bid < break_below → 撤 forex 状态机在位 XAUUSD 挂单 (只 out 不 in).
    病灶: 闸源 18:02 建了但 30min 循环 / 5min 快通道读闸链路都没 hook → 撤了第三张又挂回.
    幂等: 状态机已无 XAUUSD 挂单 → 留痕 no-op; 全链近 600s 已按闸源撤过(last_loop_cancel_ts) → 跳过.
    dry_run=True → 只打印将撤清单, 不发单不写状态机不写闸源 (验证用).
    fail-open: 闸源缺失/非active/bid读不到 → 不动不崩 5min 快通道."""
    g = {}
    try:
        g = json.load(open(os.path.join(DATA, "xau_break_cancel_gate.json"), encoding="utf-8"))
    except Exception:
        return False
    if not (isinstance(g, dict) and g.get("active")):
        return False
    try:
        bb = float(g.get("break_below", 0) or 0)
    except Exception:
        return False
    if bb <= 0:
        return False
    try:
        if int(g.get("last_loop_cancel_ts", 0)) > 0 and time.time() - int(g["last_loop_cancel_ts"]) < 600:
            log("  [xau-gate] 全链/快通道近10min已按闸源撤过, 本拍跳过(幂等窗)")
            return False
    except Exception:
        pass
    script = '''
import MetaTrader5 as mt5, json, time, os
DRY = ''' + ("True" if dry_run else "False") + '''
gpath = r"E:\\\\GoldstrategyEngine\\\\data\\\\xau_break_cancel_gate.json"
spath = r"E:\\\\GoldstrategyEngine\\\\data\\\\pending_orders_state.json"
out = {"cancelled": [], "failed": [], "noop": "gate-inactive"}
g = json.load(open(gpath, encoding="utf-8"))
if not (isinstance(g, dict) and g.get("active")):
    print("[xau-gate] " + json.dumps(out, ensure_ascii=False)); raise SystemExit(0)
bb = float(g.get("break_below", 0) or 0)
if not mt5.initialize():
    print("[xau-gate] initialize 失败, no-op (fail-open)"); raise SystemExit(0)
mt5.login(60137964, password="Lym141345$", server="TradeMaxGlobal-Demo")
tk = mt5.symbol_info_tick("XAUUSD")
bid = float(tk.bid) if tk is not None else 0.0
if bid <= 0:
    print("[xau-gate] bid 读不到, 本拍不动 (fail-open, 不拿坏数据撤单)"); mt5.shutdown(); raise SystemExit(0)
if bid >= bb:
    print("[xau-gate] bid %.2f >= %.0f 未破位, 撤单条件不成立, no-op" % (bid, bb)); mt5.shutdown(); raise SystemExit(0)
st = json.load(open(spath, encoding="utf-8")) if os.path.exists(spath) else {"pending": {}}
pend = st.get("pending", {})
hits = [(t, p) for t, p in list(pend.items()) if p.get("sym") == "XAUUSD"]
if not hits:
    out["noop"] = "no-xau-pending"
    print("[xau-gate] bid %.2f < %.0f 但状态机已无 XAUUSD 挂单, 闸源已满足, no-op" % (bid, bb))
    mt5.shutdown(); raise SystemExit(0)
changed = False
for tkt, p in hits:
    if DRY:
        out["cancelled"].append(int(tkt)); continue
    r = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": int(tkt)})
    rc = r.retcode if r else -1
    if rc in (mt5.TRADE_RETCODE_DONE, 10007, 10027):
        out["cancelled"].append(int(tkt))
        del pend[tkt]; changed = True
        st.setdefault("history", []).append({"ts": int(time.time()), "evt": "xau-gate撤单", "sym": "XAUUSD",
                                             "why": "bid %.2f < %.0f 只out不in" % (bid, bb), "ticket": int(tkt), "ret": rc})
    else:
        out["failed"].append({"ticket": int(tkt), "ret": rc})
if not DRY:
    if changed:
        st["pending"] = pend
        json.dump(st, open(spath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    g.setdefault("loop_cancels", []).append({"ts": int(time.time()), "bid": bid, "broke": bb,
                                             "tickets": out["cancelled"], "src": "event_guard_5min", "dry": False})
    g["last_loop_cancel_ts"] = int(time.time())
    json.dump(g, open(gpath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
out["noop"] = ""
print("[xau-gate] " + json.dumps(out, ensure_ascii=False))
mt5.shutdown()
'''
    r = subprocess.run([PY, "-c", script], capture_output=True, text=True, cwd=ROOT, timeout=180)
    for l in (r.stdout or "").strip().splitlines():
        log("  [xau-gate] " + l)
    if r.returncode != 0:
        log("  [xau-gate] 异常: " + (r.stderr or "").strip()[:300])
        return False
    return True


def read_risk_state():
    """L4 t_a3872914: 读组合风险体温表 data/risk_state.json (write_risk_state.py 每30min全链落盘).
    只泄压不加息: 熔断进度>=100 / 24h冷却激活 / 10pct_circuit_progress>=100 / new_entry_scale=0
    任一命中 → 返回 (True, 原因, rs_dict); 缺失/损坏 → fail-open (False, 沿用 event_risk 单源, 不崩).
    读它只做"更严"判断 (只降不升), 不发明数字, 全读体温表落盘值。"""
    rs = {}
    try:
        rs = json.load(open(RISK_STATE, encoding="utf-8"))
    except Exception:
        return False, "", {}
    triggers = []
    try:
        if float(rs.get("10pct_circuit_progress", 0.0)) >= 100:
            triggers.append("L1日级-10%熔断进度100%")
        if rs.get("24h_cooldown", {}).get("active"):
            triggers.append("连亏24h冷却激活")
        if float(rs.get("new_entry_scale", 1.0) or 0.0) == 0.0:
            triggers.append("体温表new_entry_scale=0(只泄压位)")
        if rs.get("drawdown_brake_scale", {}).get("state") in ("STOP", "HALF"):
            triggers.append("回撤刹车%s" % rs["drawdown_brake_scale"]["state"])
    except Exception:
        pass
    return (len(triggers) > 0), ("; ".join(triggers) if triggers else ""), rs


# ============================================================================
# 三段式做单时刻表 (治"任何阶段都能做单"): 读 event_calendar.json 的
# high_events_in_24h + windows, 对每个未来/进行中 HIGH/MED 数据事件生成三段:
#   S1 数据前 30min : 起 halt_new_entries(停新仓 + 撤趋势/Stop 挂单, 震荡Limit保留)
#   S2 数据瞬间~后10min : 保持 halt(观察段, 点差最毒时刻, 滑点 3-5x)
#   S3 数据后 30min   : 结构确认(无新 HIGH/未 HALT)才清 halt 放行
# 时刻全部北京时间(美东夏令时+12), 只写 data/event_guard_windows.json 时刻表,
# 撤单动作只触发在 起S1/数据瞬间 两个时刻(只撤不挂, 保险丝原则);
# 不碰币系冻结桥(crypto_freeze_gate/veto_log)与金银 MED 0.5x 线(独立gate表达)。
# fail-open: 读不到 event_calendar.json → 沿用最近快照时刻表 + 留痕, 不崩。
# ============================================================================
T0_MIN = 30          # S1: 数据前 30min 起 halt
TOX_MIN = 10         # S2: 数据瞬间~后 10min 保持 halt(观察)
CONFIRM_MIN = 30     # S3: 数据后 30min 结构确认位
BJT = datetime.timezone(datetime.timedelta(hours=8))   # 美东夏令时 ET+12 = 北京


def bjt_str(ts):
    return datetime.datetime.fromtimestamp(int(ts), BJT).strftime("%Y-%m-%d %H:%M")


def _ev_grade(w):
    """事件窗定级: HIGH 为主, MED 兜底 (事件日历 windows 本身无 grade 字段,
    由生成方 alpha_researcher 只给 HIGH 窗口; MED 语义留给 event_risk.json level=MED)。"""
    t = str(w.get("title", ""))
    pol = str(w.get("policy", ""))
    if "HIGH" in t.upper() or "高" in pol:
        return "HIGH"
    return "MED"


def _ev_time(w):
    try:
        return int(w.get("event_time", 0))
    except Exception:
        return 0


def read_calendar():
    """fail-open 读 event_calendar.json: 缺失/损坏 → 用最近落盘的时刻表快照兜底。
    返回 (cal_doc_or_None, fail_open, fail_why)。"""
    try:
        c = json.load(open(CALENDAR, encoding="utf-8"))
        return c, False, ""
    except Exception as ex:
        snap_win = None
        try:
            snap_win = json.load(open(WIN_OUT, encoding="utf-8"))
        except Exception:
            snap_win = None
        why = "event_calendar.json 读不到/损坏: %s" % str(ex)[:80]
        if snap_win is not None:
            log("  [三段式·fail-open] %s → 沿用最近时刻表快照 (生成于 %s), 不崩" % (
                why, snap_win.get("generated_bjt", "?")))
            return snap_win, True, why
        log("  [三段式·fail-open] %s 且无快照 → 本轮不出时刻表 (不崩)" % why)
        return None, True, why


def build_windows(now_ts):
    """从 event_calendar 的 windows 生成三段时刻表 (去重 by event_time, 北京时间)。"""
    cal, fail_open, why = read_calendar()
    entries = []
    seen = set()
    src = cal if isinstance(cal, dict) and "windows" in cal else None
    if src is not None:
        for w in (src.get("windows") or []):
            t = _ev_time(w)
            if t <= 0 or t in seen:
                continue
            seen.add(t)
            grade = _ev_grade(w)
            s1 = t - T0_MIN * 60
            tox_end = t + TOX_MIN * 60
            s3 = t + CONFIRM_MIN * 60
            if now_ts >= s3:
                phase = "DONE"
            elif now_ts >= tox_end:
                phase = "OBSERVING"
            elif now_ts >= s1:
                phase = "PRE_HALT"
            else:
                phase = "SCHEDULED"
            entries.append({
                "key": "ev%d" % t,
                "event_time": t,
                "event_time_bjt": bjt_str(t),
                "title": str(w.get("title", ""))[:60],
                "grade": grade,
                "source": src.get("note", "event_calendar.json"),
                "phase1_stop": {"ts": s1, "bjt": bjt_str(s1),
                                "action": "起halt_new_entries: 停新仓 + 撤趋势/Stop挂单 (震荡Limit腿保留)"},
                "phase2_observe": {"ts": t, "obs_end": tox_end,
                                   "bjt": bjt_str(t), "obs_end_bjt": bjt_str(tox_end),
                                   "action": "保持halt观察 (数据瞬间点差最毒, 滑点3-5x, 禁开仓)"},
                "phase3_confirm": {"ts": s3, "bjt": bjt_str(s3),
                                   "action": "结构确认(无新HIGH/未HALT)后清halt放行, 回补交下轮全链"},
                "phase": phase,
            })
    entries.sort(key=lambda e: e["event_time"])
    upcoming = [e for e in entries if e["event_time"] + CONFIRM_MIN * 60 >= now_ts]
    high_n = src.get("high_events_in_24h", "?") if src is not None else "?"
    return {"generated": int(now_ts),
            "generated_bjt": bjt_str(now_ts),
            "source": "event_calendar.json" if src is not None else "last_snapshot",
            "fail_open": fail_open,
            "fail_why": why,
            "high_events_in_24h": high_n,
            "now_phase_hint": _phase_hint(upcoming),
            "rules": {
                "T0": "数据前%dmin起halt(停新仓+撤趋势/Stop)" % T0_MIN,
                "tox": "数据瞬间~后%dmin保持halt(观察)" % TOX_MIN,
                "T30": "数据后%dmin结构确认才清halt" % CONFIRM_MIN,
                "scope": "只撤不挂; 不碰币系冻结桥与金银MED0.5x线(独立gate)",
                "tz": "全部北京时间(美东夏令时+12)",
            },
            "events": upcoming}


def _phase_hint(upcoming):
    """给 30min全链/看板的一句话提示: 该停/该恢复/正常。"""
    for e in upcoming:
        if e["phase"] == "PRE_HALT":
            return "该停: [%s] %s 前已起halt, 停新仓+撤趋势/Stop, 至 %s 结构确认" % (
                e["event_time_bjt"], e["title"][:24], e["phase3_confirm"]["bjt"])
        if e["phase"] == "OBSERVING":
            return "保持halt(观察): [%s] %s 数据瞬间~点差最毒, 至 %s 结构确认放行" % (
                e["event_time_bjt"], e["title"][:24], e["phase3_confirm"]["bjt"])
        if e["phase"] == "SCHEDULED":
            nxt = upcoming[0]
            return "下一事件 %s [%s] %s 前%s 起halt(停新仓)" % (
                nxt["event_time_bjt"], nxt["grade"], nxt["title"][:24],
                nxt["phase1_stop"]["bjt"].split(" ")[-1])
    return "无进行中事件: 正常挂单, 关注 event_risk.json 下一轮定级"


def maybe_fire_cancel(win, now_ts, level, do_cancel):
    """只撤不挂的两个触发时刻: ① 起S1瞬间 ② 数据瞬间。
    命中 → 撤一次并留痕 (防5min任务重复撤, 看 last_cancel_event_key/last_cancel_ts)。
    level 门控: 撤闸口命中时, 若本轮无 HIGH/HALT/halt 触发, 撤单仍执行——
    日历是确定性事实(数据要发布), 撤单是纯防御动作(只撤不挂), 不因定级滞后漏撤;
    金银 MED 0.5x 线与币系冻结桥是独立 gate, 本闸口不碰。返回 True=本轮撤过单。"""
    if not win:
        return False
    for e in win.get("events", []):
        s1 = e["phase1_stop"]["ts"]
        t0 = e["event_time"]
        for trig, label in ((s1, "起S1"), (t0, "数据瞬间")):
            if trig <= now_ts <= trig + 600:   # 5min 快通道容差窗
                key = "%s:%s" % (e["key"], label)
                prev = win.get("last_cancel_event_key")
                if prev == key and now_ts - int(win.get("last_cancel_ts", 0)) < 3600:
                    continue
                do_cancel()
                win["last_cancel_event_key"] = key
                win["last_cancel_ts"] = int(now_ts)
                return True
    return False


def write_windows(win, now_ts):
    """落盘 data/event_guard_windows.json (读端: 30min全链/看板读 generated+events 出'该停/该恢复')。"""
    if not win:
        return
    win["updated"] = int(now_ts)
    win["updated_bjt"] = bjt_str(now_ts)
    try:
        tmp = WIN_OUT + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(win, f, ensure_ascii=False, indent=2)
        os.replace(tmp, WIN_OUT)
    except Exception as ex:
        log("  [三段式] 落盘 event_guard_windows.json 失败 (fail-open): %s" % str(ex)[:120])


def print_today_schedule(win):
    """可读输出: 今日各数据事件的停/恢复时刻表 (北京时间)。"""
    print("---- 事件三段式做单时刻表 (北京时间, 美东夏令时+12) ----")
    if not win or not win.get("events"):
        print("  未来 24h 内无 HIGH/MED 数据事件 → 正常挂单 (fail_open=%s)" %
              (win.get("fail_open") if win else "no_data"))
        return
    for e in win["events"]:
        print("  [%s] %s | 停: %s (撤趋势/Stop, 震荡保留) | 观察: %s~%s | 恢复: %s 结构确认" % (
            e["event_time_bjt"], e["title"][:36],
            e["phase1_stop"]["bjt"], e["phase2_observe"]["bjt"],
            e["phase2_observe"]["obs_end_bjt"], e["phase3_confirm"]["bjt"]))
    print("  提示: %s" % win.get("now_phase_hint"))


def main():
    start = time.time()
    log("")
    log("=" * 52)
    log(f"[事件快通道] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    now_ts = int(time.time())
    cur_upd, doc = read_last_updated()
    level = str(doc.get("level", "LOW")).upper()
    halt_flag = bool(doc.get("halt_new_entries"))
    feed_ts, feed_fail_open, feed_level, feed_nhits, feed_halt = read_feed_level()

    # 双闸第一闸(自动源): feed 的 level_auto/halt_auto 与 event_risk.json 取更严者 (rank 高者优先)
    _rank = {"LOW": 0, "MED": 1, "HIGH": 2, "HALT": 3}
    if _rank.get(feed_level, 1) > _rank.get(level, 0) or feed_halt:
        log("  [双闸] 自动源 feed level=%s(hits=%d) 严于 event_risk level=%s → 取更严" % (
            feed_level, feed_nhits, level))
        level, halt_flag = feed_level, (halt_flag or feed_halt)
    if feed_fail_open:
        log("  [fail-open] 自动源抓取失败, 沿用上一份定级 level=%s + 从保守 (不额外撤单, 留痕)" % feed_level)

    # ② L4 t_a3872914 双闸第二闸(组合体温表): 读 risk_state.json, 命中只泄压位 → 并入触发
    rs_hit, rs_why, rs = read_risk_state()
    if rs_hit:
        log("  [体温表] risk_state.json 命中: %s → 并入触发(撤趋势/Stop, 震荡Limit保留)" % rs_why)
        halt_flag = True
        level = "HIGH" if level in ("LOW", "MED") else level
    elif rs:
        log("  [体温表] risk_state.json 读实值: 10pct进度=%s%% 连亏=%s 币系冻结=%s scale=%s" % (
            rs.get("10pct_circuit_progress"), rs.get("consec_losses"),
            rs.get("coin_freeze", {}).get("active"), rs.get("new_entry_scale")))

    # ②b [2026-10-14 L5 hook · chief派单] XAUUSD 破位撤单闸源 5min 快通道:
    # 闸源 active + bid < break_below → 撤在位 XAUUSD 挂单 (只 out 不 in).
    # 不走新鲜度门控: 撤单是确定性事实判断(破位价+闸源), 不依赖 event_risk 刷新;
    # 幂等 600s 窗(last_loop_cancel_ts) + 30min 全链同函数去重, 5min 连跑不会重复撤.
    try:
        run_xau_gate_cancel(dry_run=False)
    except Exception as _xge:
        log("  [xau-gate] 快通道异常(失败开放, 不崩5min): %s" % str(_xge)[:120])

    # ① 新鲜度门控: 快照里记的 updated 与现在相同 → 30min 全链已处理过该事件, 跳过
    snap = {}
    if os.path.exists(SNAP):
        try:
            snap = json.load(open(SNAP, encoding="utf-8"))
        except Exception:
            snap = {}
    snap_feed = int(snap.get("feed_updated", 0))
    if snap.get("last_updated") == cur_upd and cur_upd > 0 and snap_feed >= feed_ts:
        # 三段式时刻表即使 event_risk 无更新也要刷 (时刻表是日历驱动, 不受新鲜度门控)
        _win = build_windows(now_ts)
        write_windows(_win, now_ts)
        log("  [跳过] event_risk+feed 自上次快照无更新 (updated=%d feed_ts=%d), 本轮不动" % (cur_upd, feed_ts))
        log(f"[事件快通道完成] {now_hms()} ({time.time()-start:.1f}s, 无动作)")
        return 0

    # 写新快照 (无论动作与否都刷新, 防下轮 5min 重复撤单)
    json.dump({"last_updated": cur_upd, "feed_updated": feed_ts, "level": level,
               "ts": int(time.time())},
              open(SNAP, "w", encoding="utf-8"))

    # ③ 三段式做单时刻表 (日历驱动): 生成时刻表落盘 + 在 起S1/数据瞬间 两闸口自动撤单
    win = build_windows(now_ts)
    if win is not None:
        if maybe_fire_cancel(win, now_ts, level, run_cancel_script):
            log("  [三段式] 命中撤单闸口(起S1或数据瞬间, 只撤不挂): %s" % win.get("last_cancel_event_key"))
            log("  [标记] 挂单部 halt_new_entries=True (下轮全链 will 撤新单; 本脚本只撤不挂)")
        write_windows(win, now_ts)
        print_today_schedule(win)

    if level in ("HIGH", "HALT") or halt_flag:
        log(f"  [触发] level={level} halt={halt_flag} → 撤趋势/Stop 挂单 (三状态机)")
        run_cancel_script()
        log("  [标记] 挂单部 halt_new_entries=True (下轮全链 will 撤新单; 本脚本只撤不挂)")
    elif level == "LOW":
        log("  [恢复] level=LOW → 清 halt 标记, 恢复挂单 (回补交下轮全链, 本脚本不自动加仓)")
    else:
        log(f"  [保持] level={level} 非触发/恢复位, 不动 (快照已刷新)")

    log(f"[事件快通道完成] {now_hms()} ({time.time()-start:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
