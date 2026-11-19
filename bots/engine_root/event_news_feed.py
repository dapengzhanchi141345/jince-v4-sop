# -*- coding: utf-8 -*-
"""
event_news_feed.py — 金策宗师团 · 自动新闻事件源 (L0 输入端, 2026-09-30 t_ff8e86a1)
================================================================================
任务: 事件定级从"人工研判 event_risk.json"升级为"自动新闻源 + 确定性定级映射"。
铁律 (任务卡):
  - 只喂数据 + 定级映射, **不替风控官拍撤单** (双闸: 事件总闸撤单, 风控官复核留痕
    veto_log gate=event_recheck 口径不变)
  - 新闻抓取失败 **fail-open**: 沿用上一份定级 + 从保守, 留痕, 不阻塞交易
  - 省 token: 30min 抓一次 (缓存 30min), 不每 tick 抓; 确定性抓取+映射, 不套 LLM 判方向

三类源 (确定性 RSS/API, 全部 2026-09-30 本机探针验通):
  ① 日历/数据: marketwatch 头条 + calendargenius + fxstreet 财经日历页 →
     关键词扫 CPI/PPI/非农/FOMC/利率决议, 提取 "actual vs expected vs previous" 三元组
     (能拿到多少填多少, 缺省 null; 无实际值 → 只记待发布事件, 供 08:30 简报日历)
  ② 地缘: fxstreet/marketwatch 标题关键词 (冲突升级/谈判破裂/央行紧急声明/冻结)
  ③ 加密: cointelegraph + theblock + decrypt → 清算潮/交易所事件
     (配合币圈 D 级判定; 联动 crypto 池)

输出:
  data/event_news_feed.json  (三类条目, 每条带时间戳+来源+定级, 结构定稿)
  data/event_risk.json       (定级映射结果: level/new_entry_scale/halt_new_entries
                              + 保留原 events 人工研判条目; 自动条目前缀 [自动源])
  data/event_news_map.log    (定级映射审计行: 哪条新闻 → 哪条规则 → 什么级)

定级映射规则表 (写死, 可审计, 见 event_risk_map.json):
  数据实际值超预期 ±0.5σ(本表按百分点差阈值近似σ, σ 表内置) → MED
  ±1σ(=2倍基准差) → HIGH
  央行紧急声明关键词 / 级联清算关键词 → HALT
  关键词命中但无量化数据 → MED (保守, 不越 HIGH)
  全部未命中 → 沿用上一份 level (fail-open 保守)

调度: 本机计划任务/循环每 30min 跑一次 `python E:/GoldstrategyEngine/event_news_feed.py`。
     event_guard.py 5min 快通道继续读 event_risk.json (updated 新鲜度门控口径不变)。
"""
import os, re, json, time, html
import urllib.request, ssl, socket
import concurrent.futures
import datetime
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

ROOT = "E:/GoldstrategyEngine"
DATA = os.path.join(ROOT, "data")
FEED = os.path.join(DATA, "event_news_feed.json")
MAP_RULES = os.path.join(DATA, "event_risk_map.json")
RISK = os.path.join(DATA, "event_risk.json")
AUDIT = os.path.join(DATA, "event_news_map.log")
CACHE = os.path.join(DATA, "event_news_cache.json")
BJT = ZoneInfo("Asia/Shanghai")
CACHE_TTL = 1800          # 30min 缓存 (省 token 铁律)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
CTX = ssl.create_default_context()

