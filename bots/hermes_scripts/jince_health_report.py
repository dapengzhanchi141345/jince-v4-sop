#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策每日体检汇报 (no_agent 确定性, 0 LLM, 每日 08:45 投群):
读 03:00 全面深度体检的落盘结果 healthcheck_last.json, 出大白话汇报。
  全绿 -> 一行汇报(不打扰, 但留痕)
  有异常 -> 逐条点名 + 已自动修了哪些 + 哪些登记待续跑
  结果缺失/陈旧(>16h) -> 报警"今日 03:00 体检没跑, 系统可能卡了"
铁律: 任何失败都发声, 绝不静默; GBK 安全(纯汉字+ASCII, 无 emoji)。
"""
import os, json, datetime, zoneinfo

DATA = r"E:/GoldstrategyEngine/data"
HC = os.path.join(DATA, "healthcheck_last.json")
BJT = zoneinfo.ZoneInfo("Asia/Shanghai")


def main():
    now = datetime.datetime.now(BJT)
    if not os.path.exists(HC):
        print("【金策体检汇报】%s 找不到体检结果文件 %s, 03:00 体检可能没跑, 请总调度查" % (now.strftime("%m-%d %H:%M"), HC))
        return
    try:
        d = json.load(open(HC, encoding="utf-8"))
    except Exception as ex:
        print("【金策体检汇报】体检结果文件读不出(可能写坏): %s" % str(ex)[:100])
        return

    ts = str(d.get("ts", ""))
    # 新鲜度: 今天 03:00 的体检 ts 距今 <= 16h 才算数
    try:
        age_h = (now - datetime.datetime.fromisoformat(ts)).total_seconds() / 3600
        stale = age_h > 16
    except Exception:
        stale = True
    checks = d.get("checks", {})
    nodes = checks.get("nodes", [])
    bad_nodes = [n for n in nodes if isinstance(n, dict) and not n.get("ok")]
    fixed = d.get("auto_fixed") or []
    reg = d.get("registered_tasks") or []
    problems = []
    if stale:
        problems.append("体检结果缺失或太旧(ts=%s, 距今天 %s h) — 今日 03:00 体检没跑成" % (ts, int(age_h) if not stale else "?"))
    if not checks.get("cycle_heartbeat", {}).get("ok"):
        problems.append("全链心跳异常: " + str(checks.get("cycle_heartbeat", {}).get("detail", ""))[:60])
    if bad_nodes:
        problems.append("节点脚本异常 %d 项: %s" % (len(bad_nodes), ", ".join(n.get("name", "?") for n in bad_nodes)))
    if d.get("json_bad_after_autofix"):
        problems.append("自动修复后仍有坏 JSON: %s" % str(d.get("json_bad_after_autofix"))[:60])
    if d.get("archive_misfile_unhealed"):
        problems.append("错档文件未愈合: %s" % str(d.get("archive_misfile_unhealed"))[:60])
    if not checks.get("dashboard_gen", {}).get("ok"):
        problems.append("看板生成异常")

    head = "【金策体检汇报】体检时刻 %s" % ts[5:16].replace("T", " ") if ts else "【金策体检汇报】"
    if not problems:
        if reg:
            line = "%s 全部通过: 全链心跳正常 / 节点脚本 %d 项全绿 / 看板正常 / 自动修复 %d 项 / 待续跑 %d 项" % (
                head, len(nodes), len(fixed), len(reg))
            line += "; 待续跑: " + "; ".join(
                str(t.get("id", t))[:20] for t in reg[:3])
            print(line)  # 有待续跑项=非纯全绿, 照报
        else:
            # [11-14 瘦身] 纯全绿(无异常无待续跑) -> 静默, 本地留痕不投群
            try:
                import json as _j, os as _o
                _p = _o.path.join(_o.path.dirname(_o.path.abspath(__file__)), "health_report_silent_log.jsonl")
                with open(_p, "a", encoding="utf-8") as _f:
                    _f.write(_j.dumps({"ts": now.strftime("%F %T"), "all_green": True}, ensure_ascii=False) + "\n")
            except Exception:
                pass
        return
    print(head + " 发现 %d 项异常:" % len(problems))
    for p in problems:
        print("  · " + p)
    if fixed:
        print("  已自动修: " + "; ".join(str(x)[:40] for x in fixed[:5]))
    if reg:
        print("  登记待续跑: " + "; ".join(str(t.get("id", t))[:20] for t in reg[:5]))
    print("  处置: 异常项自动登记 task_ledger, 每30min续跑执行器接手; 卡死转人工投群。")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print("【金策体检汇报-脚本异常】%s" % str(ex)[:150])
