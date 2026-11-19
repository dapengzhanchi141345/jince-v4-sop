#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策群主持·到点带节奏 (no_agent 确定性, 0 LLM, 429-proof):
治"群太安静没人主持"——到点出一条有节奏的主持人点评(大白话):
  接住刚发生的事 + 点名各 bot 在干啥 + 预告下一场 + 一句提醒。
数据全只读(0 写 0 下单): risk_state / auto_cycle.log / event_risk /
  discussion_log / 看板快照 / 冻结闸。
时段: 白天热闹时段才发声, 深夜静默(no_agent 空 stdout=不发):
  发声时刻表=09:00 11:00 14:00 16:00 19:00 21:00 (cron 控制),
  脚本内再加一道窗口闸: 08:30-22:30 外一律静默(防误触发)。
防刷屏: 同一小时已出过主持(读 data/_host_last_hh.json)则静默。
"""
import os, json, datetime, zoneinfo

DATA = r"E:\GoldstrategyEngine\data"
BJT = zoneinfo.ZoneInfo("Asia/Shanghai")


def read_json(name, default=None):
    try:
        return json.load(open(os.path.join(DATA, name), encoding="utf-8"))
    except Exception:
        return default


def main():
    now = datetime.datetime.now(BJT)
    hm = now.strftime("%H:%M")
    # 窗口闸: 只有白天时段发声
    if not (now.strftime("%H:%M") >= "08:30" and now.strftime("%H:%M") <= "22:30"):
        return

    # 防刷屏: 同小时只出一条
    hmark = os.path.join(DATA, "_host_last_hh.json")
    hh = now.strftime("%Y-%m-%d %H")
    try:
        if json.load(open(hmark, encoding="utf-8")).get("hh") == hh:
            return
    except Exception:
        pass
    json.dump({"hh": hh, "sent_at": hm}, open(hmark, "w", encoding="utf-8"))

    rs = read_json("risk_state.json", {}) or {}
    ev = read_json("event_risk.json", {}) or {}
    freeze = read_json("crypto_freeze_gate.json", {}) or {}
    ev_level = str(ev.get("level", "?")).upper()

    # 全链心跳
    cycle_ts, ok_line = None, "全链心跳未见(查 chief 30min)"
    try:
        with open(os.path.join(DATA, "auto_cycle.log"), encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "全链自动运行完成" in line:
                    cycle_ts = line.strip().split("]")[-1].strip()
    except Exception:
        pass
    if cycle_ts:
        ok_line = "全链刚跑完(%s), 系统活着" % cycle_ts

    heat = rs.get("heat") or {}
    dd = (rs.get("drawdown_brake_scale") or {}).get("dd_pct")
    consec = rs.get("consec_losses", 0)
    coin_frozen = bool((freeze or {}).get("active") or (rs.get("coin_freeze") or {}).get("active"))
    # [2026-11-12 币系口径根治] 主持拍"币系冻结"行改读巡检实时mt5 trade_mode落盘结论(30min新鲜度),
    # 不再读静态crypto_freeze_gate.json(我方闸老值) — 11-12上午"已放"误报42连报实证后根治
    coin_broker_line = "未证实(巡检数据缺)"
    try:
        _cst = read_json("coin_tm_state.json", {}) or {}
        _cts = (_cst.get("ts") or "")
        _cage = 0
        if _cts:
            try:
                _cage = (datetime.datetime.now(BJT) - datetime.datetime.strptime(_cts, "%F %T")).total_seconds()
            except Exception:
                _cage = 9999
        if _cst.get("closed_only") and _cage < 1800:
            _tms = _cst.get("trade_mode") or {}
            coin_broker_line = "close-only(tm=%s, %s)" % (",".join(str(v) for v in _tms.values()) or "?", _cts)
        elif _cst and _cage < 1800:
            coin_broker_line = "已放(tm=1, %s)" % _cts
    except Exception:
        pass
    ev_level = str(ev.get("level", "?")).upper()

    # [2026-10-16 L5 焊点] 事件 tier 自动判级 (喂 chief 22:00 日报):
    #   L5 判据段在独立闸源 event_tier_gate.json (30min 循环只重写 event_risk.json 事件态, 判据段不再被冲).
    #   窗口外 tier_info 留空 = 日报行原样, 不啰嗦; 只否决/降档提示, 0 正向提权 0 开单.
    tier_info = ""
    try:
        gt = read_json("event_tier_gate.json", {}) or {}
        _now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        for w in gt.get("active_windows", []):
            pub = float(w.get("pub_utc", 0))
            if pub <= 0:
                continue
            post_until = pub + w.get("post_watch_min", 30) * 60
            if pub <= _now < post_until:
                # 发布后观察段: 只在闸源里记 post-watch 状态, 群消息不刷停仓提示 (人工/风控核认前不动)
                continue
            if _now >= post_until:
                # 观察段已过: 回常规档, 静默
                continue
            if _now >= pub - w.get("pre_scale0_min", 60) * 60:
                tier_info = " | S级全停档(scale=0, FOMC决议约%.1fh后)" % (max(0.0, (pub - _now) / 3600.0))
            elif _now >= pub - w.get("pre_halt_min", 360) * 60:
                tier_info = " | S级已停开新仓(FOMC决议约%.1fh后)" % ((pub - _now) / 3600.0)
            elif 0 < (pub - _now) <= 48 * 3600:
                tier_info = " | S级FOMC 48h内(按闸源: BJT 10-28 16:00停新仓/23:00全停)"
    except Exception:
        tier_info = ""

    # 主持语料(按小时带节奏, 不重复台词)
    hour = now.hour
    if hour < 12:
        open_line = "上午场: 东京盘口刚过, 现在盯的是伦敦开评前的准备"
        next_line = "下一场 15:05 伦敦开评 + 13:45 全链扫描, 有变化我会第一时间喊"
    elif hour < 15:
        open_line = "午后场: 伦敦盘口在走, 重点看欧美重叠前的方向"
        next_line = "下一场 18:05 伦敦对账, 我带着各 bot 的留痕对一遍"
    elif hour < 18:
        open_line = "傍晚场: 伦敦收口前, 看今天对账胜率回填"
        next_line = "下一场 21:05 美盘开评 + 21:30 学习进化汇报, 一天里最热闹的两场"
    else:
        open_line = "晚间场: 美盘时段, 全系统盯得最紧"
        next_line = "22:00 事件日报收口, 明天 03:00 体检 + 08:45 汇报接着走"

    lines = ["【金策主持 %s】%s" % (hm, open_line)]
    lines.append("  · 系统: %s | 净值回撤 %s%% | 连亏 %d 笔" % (
        ok_line, (dd if dd is not None else "稳"), consec))
    lines.append("  · 事件面: 等级 %s | 币系(broker实读): %s%s" % (
        ev_level, coin_broker_line, tier_info))
    lines.append("  · 风控官: 新单双闸照查, 有 D 级否决继续拦; 研发部: 样本攒着, 过五验才放行")
    lines.append("  · %s" % next_line)
    lines.append("  · 有异常我会点名, 全绿就不唠叨; 您想问啥直接 @我")
    print("\n".join(lines))


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        # 护栏: 异常也发声
        print("【金策主持-脚本异常】%s" % str(ex)[:120])
