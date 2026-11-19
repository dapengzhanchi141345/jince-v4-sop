# -*- coding: utf-8 -*-
"""金策宗师团·综合大会五板块生成器 (最小版, 确定性 0 LLM, 429 免疫 no_agent)
周六 09:05 回顾场 / 周日 15:05 前瞻场。
铁律:
  ① 国际/社会板块外网断自动降级 → 只报本地快照 + 标"落盘于 X、过期 Y 小时, 仅供参考", 不拿旧闻当新闻
  ② 情感/娱乐板块 LLM 产出永不进 data/ 决策目录 —— 本脚本只出"生活面健康分"实数, 生活格由人(们)当场口述
  ③ 每格数字带来源文件, 可回查
输出: stdout 全文 → 投递群 + 追加 discussion_log (node=synth_meeting)
"""
import json, os, time, datetime, collections, sqlite3

ROOT = os.environ.get("JINCE_ROOT", r"E:\GoldstrategyEngine")
DATA = os.path.join(ROOT, "data")
PY = None

def jget(fn, default=None):
    try:
        with open(os.path.join(DATA, fn), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def jlines(fn):
    out = []
    try:
        with open(os.path.join(DATA, fn), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        pass
    return out

def now_bjt():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))

def file_age_h(fn):
    p = os.path.join(DATA, fn)
    if not os.path.exists(p):
        return None
    return (time.time() - os.path.getmtime(p)) / 3600

def degraded_mark(fn, data=""):
    """外网降级标: 落盘时间 + 过期时长, 不静默"""
    age = file_age_h(fn)
    if age is None:
        return "%s (快照缺失, 降级)" % data
    return "%s (快照落盘 %.1f 小时前, 仅供参考)" % (data, age)

def board_intl():
    """① 国际形势 (chief 主): event_calendar HIGH 事件 + extnet 降级标 (外网断 = 只报快照, E2 触发键是 extnet 不是 GitHub)"""
    probe = jget("network_probe_last.json", {}) or {}
    extnet = str(probe.get("extnet", "?"))
    ext_down = "down" in extnet.lower()
    cal = jget("event_calendar.json", {})
    events = cal.get("events", cal) if isinstance(cal, dict) else []
    if isinstance(events, dict):
        events = [events]
    hi = [e for e in events if isinstance(e, dict) and str(e.get("level", "")).upper() in ("HIGH", "HALT")]
    body = "HIGH/HALT 事件 %d 条" % len(hi)
    if hi:
        body += ": " + "; ".join("%s(%s)" % (e.get("name", e.get("event", "?"))[:24], str(e.get("date", e.get("time", "")))[:10]) for e in hi[:5])
    body = degraded_mark("event_calendar.json", body)
    if ext_down:
        body += " | ⚠extnet 通用 web 断(快照仅参考) — E2/新闻源拉取触发键 = extnet 恢复(非 GitHub DoH 侧车)"
    body += " | 事件降档影子簿 event_high_shadow_log.jsonl 在位(L1 留痕, 不喂闸)" if os.path.exists(os.path.join(DATA, "event_high_shadow_log.jsonl")) else " | 事件降档影子簿未开(周五周会销格项)"
    return "① 国际形势格 (chief): " + body

def board_society():
    """② 社会内容 (@hermes 主): 确定性部分 = 关键源新鲜度 + social_inbox E2 进度, 社会板块 LLM 内容 @hermes 当场出"""
    parts = []
    for fn, label in (("external_intel.json", "外源情报"), ("discussion_log.jsonl", None)):
        age = file_age_h(fn)
        if label and age is not None:
            parts.append("%s 快照 %.1fh 前" % (label, age))
    inbox = []
    try:
        ib = os.path.join(DATA, "social_inbox")
        if os.path.isdir(ib):
            inbox = [f for f in os.listdir(ib) if f.endswith((".json", ".md", ".txt"))]
    except Exception:
        pass
    e2 = "E2 外部假设 inbox %d 条(只留痕零权重)" % len(inbox) if inbox else "E2 外部假设 inbox 空(外网通后首场 E2 进假设)"
    llm = " | 社会/LLM 格 @hermes 当场出(AI 圈动态+政策+内容线周报, key 池轮换不再烧额度顾虑)"
    return "② 社会内容格 (@hermes 主): " + "; ".join(parts) if parts else "② 社会内容格 (@hermes 主): (本地快照全缺, 全降级)"
    # 保持确定性: 上面 return 先走不到后面, 重构为单一 return