# ── 可达源 (2026-09-30 probe 验通; 2026-10-01 修: forexlive /feed 替代全死的 yahoo_gspc+calendargenius) ──
SOURCES = {
    "calendar": [
        ("fxstreet", "https://www.fxstreet.com/rss"),
        ("forexlive", "https://www.forexlive.com/feed"),
        ("marketwatch_top", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ],
    "geopolitics": [
        ("fxstreet", "https://www.fxstreet.com/rss"),
        ("forexlive", "https://www.forexlive.com/feed"),
        ("marketwatch_geo", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ],
    "crypto": [
        ("cointelegraph", "https://cointelegraph.com/rss"),
        ("theblock", "https://www.theblock.co/rss.xml"),
        ("decrypt", "https://decrypt.co/feed"),
    ],
}

# ── 关键词表 (确定性, 写死, 可审计) ──
DATA_KW = {  # 日历/数据类 → 高影响数据白名单 (2026-09-30 扩词: PCE/ADP/PMI/GDP价格 进头条源)
    "cpi": ["cpi", "inflation"],
    "ppi": ["ppi", "producer price"],
    "pce": ["pce", "core pce"],
    "nonfarm": ["jobs report", "payrolls", "employment", "nonfarm", "adp employment"],
    "fomc": ["fomc", "fed", "powell", "rate decision", "federal reserve", "rate hike", "rate cut"],
    "gdp": ["gdp", "gross domestic product"],
}
GEOPOL_KW = [
    "war", "strike", "attack", "military", "escalat", "strait of hormuz",
    "hormuz", "sanction", "invasion", "ceasefire", "collapse of talks",
    "talks collapse", "emergency", "urgent statement",
]
CRYPTO_KW = ["liquidation", "liquidated", "exchange hack", "stablecoin",
             "delist", "bankrupt", "cme gold", "funding rate", "margin call"]
# HALT 触发词 (央行紧急声明 / 级联清算 → HALT, 与任务卡一致)
HALT_KW = [
    "cascading liquidation", "liquidity freeze", "strait closure",
    "market-wide halt", "emergency rate", "emergency statement",
    "systemic crisis", "firewall",
]

# ── 定级映射规则表 (落盘 event_risk_map.json, 确定性可审计) ──
# σ 近似: 各数据项 1σ 的历史波动百分点差 (保守写死值, 研发口径可调)
SIGMA = {"cpi": 0.25, "ppi": 0.45, "nonfarm": 35.0, "gdp": 0.15}
RULES = [
    {"id": "R1", "type": "data",
     "desc": "数据实际值 vs 预期差 >=1σ → HIGH",
     "sigma_factor": 1.0, "level": "HIGH", "scale": 0.3},
    {"id": "R2", "type": "data",
     "desc": "数据实际值 vs 预期差 >=0.5σ → MED",
     "sigma_factor": 0.5, "level": "MED", "scale": 0.5},
    {"id": "R3", "type": "keyword_halt",
     "desc": "央行紧急声明/级联清算关键词 → HALT",
     "keywords": HALT_KW, "level": "HALT", "scale": 0.0, "halt": True},
    {"id": "R4", "type": "keyword_geo",
     "desc": "地缘重大突发关键词(无量化数据) → MED (保守, 不越HIGH)",
     "keywords": GEOPOL_KW, "level": "MED", "scale": 0.5},
    {"id": "R5", "type": "keyword_crypto",
     "desc": "加密清算潮/交易所事件关键词 → MED (配合币圈D级判定)",
     "keywords": CRYPTO_KW, "level": "MED", "scale": 0.5},
    {"id": "R6", "type": "fail_open",
     "desc": "全部未命中/抓取失败 → 沿用上一份 level (保守)",
     "level": "INHERIT", "scale": None, "halt": None},
]

LEVEL_RANK = {"LOW": 0, "MED": 1, "HIGH": 2, "HALT": 3}


def now_ts():
    return int(time.time())


def bjt_str(ts):
    return datetime.datetime.fromtimestamp(ts, BJT).strftime("%Y-%m-%d %H:%M")


def fetch(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, context=CTX, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def parse_rss_items(text, max_items=40):
    """容错解析 RSS/Atom: 取 (title, link, pub, source) 元组列表."""
    out = []
    try:
        root = ElementTree.fromstring(text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item")
        if not items:
            items = root.findall(".//atom:entry", ns)
        for it in items[:max_items]:
            def txt(*paths):
                for p in paths:
                    el = it.find(p)
                    if el is not None and (el.text or "").strip():
                        return html.unescape((el.text or "").strip())
                return ""
            out.append({
                "title": txt("title", "{http://www.w3.org/2005/Atom}title")[:300],
                "link": txt("link", "{http://www.w3.org/2005/Atom}link"),
                "pub": txt("pubDate", "{http://www.w3.org/2005/Atom}updated",
                           "{http://www.w3.org/2005/Atom}published"),
            })
    except Exception as e:
        out.append({"title": "[解析失败] " + type(e).__name__ + ": " + str(e)[:80],
                    "link": "", "pub": ""})
    return out


# ── 数据三元组提取 (确定性正则, 能抓多少抓多少, 缺省 None) ──
_PCT = r"(-?\d+(?:\.\d+)?)\s*(?:%|pct|percent)"
_NUM = r"(-?\d+(?:\.\d+)?)\s*(?:K|thousand|千)?"


def extract_triplet(title, key):
    """从标题抽 (actual, expected, previous). 抓不到返回 None 位."""
    t = title.lower()
    m = re.findall(_PCT, t)
    if key in ("cpi", "ppi") and len(m) >= 2:
        try:
            return [float(m[0]), float(m[1]), None]
        except ValueError:
            return None
    if key == "nonfarm":
        nums = re.findall(_NUM, t)
        if nums:
            try:
                vals = [float(x.rstrip("Kk")) * (1000 if "k" in x.lower() else 1) for x in nums[:3]]
                return vals + [None] * (3 - len(vals))
            except ValueError:
                return None
    if m:
        try:
            return [float(m[0])] + [None] * (2 - len(m) if len(m) == 1 else 2)
        except ValueError:
            return None
    return None


def classify(item, category, source, ts):
    """一条新闻 → 命中规则列表 [(rule_id, level, scale, halt, detail)]."""
    t = (item.get("title") or "").lower()
    hits = []
    if category == "calendar":
        for key, kws in DATA_KW.items():
            if not any(k in t for k in kws):
                continue
            triple = extract_triplet(item.get("title") or "", key)
            if triple and triple[0] is not None and triple[1] is not None:
                diff = abs(triple[0] - triple[1])
                sig = SIGMA.get(key, 0.25)
                factor = diff / sig if sig else 99
                if factor >= 1.0:
                    hits.append(("R1", "HIGH", 0.3, False,
                                 "%s 实际vs预期差 %.2f >= 1σ(%.2f)" % (key, diff, sig)))
                elif factor >= 0.5:
                    hits.append(("R2", "MED", 0.5, False,
                                 "%s 实际vs预期差 %.2f >= 0.5σ(%.2f)" % (key, diff, sig)))
                else:
                    hits.append(("R6", "INHERIT", None, None,
                                 "%s 差 %.2f < 0.5σ, 未触发" % (key, diff)))
            else:
                # 命中数据关键词但无量化值 → 保守 MED (R2 语义: 有数据事件临近/发生)
                hits.append(("R2", "MED", 0.5, False,
                             "%s 关键词命中, 无量化三元组 → 保守MED" % key))
    elif category == "geopolitics":
        for kw in GEOPOL_KW:
            if kw in t:
                level = "HIGH" if ("strait of hormuz" in t or "hormuz" in t
                                   and "closure" in t or "closure" in t and "strait" in t) else "MED"
                # 任务卡: 谈判破裂/冲突升级 → 至少 MED; 海峡全闭属 HALT 前置, 由 R3 关键词管
                hits.append(("R4", level, 0.5, False, "地缘关键词 '%s'" % kw))
                break
    elif category == "crypto":
        for kw in CRYPTO_KW:
            if kw in t:
                hits.append(("R5", "MED", 0.5, False, "加密关键词 '%s' (币圈D级联动)" % kw))
                break
    # HALT 关键词全局 (任何类目命中即 HALT, 央行紧急声明/级联清算)
    for kw in HALT_KW:
        if kw in t:
            hits.append(("R3", "HALT", 0.0, True, "HALT关键词 '%s'" % kw))
    return hits


def aggregate_level(hits, prev_level):
    """取命中里最高级; 全无命中 → INHERIT 沿用上一份. (hits: dict 列表, 字段 rule/level/scale/halt/detail)"""
    lv = "LOW"
    n_hit = 0
    for h in hits:
        n_hit += 1
        if LEVEL_RANK.get(h.get("level"), 0) > LEVEL_RANK.get(lv, 0):
            lv = h["level"]
    if n_hit == 0:
        return "INHERIT", None, False
    halt = any(bool(h.get("halt")) for h in hits)
    if lv == "LOW":
        return "LOW", 1.0, False
    scale = {"MED": 0.5, "HIGH": 0.3, "HALT": 0.0}.get(lv, 0.5)
    return lv, scale, halt


def _aggregate_dicts(all_hits, prev_level):
    """all_hits: 条目级 dict (含 hits 子列表) → 展平后再聚合."""
    if all_hits and isinstance(all_hits[0], dict) and "hits" in all_hits[0]:
        flat = [h for it in all_hits for h in it.get("hits", [])]
    else:
        flat = all_hits
    return aggregate_level(flat, prev_level)


def load_prev_risk():
    try:
        return json.load(open(RISK, encoding="utf-8"))
    except Exception:
        return {}


def write_map_rules():
    doc = {
        "version": 1,
        "updated": now_ts(),
        "sigma_table": SIGMA,
        "rules": RULES,
        "aggregate": "命中取最高级; 全无命中=INHERIT沿用上一份(保守); HALT关键词全局优先",
        "scale_map": {"LOW": 1.0, "MED": 0.5, "HIGH": 0.3, "HALT": 0.0},
        "gate_note": "自动源只喂数据+定级映射, 撤单双闸不变: 事件总闸撤 + 风控官复核 veto_log gate=event_recheck",
    }
    json.dump(doc, open(MAP_RULES, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def main():
    ts = now_ts()
    audit = []
    feed = {"updated": ts, "fetched_at_bjt": bjt_str(ts), "categories": {}}
    fetched = {}
    errors = []

    # 30min 缓存 (省 token 铁律): 缓存新鲜 → 只复用上次抓取结果, 不重抓
    if os.path.exists(CACHE):
        try:
            c = json.load(open(CACHE, encoding="utf-8"))
        except Exception:
            c = {}
        if c.get("ts") and ts - c.get("ts", 0) < CACHE_TTL:
            print("[event_news_feed] 30min缓存内 (ts=%s), 跳过抓取, 复用上次结果" % c.get("fetched_at_bjt", "?"))
            if c.get("categories"):
                feed["categories"] = c["categories"]
                errors = c.get("errors", [])

    def work(cat_src):
        cat, src = cat_src
        for name, url in SOURCES[cat]:
            try:
                items = parse_rss_items(fetch(url))
                for it in items:
                    hits = classify(it, cat, name, ts)
                    it["source"] = name
                    it["category"] = cat
                    it["ts_fetched"] = ts
                    it["hits"] = [
                        {"rule": h[0], "level": h[1], "scale": h[2], "halt": h[3], "detail": h[4]}
                        for h in hits]
                    it["level"] = max((h[1] for h in hits if h[1] not in ("INHERIT", None)),
                                      default=None)
                    fetched.setdefault(cat, []).append(it)
            except Exception as e:
                errors.append("%s/%s: %s: %s" % (cat, name, type(e).__name__, str(e)[:100]))

    if not any(feed["categories"].get(c, {}).get("n_items") for c in ("calendar", "geopolitics", "crypto")):
        flat = [(cat, (name, url)) for cat, srcs in SOURCES.items() for name, url in srcs]
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            list(ex.map(work, flat))

    if fetched:
        # 新抓取: 合并进 feed 并刷新缓存
        for cat, items in fetched.items():
            # 同类目内 (title, source) 去重: 同源 R30min 缓存会叠加重复条目
            seen, deduped = set(), []
            for it in items:
                k = ((it.get("title") or "").strip().lower(), it.get("source"))
                if k in seen:
                    continue
                seen.add(k)
                deduped.append(it)
            feed["categories"][cat] = {
                "n_items": len(deduped),
                "n_hits": len([it for it in deduped if it.get("hits")]),
                "items": [it for it in deduped if it.get("hits")],
                "errors": [e for e in errors if e.startswith(cat)],
            }
        cachel = {"ts": ts, "fetched_at_bjt": bjt_str(ts), "categories": feed["categories"], "errors": errors}
        json.dump(cachel, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)

    # 补全缺失类目 (全零的类目也要有结构, 供 08:30 简报读)
    for cat in ("calendar", "geopolitics", "crypto"):
        blk = feed["categories"].setdefault(cat, {"n_items": 0, "n_hits": 0, "items": [], "errors": []})
        blk.setdefault("errors", [e for e in errors if e.startswith(cat)])

    # 聚合: 每条命中记审计行
    for cat, blk in feed["categories"].items():
        for it in blk.get("items", []):
            for h in it.get("hits", []):
                audit.append("%s [cat=%s src=%s] %s→%s rule=%s :: %s :: %s" % (
                    bjt_str(ts), cat, it.get("source"),
                    (it.get("title") or "")[:80], h.get("level"), h.get("rule"),
                    h.get("detail"), it.get("link", "")))

    # 定级
    prev = load_prev_risk()
    prev_level = str(prev.get("level", "LOW")).upper()
    all_hits = [h for blk in feed["categories"].values() for it in blk.get("items", [])
                for h in it.get("hits", [])]
    level, scale, halt = _aggregate_dicts(all_hits, prev_level)
    if level == "INHERIT":
        level = prev_level if prev_level in LEVEL_RANK else "MED"
        scale = {"LOW": 1.0, "MED": 0.5, "HIGH": 0.3, "HALT": 0.0}.get(level, 0.5)
        audit.append("%s [auto-source] 全部未命中 → INHERIT 沿用上一份 level=%s (fail-open保守)" % (bjt_str(ts), level))
        halt = level == "HALT"

    # 落盘 feed (三类, 含时间戳+来源+定级; 只留命中条目, 省体积)
    feed["level_auto"] = level
    feed["scale_auto"] = scale
    feed["halt_auto"] = halt
    feed["fail_open"] = bool(errors)
    feed["errors"] = errors
    json.dump(feed, open(FEED, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # 定级映射写 event_risk.json (保留原 events 人工条目, 自动条目前缀 [自动源]; 人工研判不被覆盖)
    auto_events = []
    for cat in ("calendar", "geopolitics", "crypto"):
        for it in feed["categories"][cat]["items"]:
            auto_events.append({
                "time": ts, "title": "[自动源·%s] %s" % (cat, (it["title"] or "")[:200]),
                "impact": "high" if it.get("level") in ("HIGH", "HALT") else
                          ("medium" if it.get("level") == "MED" else "low"),
                "symbols": [], "source": it.get("source"), "rule": it["hits"][0]["rule"],
            })
    doc = {
        "updated": ts,
        "level": level,
        "new_entry_scale": scale,
        "halt_new_entries": bool(halt),
        "events": (prev.get("events", []) or [])[-80:] + auto_events,  # 人工条目滚动保留80条
        "auto_source": {
            "ts": ts, "level": level, "n_hits": len(all_hits), "fail_open": bool(errors),
            "note": "自动源只喂数据+映射, 撤单双闸: 事件总闸撤 + 风控官 event_recheck 复核留痕",
        },
    }
    # 契约断言 (与 event_director 一致)
    if level == "HIGH" and doc["new_entry_scale"] not in (0.3, 1.0):
        doc["new_entry_scale"] = 0.3
    if level == "HALT":
        doc["halt_new_entries"] = True
    if level in ("LOW", "MED"):
        doc["halt_new_entries"] = False
    json.dump(doc, open(RISK, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    write_map_rules()
    with open(AUDIT, "a", encoding="utf-8") as f:
        f.write("\n".join(audit) + ("\n" if audit else ""))

    # ── 08:30 简报「今日事件日历」: 当日待发布 + 已发生 高影响事件 3-5 条 ──
    # 口径: 从 feed 的 calendar+geopolitics n_hits 条目中取当日(北京日)命中条目,
    #       按时序排列, 时间+来源+定级+标题, 最多 5 条;
    #       挂单交易部按「事件前 1h 不挂新单」口径联动 (L6 铁律已有)。
    _all_items = []
    for cat in ("calendar", "geopolitics"):
        blk = feed["categories"].get(cat, {})
        for it in blk.get("items", []):
            if it.get("hits"):
                _all_items.append(it)
    # 排序: 按 pub 时间倒序 (最新的在前); 无 pub 的放最后
    def _pub_ts(it):
        p = (it.get("pub") or "").strip()
        if not p:
            return ""
        out = ""
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S",
                    "%d %b %Y %H:%M:%S", "%a, %d %b %Y %H:%M %Z"):
            try:
                out = datetime.datetime.strptime(p[:len(fmt)], fmt).strftime("%Y%m%d%H%M")
                break
            except ValueError:
                continue
        return out
    _all_items.sort(key=_pub_ts, reverse=True)
    today_str = datetime.datetime.now(BJT).strftime("%Y-%m-%d")
    # 新鲜度判定: 发布日期=今天 或 本次抓取到的 才算今日实发; 无新鲜项=走缓存兜底(degraded)
    _fresh = [it for it in _all_items
              if _pub_ts(it).startswith(today_str.replace("-", "")) or
              it.get("ts_fetched") == ts]
    _degraded = len(_fresh) == 0
    _today_items = _fresh if _fresh else _all_items[:5]
    calendar_block = {
        "date": today_str,
        "generated_at_bjt": bjt_str(ts),
        "n_events": min(len(_today_items), 5),
        "fresh_events": len(_fresh),          # 新增: 今日实发条数(0=全走缓存兜底)
        "degraded": _degraded,                # 新增: True=外网断/源未刷新, events 为缓存兜底非今日实发
        "events": [
            {
                "title": (it.get("title") or "")[:120],
                "time_bjt": it.get("pub", ""),
                "source": it.get("source"),
                "category": it.get("category"),
                "level": it.get("hits", [{}])[0].get("level") if it.get("hits") else None,
                "link": it.get("link", ""),
            }
            for it in _today_items[:5]
        ],
        # 动态 note: degraded 时明确"外网断,以下为缓存兜底",下游(简报/日报)据此说准话, 不再误报"整份过期/需手动核验"
        "note": ("08:30简报读此块; 挂单交易部按「事件前1h不挂新单」口径联动(L6铁律)"
                 + (" ; 降级:今日新鲜新闻0条(外网断/源未刷新),以上为近数日缓存兜底,非今日实发"
                    if _degraded else "")),
    }
    _cal_path = os.path.join(DATA, "event_daily_calendar.json")
    json.dump(calendar_block, open(_cal_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print("[event_news_feed] %s level=%s scale=%.1f halt=%s hits=%d fail_open=%s" % (
        bjt_str(ts), level, scale, halt, len(all_hits), bool(errors)))
    for e in errors:
        print("  [ERR] " + e)
    print("  feed → %s" % FEED)
    print("  risk → %s" % RISK)
    print("  audit → %s" % AUDIT)
    print("  calendar → %s (%d events)" % (_cal_path, calendar_block["n_events"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
