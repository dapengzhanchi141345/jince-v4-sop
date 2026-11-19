#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日晨报采集器（0 LLM，确定性）：把各数据源收成一份紧凑摘要打印到 stdout。
晨报哨兵 cron 用它当 script，agent 拿到 stdout 后组织成大白话早报。
数据源：金策体检/共享真值/事件日历/任务台账/状态卡 + AgentCommons 未读收件箱。
任何源缺失/过旧 → 标 [缺失] 不编数，agent 照实报。"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta

BJT = timezone(timedelta(hours=8))
HERE = os.path.dirname(os.path.abspath(__file__))

JINCE_DATA = r"E:\GoldstrategyEngine\data"
LIVE_STATE = r"E:\AgentCommons\shared\live_state.json"
STATE_CARD = r"E:\workbuddy\金策宗师团\金策宗师团_当前状态卡.md"
INBOX = r"E:\AgentCommons\bus\inbox\hermes"

STALE_MIN = 30  # 共享真值 30min 口径


def now_bjt():
    return datetime.now(BJT)


def age_str(path):
    try:
        m = os.path.getmtime(path)
        mins = (time.time() - m) / 60
        return mins
    except OSError:
        return None


def section(title, lines):
    out = [f"## {title}"]
    out.extend(lines if lines else ["- （无数据）"])
    return "\n".join(out)


def main():
    ts = now_bjt().strftime("%Y-%m-%d %H:%M BJT")
    print(f"# 晨报原料 {ts}\n")

    # 1) 金策共享真值 live_state（净值/余额/持仓数，超 30min 标过期）
    ls_lines = []
    try:
        with open(LIVE_STATE, encoding="utf-8") as f:
            ls = json.load(f)
        age_min = (time.time() - float(ls.get("ts_unix") or 0)) / 60
        fresh = age_min <= STALE_MIN
        acc = ls.get("account") or {}
        pos = ls.get("positions") or []
        od = ls.get("orders") or []
        ls_lines.append(
            f"- 净值={acc.get('equity')} 余额={acc.get('balance')} 持仓={len(pos)} 挂单={len(od)}（{ls.get('ts','?')}，写侧 {ls.get('writer','?')}）"
            + ("" if fresh else f"  ⚠已{int(age_min)}min未更新(超{STALE_MIN}min口径=过期, 报数前须先跑 snapshot --shared)")
        )
    except Exception as e:
        ls_lines.append(f"- [缺失] live_state 读不出: {e}")
    print(section("金策·账户", ls_lines) + "\n")

    # 2) 金策每日体检（03:00 结果）
    hc_lines = []
    hc = os.path.join(JINCE_DATA, "healthcheck_last.json")
    try:
        with open(hc, encoding="utf-8") as f:
            h = json.load(f)
        checks = h.get("checks") or {}
        nodes = checks.get("nodes") if isinstance(checks, dict) else checks
        if isinstance(nodes, dict):
            nodes = [nodes]
        bad = []
        if isinstance(checks, dict):
            for k, v in checks.items():
                if isinstance(v, dict) and "ok" in v and not v.get("ok"):
                    bad.append(f"{k}({str(v.get('detail',''))[:40]})")
        for n in nodes or []:
            if isinstance(n, dict) and not n.get("ok", True):
                bad.append(f"{n.get('name')}({n.get('detail','')[:40]})")
        auto = h.get("auto_fixed") or []
        verdict = "全绿" if not bad else f"异常{len(bad)}项"
        hc_lines.append(f"- 体检判定={verdict}（{h.get('ts','?')}，节点 {len(nodes or [])} 个）")
        for b in bad[:6]:
            hc_lines.append(f"- ✗ {b}")
        if auto:
            hc_lines.append(f"- 已自修: {len(auto)} 件")
    except Exception as e:
        hc_lines.append(f"- [缺失] 体检结果读不出: {e}（可能 03:00 没跑）")
    print(section("金策·体检", hc_lines) + "\n")

    # 3) 今明事件日历（CPI/NFP 等冻结窗）
    ev_lines = []
    ev = os.path.join(JINCE_DATA, "event_calendar.json")
    try:
        with open(ev, encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("events") or data.get("windows") or (data if isinstance(data, list) else [])
        day = now_bjt().strftime("%Y-%m-%d")
        tom = now_bjt().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        pick = []
        for it in items:
            if not isinstance(it, dict):
                continue
            t = str(it.get("time") or it.get("date") or "")
            lvl = str(it.get("level") or it.get("impact") or "")
            name = str(it.get("name") or it.get("event") or t)
            if t[:10] in (day, tom.strftime("%Y-%m-%d")) and t[:10] != "":
                pick.append(f"{t} {name} {lvl}".strip())
        ev_lines.extend(f"- {p}" for p in pick[:8]) or ev_lines.append("- 今明无高冲击事件")
    except Exception as e:
        ev_lines.append(f"- [缺失] 事件日历读不出: {e}")
    print(section("今明·事件窗", ev_lines) + "\n")

    # 4) 任务台账未结（open/partial 计数 + 头部 5 条）
    tl_lines = []
    tl = os.path.join(JINCE_DATA, "task_ledger.json")
    try:
        with open(tl, encoding="utf-8") as f:
            tasks = json.load(f)
        tasks = tasks.get("tasks") if isinstance(tasks, dict) else tasks
        open_t = [t for t in tasks if isinstance(t, dict) and (t.get("status") in ("open", "partial", "blocked_due"))]
        tl_lines.append(f"- 未结任务 {len(open_t)} 条 / 台账总数 {len(tasks)}")
        for t in open_t[:5]:
            tl_lines.append(f"  · {t.get('id')} [{t.get('status')}] {str(t.get('note') or t.get('title') or '')[:60]}")
    except Exception as e:
        tl_lines.append(f"- [缺失] 任务台账读不出: {e}")
    print(section("金策·任务台账", tl_lines) + "\n")

    # 5) 状态卡最新条目（金策现状一句话）
    sc_lines = []
    try:
        with open(STATE_CARD, encoding="utf-8") as f:
            card = f.read()
        heads = re.findall(r"^## .+$", card, flags=re.M)
        sc_lines.append(f"- 状态卡最新节: {heads[0] if heads else '未知'}")
        # 最新净值现状行
        m = re.findall(r"净值现状[^；\n]{0,120}", card)
        if m:
            sc_lines.append(f"- 最近净值口径: {m[0][:120]}")
    except Exception as e:
        sc_lines.append(f"- [缺失] 状态卡读不出: {e}")
    print(section("金策·状态卡", sc_lines) + "\n")

    # 6) AgentCommons 未读收件箱（三方总调）
    ib_lines = []
    try:
        entries = [n for n in os.listdir(INBOX) if n != "processed" and not n.startswith(".")]
        ib_lines.append(f"- hermes 未读件 {len(entries)}")
        for n in entries[:5]:
            ib_lines.append(f"  · {n}")
    except Exception as e:
        ib_lines.append(f"- [缺失] 收件箱读不出: {e}")
    print(section("共同体·收件箱", ib_lines) + "\n")

    # 7) 邮件（独立脚本，未接入/失败只出一行不崩）
    try:
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "mail_collect.py")],
            capture_output=True, text=True, timeout=60)
        mail_out = (r.stdout or "").strip() or "- 邮件连接器：脚本无输出"
    except Exception as e:
        mail_out = f"- [缺失] 邮件采集脚本跑不出: {e}"
    print("## 邮件\n" + mail_out)


if __name__ == "__main__":
    main()
