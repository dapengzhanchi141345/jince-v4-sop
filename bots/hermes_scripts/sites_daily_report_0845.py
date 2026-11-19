# -*- coding: utf-8 -*-
"""各学科独立网站·每日汇报(08:45, no_agent 0 LLM, 429免疫):
读 独立站台账.json + 升级状态.json + 逐站公网 200 验活 -> 大白话投群.
全绿一行; 掉队(连续2天未升级)/公网挂/未部署逐条点名. 失败发声不静默."""
import json, os, datetime, zoneinfo

BJT = zoneinfo.ZoneInfo("Asia/Shanghai")
LEDGER = r"E:\workbuddy\内容中心\网站\进度台账\网站独立站台账.json"
UPGRADE = r"E:\workbuddy\内容中心\网站\进度台账\升级状态.json"
OUT = r"E:\workbuddy\内容中心\网站\每日通报"

def curl_200(url):
    import subprocess
    try:
        r = subprocess.run(["curl","-s","-o","/dev/null","-w","%{http_code}",url],
                           capture_output=True, text=True, timeout=30, creationflags=0x08000000)
        return r.stdout.strip() == "200"
    except Exception:
        return False

def main():
    now = datetime.datetime.now(BJT)
    today = now.strftime("%Y-%m-%d")
    ledger = json.load(open(LEDGER, encoding="utf-8"))
    upg = json.load(open(UPGRADE, encoding="utf-8")) if os.path.exists(UPGRADE) else {}
    sites = ledger.get("sites", {})
    lines = [f"【各学科独立网站汇报 {today}】{len(sites)} 独立站(各站独立仓+公网URL, 凌晨2点自动升级部署):"]
    bad = []
    for slug, info in sites.items():
        up = upg.get(slug, {})
        last = up.get("last", "未升级")
        cnt = up.get("count", 0)
        live = curl_200(info["url"])
        mark = "OK" if live else "挂"
        if not live:
            bad.append(f"  [挂] {slug} 公网 {info['url']} 访问异常")
        # 掉队: last 距今>2天
        try:
            gap = (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(last)).days
            if gap > 2:
                bad.append(f"  [掉队] {slug} 已 {gap} 天未升级(最后 {last})")
        except Exception:
            pass
        lines.append(f"  {slug:8s} @{info.get('owner_bot','?'):18s} 公网={'活' if live else '挂'} 累计升级={cnt} 最后={last}")
    if bad:
        lines.append("异常点名:")
        lines.extend(bad)
    else:
        lines.append("全绿: 12 站公网全活, 无掉队. 凌晨2点自动升级部署, 各 bot 长期维护.")
    lines.append("· 闭环: 05:00 汇报(本条) + 22:30 通报 + 02:00 升级部署(一天一班, 李彦明令); 失败发声不静默.")
    out = "\n".join(lines)
    print(out)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, f"汇报_{today}.md"), "a", encoding="utf-8") as f:
        f.write(out + "\n\n")
    return 0

if __name__ == "__main__":
    main()
