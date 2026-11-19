#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策宗师团 · 后台训练每日验收 (no_agent 0 LLM, 429-proof)
用户令(2026-10-08): "不进场也要后台模拟训练, 要有训练机制" + "训练机制进一步完善".
[2026-10-09 坚决执行修正] 根账: 旧版把 6.7h 的全宇宙回测塞进 900s 超时 subprocess, 每天 01:30 枪永远超时→
报告①全是"降级空转", 制度=有闹钟没内容. 现改为: 每日 00:10 独立 no_agent 后台跑全宇宙(training_full_universe.py,
不限时), 01:30 本枪只验收上一轮 backtest_edge.json + 读 backtest_edge_run_stamp.json 判"有没有新产物+引擎自检哨兵".
读不到当日/近 36h 内新产物 → 报告 fail-loud(不静默降级), 看门狗抓 delivery_queued/failed 补投.
三步(单步崩不影响其余, 但 ① 验收必须报 fail-loud):
  1) 验收回测产物: 读 backtest_edge.json + run_stamp (判 新鲜度<=36h + engine_selfcheck_pass)
  2) 交叉五验: 读五验队列 WATCH/OBSERVE/PENDING 卡, 对照回测正 edge 候选, 标 攒够升级/继续观察
  3) 出报告: 写 data/training_daily_report_YYYYMMDD.md + 投群正文(stdout); 验收不过 fail-loud 抬头报