def board_society_v2():
    parts = []
    age = file_age_h("external_intel.json")
    if age is not None:
        parts.append("外源情报快照 %.1fh 前" % age)
    else:
        parts.append("外源情报快照缺失(降级)")
    inbox = []
    try:
        ib = os.path.join(DATA, "social_inbox")
        if os.path.isdir(ib):
            inbox = [f for f in os.listdir(ib) if f.endswith((".json", ".md", ".txt"))]
    except Exception:
        pass
    parts.append("E2 外部假设 inbox %d 条(只留痕零权重不喂闸)" % len(inbox) if inbox else "E2 外部假设 inbox 空(外网通后首场 E2 进)")
    parts.append("社会/LLM 格 @hermes 当场出(AI 圈+政策+内容线, 允许烧 LLM, 娱乐格隔离闸照旧)")
    return "② 社会内容格 (@hermes 主): " + " | ".join(parts)

def board_rd():
    """③ 科研研发 (strategy-rd 主): 复用周会 rd_block 口径"""
    et = jget("edge_tracker.json", {})
    syms = et.get("symbols", {})
    strats = et.get("strategies", {})
    v5 = []
    for fn in sorted(os.listdir(DATA)) if os.path.isdir(DATA) else []:
        if fn.startswith("rd_verify_batch") and fn.endswith(".json"):
            b = jget(fn, {})
            items = b.get("items", b.get("decisions", []))
            pend = [i for i in items if isinstance(i, dict) and "PASS" not in str(i.get("verdict", "")).upper()]
            v5.append("%s(%d 待验)" % (fn, len(pend)))
    nsyms = len(syms)
    return "③ 科研研发格 (@strategy-rd 主): edge_tracker 品种 %d / 策略 %d | 五验批次 %s | E 节点进度见 rd_decisions(e_nodes_ 前缀, 周五周会 ③ 行自动念)" % (nsyms, len(strats), "; ".join(v5) or "无批次")

def tsf(e):
    v = e.get("ts", 0)
    try:
        return float(v)
    except Exception:
        try:
            import datetime as _dt
            return _dt.datetime.fromisoformat(str(v)).timestamp()
        except Exception:
            return 0.0

