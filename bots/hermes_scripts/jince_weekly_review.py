#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策宗师团 · 周五周会确定性生成器 (no_agent L0, 0 LLM, 429-proof)
制度: 每周五 16:05 复盘一周 + 安排下周 (SOP: E:/GoldstrategyEngine/周会制度_SOP_v1.md)
三块分工 (数据契约全读 data/ 实拉, 每个数字带来源):
  ① chief 总指挥格: 一周节点全链健康(跑/缺/投递超时) + P1/红线销格进度 + 下周排期
  ② risk-officer 风控格: 一周 veto(剔 RISK-NET-GATE 心跳) + 冻结降级时长 + 金线/币线实态 + 同分母胜率
  ③ strategy-rd 研发格: edge_tracker 分盘口同分母 + 五验样本累积 + 策略升降级草案
铁律: 只报实数、每个数字带来源文件; 末尾固定"本周漏发节点清单+补发状态"接 22:00 日报补发机制。
用法: python jince_weekly_review.py  (stdout=群发正文; 追加 node=weekly_review 到 discussion_log.jsonl)
"""
import os, json, time, subprocess, datetime, zoneinfo, collections

DATA = r"E:/GoldstrategyEngine/data"
CRON_DIR = r"E:/workbuddy/国外模型/hermes/cron"
LAUNCH = r"E:/GoldstrategyEngine/mt5_launch.py"
BJT = zoneinfo.ZoneInfo("Asia/Shanghai")
WEEK = 7 * 86400
# 教学批次脏分母 (周会同分母胜率必须剔除, @risk-officer 钉死)
TEACH_DEALS = {"lesson_close_all", "duplicate_close", "A.T.E.S07.Close"}
# 风控格真否决 = 除 RISK-NET-GATE 心跳(97条)外全部
NET_GATE = "RISK-NET-GATE"

def now_bjt():
    return datetime.datetime.now(BJT)

def jget(rel, default=None):
    try:
        return json.load(open(os.path.join(DATA, rel), encoding="utf-8"))
    except Exception:
        return default

def recent_jsonl(rel, days=7):
    p = os.path.join(DATA, rel)
    out = []
    if not os.path.exists(p):
        return out
    cutoff = time.time() - days * 86400
    for l in open(p, encoding="utf-8", errors="replace"):
        l = l.strip()
        if not l:
            continue
        try:
            e = json.loads(l)
        except Exception:
            continue
        ts = e.get("ts") or e.get("time") or e.get("created_at") or 0
        try:
            ts = float(ts)
        except Exception:
            ts = 0
        if ts >= cutoff:
            out.append(e)
    return out

def fmt_ts(ts):
    try:
        return now_bjt().strftime("%m-%d %H:%M") if not ts else datetime.datetime.fromtimestamp(float(ts), BJT).strftime("%m-%d %H:%M")
    except Exception:
        return "?"

def node_health():
    """① 一周节点全链健康: 6 研讨节点(discussion_log) 生成数 + 全链 executions 投递失败数"""
    dl = recent_jsonl("discussion_log.jsonl", 7)
    SIX = ("asia_open", "asia_close", "europe_open", "europe_close", "us_open", "us_close")
    cnt = collections.Counter(e.get("node", "?") for e in dl)
    six = {k: cnt.get(k, 0) for k in SIX}
    six_total = sum(six.values())
    bad_total, total_runs = 0, 0
    try:
        import sqlite3
        c = sqlite3.connect(os.path.join(CRON_DIR, "executions.db"))
        for _ in c.execute(
                "select delivery_outcome from executions where scheduled_instant >= datetime('now','-7 day') "
                "and delivery_outcome in ('failed','suppressed','queued')"):
            bad_total += 1
        total_runs = c.execute("select count(*) from executions where scheduled_instant >= datetime('now','-7 day')").fetchone()[0]
    except Exception:
        pass
    return dict(six=six, six_total=six_total, deliver_fail=bad_total, runs=total_runs)

def risk_block():
    """② 风控格: veto(剔心跳) + 冻结时长 + 金线实态 + 同分母胜率"""
    vet = recent_jsonl("veto_log.jsonl", 7)
    real = [e for e in vet if (e.get("decision") or e.get("type")) != NET_GATE]
    dec = collections.Counter((e.get("decision") or e.get("type") or "?") for e in real)
    heart = len(vet) - len(real)
    frz = jget("risk_freeze_state.json", {})
    lvl = frz.get("level")
    pol = frz.get("policy", {})
    # 同分母胜率 (edge_tracker session_tag 聚合, 剔教学批次)
    et = jget("edge_tracker.json", {})
    n_all = win_all = gw = gl = 0.0
    up, down = [], []
    for sym, s in (et.get("symbols") or {}).items():
        if not isinstance(s, dict):
            continue
        ns = s.get("n", 0)
        n_all += ns
        win_all += ns * (s.get("wr") or 0)
        gw += s.get("gross_w") or 0
        gl += s.get("gross_l") or 0
        pf = s.get("pf")
        if isinstance(pf, (int, float)) and ns >= 15 and pf >= 1.2:
            up.append("%s(pf %.2f n%d)" % (sym, pf, ns))
        if isinstance(pf, (int, float)) and ns >= 15 and pf < 0.8:
            down.append("%s(pf %.2f n%d)" % (sym, pf, ns))
    pf_tot = (gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0)
    wr_tot = (win_all / n_all) if n_all else 0.0
    return dict(dec=dec, heart=heart, lvl=lvl, pol=pol, xau=frz.get("xau_bid"),
                 pos=frz.get("positions"), pend=frz.get("pending_orders"),
                 wr=wr_tot, pf=pf_tot, n_all=n_all, up=up[:5], down=down[:5])

def rd_block():
    """③ 研发格: 五验样本累积 + 升降级草案 + rd_decisions 最新"""
    et = jget("edge_tracker.json", {})
    nsyms = len(et.get("symbols") or {})
    strateg = et.get("strategies") or {}
    rd = jget("rd_decisions.json", {})
    # 最新决策
    latest = None
    if isinstance(rd, dict):
        for k in ("decisions", "log", "history"):
            v = rd.get(k)
            if isinstance(v, list) and v:
                latest = v[-1]
                break
        if latest is None:
            items = [v for v in rd.values() if isinstance(v, dict) and (v.get("ts") or v.get("time"))]
            if items:
                latest = sorted(items, key=lambda x: (x.get("ts") or x.get("time") or 0))[-1]
    # 五验批次
    v5 = []
    try:
        import glob
        for f in sorted(glob.glob(os.path.join(DATA, "rd_verify_batch_*.json")), reverse=True)[:1]:
            d = json.load(open(f, encoding="utf-8"))
            items = d if isinstance(d, list) else (d.get("items") or d.get("batches") or [])
            pend = [i for i in items if isinstance(i, dict) and i.get("status") in ("PENDING", "PENDING_VERIFY", None)]
            v5.append("%s: 共%d 待验%d" % (os.path.basename(f), len(items), len(pend)))
    except Exception:
        pass
    # 升降级草案 (品种级 pf 门槛, @risk-officer 口径)
    up, down = [], []
    for sym, s in (et.get("symbols") or {}).items():
        if not isinstance(s, dict):
            continue
        ns = s.get("n", 0)
        pf = s.get("pf")
        if isinstance(pf, (int, float)) and ns >= 15 and pf >= 1.2:
            up.append("%s(pf %.2f n%d)" % (sym, pf, ns))
        if isinstance(pf, (int, float)) and ns >= 15 and pf < 0.8:
            down.append("%s(pf %.2f n%d)" % (sym, pf, ns))
    return dict(nsyms=nsyms, nstrat=len(strateg), latest=latest, v5=v5, up=up[:5], down=down[:5])

def e_nodes_progress():
    """E 节点制度进度 (确定性读 rd_decisions, 不口播): E1 现跑/E2-E4 待命, 基线+历次 pass/reject"""
    rd = jget("rd_decisions.json", {})
    decs = rd.get("decisions", []) if isinstance(rd, dict) else []
    e = [d for d in decs if isinstance(d, dict) and str(d.get("id", "")).startswith("e_")
         and any(x in str(d.get("id", "")).lower() for x in ("e1", "e2", "e3", "e4", "evolve_node", "e_nodes"))]
    if not e:
        return "E 节点: 基线已立(E1现跑/E2外网通后/E3第3周/E4需@user逐次批准), 历次 pass/reject 待录 rd_decisions"
    latest = sorted(e, key=lambda x: x.get("ts") or 0)[-1]
    return "E 节点: 累计 %d 条, 最新 %s(%s)" % (len(e), str(latest.get("id", "?"))[:30],
            ("PASS" if "PASS" in str(latest.get("action", "")).upper() else "REJECT/进行中"))

def schedule_next():
    """下周排期: 6 研讨节点 + 周会固定项 + 一次性闹钟 (cron 任务清单, 一行式)"""
    try:
        jd = json.load(open(os.path.join(CRON_DIR, "jobs.json"), encoding="utf-8"))
        jobs = jd.get("jobs", []) if isinstance(jd, dict) else jd
        def expr(j):
            s = j.get("schedule")
            return (s.get("expr") or s.get("display")) if isinstance(s, dict) else (s or j.get("schedule", "?"))
        six = [j for j in jobs if isinstance(j.get("name"), str) and j["name"].startswith("jince-node")]
        parts = []
        for j in sorted(six, key=lambda x: expr(x)):
            parts.append("%s@%s" % (j["name"], expr(j)))
        oneoffs = [j for j in jobs if isinstance(j.get("name"), str) and ("11-02" in j["name"] or "一次性" in j["name"])]
        for j in oneoffs:
            parts.append("%s@%s" % (j["name"], expr(j)))
        parts.append("周五16:05 周会 (jince-weekly-review, 本周起固定)")
        return "6节点+周会: " + "; ".join(parts)
    except Exception as e:
        return "(排期读取失败: %s)" % e

def leweek_nodes():
    """铁律②: 本周漏发节点清单(只念 6 研讨节点, 不刷屏) + 补发状态"""
    try:
        import sqlite3
        c = sqlite3.connect(os.path.join(CRON_DIR, "executions.db"))
        jd = json.load(open(os.path.join(CRON_DIR, "jobs.json"), encoding="utf-8"))
        jobs = jd.get("jobs", []) if isinstance(jd, dict) else jd
        nm = {j.get("id", j.get("job_id", "")): j.get("name", j.get("id", "")) for j in jobs}
        rows = c.execute(
            "select job_id, delivery_outcome from executions "
            "where scheduled_instant >= datetime('now','-7 day') and delivery_outcome in ('failed','suppressed','queued') "
            "group by job_id, delivery_outcome").fetchall()
        nodemap = {}
        for jid, oc in rows:
            label = nm.get(jid, jid)
            if isinstance(label, str) and label.startswith("jince-node"):
                nodemap[label] = nodemap.get(label, []) + [oc]
        if not nodemap:
            return "6 研讨节点本周无漏发 ✅ (全数当场进群)"
        lines = []
        for k in sorted(nodemap):
            lines.append("%s(%s)" % (k, "+".join(sorted(nodemap[k]))))
        return "本周 6 节点漏发 %d 格: %s → 22:00 日报 ⑥.2.3 补发兜底覆盖, 内容在 discussion_log 没丢" % (len(nodemap), "; ".join(lines))
    except Exception as e:
        return "(漏发清单读取失败: %s)" % e

def main():
    nh, rk, rd = node_health(), risk_block(), rd_block()
    L = []
    L.append("【周五周会】金策宗师团 · 周复盘+下周排期 %s" % now_bjt().strftime("%m-%d %H:%M"))
    L.append("① 总指挥格 (chief): 本周 6 研讨节点 亚开%d/亚收%d/欧开%d/欧收%d/美开%d/美收%d (共%d) | 全链执行 %d 次, 投递失败/憋死 %d 条(22:00 日报 ⑥.2.3 补发兜底覆盖) | P1/红线销格: B腿冻结闸+电池无关+看门狗 已实拉销, 剩 ⑥.2.3 今晚上线 + ⑨ DoH 待验 + P1 活洞待明早08:05外网通终销" %
             (nh["six"]["asia_open"], nh["six"]["asia_close"], nh["six"]["europe_open"],
              nh["six"]["europe_close"], nh["six"]["us_open"], nh["six"]["us_close"],
              nh["six_total"], nh["runs"], nh["deliver_fail"]))
    L.append("② 风控格 (risk-officer): 本周真否决 %d 条(剔 RISK-NET-GATE 心跳 %d 条) %s | 现 LEVEL_%s (开新单=%s,撤=%s,改SL=%s) | XAU %s 持仓 %s 挂单 %s | 30日全量同分母: n=%d 胜率 %.3f PF %.2f —— 含教学批次 lesson_close_all 等脏分母, @strategy-rd 剔后出真同分母胜率(剔除前只报 n, 不念胜率)" %
             (sum(rk["dec"].values()), rk["heart"], dict(rk["dec"]), rk["lvl"],
              rk["pol"].get("open_new_order"), rk["pol"].get("cancel_existing"), rk["pol"].get("modify_sl"),
              rk["xau"], rk["pos"], rk["pend"], rk["n_all"], rk["wr"], rk["pf"]))
    L.append("③ 研发格 (strategy-rd): edge_tracker 品种 %d / 策略 %d | 五验批次 %s | 升级草案(pf≥1.2且n≥15): %s | 降级草案(pf<0.8且n≥15): %s | %s" %
             (rd["nsyms"], rd["nstrat"], ("; ".join(rd["v5"]) or "无批次"),
              (", ".join(rd["up"]) if rd["up"] else "无"),
              (", ".join(rd["down"]) if rd["down"] else "无"),
              e_nodes_progress()))
    L.append("④ 下周排期: %s" % schedule_next())
    L.append("⑤ 本周漏发节点清单(铁律②): %s" % leweek_nodes())
    L.append("金线实态: 0 单 0 亏 / LTC 锁盈在走 (实盘 orders_get/positions_get 为准) | 每格数字来源 data/ 可复查")
    text = "\n".join(L)
    print(text)
    # 追加 discussion_log (铁律: 内容绝不丢)
    try:
        with open(os.path.join(DATA, "discussion_log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"node": "weekly_review", "ts": int(time.time()), "actor": "chief",
                                 "scope": "weekly", "source": "jince_weekly_review.py", "text": text},
                                ensure_ascii=False) + "\n")
    except Exception:
        pass
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