红线: 历史回测≠未来收益; 只给样本攒进度不给方向指令; 不动实盘挂单/持仓.
"""
import os, json, time, subprocess, datetime, zoneinfo, glob

DATA = r"E:/GoldstrategyEngine/data"
ATE = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/pythonw.exe"
ROOT = r"E:\GoldstrategyEngine"
try:
    BJT = zoneinfo.ZoneInfo("Asia/Shanghai")
except Exception:
    # 11-16 根修: 无 tzdata 的机器(Windows uv python) fallback 固定 UTC+8 (北京无夏令时, 等价)
    BJT = datetime.timezone(datetime.timedelta(hours=8))

def step1_verify_backtest():
    """验收全宇宙回测产物(由 00:10 后台 no_agent 跑, 不限时). 判 新鲜度+引擎自检哨兵.
    读不到近 36h 内新产物 / 引擎自检不过 -> 返回 (None|out, fail_reason), 报告 fail-loud, 不静默降级."""
    edge_f = os.path.join(DATA, "backtest_edge.json")
    stamp_f = os.path.join(DATA, "backtest_edge_run_stamp.json")
    out = None
    if os.path.exists(edge_f):
        out = json.load(open(edge_f, encoding="utf-8"))
    stamp = {}
    if os.path.exists(stamp_f):
        stamp = json.load(open(stamp_f, encoding="utf-8"))
    gen_ts = out.get("generated") if out else None
    age_h = None
    if gen_ts:
        try:
            gt = datetime.datetime.fromisoformat(gen_ts)
            if gt.tzinfo is None:
                gt = gt.replace(tzinfo=datetime.timezone.utc)  # 引擎 generated 是 naive UTC
            age_h = (datetime.datetime.now(datetime.timezone.utc) - gt).total_seconds()/3600
        except Exception:
            age_h = 999
    if not out or not gen_ts:
        return None, "回测无产物(backtest_edge.json 缺失) -- 00:10 后台全宇宙 job 没跑成, 查 backtest_edge_run_stamp.json"
    if age_h > 36:
        return out, ("回测产物过期 %.0fh(>36h) -- 00:10 后台全宇宙 job 可能没跑成/超时, 见 run_stamp(rc/sentinel)" % age_h)
    # 引擎自检哨兵 [2026-10-13 L5-fix]: 现卷 fresh(<=36h) 时以现卷现算为准(同分母重算, 防冻结旧 stamp 顶锅):
    #   stamp 写戳晚于/先于现卷刷新都可能出现"stamp 指旧卷哨兵 + 现卷已 0 虚高"的分裂, 旧式信 stamp 连误报 3 天.
    if out and out.get("generated") and (age_h or 999) <= 36:
        live_bad = 0
        for _s, _dd in (out.get("per_symbol") or {}).items():
            for _n, _rr in (_dd.get("strats") or {}).items():
                if isinstance(_rr, dict) and _rr.get("n", 0) > 500 and (_rr.get("wr") or 0) > 0.9:
                    live_bad += 1
        if live_bad > 3:
            return out, ("引擎自检哨兵不过(现卷重算): 胜率虚高腿 %d 条(>3) -- 回测口径有偏, 本轮回测作废, @strategy-rd 认领修引擎触价判定" % live_bad)
    elif not stamp.get("engine_selfcheck_pass", True):
        # 现卷缺失/过期才退回 stamp 口径, 且明说依据
        if stamp.get("precheck_fail"):
            return out, ("00:10 全宇宙 job 快检崩(MT5终端/依赖), 无新卷 -- 查 backtest_engine_stderr.log, 非引擎触价问题; 池闸维持 suspended"
                         " stamp: %s" % json.dumps(stamp.get("stderr_tail", "")[-200:], ensure_ascii=False))
        return out, ("引擎自检哨兵不过(依据stamp, 现卷%s): 胜率虚高腿 %s 条(>3) -- 回测口径有偏, @strategy-rd 认领"
                     % ("已刷新" if out and out.get("generated") else "缺失", stamp.get("sentinels_high_wr_legs")))
    return out, None

def step1b_host_gate():
    """[2026-10-10 L5 双闸焊入] 宿主闸③自动验: 读 host_root_stamp.json (training_host_gate_check.py 00:30 实拉落盘).
    三件齐 (taskeng 自动枪父链追调度器根 ∧ 新卷覆盖 void ∧ 残链 36364 未当宿主) 缺任一件 → fail-loud 抬头报
    '双闸未销', 池单闸维持 suspended、出徒 0 放大. stamp 缺失(00:30 任务没跑成) 同样 fail-loud, 不静默."""
    f = os.path.join(DATA, "host_root_stamp.json")
    if not os.path.exists(f):
        return "双闸未销: host_root_stamp.json 缺失(00:30 宿主验任务没跑成) -- 池单闸维持 suspended, 出徒 0 放大"
    # [2026-11-12 根治] stamp 时效: 宿主验任务未跑(cron 未排/挂)→stamp 滞留旧数据, 旧 verdict 不可信.
    # >6h 判过期, 报"数据过期"而非拿 2 天前旧闸状态误报双闸未销 (11-12 实锤: stamp 11-10 滞留 2 天致 01:31 验收假阳性).
    import time as _t
    age_h = (_t.time() - os.path.getmtime(f)) / 3600.0
    st = json.load(open(f, encoding="utf-8"))
    if st.get("host_gate_fail") or st.get("verdict") != "PASS":
        stale_note = " [⚠️ stamp 已 %.1fh 未更新=宿主验任务没跑, 以下 verdict 为旧数据, 非现行闸状态; cron adb92b73b3a4 00:30 起重建]" % age_h if age_h > 6 else ""
        return "双闸未销: 宿主闸③ verdict=%s (%s) -- 池单闸维持 suspended, 出徒 0 放大%s" % (
            st.get("verdict"), "; ".join(st.get("fail_reasons", [])) or st.get("note", ""), stale_note)
    return None

# [2026-10-26 L5] 01:30 验收枪: 上游 00:10 全宇宙回测 job 处于"主动暂停"态时, 本轮转中性提示,
# 不再 FAIL-LOUD 刷屏(半个月来"上游停+下游照跑"造成 16 天假报警的根缺口). 上游重启用后自动恢复真验收,
# 不影响出徒闸门. 上游 job id 固定 0878a08d2a92.
def upstream_backtest_paused():
    try:
        jd = json.load(open(r"E:/workbuddy/国外模型/hermes/cron/jobs.json", encoding="utf-8"))
    except Exception:
        return None
    jobs = jd.get("jobs") if isinstance(jd, dict) else jd
    for j in jobs or []:
        if j.get("id") == "0878a08d2a92":
            if j.get("enabled") is False:
                pr = (j.get("paused_reason") or "原因见 jobs.json paused_reason").strip()
                return ("上游 00:10 全宇宙回测已主动暂停(%s) -> 验收枪本轮中性跳过(宿主闸/双闸同源, 均不 FAIL); "
                        "待引擎修复+重启用后自动恢复真验收. 池单闸维持 suspended, 出徒 0 放大." % pr)
            return None
    return None

def step2_cross_verify(out, fail_reason):
    """交叉五验: verdict/status 为 WATCH/OBSERVE/PENDING 的卡, 是否进回测正 edge 候选."""
    cands = {}
    if out and not fail_reason:
        for sym, d in (out.get("per_symbol") or {}).items():
            b = (d or {}).get("best")
            if b:
                cands[sym] = (b[0], b[1].get("pf"), b[1].get("n"), b[1].get("wr"))
    rows = []
    for f in sorted(glob.glob(os.path.join(DATA, "rd_verify_batch_*.json"))):
        try:
            b = json.load(open(f, encoding="utf-8"))
            cards = b.get("cards") or b.get("items") or []
        except Exception:
            continue
        for c in cards:
            v = c.get("verdict") or c.get("status") or ""
            vt = v.upper()
            if not any(k in vt for k in ("WATCH", "OBSERVE", "PENDING")):
                continue
            sym = c.get("symbol") or ""
            hit = cands.get(sym)
            rows.append({"file": os.path.basename(f), "id": c.get("id"), "sym": sym,
                         "verdict": v[:40],
                         "in_backtest": bool(hit),
                         "bt": ("pf=%s n=%s wr=%s" % (hit[1], hit[2], hit[3])) if hit else "不在正edge候选",
                         "action": "攒够样本→升级" if hit else "继续观察攒样本"})
    return cands, rows

def step3_report(out, fail_reason, cands, rows, today):
    lines = []
    lines.append("【金策后台训练·每日验收】%s %s UTC+8 (no_agent 0 LLM)" % (today, datetime.datetime.now(BJT).strftime("%H:%M")))
    if fail_reason:
        lines.append("!! FAIL-LOUD 验收不过: %s" % fail_reason)
    if out and not fail_reason:
        so = (out or {}).get("strategy_overall", {})
        if so:
            best = sorted(so.items(), key=lambda x: -(x[1].get("pf") if isinstance(x[1].get("pf"), (int, float)) else 0))[:5]
            lines.append("① 回测策略级整体edge(全宇宙 %s 品种, 产物 %s):" % (out.get("symbols_tested"), out.get("generated")))
            for name, a in best:
                lines.append("   %-8s n=%s pf=%s wr=%s" % (name, a.get("n"), a.get("pf"), a.get("wr")))
        lines.append("   正edge候选: %d 条(%s)" % (len(cands), ", ".join(sorted(cands.keys())) or "无"))
    lines.append("")
    lines.append("② 五验 WATCH/OBSERVE/PENDING 交叉(%d 条):" % len(rows))
    promoted = [r for r in rows if r["in_backtest"]]
    if promoted:
        for r in promoted[:6]:
            lines.append("   ✅ [%s·%s] %s -> 回测正edge(%s), 攒够可升级" % (r["id"], r["sym"], r["file"], r["bt"]))
    still = [r for r in rows if not r["in_backtest"]]
    if still:
        lines.append("   ⏳ 继续观察攒样本: %d 条未进回测正edge(%s)" % (len(still), ", ".join(r["id"] for r in still[:8]) or "无"))
    if rows:
        lines.append("   · 涉及品种: %s" % ", ".join(sorted(set(r['sym'] for r in rows if r['sym']))))
    lines.append("")
    lines.append("③ 训练口径: 后台 30min 全链天天攒样本(edge_tracker 164 腿) + 每日 00:10 全宇宙回测 + 01:30 验收交叉; 哪条腿样本≥30+胜率/盈亏比达标才放大实盘. 只给进度不给方向指令. 历史回测≠未来收益.")
    # [2026-10-08 L5桥接] 出徒进度台账: 每腿 OOS x/30 + 出徒四件齐, 每日自动刷新
    try:
        tr = json.load(open(os.path.join(DATA, "training_graduation_tracker.json"), encoding="utf-8"))
        import time as _t
        et_ = json.load(open(os.path.join(DATA, "edge_tracker.json"), encoding="utf-8"))
        for leg in tr.get("legs", []):
            sym_ = leg["leg"].replace(".NAS", "") if leg["leg"] == "RIVN.NAS" else leg["leg"]
            n_ = et_["symbols"].get(sym_, {}).get("n", 0)
            leg["oos_now"] = n_
            leg["oos_remaining"] = max(0, leg.get("oos_target", 30) - n_)
            leg["last_refresh"] = int(_t.time())
        tr["updated_ts"] = int(_t.time())
        json.dump(tr, open(os.path.join(DATA, "training_graduation_tracker.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        lines.append("")
        lines.append("④ 出徒进度(L5台账, 每日自动刷新):")
        for leg in tr.get("legs", []):
            lines.append("   [%s] %s OOS %d/%d 差%d笔 | %s" % (
                "N" if leg["oos_remaining"] == 0 and leg.get("sl_required") else ".",
                leg["leg"], leg["oos_now"], leg.get("oos_target", 30), leg["oos_remaining"],
                "可提请L4二次APPROVE" if leg["oos_remaining"] == 0 else "继续攒样"))
    except Exception as e:
        lines.append("④ [warn] 出徒台账刷新失败: %s" % e)
    text = "\n".join(lines)
    try:
        rep = os.path.join(DATA, "training_daily_report_%s.md" % today)
        open(rep, "w", encoding="utf-8").write(text + "\n\n--- 正edge候选全量 ---\n" + json.dumps(
            {"per_symbol_best": {k: v for k, v in cands.items()}, "fail_loud": fail_reason}, ensure_ascii=False, indent=1))
    except Exception as e:
        text += "\n· [warn] 报告落盘失败: %s" % e
    return text

if __name__ == "__main__":
    today = datetime.datetime.now(BJT).strftime("%Y-%m-%d")
    out, fail_reason = step1_verify_backtest()
    # [2026-10-26 L5] 上游 00:10 全宇宙回测 job 主动暂停 -> 本轮验收枪转中性, 不 FAIL-LOUD 刷屏;
    #   宿主闸同源同源跳过(它判 FAIL 也是"没新产物"的同因). 上游重启用后自动恢复真验收.
    neutral_note = upstream_backtest_paused()
    host_fail = step1b_host_gate()
    if neutral_note:
        # 吞掉 fail_reason + host_fail(均同因: 上游停 -> 无新产物 -> 宿主链断), 改中性提示
        fail_reason = None
        host_fail = None
    else:
        if host_fail and not fail_reason:
            fail_reason = host_fail
        elif host_fail and fail_reason:
            fail_reason = fail_reason + " || " + host_fail
    cands, rows = step2_cross_verify(out, fail_reason if not neutral_note else None)
    text = step3_report(out, fail_reason, cands, rows, today)
    if neutral_note:
        text = "【金策后台训练·每日验收】%s (no_agent 0 LLM) · 上游暂停中性档\n" % today + \
               "· " + neutral_note + "\n" + text
    print(text)
