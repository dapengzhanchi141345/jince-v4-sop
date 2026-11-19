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
BJT = zoneinfo.ZoneInfo("Asia/Shanghai")

def step1_verify_backtest():
    """验收全宇宙回测产物. [2026-11-04 L5③] detached 启动后 wrapper 不再算哨兵/广度, 验收枪自读
    backtest_edge.json 真产物 + 判 in-progress(引擎收工中, 软注不销账) + 空卷广度(根因①回归).
    读不到近 36h 内新产物 / 引擎触价口径不过 / 空卷 -> 返回 (None|out, fail_reason), fail-loud, 不静默降级."""
    edge_f = os.path.join(DATA, "backtest_edge.json")
    stamp_f = os.path.join(DATA, "backtest_edge_run_stamp.json")
    out = None
    if os.path.exists(edge_f):
        out = json.load(open(edge_f, encoding="utf-8"))
    stamp = {}
    if os.path.exists(stamp_f):
        stamp = json.load(open(stamp_f, encoding="utf-8"))
    # [③] in-progress 判定: 已有引擎在跑(in_progress), 或本枪 launched 但产物 generated 早于 launch_ts
    #   (detached 引擎还没写完新卷, 读到的 out 仍是上一卷) -> 软注, 不销账.
    in_progress = bool(stamp.get("in_progress"))
    if stamp.get("launched") and out and out.get("generated"):
        try:
            _gen_t = datetime.datetime.fromisoformat(str(out.get("generated"))[:19]).replace(tzinfo=datetime.timezone.utc)
            _l_t = datetime.datetime.fromisoformat(str(stamp.get("launch_ts", "2000-01-01T00:00:00"))[:19]).replace(tzinfo=datetime.timezone.utc)
            if _gen_t < _l_t:
                in_progress = True
        except Exception:
            pass
    # [2026-11-04 L5③v2] 防"卡死在 in-progress": 时间戳判 in-progress(产物比 launch 旧) 但实际无 backtest_engine.py 进程
    #   = 引擎崩了/收工没写新卷, 不是"还在跑" -> 摘掉 in-progress, 让它走 FAIL-LOUD(空卷/哨兵/过期) 而非永远软注.
    if in_progress:
        import subprocess as _sp
        try:
            _wo = _sp.run('wmic process where "CommandLine like \'%backtest_engine.py%\'" get ProcessId /FORMAT LIST',
                          shell=True, capture_output=True, text=True, timeout=25).stdout
            _ep = [x for x in _wo.replace('\r', '').split() if x.isdigit() and int(x) != os.getpid()]
            if not _ep:
                in_progress = False
        except Exception:
            pass
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
        if in_progress:
            return None, ("IN_PROGRESS: 引擎 pid=%s 收工中(00:10 detached 启动, 预计 ~02:46 收工), 本拍不销账, 收工后下枪读真产物验新卷; 历史回测≠未来收益"
                          % (stamp.get("reusing_engine_pid") or stamp.get("engine_pid")))
        return None, "回测无产物(backtest_edge.json 缺失) -- 00:10 后台全宇宙 job 没跑成, 查 backtest_edge_run_stamp.json"
    # [②] 引擎自检哨兵(枪侧算): n>500 & 触价率>0.97(不可能区) 的腿 -> 引擎/数据口径事故, 打回.
    #   0.9~0.97 是真·高胜率腿(策略属性), 不算口径事故(铁律: 高胜率≠正期望, 只与否决门).
    bad = 0
    for _sym, _dd in (out.get("per_symbol") or {}).items():
        for _name, _rr in (_dd.get("strats") or {}).items():
            if isinstance(_rr, dict) and _rr.get("n", 0) > 500 and (_rr.get("wr") or 0) > 0.97:
                bad += 1
    # [①] 空卷广度(枪侧算): 期望池=stamp.expected_pool(本 job argv=PO6 6腿池), 缺省才全宇宙 tradable.
    #   治 chief 点名的"breadth 假空卷"(PO6 job 拿全宇宙当期望池 -> 永远 6/40 判空卷).
    empty_volume = bool((stamp or {}).get("empty_volume"))
    try:
        _expected = [s for s in (stamp.get("expected_pool") or []) if s]
        if not _expected:   # FULL(无 argv)或旧 stamp 无该字段 -> 全宇宙 tradable
            import importlib
            _su = importlib.import_module("symbol_universe")
            _expected = [k for k, v in _su.UNIVERSE.items() if v.get("tradable", True)]
        _covered = {s for s, sd in (out.get("per_symbol") or {}).items()
                   if any((r.get("n") or 0) > 0 for r in (sd.get("strats") or {}).values() if isinstance(r, dict))}
        empty_volume = empty_volume or not (set(_expected) <= _covered)
    except Exception:
        pass
    if in_progress:
        return out, ("IN_PROGRESS: 引擎 pid=%s 收工中, 本拍不销账; 已验上一卷: 胜率哨兵不过腿 %d, 空卷=%s, %d 信号; 收工后下枪验新卷"
                     % (stamp.get("reusing_engine_pid") or stamp.get("engine_pid"), bad, empty_volume, (out.get("n_signals") or 0)))
    if age_h is not None and age_h > 36:
        return out, "回测产物过期 %.0fh(>36h) -- 00:10 全宇宙 job 没跑成/超时, 见 run_stamp" % age_h
    if bad > 0:
        return out, "引擎自检哨兵不过: 触价率>0.97&n>500 的腿 %d 条 -- 回测口径有偏, 本轮作废, @strategy-rd 修引擎触价判定" % bad
    if empty_volume:
        return out, "EMPTY_VOLUME: 腿池广度不过(空卷) -- 根因① TIMECAP 空卷复发, 转查 tf_cache 缓存/IPC 成交匹配, 不得销账"
    return out, None

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
            # [2026-10-14 L5-fix] 治本: 有些 rd_verify_batch card 只带人类描述 item、无机器 id
            #   (rd_verify_batch_20261013 4 张全 item 无 id) -> 旧 c.get("id")=None, 下游 join 崩 exit1.
            #   兜底取 item, 机器 id 缺失不再 None.
            rows.append({"file": os.path.basename(f), "id": c.get("id") or c.get("item"), "sym": sym,
                         "verdict": v[:40],
                         "in_backtest": bool(hit),
                         "bt": ("pf=%s n=%s wr=%s" % (hit[1], hit[2], hit[3])) if hit else "不在正edge候选",
                         "action": "攒够样本→升级" if hit else "继续观察攒样本"})
    return cands, rows

