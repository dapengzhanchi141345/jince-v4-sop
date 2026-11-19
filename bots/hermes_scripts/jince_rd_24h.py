#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策 24h 研发轮转段生成器 (no_agent L0, 0 LLM, 429-proof)
每段 4h(04/08/12/16/20 BJT) 由 strategy-rd profile 的 5 个 cron 各挂一个。
职责(只留痕, 不做交易动作):
 1) 按当前北京时间取本段主题(趋势CTA/动量/事件/统计套利/资金费率·波动率陷阱)
 2) 落 rd_ledger_24h.json 一条(追加): ts/主题/候选/判定/离P4还差/心跳=alive
 3) 投群 1 条大白话段报(谁在跑/本段主题/判定/下一段), 并落运营同步钩子
    (data/ops_sync_queue.json 追加一条: 错开研发高峰 60-90s, ops-manager 自取)
所有外部读: rd_ledger.json(最新判定) / data 目录学习文件 mtime / veto_log
fail-open: 任何一步崩 → 记 degraded=true, 台账照写, 交易全链零影响(本脚本不碰挂单/真闸)。
用法:
  python jince_rd_24h.py            # 无参: 按北京时间自动选本段
  python jince_rd_24h.py cta_trend # 显式主题key(补发/测试用)
"""
import os, sys, json, time, datetime, zoneinfo, random

DATA = r"E:/GoldstrategyEngine/data"
LEDGER = os.path.join(DATA, "rd_ledger_24h.json")
OPSQ = os.path.join(DATA, "ops_sync_queue.json")
RDL = os.path.join(DATA, "rd_ledger.json")
BJT = zoneinfo.ZoneInfo("Asia/Shanghai")

# 主题轮转表(与 5 个 cron 对齐): 段起时刻 BJT -> (key, 中文名, 研学要点)
ROUTES = [
    ("04", "cta_trend",     "趋势CTA",     "趋势跟踪族: ADX/吊灯止损/动量确认 最新研究与参数前沿"),
    ("08", "momentum",      "动量",        "日内/跨时段动量: 开盘动量/收盘反转/动量衰减 最新证据"),
    ("12", "event",         "事件驱动",    "NFP/CPI/利率决议等宏观事件: 事件前后价差/波动率跳变 最新统计"),
    ("16", "stat_arb",      "统计套利",    "配对/跨品种协整/基差: 半衰期/价差z分数 最新方法"),
    ("20", "vol_trap",      "资金费率·波动率陷阱", "永续资金费率/期限结构/波动率聚集与陷阱清单: 费率信号最新研究"),
]

def now_bjt():
    return datetime.datetime.now(BJT)

def pick_theme(key=None):
    if key:
        for h, k, cn, brief in ROUTES:
            if k == key:
                return k, cn, brief
    h = now_bjt().hour
    # 段归属: [04,08)→cta 04起;  [08,12)→momentum; [12,16)→event; [16,20)→stat_arb; [20,24)∪[0,4)→vol_trap
    if 4 <= h < 8:   return "cta_trend", "趋势CTA", ROUTES[0][3]
    if 8 <= h < 12:  return "momentum", "动量", ROUTES[1][3]
    if 12 <= h < 16: return "event", "事件驱动", ROUTES[2][3]
    if 16 <= h < 20: return "stat_arb", "统计套利", ROUTES[3][3]
    return "vol_trap", "资金费率·波动率陷阱", ROUTES[4][3]

def next_theme():
    h = now_bjt().hour
    order = ["cta_trend", "momentum", "event", "stat_arb", "vol_trap"]
    idx = {"cta_trend": 0, "momentum": 1, "event": 2, "stat_arb": 3, "vol_trap": 4}
    cur = "cta_trend" if 4 <= h < 8 else ("momentum" if 8 <= h < 12 else ("event" if 12 <= h < 16 else ("stat_arb" if 16 <= h < 20 else "vol_trap")))
    nxt = order[(idx[cur] + 1) % 5]
    nxt_h = {"cta_trend": "04", "momentum": "08", "event": "12", "stat_arb": "16", "vol_trap": "20"}[nxt]
    cn = dict((k, c) for _, k, c, _ in ROUTES)[nxt]
    return nxt, nxt_h, cn

def learn_files_last7d():
    """fail-open: 最近 7 天内 mtime 的学习/研报文件(=本窗口实际研学落库证据)"""
    out = []
    now = time.time()
    try:
        for f in os.listdir(DATA):
            if not f.endswith((".md", ".json")):
                continue
            p = os.path.join(DATA, f)
            if f.startswith(("_", ".", "rd_ledger", "ops_sync", "discussion")):
                continue
            try:
                mt = os.path.getmtime(p)
            except Exception:
                continue
            if now - mt <= 7 * 86400:
                out.append((f, mt))
    except Exception:
        return []
    out.sort(key=lambda x: -x[1])
    return out[:8]

def last_rd_verdict():
    """rd_ledger.json 最后一条: 候选名+判定 (离P4还差 取它的 gates_failed)
    [2026-10-14 L5-fix chief 04:19 口径] 收口判据=verdict 带 5/5 PASS;
    gates_failed 为空 != 已收口 (无显式失败项只是没列, FIXED_ROOTCAUSE/WATCH/REJECT/BLOCKED 均=未收口)."""
    try:
        d = json.load(open(RDL, encoding="utf-8"))
        es = d.get("entries", [])
        if not es:
            return "无", "—", []
        e = es[-1]
        # [2026-10-14 L5-fix] 候选名读 hypo/task/topic 三字段(strategy-rd 近期条目用 topic, 旧条目用 hypo;
        #   只读 hypo/task 时近 10 条全落"(无名候选)", chief 06:02 点名):
        hyp = e.get("hypo") or e.get("task") or e.get("topic") or "(无名候选)"
        v = e.get("verdict") or e.get("kind") or "?"
        gf = [g for g in (e.get("gates_failed") or []) if g]
        return hyp, str(v)[:40], gf[:3], e
    except Exception:
        return "(读失败)", "—", [], None

def closedout_wording(verdict, gates, e):
    """段报'离P4还差'措辞: 只有 verdict 含 '5/5' 且含 'PASS' 才许写'已收口';
    否则=未收口, 卡在 = gates_failed 显式项 + awaiting 兜底 (chief 04:19 规则, 防假收口)."""
    v = str(verdict)
    if "5/5" in v and "PASS" in v.upper():
        return "5/5全过, 已收口"
    items = list(gates or [])
    if not items and isinstance(e, dict):
        aw = e.get("awaiting") or e.get("note") or ""
        if aw:
            items = ["见awaiting: " + str(aw)[:60]]
    return "未收口" + (", 卡在: " + "; ".join(str(g)[:40] for g in items[:3]) if items else "(gates_failed为空, 非5/5不计收口)")

def append_ledger(rec):
    try:
        d = json.load(open(LEDGER, encoding="utf-8"))
        if not isinstance(d, dict) or "entries" not in d:
            d = {"entries": []}
    except Exception:
        d = {"entries": []}
    d["entries"].append(rec)
    tmp = LEDGER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, LEDGER)

def append_ops_queue(rec):
    """运营同步钩子: 研发段结束(本脚本=段末投递) 追加一条给 ops-manager;
    ops-manager 侧自取脚本错峰 60-90s(错开研发高峰), 取完置 taken=ts。"""
    try:
        d = json.load(open(OPSQ, encoding="utf-8"))
        if not isinstance(d, dict) or "queue" not in d:
            d = {"queue": []}
    except Exception:
        d = {"queue": []}
    d["queue"].append(rec)
    if len(d["queue"]) > 200:
        d["queue"] = d["queue"][-200:]
    tmp = OPSQ + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OPSQ)

def main():
    key_arg = sys.argv[1] if len(sys.argv) > 1 else None
    theme, theme_cn, brief = pick_theme(key_arg)
    nxt, nxt_h, nxt_cn = next_theme()
    now = now_bjt()
    learn = [f for f, _ in learn_files_last7d()]
    hyp, verdict, gates, last_e = last_rd_verdict()

    rec = {
        "ts": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "bot": "strategy-rd",
        "theme": theme,
        "theme_cn": theme_cn,
        "brief": brief,
        "learn_files": list(learn),
        "candidate": hyp,
        "verdict": verdict,
        "p4_gap": closedout_wording(verdict, gates, last_e),
        "next_theme": f"{nxt_h}点 {nxt_cn}",
        "heartbeat": "alive",
        "degraded": False,
    }
    try:
        append_ledger(rec)
    except Exception as e:
        rec["degraded"] = True
        rec["ledger_err"] = str(e)[:120]
    ops = {
        "ts": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "from": "strategy-rd",
        "to": "ops-manager",
        "type": "sync_rd_segment",
        "theme": theme_cn,
        "new_candidate": hyp,
        "verdict": verdict,
        "p4_gap": rec["p4_gap"],
        "content_hooks": "档1内容排期(该主题最新证据1条+来源) + 对客物料更新 + 读者池标签",
        "stagger_hint": "研发高峰已过, 建议错开60-90s后取本条(ops_rd_sync.py 自取)",
        "taken": None,
    }
    try:
        append_ops_queue(ops)
    except Exception as e:
        rec["ops_err"] = str(e)[:120]

    lines = [f"[金策研发4h段报 {now.strftime('%H:%M')}] @strategy-rd 本段主题: {theme_cn}"]
    if learn:
        lines.append(f"- 研学蒸馏: 近7天落库 {len(learn)} 份: {', '.join(learn[:4])}" + (" …" if len(learn) > 4 else ""))
    else:
        lines.append("- 研学蒸馏: 本窗口无新落库文件(降级=沿用既有知识库, 不阻塞)")
    lines.append(f"- 候选: {hyp[:40]} 判定={verdict}")
    lines.append(f"- 离P4还差: {rec['p4_gap'][:60]}")
    lines.append(f"- 运营钩子: 已入队 (ops-manager 错峰自取, 内容排期/物料/读者池)")
    lines.append(f"- 下一段: {now.strftime('%m-%d')} {nxt_h}:00 {nxt_cn}")
    lines.append(f"- 心跳=alive rd_ledger_24h 已落盘[{'降级' if rec.get('degraded') else '正常'}]")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
