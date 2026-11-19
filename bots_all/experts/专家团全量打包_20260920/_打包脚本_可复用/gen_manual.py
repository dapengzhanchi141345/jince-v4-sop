# -*- coding: utf-8 -*-
"""根据元数据生成：04_专家团精读手册.md（供另一个智能体学习）。"""
import json, os

BASE = r"E:\workbuddy\专家团\专家团全量打包_20260920"
d = json.load(open(os.path.join(BASE, "05_专家元数据.json"), encoding="utf-8"))
experts = d["experts"]
m = {e["dir"]: e for e in experts}

# 分类分组（按用途）
GROUPS = [
    ("一、学科教学主团（10 科）", [
        ("bio-master", "生物"), ("chem-master", "化学"), ("chinese-master", "语文"),
        ("english-master", "英语"), ("geo-master", "地理"), ("history-master", "历史"),
        ("morality-master", "道法"), ("math-all-domain", "数学"),
        ("physics-omnibus", "物理"), ("it-edu-team", "信息科技"),
    ]),
    ("二、阅卷评分官（10 科）", [
        ("bio-grader", "生物"), ("chem-grader", "化学"), ("chi-grader", "语文"),
        ("eng-grader", "英语"), ("geo-grader", "地理"), ("his-grader", "历史"),
        ("mor-grader", "道法"), ("math-grader", "数学"),
        ("physics-grader", "物理"), ("it-grader", "信息科技"),
    ]),
    ("三、学科辅助与专项", [
        ("bio-basics", "生物·基础学段"), ("bio-pro", "生物·进阶段"),
        ("bio-frontier", "生物·竞赛前沿"), ("color-design-master", "配色设计"),
    ]),
    ("四、玄学命理", [("tianji-ge", "天机阁"), ("bazi-calculator", "命理排盘师")]),
    ("五、医疗健康", [("qihuang-medical", "岐黄医典")]),
    ("六、财会与金融", [
        ("suan-jing-ge", "算经阁"), ("goldstrategy-guild", "金策宗师团"),
        ("mt5-ea-expert", "MT5 EA 编程专家"),
    ]),
    ("七、教育行政与教科研", [
        ("education-admin", "教务智能体"), ("teacher-promotion-filling", "青云梯"),
        ("gewu-zhidao", "格物致知科研智库"),
    ]),
    ("八、考研与教育IP运营", [
        ("yan-shu-kaoyan", "研枢考研专家团"), ("jiao-lian-zhong-shu", "教联中枢"),
    ]),
    ("九、媒体创作与娱乐", [
        ("video-crew", "视频创作团"), ("music-craft-studio", "音律工坊"),
        ("yimou-pavilion", "弈谋阁"), ("ebook-to-movie", "电子书转电影"),
    ]),
]

ROUTE_TABLE = [
    ("生物 / 生命科学", "万物生", "bio-master", "生阅卷", "bio-grader"),
    ("化学", "炼金士", "chem-master", "化阅核", "chem-grader"),
    ("语文", "锦心子", "chinese-master", "文阅卷", "chi-grader"),
    ("英语", "通语者", "english-master", "英阅卷", "eng-grader"),
    ("地理", "山海客", "geo-master", "地阅评", "geo-grader"),
    ("历史", "史鉴君", "history-master", "史阅评", "his-grader"),
    ("道法 / 政治", "明辨君", "morality-master", "德阅判", "mor-grader"),
    ("数学", "数算子", "math-all-domain", "数阅卷", "math-grader"),
    ("物理", "格物君", "physics-omnibus", "格阅卷", "physics-grader"),
    ("信息科技 / 信息技术", "码智君", "it-edu-team", "信阅卷", "it-grader"),
    ("八字 / 风水 / 占卜 / 起名 / 择吉", "天机阁", "tianji-ge", "—", "—"),
    ("中医 / 中西医诊疗", "岐黄医典", "qihuang-medical", "—", "—"),
    ("会计 / 报表 / 税务 / 审计", "算经阁", "suan-jing-ge", "—", "—"),
    ("黄金 / 外汇 / MT5 / EA / 量化", "金策宗师团 / MT5 EA 编程专家", "goldstrategy-guild / mt5-ea-expert", "—", "—"),
    ("教务 / 学校管理 / 排课", "教务智能体", "education-admin", "—", "—"),
    ("职称晋级 / 评审填表", "青云梯", "teacher-promotion-filling", "—", "—"),
    ("课题申报 / 教育科研", "格物致知科研智库", "gewu-zhidao", "—", "—"),
    ("考研（公共课+14门类）", "研枢考研专家团", "yan-shu-kaoyan", "—", "—"),
    ("教育IP内容编排 / 多平台分发", "教联中枢", "jiao-lian-zhong-shu", "—", "—"),
    ("视频 / 分镜 / 剪辑", "视频创作团", "video-crew", "—", "—"),
    ("AI 音乐 / 词曲 / 编曲 / 混音", "音律工坊", "music-craft-studio", "—", "—"),
    ("棋类博弈 / 战略推演", "弈谋阁", "yimou-pavilion", "—", "—"),
    ("电子书转电影", "电子书转电影", "ebook-to-movie", "—", "—"),
    ("配色 / 设计 Token", "色彩设计大师", "color-design-master", "—", "—"),
]

