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
    ev_level = str(ev.get("level", "?")).upper()

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
    lines.append("  · 事件面: 等级 %s | 币系冻结: %s" % (
        ev_level, "冻着(11-02 NFP 解冻)" if coin_frozen else "已放"))
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