def step3_report(out, fail_reason, cands, rows, today):
    lines = []
    lines.append("【金策后台训练·每日验收】%s %s UTC+8 (no_agent 0 LLM)" % (today, datetime.datetime.now(BJT).strftime("%H:%M")))
    if fail_reason:
        if fail_reason.startswith("IN_PROGRESS:"):
            lines.append("⏳ %s" % fail_reason)
        else:
            lines.append("!! FAIL-LOUD 验收不过: %s" % fail_reason)
    if out and not fail_reason:
        so = (out or {}).get("strategy_overall", {})
        if so:
            best = sorted(so.items(), key=lambda x: -(x[1].get("pf") if isinstance(x[1].get("pf"), (int, float)) else 0))[:5]
            lines.append("① 回测策略级整体edge(全宇宙 %s 品种, 产物 %s):" % (out.get("symbols_tested"), out.get("generated")))
            for name, a in best:
                lines.append("   %-8s n=%s pf=%s wr=%s" % (name, a.get("n"), a.get("pf"), a.get("wr")))
        lines.append("   正edge候选: %d 条(%s)" % (len(cands), ", ".join(sorted(cands.keys())) or "无"))
    elif out and fail_reason and fail_reason.startswith("IN_PROGRESS:"):
        so = (out or {}).get("strategy_overall", {})
        if so:
            best = sorted(so.items(), key=lambda x: -(x[1].get("pf") if isinstance(x[1].get("pf"), (int, float)) else 0))[:5]
            lines.append("   上一卷策略级edge(%s 品种, 产物 %s), 引擎收工后自动刷新:" % (out.get("symbols_tested"), out.get("generated")))
            for name, a in best:
                lines.append("   %-8s n=%s pf=%s wr=%s" % (name, a.get("n"), a.get("pf"), a.get("wr")))
    lines.append("")
    lines.append("② 五验 WATCH/OBSERVE/PENDING 交叉(%d 条):" % len(rows))
    promoted = [r for r in rows if r["in_backtest"]]
    if promoted:
        for r in promoted[:6]:
            lines.append("   ✅ [%s·%s] %s -> 回测正edge(%s), 攒够可升级" % (r.get("id") or r.get("item") or "?", r["sym"], r["file"], r["bt"]))
    still = [r for r in rows if not r["in_backtest"]]
    if still:
        # [2026-10-14 L5-fix] 治本: join 前 None 兜底(防任何 card 缺 id+item 时整脚本崩, 今晨 01:30 崩 exit1 根因).
        _still_ids = ", ".join(str(r.get("id") or r.get("item") or "?") for r in still[:8]) or "无"
        lines.append("   ⏳ 继续观察攒样本: %d 条未进回测正edge(%s)" % (len(still), _still_ids))
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
    cands, rows = step2_cross_verify(out, fail_reason)
    print(step3_report(out, fail_reason, cands, rows, today))
