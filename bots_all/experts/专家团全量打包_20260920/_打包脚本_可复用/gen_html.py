# -*- coding: utf-8 -*-
"""根据元数据生成 03_专家团全景学习手册.html（深色主题可视化手册）。"""
import json, os, html

BASE = r"E:\workbuddy\专家团\专家团全量打包_20260920"
d = json.load(open(os.path.join(BASE, "05_专家元数据.json"), encoding="utf-8"))
m = {e["dir"]: e for e in d["experts"]}

GROUPS = [
    ("🧬 学科教学主团", "#7dd3fc", [
        ("bio-master", "生物"), ("chem-master", "化学"), ("chinese-master", "语文"),
        ("english-master", "英语"), ("geo-master", "地理"), ("history-master", "历史"),
        ("morality-master", "道法"), ("math-all-domain", "数学"),
        ("physics-omnibus", "物理"), ("it-edu-team", "信息科技"),
    ]),
    ("✅ 阅卷评分官", "#86efac", [
        ("bio-grader", "生物"), ("chem-grader", "化学"), ("chi-grader", "语文"),
        ("eng-grader", "英语"), ("geo-grader", "地理"), ("his-grader", "历史"),
        ("mor-grader", "道法"), ("math-grader", "数学"),
        ("physics-grader", "物理"), ("it-grader", "信息科技"),
    ]),
    ("🔬 学科辅助与专项", "#c4b5fd", [
        ("bio-basics", "生物·基础"), ("bio-pro", "生物·进阶"),
        ("bio-frontier", "生物·前沿"), ("color-design-master", "配色设计"),
    ]),
    ("🀄 玄学命理", "#fca5a5", [("tianji-ge", "天机阁"), ("bazi-calculator", "命理排盘师")]),
    ("⚕️ 医疗健康", "#5eead4", [("qihuang-medical", "岐黄医典")]),
    ("💹 财会与金融", "#fcd34d", [
        ("suan-jing-ge", "算经阁"), ("goldstrategy-guild", "金策宗师团"),
        ("mt5-ea-expert", "MT5 EA 编程"),
    ]),
    ("🏫 教育行政与教科研", "#93c5fd", [
        ("education-admin", "教务智能体"), ("teacher-promotion-filling", "青云梯"),
        ("gewu-zhidao", "科研智库"),
    ]),
    ("🎓 考研与教育IP", "#f9a8d4", [
        ("yan-shu-kaoyan", "研枢考研"), ("jiao-lian-zhong-shu", "教联中枢"),
    ]),
    ("🎬 媒体创作与娱乐", "#fdba74", [
        ("video-crew", "视频创作团"), ("music-craft-studio", "音律工坊"),
        ("yimou-pavilion", "弈谋阁"), ("ebook-to-movie", "电子书转电影"),
    ]),
]

TYPE_BADGE = {"team": ("团队", "#38bdf8"), "agent": ("单体", "#a78bfa")}


def esc(s):
    return html.escape(str(s)) if s else ""


cards_html = []
for title, color, items in GROUPS:
    inner = []
    for slug, label in items:
        e = m.get(slug)
        if not e:
            continue
        tname, tcolor = TYPE_BADGE.get(e.get("expertType"), ("未知", "#94a3b8"))
        tags = "".join(
            f'<span class="tag">{esc(t)}</span>' for t in (e.get("tags_zh") or []) if t
        )
        mems = "".join(
            f'<span class="mem{" lead" if mm.get("role")=="lead" else ""}">'
            f'{esc(mm.get("name_zh"))}<i>{esc(mm.get("profession_zh") or "")}</i></span>'
            for mm in (e.get("members") or [])
        )
        mem_block = f'<div class="mems">{mems}</div>' if mems else ""
        cards_html.append(f'''
      <div class="card">
        <div class="card-head">
          <span class="dot" style="background:{color}"></span>
          <span class="name">{esc(e['displayName_zh'])}</span>
          <span class="badge" style="color:{tcolor};border-color:{tcolor}55">{tname}</span>
        </div>
        <div class="slug">{esc(e['dir'])} <em>v{esc(e['version'] or '-')}</em> · {e['agentCount']} 子代理 · {esc(e['sizeHuman'])}</div>
        <div class="desc">{esc(e.get('oneLine_zh') or '')}</div>
        <div class="tags">{tags}</div>
        {mem_block}
      </div>''')

