# -*- coding: utf-8 -*-
"""扫描 my-experts 市场，抽取全部专家的机器可读元数据。"""
import json, os, re, sys, io

SRC = r"C:\Users\ASUS\.workbuddy\plugins\marketplaces\my-experts\plugins"
OUT = r"E:\workbuddy\专家团\专家团全量打包_20260920\05_专家元数据.json"

SKIP_DIRS = {"it-edu-team_v5_backup", "marketplace.json"}


def read_json(p):
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def read_text(p):
    for enc in ("utf-8", "utf-8-sig", "gbk", "latin-1"):
        try:
            with open(p, "r", encoding=enc) as f:
                return f.read()
        except Exception:
            continue
    return ""


def _nested(raw, block, lang="zh"):
    """从 frontmatter 文本里抽取 displayName.zh / profession.zh 之类的嵌套值。"""
    m = re.search(rf"^{block}:\s*\n((?:[ \t]+.*\n?)+)", raw, re.M)
    if not m:
        return None
    seg = m.group(1)
    mm = re.search(rf"^\s+{lang}:\s*(.+)$", seg, re.M)
    if mm:
        return mm.group(1).strip().strip('"').strip("'")
    return None


def parse_frontmatter(txt):
    if not txt.startswith("---"):
        return {}
    m = re.match(r"^---\s*\n(.*?)\n---", txt, re.S)
    if not m:
        return {}
    raw = m.group(1)
    fm = {}
    for key in ("name", "description", "maxTurns"):
        mm = re.search(rf"^{key}:\s*(.+)$", raw, re.M)
        if mm:
            fm[key] = mm.group(1).strip().strip('"').strip("'")
    fm["displayName_zh"] = _nested(raw, "displayName", "zh")
    fm["displayName_en"] = _nested(raw, "displayName", "en")
    fm["profession_zh"] = _nested(raw, "profession", "zh")
    fm["profession_en"] = _nested(raw, "profession", "en")
    return fm


def human_size(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{u}" if u == "B" else f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}TB"


def dir_size(p):
    total = 0
    for root, _, files in os.walk(p):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(root, fn))
            except Exception:
                pass
    return total


experts = []
for name in sorted(os.listdir(SRC)):
    pdir = os.path.join(SRC, name)
    if not os.path.isdir(pdir) or name in SKIP_DIRS:
        continue

    pj = read_json(os.path.join(pdir, ".codebuddy-plugin", "plugin.json")) or {}
    readme = read_text(os.path.join(pdir, "README.md"))

    # agents
    agents_dir = os.path.join(pdir, "agents")
    agent_files = sorted(os.listdir(agents_dir)) if os.path.isdir(agents_dir) else []

    members = []
    for m in pj.get("members", []):
        members.append({
            "id": m.get("id"),
            "name_zh": (m.get("displayName") or {}).get("zh"),
            "name_en": (m.get("displayName") or {}).get("en"),
            "profession_zh": (m.get("profession") or {}).get("zh"),
            "role": m.get("role"),
        })

    # 若 plugin.json 无 members，回落到 agents frontmatter
    if not members:
        lead = agent_files[0][:-3] if agent_files else None
        for af in agent_files:
            txt = read_text(os.path.join(agents_dir, af))
            fm = parse_frontmatter(txt)
            members.append({
                "id": fm.get("name", af[:-3]),
                "name_zh": fm.get("displayName_zh"),
                "name_en": fm.get("displayName_en"),
                "profession_zh": fm.get("profession_zh"),
                "role": "lead" if af[:-3] == lead else "member",
            })

    # 用 agents frontmatter 补全缺失的成员信息
    fm_map = {}
    for af in agent_files:
        txt = read_text(os.path.join(agents_dir, af))
        fm_map[fm_name := parse_frontmatter(txt).get("name", af[:-3])] = parse_frontmatter(txt)
    for m in members:
        fm = fm_map.get(m.get("id")) or {}
        if not m.get("name_zh"):
            m["name_zh"] = fm.get("displayName_zh")
        if not m.get("profession_zh"):
            m["profession_zh"] = fm.get("profession_zh")
        if not m.get("name_en"):
            m["name_en"] = fm.get("displayName_en")

    # 内嵌技能
    embedded = []
    sk = os.path.join(pdir, "skills")
    if os.path.isdir(sk):
        for s in sorted(os.listdir(sk)):
            if os.path.isdir(os.path.join(sk, s)):
                embedded.append(s)
    for s in sorted(os.listdir(pdir)):
        if s.startswith("skill-") and os.path.isdir(os.path.join(pdir, s)):
            embedded.append(s)

    refs = []
    rf = os.path.join(pdir, "references")
    if os.path.isdir(rf):
        refs = sorted(os.listdir(rf))

    # 头部简介：取 README 第一个非标题段落
    intro = ""
    for line in readme.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith(">") and not line.startswith("|"):
            intro = line
            break

    experts.append({
        "dir": name,
        "name": pj.get("name", name),
        "displayName_zh": (pj.get("displayName") or {}).get("zh") or name,
        "displayName_en": (pj.get("displayName") or {}).get("en"),
        "profession_zh": (pj.get("profession") or {}).get("zh"),
        "version": pj.get("version"),
        "author": (pj.get("author") or {}).get("name"),
        "expertType": pj.get("expertType"),
        "leadAgent": pj.get("agentName") or (pj.get("teamInfo") or {}).get("leadAgent"),
        "agentCount": len(agent_files),
        "agents": [a[:-3] for a in agent_files if a.endswith(".md")],
        "teamSize": len(members),
        "members": members,
        "tags_zh": [t.get("zh") for t in pj.get("tags", []) if isinstance(t, dict)],
        "oneLine_zh": ((pj.get("displayDescription") or {}).get("zh") or intro)[:300],
        "initPrompt_zh": (pj.get("defaultInitPrompt") or {}).get("zh"),
        "quickPrompts_zh": [q.get("zh") for q in pj.get("quickPrompts", []) if isinstance(q, dict) and q.get("zh")],
        "embeddedSkills": embedded,
        "references": refs,
        "hasSettings": os.path.isfile(os.path.join(pdir, "settings.json")),
        "sizeHuman": human_size(dir_size(pdir)),
        "categoryId": pj.get("categoryId"),
        "hasPluginJson": bool(pj),
    })

meta = {
    "generatedAt": "2026-09-20",
    "source": SRC,
    "expertCount": len(experts),
    "totalAgents": sum(e["agentCount"] for e in experts),
    "experts": experts,
}

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

print(f"[OK] 专家数={len(experts)}  子代理总数={meta['totalAgents']}")
for e in experts:
    print(f"  {e['displayName_zh']:<12} {e['dir']:<26} v{e['version']:<8} {e['expertType']:<6} agents={e['agentCount']:<3} size={e['sizeHuman']}")
