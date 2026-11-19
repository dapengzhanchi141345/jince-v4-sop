#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策宗师团 · 盘口中间深度解析节点 (no_agent L0, 0 LLM, 429-proof, 2026-10-08 用户令"加大例会密度")
3 个盘口中间节点:
  asia_midday    10:05  (东京 08:05开 <-> 12:05关 中间)
  europe_midday  16:35  (伦敦 15:05开 <-> 18:05关 中间)
  us_midday      23:35  (纽约 21:05开 <-> 02:05关 中间)
比开/关评节点多两段:
  ② 半日对账: 开评研判方向 vs 当前实价 — 逐品种判 命中/做反/未动, 根因归类
  ⑤ 进化点:   当前盘面最值得研发跟进的 1 条确定性信号(进五验队列, 0 LLM)
全员参与: 投群后 @chief 归纳 / @risk-officer 复核 / @strategy-rd 认领进化点.
用法: jince_midday_deep.py [asia_midday|europe_midday|us_midday]
"""
import os, json, time, sys, datetime, subprocess, zoneinfo
import jince_edu

DATA = r"E:/GoldstrategyEngine/data"
ATE_PY = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/pythonw.exe"
BJT = zoneinfo.ZoneInfo("Asia/Shanghai")

MID_NODES = {"asia_midday": "亚盘半日深析", "europe_midday": "欧盘半日深析", "us_midday": "美盘半日深析"}

def jget(path, default):
    try:
        return json.load(open(os.path.join(DATA, path), encoding="utf-8"))
    except Exception:
        return default

def latest_advisory():
    cands = [f for f in os.listdir(DATA) if f.startswith("daily_advisory_") and f.endswith(".json")]
    if not cands:
        return None, None
    f = max(cands, key=lambda x: os.path.getmtime(os.path.join(DATA, x)))
    return f, json.load(open(os.path.join(DATA, f), encoding="utf-8"))

def live_ticks(syms, timeout=30):
    code = ("import os,json,MetaTrader5 as m\n"
            "os.environ.pop('PYTHONPATH',None);os.environ.pop('PYTHONHOME',None)\n"
            "ok=m.initialize()\n"
            "out={}\n"
            "for s in %r:\n"
            "    t=m.symbol_info_tick(s)\n"
            "    if t and t.bid>0: out[s]=(t.bid+t.ask)/2.0\n"
            "print(json.dumps(out))\n") % list(syms)
    try:
        r = subprocess.run([ATE_PY, "-c", code], capture_output=True, text=True,
                           timeout=timeout, cwd=r"E:/GoldstrategyEngine",
                           env={k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")})
        for line in reversed(r.stdout.strip().splitlines()):
            if line.strip().startswith("{"):
                return json.loads(line)
        return {}
    except Exception:
        return {}

LIVE_STATE = r"E:\AgentCommons\shared\live_state.json"

def our_exposure():
    """[2026-11-11 根治] ③段持仓/挂单 = 共享真值源 live_state.json 优先(yushi实写, 含positions+orders),
    >30min 判 stale 明示; 文件缺失/损坏才降级派生簿(fail-LOUD标'派生, 可能滞后'), 根治旧版
    '只读挂单派生簿→8张活持仓漏报(误报无open单)'缺陷(11-11 23:36半日节点实锤).
    返回 dict{source, fresh, mins, pos_rows, order_rows}."""
    try:
        mtime = os.path.getmtime(LIVE_STATE)
        mins = int((time.time() - mtime) / 60)
        d = json.load(open(LIVE_STATE, encoding="utf-8"))
        pos_rows = ["持 #%s %s %s %s手 @%s 浮=%s" % (
            p.get("ticket", p.get("id", "?")), p.get("symbol"), p.get("side", "?"),
            p.get("volume"), p.get("price_open"), p.get("profit")) for p in d.get("positions", [])][:6]
        order_rows = ["挂 #%s %s %s %s手 @%s (magic %s)" % (
            o.get("ticket", o.get("id", "?")), o.get("symbol"), o.get("otype", o.get("type", "?")),
            o.get("volume"), o.get("price"), o.get("magic")) for o in d.get("orders", [])][:6]
        return {"source": "live_state.json", "fresh": mins <= 30, "mins": mins,
                "pos_rows": pos_rows, "order_rows": order_rows}
    except Exception as e:
        # 降级派生簿 (fail-LOUD: 明示数据源, 不冒充实盘断言)
        open_rows = []
        for bf in ("pending_orders_brief.md", "crypto_pending_brief.md", "equity_pending_brief.md"):
            p = os.path.join(DATA, bf)
            if not os.path.exists(p):
                continue
            for line in open(p, encoding="utf-8", errors="replace"):
                if "status=open" in line or "status=filled" in line:
                    open_rows.append(line.strip()[:120])
        return {"source": "派生簿(live_state不可用: %s)" % str(e)[:40], "fresh": False, "mins": None,
                "pos_rows": [], "order_rows": open_rows[:8]}

def meta_winrate():
    m = jget("meta_evolution.json", {})
    g = m.get("stats", {}).get("swing", {})
    if g:
        return "swing 腿 n=%s WR=%s exp_R=%s" % (g.get("n_total"), g.get("wr"), g.get("expectancy_R"))
    return "meta_evolution: 无 swing 统计"

def governor():
    g = jget("governor_state.json", {})
    return "净值峰值=%s 回撤=%s%% 净方向=%s 热持仓=%s%%/挂单=%s%%" % (
        g.get("peak_equity"), g.get("dd_pct"), g.get("net_side"), g.get("live_heat"), g.get("latent_heat"))

def event_level():
    r = jget("event_risk.json", {})
    return "事件面=%s scale=%s" % (r.get("level"), r.get("new_entry_scale"))

def half_day_recon(ad, ticks, topn=6):
    """② 半日对账: 开评研判(方向+开评价) vs 当前实价, 逐品种判 命中/做反/未动/未出实价"""
    s = ad["sections"][0]
    items = [it for it in s.get("items", []) if it.get("sym") and it.get("mom_m30_24h") is not None]
    items.sort(key=lambda x: abs(x.get("mom_m30_24h") or 0), reverse=True)
    rows = []
    for it in items[:topn]:
        sym = it["sym"]
        d = it.get("direction")
        open_px = it.get("price")
        now_px = ticks.get(sym)
        if not now_px or d not in ("LONG", "SHORT"):
            rows.append("%-9s 研判=%s(开评价%s) 未出实价" % (sym, d, open_px))
            continue
        drift = now_px - open_px
        drift_pct = drift / open_px * 100 if open_px else 0
        good = (d == "LONG" and drift > 0) or (d == "SHORT" and drift < 0)
        # [2026-10-08 教学层] 噪音闸: |偏差|<0.3% 是盘口正常噪音, 判"持平"不判做反
        # (顶配操盘手纪律: 小噪音不是判断错误, 别为它推翻/焦虑, 等方向走出来再算数)
        if abs(drift_pct) < 0.3:
            verdict = "持平(噪音内)"
        else:
            verdict = "命中" if good else "做反"
        rows.append("%-9s 研判=%s 开评=%s 现=%s 偏=%+.2f%% -> %s" % (sym, d, open_px, now_px, drift_pct, verdict))
    return rows

def evolution_point(ad, topn=4):
    """⑤ 进化点: 确定性挑 1 条最值得研发跟进的信号(系统方向 vs 24h动量矛盾 = 最值得复验)"""
    s = ad["sections"][0]
    cands = [it for it in s.get("items", []) if it.get("sym") and it.get("mom_m30_24h") is not None]
    # 矛盾信号: 24h 动量与系统研判方向相反且 |动量|>=3% (方向闸 vs 动量层缺口, 漏行情反思 SOP 第2条同源)
    contra = []
    for it in cands:
        d = it.get("direction")
        mom = it.get("mom_m30_24h") or 0
        if d == "LONG" and mom <= -3:
            contra.append((abs(mom), it["sym"], "系统LONG但24h %+.1f%%, 动量层与方向层矛盾 -> 建议 strategy-rd 同分母复验该品种方向闸" % mom))
        elif d == "SHORT" and mom >= 3:
            contra.append((abs(mom), it["sym"], "系统SHORT但24h %+.1f%%, 动量层与方向层矛盾 -> 建议 strategy-rd 同分母复验该品种方向闸" % mom))
    contra.sort(key=lambda x: x[0], reverse=True)
    if contra:
        _, sym, msg = contra[0]
        return "[%s] %s" % (sym, msg)
    # 无矛盾: 取 |动量| 最大的一条做观察
    cands.sort(key=lambda x: abs(x.get("mom_m30_24h") or 0), reverse=True)
    if cands:
        it = cands[0]
        return "[%s] 24h %+.1f%% 系统%s(conf %s), 无方向矛盾, 进观察列攒样本" % (
            it["sym"], it.get("mom_m30_24h") or 0, it.get("direction"), it.get("confidence"))
    return "(无进化点, 数据不足)"

def build(node_key=None):
    if node_key in MID_NODES:
        cn = MID_NODES[node_key]
    else:
        # 未传/传错 = 按钟点退给最近的中间节点, 都不在则静默
        h = datetime.datetime.now(BJT).hour
        if 9 <= h < 12:
            node_key, cn = "asia_midday", MID_NODES["asia_midday"]
        elif 15 <= h < 19:
            node_key, cn = "europe_midday", MID_NODES["europe_midday"]
        else:
            node_key, cn = "us_midday", MID_NODES["us_midday"]
    af, ad = latest_advisory()
    if not ad:
        print("· %s: 无 daily_advisory, 降级静默" % cn)
        return
    s = ad["sections"][0]
    bj_basis = s.get("beijing")
    movers_items = [it for it in s.get("items", []) if it.get("sym") and it.get("mom_m30_24h") is not None]
    movers_items.sort(key=lambda x: abs(x.get("mom_m30_24h") or 0), reverse=True)
    movers = movers_items[:6]
    tick_syms = list(dict.fromkeys([m["sym"] for m in movers]))
    ticks = live_ticks(tick_syms)
    recon_rows = half_day_recon(ad, ticks)
    ev = evolution_point(ad)
    exp = our_exposure()
    lines = []
    lines.append("【%s】金策宗师团 · 节点 %s UTC+8" % (cn, datetime.datetime.now(BJT).strftime("%m-%d %H:%M")))
    lines.append("· 数据基准: 研判 %s(%s) + 实时tick %d品种 %s" % (bj_basis, af, len(ticks), datetime.datetime.now(BJT).strftime("%H:%M")))
    lines.append("")
    lines.append("① 动量 top(24h):")
    for m in movers:
        t = ticks.get(m["sym"])
        px = ("%.4g" % t) if t else str(m.get("px"))
        lines.append("   %-9s 24h=%+.1f%% 现=%s 系统=%s(conf %s) %s" % (
            m["sym"], m["mom_m30_24h"], px, m.get("direction"), m.get("confidence"), (m.get("action") or "")[:16]))
    lines.append("")
    lines.append("② 半日对账(开评研判 vs 当前实价):")
    for r in recon_rows:
        lines.append("   " + r)
    lines.append("")
    lines.append("③ 我方挂单/持仓 (真值源 %s%s):" % (
        exp.get("source"), "" if exp.get("fresh") else " ⚠️ 滞后/降级, 非实盘断言"))
    npos, nord = len(exp.get("pos_rows", [])), len(exp.get("order_rows", []))
    lines.append("   实读口径: 活持仓 %d 张 | 活挂单 %d 张" % (npos, nord))
    for r in exp.get("pos_rows", []):
        lines.append("   " + r)
    for r in exp.get("order_rows", []):
        lines.append("   " + r)
    if not npos and not nord:
        lines.append("   (真值源 0 持仓 0 挂单)")
    lines.append("")
    lines.append("④ 引擎健康: %s | %s | %s" % (meta_winrate(), governor(), event_level()))
    lines.append("")
    lines.append("⑤ 进化点(进五验队列): %s  <- @strategy-rd 认领; @chief 归纳 @risk-officer 复核" % ev)
    lines.append("")
    lines.append(jince_edu.edu_section(s.get("items", []), ticks))
    lines.append("· 全员参与铁律: 本节点后各岗 30min 内接力发言(归纳/复核/认领), 漏接的 22:00 日报点名。历史回测≠未来收益。")
    text = "\n".join(lines)
    # 追加 discussion_log (带中间节点专属 key, 看门狗 NODE_KEYS 扩展后能识别)
    # [2026-10-08 补发机制] --noreceipt: 补投已生成的节点时不重复写 log (正文已落过), 防 30min 补发刷屏
    if "--noreceipt" not in sys.argv:
        try:
            rec = {"node": node_key, "ts": int(time.time()),
                   "beijing": datetime.datetime.now(BJT).strftime("%Y-%m-%d %H:%M"),
                   "gen": "no_agent_L0_middeep_429proof",
                   "recon": recon_rows, "evo": ev, "movers_n": len(movers), "ok": True}
            with open(os.path.join(DATA, "discussion_log.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception as e:
            text += "\n· [warn] discussion_log 写失败: %s" % e
    print(text)

if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != "--noreceipt" else None)