def board_risk():
    """④ 风控 (risk-officer 主): 7 天否决分型 + 冻结三态 + 红线三字段
    [L4 口径 2026-10-04] 两处修正:
    a) "真否决"细分两档念(纯否决 VETO-CANCEL/CONFIRM-STOP vs 审计/确认留痕), 防把 13 条审计念成 13 条否决
    b) consec_losses 是历史峰值非当前冷却态: 必须叠加 cooldown_until vs now, 已过期标"(冷却已释放)", 防误读为正在冷却"""
    veto = jlines("veto_log.jsonl")
    now = time.time()
    week = [v for v in veto if isinstance(v, dict) and (now - tsf(v)) < 7 * 86400]
    dec = collections.Counter()
    heart = 0
    for v in week:
        cat = str(v.get("gate", v.get("decision", v.get("category", "?"))))
        if "RISK-NET-GATE" in cat.upper() or "risk-network" in cat.lower():
            heart += 1
        else:
            dec[cat] += 1
    pure_veto = 0
    for v in week:
        if "RISK-NET-GATE" in str(v.get("gate", v.get("category", ""))).upper() or "risk-network" in str(v.get("gate", v.get("category", ""))).lower():
            continue
        if v.get("decision") in ("VETO-CANCEL", "CONFIRM-STOP"):
            pure_veto += 1
    audit = sum(dec.values()) - pure_veto
    frz = jget("risk_freeze_state.json", {})
    lvl = frz.get("level", "?")
    pol = frz.get("policy", {})
    red = []
    for fn in ("pending_orders_state.json", "crypto_pending_state.json", "equity_pending_state.json"):
        st = jget(fn, {}) or {}
        do = st.get("daily_opens", "-")
        do = len(do) if isinstance(do, dict) else do
        cl = st.get("consec_losses", "-")
        cu = st.get("cooldown_until", 0) or 0
        cl_note = " %s(冷却已释放,非在冷却)" % ("历史峰值" if cu and cu < now else "") if isinstance(cl, int) and cl >= 3 and cu and cu < now else ""
        red.append("%s:日开%s/连亏%s%s/日实亏%s" % (fn.split("_")[0], do, cl, cl_note, st.get("day_realized_pnl", "-")))
    return "④ 风控格 (@risk-officer 主): 7 天否决 %d 条(纯否决 %d + 审计确认 %d, 闸刷新留痕 %d 条剥出) | LEVEL_%s(开新=%s) | 红线 %s | 金线 0 单 0 亏以实盘为准" % (
        sum(dec.values()), pure_veto, audit, heart, lvl, pol.get("open_new_order"), "; ".join(red))

def board_life():
    """⑤ 生活面健康分 (chief 主): 系统活得好不好 —— 修坑/自拉回/异常数, 实数出; 生活格口述不在此"""
    log = jlines("discussion_log.jsonl")
    now = time.time()
    week = [e for e in log if isinstance(e, dict) and (now - tsf(e)) < 7 * 86400]
    fix = [e for e in week if any(k in str(e.get("node", "")).lower() for k in ("fix", "correct", "audit", "销"))]
    # 看门狗真落点 = network_probe_last.json (5min 覆写式, 无历史): 报"最后状态+TS", 超 1h 未刷新 = 看门狗停摆故障
    probe = jget("network_probe_last.json") or {}
    gw = probe.get("gateway", "?")
    pts = probe.get("ts", "?")
    probe_stale = False
    try:
        import datetime as _dt
        pt = _dt.datetime.strptime(str(pts).split(".")[0], "%m-%d %H:%M:%S").replace(year=_dt.datetime.now().year, tzinfo=None)
        probe_stale = (time.time() - pt.timestamp()) > 3600
    except Exception:
        probe_stale = False
    gw_note = "看门狗: gateway 最后态 '%s' @ %s" % (gw, pts)
    if probe_stale:
        gw_note += " ⚠ 探针超 1h 未刷新 = 看门狗任务停摆(故障行, 22:00 日报报)"
    return "⑤ 生活面格 (chief): 本周修坑/审计节点 %d 条 | %s | 纪律: 生活/人类观察口述格 @hermes 主持, 永不进 data/ 决策目录" % (len(fix), gw_note)

def main():
    L = ["【综合大会·%s】金策宗师团五板块 %s" % ("回顾" if now_bjt().weekday() == 5 else "前瞻", now_bjt().strftime("%m-%d %H:%M"))]
    L.append(board_intl())
    L.append(board_society_v2())
    L.append(board_rd())
    L.append(board_risk())
    L.append(board_life())
    L.append("隔离闸: 情感/LLM 产出只在 discussion_log 口述留痕, 不喂任何闸源/决策目录 | 红线日≤3单/10%熔断/连亏3笔冷却 一字未动 | 历史回测≠未来收益")
    text = "\n".join(L)
    print(text)
    try:
        with open(os.path.join(DATA, "discussion_log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"node": "synth_meeting", "ts": int(time.time()), "actor": "chief",
                                 "scope": "synth", "source": "jince_synth_meeting.py", "text": text},
                                ensure_ascii=False) + "\n")
    except Exception:
        pass
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
