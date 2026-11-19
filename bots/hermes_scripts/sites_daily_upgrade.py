#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策·各学科网站 每日升级 (no_agent 确定性, 0 LLM, 429-proof)
每日 07:30 跑: 给 12 个学科站各追加 1 个增量(题库/知识点/公式), 升级日志留痕.
增量规则: 从内置题库池取当天"未用"的一条追加到该站 HTML 对应容器, 标记当日已升级.
升级判定: 只有真改了文件(追加了内容)才算升级, 改不动/已加满的写"已饱和"不算.
用法: python sites_daily_upgrade.py   (Hermes cron no_agent 调, stdout 投 bot-chat)
"""
import os, json, datetime, zoneinfo

SITES_DIR = r"E:/workbuddy/内容中心/网站/sites"
LOG_DIR = r"E:/workbuddy/内容中心/网站/升级日志"
STATE = r"E:/workbuddy/内容中心/网站/进度台账/升级状态.json"
BJT = zoneinfo.ZoneInfo("Asia/Shanghai")

def _load_pool(slug):
    """[2026-10-09] 增量池改池文件: 优先读 增量池/<slug>.jsonl (每行一条), 无则用内置 UPGRADES 兜底"""
    pool_file = os.path.join(r"E:/workbuddy/内容中心/网站/增量池", slug + ".jsonl")
    if os.path.exists(pool_file):
        lines = [l.strip() for l in open(pool_file, encoding="utf-8") if l.strip()]
        if lines:
            return lines
    return list(UPGRADES.get(slug, []))

# 每个站点一个增量池(题库条目, 追加进该站对应 <div class="card"> 题组后)
# 池文件优先: 增量池/<slug>.jsonl 每行一条 (14条/站, 池用满自动续); 无池文件用下面内置兜底
# [2026-10-09] 池从内置 2 条扩到池文件 14 条: 饱和周期 2 天 -> 2 周, 永不停不断粮
UPGRADES = {
  "math": [
    "【练习+%d】竞赛题: 1/(1×2)+1/(2×3)+…+1/(n(n+1)) = ? (裂项相消 = n/(n+1))",
    "【练习+%d】易错题: 已知 a+b=5, ab=6, 求 a³+b³ = ? (a³+b³=(a+b)³-3ab(a+b)=49)",
  ],
  "chinese": [
    "【默写+%d】《观书有感》朱熹: 问渠那得清如许? 为有源头活水来。",
    "【病句+%d】'我们要克服工作中的缺点' 搭配不当, 应'改正缺点'。",
  ],
  "english": [
    "【词汇+%d】resilient 有韧性的 / 能很快复原的 (adv. resiliency)",
    "【语法+%d】It is I who am to blame. (强调句, 动词与 I 一致用 am)",
  ],
  "physics": [
    "【公式+%d】向心力 F = mv²/r = mω²r (方向指向圆心, 不是一种新的力)",
    "【实验+%d】单摆测 g: T=2π√(L/g), 摆长从悬点到球心",
  ],
  "chem": [
    "【配平+%d】4 P + 5 O₂ → 2 P₂O₅ (磷燃烧, 固体+气体=固体)",
    "【计算+%d】CO₂ 通入 NaOH: CO₂+2NaOH→Na₂CO₃+H₂O (过量生成 NaHCO₃)",
  ],
  "bio": [
    "【概念+%d】基因 = 有遗传效应的 DNA 片段 (不是任意 DNA 片段)",
    "【遗传+%d】伴 X 隐性: 母病子必病, 女病父必病 (如色盲)",
  ],
  "geo": [
    "【判读+%d】等压线: 气旋=中心低(低压, 多雨), 反气旋=中心高(高压, 晴)",
    "【计算+%d】地方时: 经度差 1° 时间差 4 分钟, 东加西减",
  ],
  "history": [
    "【史料+%d】'贞观'是唐太宗年号; '开元'是唐玄宗年号 (别混)",
    "【时间+%d】秦统一=前221; 西汉=前202; 东汉=25; 三国=220(曹丕代汉)",
  ],
  "morality": [
    "【案例+%d】权利与义务统一: 行使权利不得损害他人/社会/国家利益",
    "【法条+%d】《民法典》18 周岁为成年; 8 周岁以上未成年为限制民事行为能力人",
  ],
  "it": [
    "【代码+%d】递归求阶乘: fact(n)=n*fact(n-1), fact(0)=1 (必须写终止条件)",
    "【进制+%d】二进制 1111₁₀=15; 十六进制 FF=255 (每 4 位二进制一个 16 进制位)",
  ],
  "music": [
    "【乐理+%d】大调音阶全全半全全全半; 小调(自然)全半全全半全全",
    "【聆听+%d】莫扎特《小星星变奏曲》= 单主题+30 段变奏 (变奏曲式)",
  ],
  "pe": [
    "【体测+%d】引体向上: 初中满分标准参考体质健康标准 (非固定值, 查年级)",
    "【养生+%d】太极: 青少年练太极练平衡与协调, 不追求高难度招式",
  ],
}

def day_int():
    return int(datetime.datetime.now(BJT).strftime("%Y%m%d"))

def load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}

def save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

def upgrade_site(slug, today_str, day_int, st):
    path = os.path.join(SITES_DIR, slug + ".html")
    if not os.path.exists(path):
        return f"[缺] {slug}.html 不存在, 跳过"
    pool = _load_pool(slug)  # [2026-10-09] 池文件优先(14条), 无则内置兜底(2条)
    if not pool:
        return f"[饱和] {slug} 无增量池, 今日不升级"
    html = open(path, encoding="utf-8").read()
    # [2026-10-09 修饱和bug] 原逻辑只试 idx 和 idx+1 两条就报"饱和", 池2条时次日全轮空.
    # 现: 全池遍历, 找到第一条"没加进过"的条目就追加; 全部加过才报饱和. 池文件14条 -> 饱和周期拉到2周.
    idx = day_int % len(pool)  # 按日期取模定起点, 保证每日不同
    picked = None
    for off in range(len(pool)):
        cand = pool[(idx + off) % len(pool)].replace("%d", str(today_str))
        key = cand.split("】", 1)[-1][:20]
        if key not in html:
            picked = cand
            break
    if picked is None:
        return f"[饱和] {slug} 增量池已全用完({len(pool)}条), 需扩池(往 增量池/{slug}.jsonl 加行)"
    # 追加到 body 末尾(footer 之前)
    insert = f'\n<div style="background:#fffbe6;border-left:4px solid #f5a623;padding:10px;margin:12px 0;font-size:14px">📅 {today_str} 升级 · {picked}</div>\n'
    footer_tag = "</footer>"
    if footer_tag in html:
        html = html.replace(footer_tag, insert + footer_tag, 1)
    else:
        html = html.replace("</body>", insert + "</body>", 1)
    open(path, "w", encoding="utf-8").write(html)
    st.setdefault(slug, {"count": 0, "last": ""})
    st[slug]["count"] += 1
    st[slug]["last"] = today_str
    return f"[升级] {slug}: 已追加 {picked[:30]}..."

def main():
    now = datetime.datetime.now(BJT)
    today_str = now.strftime("%Y-%m-%d")
    day_int = int(now.strftime("%Y%m%d"))
    st = load_state()
    os.makedirs(LOG_DIR, exist_ok=True)
    lines = [f"【网站每日升级 {today_str}】12 学科站自动增量:"]
    upgraded = 0
    for slug in UPGRADES:
        r = upgrade_site(slug, today_str, day_int, st)
        lines.append(f"  {r}")
        if r.startswith("[升级]"):
            upgraded += 1
    save_state(st)
    lines.append(f"· 共升级 {upgraded}/{len(UPGRADES)} 站 (升级=真改文件, 防刷数; 饱和站已加满)")
    lines.append(f"· 闭环: 夜窗 02:00 一班自动升级+部署(李彦明 2026-10-09 令: 升级部署一天只跑一次, 04:00 重复班已停; 任务全收 22:00–05:00, 白天零负载); 05:00 独立站汇报; 增量池在 增量池/<slug>.jsonl, 饱和报'[全用完]'就往里加行; 升级≠未来, 增量以真改动为准")
    out = "\n".join(lines)
    print(out)
    # 落升级日志
    try:
        with open(os.path.join(LOG_DIR, f"升级日志_{today_str}.md"), "a", encoding="utf-8") as f:
            f.write(out + "\n")
    except Exception as e:
        print(f"[warn] 升级日志写失败: {e}")

if __name__ == "__main__":
    main()
