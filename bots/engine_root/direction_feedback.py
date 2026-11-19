#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策·研判→做单 方向反馈环 (no_agent 0 LLM, 429-proof)
用户令(2026-10-10): "学会根据分析优化做单方向, 不能只分析不会做单".
实数底座: daily_advisory 天天出 150 项方向研判(方向+置信+形态), 但全链出候选 0 读它(断线);
半日对账 66 条 recon 已记 命中30/做反32(总准头 0.48=噪音), 但没拿回去优化.
本环三件:
  1) 准头表: 按 品种×方向 聚合 recon(命中/做反) -> data/direction_feedback.json(总准头+分品种准头)
  2) 方向闸: 30min 出候选时查准头表——
       品种总样本>=5 且 准头>=0.60 且 候选方向==研判方向 -> 提权 WATCH->PROMOTE(仍只进WATCH, 放大走出徒四件齐)
       品种总样本>=5 且 准头<0.40 -> 候选方向==研判方向时 降级 只做否决门(不正向提权, 铁律不变)
       样本<5 -> 维持原 WATCH(证据不够不表态)
  3) 巡检: 准头表>48h没刷新 或 recon 一天0条 -> fail-loud(反馈环断了)
红线: 提权不提仓(仍走出徒四件齐); 研判只做否决门+提权, 不单独开仓; 历史回测≠未来收益.
"""
import os, json, glob, datetime, time, re, sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = r"E:/GoldstrategyEngine"
DATA = ROOT + "/data"
FB = os.path.join(DATA, "direction_feedback.json")
LOGF = os.path.join(DATA, "discussion_log.jsonl")
PROMOTE_TH = 0.60   # 准头>=0.60 才提权
VETO_TH = 0.40      # 准头<0.40 降级只做否决门
MIN_N = 5           # 样本<5 不表态

def parse_recon():
    """从 discussion_log.jsonl 抽 recon 行, 返回 {sym: {hit:int, rev:int, na:int}}."""
    stat = {}
    tot = 0
    for line in open(LOGF, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        for r in (d.get("recon") or []):
            tot += 1
            m = re.match(r"^(\S+)\s+研判=(\S+)\s+开评=([\d.]+)\s+现=([\d.]+)\s+偏=([+\-]?[\d.]+)%", r)
            if not m:
                continue
            sym, verdict = m.group(1), r
            s = stat.setdefault(sym, {"hit": 0, "rev": 0, "na": 0})
            if "命中" in verdict:
                s["hit"] += 1
            elif "做反" in verdict:
                s["rev"] += 1
            else:
                s["na"] += 1
    return stat, tot

def build_feedback():
    stat, tot = parse_recon()
    now = datetime.datetime.now()
    out = {
        "ts": now.isoformat(),
        "total_recon": tot,
        "overall_hit": sum(v["hit"] for v in stat.values()),
        "overall_rev": sum(v["rev"] for v in stat.values()),
        "sym": {},
    }
    for sym, v in stat.items():
        n = v["hit"] + v["rev"]
        out["sym"][sym] = {
            "n": n,
            "hit": v["hit"],
            "rev": v["rev"],
            "acc": round(v["hit"] / n, 3) if n else None,
            "action": ("promote" if n >= MIN_N and v["hit"] / n >= PROMOTE_TH
                       else "veto_only" if n >= MIN_N and v["hit"] / n < VETO_TH
                       else "insufficient"),
        }
    json.dump(out, open(FB, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out

def gate_lines(fb):
    """出报告行: 提权/降级/不表态 + 巡检."""
    lines = []
    prom = [s for s, v in (fb.get("sym") or {}).items() if v.get("action") == "promote"]
    veto = [s for s, v in (fb.get("sym") or {}).items() if v.get("action") == "veto_only"]
    insuf = [s for s, v in (fb.get("sym") or {}).items() if v.get("action") == "insufficient"]
    lines.append("① 方向闸: 提权 %s | 降级只做否决门 %s | 样本不足不表态 %d 品种" % (
        ", ".join(prom) or "无", ", ".join(veto) or "无", len(insuf)))
    for s in prom:
        v = fb["sym"][s]
        lines.append("   ✅ [%s] 准头 %.2f (n=%d) -> 候选方向==研判方向时 WATCH->PROMOTE(仍只进WATCH, 放大走出徒四件齐)" % (s, v["acc"], v["n"]))
    for s in veto:
        v = fb["sym"][s]
        lines.append("   ⚠️ [%s] 准头 %.2f (n=%d) -> 候选方向==研判方向时 只做否决门不正向提权(铁律)" % (s, v["acc"], v["n"]))
    # 巡检
    try:
        age_h = (datetime.datetime.now() - datetime.datetime.fromisoformat(fb["ts"])).total_seconds() / 3600
        if age_h > 48:
            lines.append("   ⚠️ [巡检] 准头表 %.0fh 未刷新(>48h) -> 对账半日节点没跑/断环, @hermes 查半日对账" % age_h)
        if fb.get("total_recon", 0) == 0:
            lines.append("   ⚠️ [巡检] recon 总条数 0 -> 反馈环无数据, 检查半日对账输出")
    except Exception as e:
        lines.append("   ⚠️ [巡检] 准头表解析异常: %s" % str(e)[:40])
    return lines

if __name__ == "__main__":
    fb = build_feedback()
    tot = fb.get("total_recon", 0)
    print("【研判→做单 方向反馈环】%s (no_agent 0 LLM)" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("研判方向准头: 命中%d/做反%d (总%.2f, 样本%d条)" % (fb["overall_hit"], fb["overall_rev"],
          round(fb["overall_hit"] / max(1, fb["overall_hit"] + fb["overall_rev"]), 2), tot))
    for ln in gate_lines(fb):
        print(ln)
    print("口径: 提权不提仓(放大仍走出徒四件齐); 研判只做否决门+提权; 历史回测≠未来收益.")