route_rows = ""
ROUTE = [
    ("生物", "万物生", "生阅卷"), ("化学", "炼金士", "化阅核"), ("语文", "锦心子", "文阅卷"),
    ("英语", "通语者", "英阅卷"), ("地理", "山海客", "地阅评"), ("历史", "史鉴君", "史阅评"),
    ("道法", "明辨君", "德阅判"), ("数学", "数算子", "数阅卷"), ("物理", "格物君", "格阅卷"),
    ("信息科技", "码智君", "信阅卷"),
]
for dom, main, grd in ROUTE:
    route_rows += f'<tr><td>{dom}</td><td class="hl">@{main}</td><td class="hl2">@{grd}</td></tr>'

OTHER_ROUTE = [
    ("八字/风水/占卜", "@天机阁"), ("中医诊疗", "@岐黄医典"), ("会计税务", "@算经阁"),
    ("黄金/外汇/EA", "@金策宗师团 + @MT5 EA 编程专家"), ("教务/排课", "@教务智能体"),
    ("职称填表", "@青云梯"), ("课题申报", "@格物致知科研智库"), ("考研", "@研枢考研专家团"),
    ("教育IP运营", "@教联中枢"), ("视频创作", "@视频创作团"), ("AI 音乐", "@音律工坊"),
    ("棋类推演", "@弈谋阁"), ("电子书转电影", "@电子书转电影"), ("配色设计", "@色彩设计大师"),
]
other_rows = "".join(f'<tr><td>{a}</td><td class="hl">{b}</td></tr>' for a, b in OTHER_ROUTE)

stats = [
    (d["expertCount"], "个专家"),
    (d["totalAgents"], "个子代理"),
    (10, "个学科团"),
    (10, "个阅卷官"),
]