L = []
w = L.append

w("# 李彦明老师 · 专家团全量精读手册")
w("")
w("> **用途**：把本文件完整交给任意一个 AI，它即可掌握李老师全部专家团的职责、阵容、调用方式与路由规则。")
w("> **生成日期**：2026-09-20 ｜ **资产来源**：`~/.workbuddy/plugins/marketplaces/my-experts`")
w(f"> **规模**：{d['expertCount']} 个专家 / {d['totalAgents']} 个子代理 Agent")
w("")
w("---")
w("")
w("## 0. 一句话说明")
w("")
w("李老师（李彦明，山东寿光初中信息科技教师 + MT5 量化开发者）在 WorkBuddy 里搭了一套"
  "**专家团矩阵**：把每个专业领域做成独立的「专家」，团队型专家内部再分多个子角色协作。"
  "使用方式是在对话里 `@专家名` 召唤。")
w("")
w("---")
w("")
w("## 1. 任务路由铁律（收到任务的第一个动作）")
w("")
w("```")
w("用户发任务 → 判断任务核心类型")
w("  ├─ 学科教学（生物/化学/地理/英语/语文/道法/历史/数学/物理/信息科技）")
w("  │    ├─ 备课/教学/讲解/课件  → 召唤对应学科主团")
w("  │    └─ 阅卷/评分/判分/改卷  → 召唤对应阅卷评分官")
w("  ├─ 命理玄学（八字/风水/占卜/起名/择吉）→ 天机阁")
w("  ├─ 医疗健康（问诊/用药/中医）→ 岐黄医典")
w("  ├─ 财会税务 → 算经阁")
w("  ├─ 黄金/外汇/EA/量化 → 金策宗师团 / MT5 EA 编程专家")
w("  ├─ 教务/学校管理/排课 → 教务智能体")
w("  ├─ 职称晋级填表 → 青云梯")
w("  ├─ 课题申报/教科研 → 格物致知科研智库")
w("  ├─ 考研 → 研枢考研专家团")
w("  ├─ 多平台内容运营 → 教联中枢")
w("  ├─ 视频/音乐/棋类/电子书转电影 → 对应创作团")
w("  └─ 遍历后无匹配 → 明确告知「当前无对应专属智能体，我来直接处理」")
w("```")
w("")
w("**铁律**：① 归属必须明确，第一动作就是判断归谁；② 判断出归属立即召唤，不让用户催；"
  "③ 无匹配就直说，不硬套；④ 不假设「可能也适合哪个」，以任务核心类型为准。")
w("")
w("### 路由速查表")
w("")
w('| 任务领域 | 专家显示名 | 目录名 | 配套阅卷官 | 阅卷官目录 |')
w("|---|---|---|---|---|")
for dom, disp, slug, gdisp, gslug in ROUTE_TABLE:
    w(f"| {dom} | @{disp} | `{slug}` | {('@'+gdisp) if gdisp!='—' else '—'} | {('`'+gslug+'`') if gslug!='—' else '—'} |")
