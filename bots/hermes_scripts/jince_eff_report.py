#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策 2h 效率播报生成器 (no_agent L0, 0 LLM, 429-proof)
按监工计划第五节格式, 扫各台账/auto_cycle.log/rd_ledger_24h, 一页可扫投群 1 条:
  [金策效率播报 HH:mm]
  - 研发 / 运营 / 交易 / 睡眠检测 / 下一段
数据源(全在 E:\\GoldstrategyEngine\\data, 只读):
  auto_cycle.log            chief 30min 全链心跳(最后一条'全链自动运行完成'时刻)
  rd_ledger_24h.json        研发 4h 段心跳(最新条 ts/主题/候选/判定/离P4)
  ops_sync_queue.json       运营同步钩子队列(未取条数)
  veto_log.json             risk-officer 事件驱动留痕
  network_probe_last.json   看门狗自身心跳(gateway/mt5/extnet)
fail-open: 任何源缺失 → 该行标'缺(降级)', 不崩, 播报照发(台账本身=心跳留痕)。
"""
import os, json, time, datetime, zoneinfo

DATA = r"E:/GoldstrategyEngine/data"
BJT = zoneinfo.ZoneInfo("Asia/Shanghai")

ROUTES = [("04", "趋势CTA"), ("08", "动量"), ("12", "事件驱动"),
          ("16", "统计套利"), ("20", "资金费率·波动率陷阱")]

def last_cycle_ts():
    """auto_cycle.log 最后一行完成时刻(格式: '[全链自动运行完成] YYYY-MM-DD HH:MM:SS')"""
    p = os.path.join(DATA, "auto_cycle.log")
    last = None
    try:
        with open(p, encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "全链自动运行完成" in line:
                    last = line.strip()
    except Exception:
        return None
    return last

def last_line_kw(path, kw, n=4):
    p = os.path.join(DATA, path)
    out, tries = [], 0
    try:
        with open(p, encoding="utf-8", errors="ignore") as f:
            for line in f:
                if kw in line:
                    out.append(line.strip()[-200:])
                    tries += 1
                    if tries >= n:
                        break
    except Exception:
        return None
    return out or None

def last_ledger24():
    p = os.path.join(DATA, "rd_ledger_24h.json")
    try:
        d = json.load(open(p, encoding="utf-8"))
        es = d.get("entries", [])
        return es[-1] if es else None
    except Exception:
        return None

def ops_pending():
    p = os.path.join(DATA, "ops_sync_queue.json")
    try:
        d = json.load(open(p, encoding="utf-8"))
        q = [x for x in d.get("queue", []) if not x.get("taken")]
        if not q:
            return 0, None
        return len(q), q[-1]
    except Exception:
        return None, None

def last_veto_ts():
    """veto_log.json: 最后动作时刻(bot 是否活的佐证, 事件驱动)"""
    p = os.path.join(DATA, "veto_log.json")
    try:
        d = json.load(open(p, encoding="utf-8"))
        items = d if isinstance(d, list) else d.get("entries", [])
        if not items:
            return None
        e = items[-1]
        return e.get("ts") or e.get("time") or e.get("beijing")
    except Exception:
        return None

def probe():
    try:
        d = json.load(open(os.path.join(DATA, "network_probe_last.json"), encoding="utf-8"))
        return d
    except Exception:
        return {}

def next_segment():
    h = datetime.datetime.now(BJT).hour
    for hh, cn in ROUTES:
        if h < int(hh):
            return f"{hh}:00 {cn}"
    return "明日 04:00 趋势CTA"

def main():
    now = datetime.datetime.now(BJT)
    hm = now.strftime("%H:%M")
    lines = [f"[金策效率播报 {hm}]"]

    # 研发
    rd = last_ledger24()
    if rd:
        lines.append(f"- 研发: 本段学{rd.get('theme_cn', rd.get('theme', '?'))} 新增<{str(rd.get('candidate', '?'))[:26]} 判定={rd.get('verdict', '?')} 离P4:{str(rd.get('p4_gap', '?'))[:30]} (心跳 {str(rd.get('ts'))[11:16]})")
    else:
        lines.append("- 研发: 台账缺(降级=未见 rd_ledger_24h 条目)")

    # 运营
    pend, lastops = ops_pending()
    if pend == 0:
        lines.append("- 运营: 队列空(全部已同步)")
    elif pend is None:
        lines.append("- 运营: 台账缺(降级)")
    else:
        lines.append(f"- 运营: 待同步 {pend} 条(最新: {lastops.get('theme', '?')} @{str(lastops.get('ts'))[11:16]})")

    # 交易
    cyc = last_cycle_ts()
    if cyc:
        lines.append(f"- 交易: 全链绿 | chief 30min心跳最后: {cyc.split(']')[-1].strip()}")
    else:
        lines.append("- 交易: 全链心跳缺(降级=auto_cycle.log 未见完成行, 查 chief/gateway)")
    vt = last_veto_ts()
    if vt:
        lines.append(f"- 风控: 最后动作 {str(vt)[:16]} (事件驱动, 无轮转=正常)")

    # 睡眠检测
    pr = probe()
    sleepbit = f"gateway={pr.get('gateway', '?')[:18]} mt5={str(pr.get('mt5', '?'))[:24]}"
    lines.append(f"- 睡眠检测: 看门狗心跳 {pr.get('ts', '?')} | {sleepbit} | 超时点名见【看门狗】消息")

    # 下一段
    lines.append(f"- 下一段: {next_segment()}")

    # [11-13 深度优化·防刷屏] 全绿稳态=静默拍(标记行被吞不投群), 仅新事件投群:
    # 研发判定翻APPROVE / 运营队列有新增 / 全链心跳缺失 / 探活源缺失
    silent_ok = (
        rd is not None and str(rd.get("verdict", "?")) != "APPROVE"
        and pend == 0
        and cyc is not None
        and bool(pr)
    )
    if silent_ok:
        # [11-13 瘦身三刀] 标记行不投群(空stdout真静默), 留痕本地jsonl
        import os as _os_e
        try:
            with open(_os_e.path.join(DATA, "eff_ok_log.jsonl"), "a", encoding="utf-8") as _f:
                _f.write(json.dumps({"ts": hm, "kind": "all_green"}, ensure_ascii=False) + "\n")
        except Exception:
            pass
        return
    print("\n".join(lines))

if __name__ == "__main__":
    main()