HTML = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>李彦明老师 · 专家团全景学习手册</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 0;
    background: linear-gradient(180deg, #0b1120 0%, #111827 100%);
    color: #e5e7eb;
    font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
    line-height: 1.65;
  }}
  .wrap {{ max-width: 1180px; margin: 0 auto; padding: 48px 28px 80px; }}
  header {{ text-align: center; margin-bottom: 44px; }}
  h1 {{
    font-size: 34px; margin: 0 0 12px; font-weight: 700; letter-spacing: .5px;
    background: linear-gradient(90deg, #7dd3fc, #c4b5fd 50%, #fca5a5);
    -webkit-background-clip: text; background-clip: text; color: transparent;
  }}
  .sub {{ color: #94a3b8; font-size: 14px; }}
  .stats {{ display: flex; justify-content: center; gap: 14px; flex-wrap: wrap; margin: 26px 0 0; }}
  .stat {{
    background: #1e293b; border: 1px solid #334155; border-radius: 12px;
    padding: 14px 26px; min-width: 118px;
  }}
  .stat b {{ display: block; font-size: 26px; color: #7dd3fc; font-weight: 700; }}
  .stat span {{ font-size: 12px; color: #94a3b8; }}

  section {{ margin-top: 46px; }}
  h2 {{
    font-size: 20px; margin: 0 0 6px; padding-left: 12px;
    border-left: 4px solid #38bdf8; color: #f1f5f9;
  }}
  h2 .cnt {{ font-size: 13px; color: #64748b; font-weight: 400; margin-left: 8px; }}
  .sect-note {{ color: #94a3b8; font-size: 13px; margin: 0 0 18px 16px; }}

  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); gap: 16px; }}
  .card {{
    background: #16233a; border: 1px solid #24344d; border-radius: 14px;
    padding: 16px 18px; transition: .18s;
  }}
  .card:hover {{ border-color: #3b82f6; transform: translateY(-2px); background: #1a2a45; }}
  .card-head {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }}
  .dot {{ width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }}
  .name {{ font-size: 16.5px; font-weight: 650; color: #f8fafc; }}
  .badge {{
    margin-left: auto; font-size: 11px; border: 1px solid; border-radius: 6px;
    padding: 1px 7px; flex-shrink: 0;
  }}
  .slug {{ font-size: 11.5px; color: #64748b; font-family: ui-monospace, Consolas, monospace; margin-bottom: 8px; }}
  .slug em {{ color: #7dd3fc; font-style: normal; }}
  .desc {{ font-size: 13px; color: #cbd5e1; margin-bottom: 10px; }}
  .tags {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .tag {{
    font-size: 11px; background: #1e3a5f; color: #93c5fd;
    border-radius: 5px; padding: 2px 8px;
  }}
  .mems {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 11px; padding-top: 11px; border-top: 1px dashed #24344d; }}
  .mem {{
    font-size: 11.5px; background: #1b2b43; border: 1px solid #2b3d58;
    border-radius: 7px; padding: 3px 9px; color: #e2e8f0;
  }}
  .mem.lead {{ background: #3b1d3d; border-color: #7e2d6e; color: #f9a8d4; }}
  .mem i {{ color: #64748b; font-style: normal; margin-left: 5px; font-size: 10.5px; }}

  table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
  th, td {{ padding: 9px 13px; text-align: left; border-bottom: 1px solid #24344d; }}
  th {{ background: #1e293b; color: #94a3b8; font-weight: 500; font-size: 12.5px; }}
  tr:hover td {{ background: #16233a; }}
  .hl {{ color: #7dd3fc; font-weight: 600; }}
  .hl2 {{ color: #86efac; font-weight: 600; }}

  .cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  @media (max-width: 820px) {{ .cols {{ grid-template-columns: 1fr; }} }}

  footer {{ margin-top: 60px; text-align: center; color: #475569; font-size: 12px;
    border-top: 1px solid #1e293b; padding-top: 22px; }}
  code {{ background: #1e293b; padding: 1px 6px; border-radius: 4px; color: #7dd3fc;
    font-family: ui-monospace, Consolas, monospace; font-size: 12.5px; }}
  .flow {{ background: #0f172a; border: 1px solid #1e293b; border-radius: 12px;
    padding: 18px 22px; font-family: ui-monospace, Consolas, monospace;
    font-size: 12.5px; color: #94a3b8; white-space: pre; overflow-x: auto; }}
  .flow b {{ color: #7dd3fc; font-weight: 500; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>李彦明老师 · 专家团全景学习手册</h1>
    <div class="sub">WorkBuddy 专家团矩阵 · 生成于 2026-09-20 · 资产来源 my-experts 市场</div>
    <div class="stats">
      {''.join(f'<div class="stat"><b>{v}</b><span>{k}</span></div>' for v, k in stats)}
    </div>
  </header>

  <section>
    <h2>任务路由铁律</h2>
    <p class="sect-note">收到任务的第一动作：判断归属，立即召唤，无匹配则直说。</p>
    <div class="flow"><b>用户发任务</b> → 判断任务核心类型
  ├─ 学科教学 → <b>主团</b>（备课/讲解/课件）或 <b>阅卷官</b>（判分/评分/改卷）
  ├─ 命理玄学 → <b>天机阁</b>        ├─ 中医诊疗 → <b>岐黄医典</b>
  ├─ 财会税务 → <b>算经阁</b>        ├─ EA/量化 → <b>金策宗师团</b>
  ├─ 教务排课 → <b>教务智能体</b>     ├─ 职称填表 → <b>青云梯</b>
  ├─ 课题申报 → <b>科研智库</b>       ├─ 考研 → <b>研枢考研团</b>
  └─ 遍历无匹配 → 明确告知「我来直接处理」</div>
  </section>

  <section>
    <h2>学科路由速查 <span class="cnt">10 科 · 主团 + 阅卷官</span></h2>
    <div class="cols">
      <table>
        <tr><th>学科</th><th>教学主团</th><th>阅卷官</th></tr>
        {route_rows}
      </table>
      <table>
        <tr><th>其他领域</th><th>召唤方式</th></tr>
        {other_rows}
      </table>
    </div>
  </section>

  <section>
    <h2>专家团全量清单 <span class="cnt">{d['expertCount']} 位专家 · {d['totalAgents']} 个子代理</span></h2>
    <p class="sect-note">紫色标记为主理人，灰色为团队成员。</p>
    <div class="grid">
      {''.join(cards_html)}
    </div>
  </section>

  <section>
    <h2>迁移与还原</h2>
    <div class="cols">
      <div>
        <p class="sect-note">① 专家包还原</p>
        <div class="flow">解压 01_专家团核心包_my-experts.zip
  → C:\\Users\\&lt;用户名&gt;\\.workbuddy\\
      plugins\\marketplaces\\
重启 WorkBuddy → 专家中心</div>
      </div>
      <div>
        <p class="sect-note">② 依赖技能还原 + AI 学习</p>
        <div class="flow">解压 02_依赖技能包_dependency-skills.zip
  → C:\\Users\\&lt;用户名&gt;\\.workbuddy\\skills\\
把 04_专家团精读手册.md 交给目标 AI</div>
      </div>
    </div>
  </section>

  <footer>
    共 {d['expertCount']} 位专家 / {d['totalAgents']} 个子代理 · 由 WorkBuddy 自动打包生成
  </footer>
</div>
</body>
</html>'''

out = os.path.join(BASE, "03_专家团全景学习手册.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(HTML)
print("[OK]", out, len(HTML), "chars")