w("")
w("---")
w("")
w("## 2. 专家团全量清单（按类别）")
w("")
for title, items in GROUPS:
    w(f"### {title}")
    w("")
    w("| 专家 | 目录 | 版本 | 类型 | 子代理 | 头像/资源 |")
    w("|---|---|---|---|---|---|")
    for slug, label in items:
        e = m.get(slug)
        if not e:
            continue
        w(f"| **{e['displayName_zh']}** | `{e['dir']}` | v{e['version'] or '-'} | {e['expertType']} | {e['agentCount']} | {e['sizeHuman']} |")
    w("")

w("---")
w("")
w("## 3. 每个专家详解（阵容 + 职责 + 入口提问）")
w("")

order = [s for _, items in GROUPS for s, _ in items]
seen = set()
for slug in order + [e["dir"] for e in experts]:
    if slug in seen:
        continue
    seen.add(slug)
    e = m.get(slug)
    if not e:
        continue
    w(f"### {e['displayName_zh']}　`{e['dir']}`　v{e['version'] or '-'}")
    w("")
    if e.get("displayName_en"):
        w(f"- **英文名**：{e['displayName_en']}")
    w(f"- **定位**：{e.get('profession_zh') or '—'}")
    w(f"- **类型**：{e['expertType']} ｜ **子代理数**：{e['agentCount']} ｜ **包体**：{e['sizeHuman']}")
    if e.get("tags_zh"):
        w(f"- **标签**：{' / '.join([t for t in e['tags_zh'] if t])}")
    if e.get("oneLine_zh"):
        w(f"- **简介**：{e['oneLine_zh']}")
    if e["members"]:
        w("")
        w("  | 角色 | 姓名 | 头衔 |")
        w("  |---|---|---|")
        for mem in e["members"]:
            tag = "**主理人**" if mem.get("role") == "lead" else "成员"
            w(f"  | {tag} | {mem.get('name_zh') or '—'} | {mem.get('profession_zh') or '—'} |")
    if e.get("embeddedSkills") or e.get("references"):
        w("")
        extras = []
        if e.get("embeddedSkills"):
            extras.append("内嵌技能：" + "、".join(e["embeddedSkills"]))
        if e.get("references"):
            extras.append("参考资料：" + "、".join(e["references"]))
        w(f"- **附带资源**：{'；'.join(extras)}")
    if e.get("quickPrompts_zh"):
        w("")
        w("- **入口提问（试试这样问）**：")
        for q in e["quickPrompts_zh"][:5]:
            w(f"  - {q}")
    w("")

w("---")
w("")
w("## 4. 迁移与还原方法")
w("")
w("### 4.1 专家包还原")
w("1. 找到目标账号目录：`C:\\Users\\<用户名>\\.workbuddy\\plugins\\marketplaces\\`")
w("2. 解压 `01_专家团核心包_my-experts.zip` 到该目录 → 得到 `my-experts\\` 文件夹")
w("   - 正确结构：`...\\marketplaces\\my-experts\\plugins\\<各专家目录>\\`")
w("3. 重启 WorkBuddy → 左侧「专家中心 → 我的专家」应显示全部专家")
w("")
w("### 4.2 依赖技能还原")
w("1. 解压 `02_依赖技能包_dependency-skills.zip` 到 `C:\\Users\\<用户名>\\.workbuddy\\skills\\`")
w("2. ⚠️ `agnes-ai-support` 的 API Key 已剔除，需自行写入 `.agnes-key`（格式 `AGNES_API_KEY=sk-xxxx`）")
w("")
w("### 4.3 让 AI 学会")
w("把本文件（`04_专家团精读手册.md`）发给目标 AI，或让它读取该文件即可。")
w("")
w("---")
w("")
w(f"*共 {d['expertCount']} 位专家 / {d['totalAgents']} 个子代理 · 由 WorkBuddy 自动生成于 2026-09-20*")
w("")

out = os.path.join(BASE, "04_专家团精读手册.md")
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(L))
print("[OK]", out, len("\n".join(L)), "chars")
