#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策·各学科网站 每日 22:30 进度通报 (no_agent 确定性, 0 LLM, 429-proof)
汇总 12 学科站: 首版状态/累计升级次数/最后升级日/掉队名单(连续2天未升级), 投群.
用法: python sites_daily_report.py   (stdout 投 bot-chat)
"""
import os, json, datetime, zoneinfo

SITES_DIR = r"E:/workbuddy/内容中心/网站/sites"
STATE = r"E:/workbuddy/内容中心/网站/进度台账/升级状态.json"
BJT = zoneinfo.ZoneInfo("Asia/Shanghai")

SLUGS = ["math","chinese","english","physics","chem","bio",
         "geo","history","morality","it","music","pe"]
CN = {"math":"数学","chinese":"语文","english":"英语","physics":"物理","chem":"化学","bio":"生物",
      "geo":"地理","history":"历史","morality":"道法","it":"信息科技","music":"音乐","pe":"体育"}

def load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}

def main():
    now = datetime.datetime.now(BJT)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    st = load_state()
    lines = [f"【网站进度通报 {today}】12 学科站:", ""]
    lagging = []
    for slug in SLUGS:
        p = os.path.join(SITES_DIR, slug + ".html")
        exists = os.path.exists(p)
        sz = os.path.getsize(p) if exists else 0
        rec = st.get(slug, {})
        cnt = rec.get("count", 0)
        last = rec.get("last", "-")
        # 掉队: 最后升级日早于昨天 且 有升级历史(首版完成但连续2天没升)
        if exists and cnt > 0 and last < yesterday:
            lagging.append(slug)
        mark = "✔" if exists else "✘"
        lines.append(f"  {mark} {CN[slug]:4s} | 首版={'已建' if exists else '未建'} | 累计升级 {cnt} | 最后 {last} | {sz//1024}KB")
    lines.append("")
    if lagging:
        lines.append(f"⚠ 掉队名单(连续≥2天未升级): {[CN[s] for s in lagging]} — 明日 07:30 优先补升级")
    else:
        lines.append("· 无掉队, 全部站均在规定节奏内")
    lines.append(f"· 闭环: 每日 07:30 自动升级(真改文件, 饱和站已加满不刷数) | 22:30 本通报 | 停摆=失职, 掉队连续2天点名")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
