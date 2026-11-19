#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""金策共同体自动取件哨 (hermes 收件箱, 每15min, 确定性 0 LLM, watchdog 静默模式)。

根治"消息躺收件箱等人问"卡壳:
- 0 新件 -> 无输出 (cron no_agent 空 stdout 不发任何东西, 静默)
- >0 新件 -> 逐件打印 主题+正文摘要 (经 cron 投递到群, 主 bot 当日处置)

取件源: E:\AgentCommons\bus\inbox\hermes\*.json (commons 消息)
去重态: jince_commons_pickup_seen.json (仅取件时更新, 0 新件不碰盘)
说明: drain 搬入 processed/ 的件已不在 inbox, 天然不重复; 未搬走的跨周期件靠 seen 去重。
历史回测≠未来收益。
"""
import json, os, re, time

INBOX = r"E:\AgentCommons\bus\inbox\hermes"
SEEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jince_commons_pickup_seen.json")


def main():
    seen = {}
    if os.path.exists(SEEN):
        try:
            seen = json.load(open(SEEN, encoding="utf-8"))
        except Exception:
            seen = {}

    fresh = []
    seen_subj_day = {}
    try:
        seen_subj_day = json.load(open(SEEN.replace("_seen.json", "_seen_subj.json"), encoding="utf-8"))
    except Exception:
        seen_subj_day = {}
    today_s = time.strftime("%F")
    if os.path.isdir(INBOX):
        for fn in sorted(os.listdir(INBOX)):
            if not fn.endswith(".json"):
                continue
            try:
                m = json.load(open(os.path.join(INBOX, fn), encoding="utf-8"))
            except Exception:
                continue
            mid = m.get("id") or fn
            if mid in seen:
                continue
            body = (m.get("body") or "").replace("\n", " ")
            # [11-14 瘦身] 周期重发去重: 同主题(去尾部时刻戳)同日已报过/已ACK -> 跳过(防V4.1十分钟3件刷对话); 换版本(主题变)照报
            subj_raw = m.get("subject", fn)
            # [11-14] 主题尾部时刻戳归一: "V4.1(现状优先) 07:40" / "做单思路 17 18" 两族格式都去尾, 防周期重发/整点拍刷屏
            subj_norm = re.sub(r"\s+\d{1,2}:\d{2}$", "", re.sub(r"\s+\d{1,2}\s+\d{2}$", "", subj_raw)).rstrip()
            subj_key = subj_norm + "|" + today_s
            if subj_key in seen_subj_day:
                seen[mid] = int(time.time())
                continue  # 同日同主题周期重发 -> 静默(首件已处置, 台账留痕)
            fresh.append((mid, m.get("from", "?"), subj_raw, body[:300]))
            seen[mid] = int(time.time())
            seen_subj_day[subj_key] = int(time.time())

    if not fresh:
        return  # 静默 (watchdog)

    # 仅取件时回写去重态, 且只留最近 500 条防膨胀
    for k in sorted(seen, key=seen.get, reverse=True)[500:]:
        del seen[k]
    json.dump(seen, open(SEEN, "w", encoding="utf-8"), ensure_ascii=False)
    for k in sorted(seen_subj_day, key=seen_subj_day.get, reverse=True)[100:]:
        del seen_subj_day[k]
    json.dump(seen_subj_day, open(SEEN.replace("_seen.json", "_seen_subj.json"), "w", encoding="utf-8"), ensure_ascii=False)

    print("[金策共同体·自动取件] hermes 收件箱新增 %d 件 (及时响应: 当日主链路处置, 不再滞留):" % len(fresh))
    for mid, frm, subj, body in fresh:
        print("· [%s] %s | %s" % (frm, mid, subj))
        print("  %s" % body)
    print("处置纪律: 策略类当日划重点给李彦明; CR/回执类当日补回执; 缺陷类进 23:00-06:00 调试窗口。")


if __name__ == "__main__":
    main()
