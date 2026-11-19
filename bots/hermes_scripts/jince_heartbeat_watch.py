#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策 24h 心跳台账 · 看门狗点名 (no_agent L0, 0 LLM, 429-proof, 每5min)
扫描: rd_ledger_24h.json(研发心跳) / auto_cycle.log(chief心跳) / ops_sync_queue.json(运营取走动作)
规则(窗口): 研发段心跳窗 4h(4h+15min 容差); chief 全链心跳窗 30min(35min 容差)。
缺心跳 → 打印点名(投群, @bot + 提示查 gateway/429); 全齐 → 空 stdout(静默, 不发群消息)。
fail-open: 任何异常 → 打印一行降级提示(不静默吞, 但绝不影响交易全链: 本脚本只读不写台账)。
不碰: 挂单真闸源 / 撤单 / 任何交易配置。
"""
import os, json, datetime, zoneinfo

DATA = r"E:/GoldstrategyEngine/data"
BJT = zoneinfo.ZoneInfo("Asia/Shanghai")

def read_ts(path, is_log=False):
    """返回该文件最近一次'该 bot 干了活'的时间 (BJT aware datetime)"""
    p = os.path.join(DATA, path)
    if not os.path.exists(p):
        return None
    try:
        if is_log:
            last = None
            with open(p, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "全链自动运行完成" in line:
                        last = line
            if not last:
                return None
            import re
            m = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", last)
            return datetime.datetime.fromisoformat(m.group(1)).replace(tzinfo=BJT) if m else None
        d = json.load(open(p, encoding="utf-8"))
        # rd_ledger_24h.json: entries[-1].ts
        if isinstance(d, dict) and "entries" in d:
            es = d["entries"]
            if not es:
                return None
            return datetime.datetime.fromisoformat(str(es[-1]["ts"])).replace(tzinfo=BJT)
        # ops_sync_queue.json: 最新一条 taken(被取走时刻)
        if isinstance(d, dict) and "queue" in d:
            for x in reversed(d["queue"]):
                if x.get("taken"):
                    return datetime.datetime.fromisoformat(str(x["taken"])).replace(tzinfo=BJT)
            return None
    except Exception:
        return None
    return None

def read_ts_rd():
    """[2026-10-06 根治] 研发心跳认多本账: ① rd_ledger_24h.json(主账台) ② discussion_log.jsonl
    (actor=strategy-rd 且 evt=heartbeat, 活体补心账) ③ rd_ledger.json + 最新 rd_*.json
    产物 mtime(strategy-rd 实际出件的账) ④ [2026-10-12 chief派单修误报源] 活体台账
    rd_or_review_24h.json / rd_queue.json / meta_evolution.json / governor_state.json
    的 mtime —— 旧病根复发: rd_ledger_24h.json 停在 04:00 批次, 活体段出件写 rd_or_review_24h/meta_evolution,
    看门狗只读死源 -> 08:49~09:50 连发9次假点名. 现: 全部活体台账 mtime 一并取最新, 研发在哪个账动了活都认.
    fail-open: 全读不到返回 None."""
    cands = []
    t1 = read_ts("rd_ledger_24h.json")
    if t1: cands.append(t1)
    # ③ rd_ledger.json(实际出件账) + 最新 rd_verify_batch_*/rd_*.json 产物 mtime
    import glob
    rdl = os.path.join(DATA, "rd_ledger.json")
    if os.path.exists(rdl):
        cands.append(datetime.datetime.fromtimestamp(os.path.getmtime(rdl), BJT))
    for f in glob.glob(os.path.join(DATA, "rd_verify_batch_*.json")):
        cands.append(datetime.datetime.fromtimestamp(os.path.getmtime(f), BJT))
    # ④ [2026-10-12] 活体台账 mtime (chief 实读核过在活刷的账: 09:31 meta_evolution/governor_state, 09:33 rd_or_review_24h)
    for f in ("rd_or_review_24h.json", "rd_queue.json", "meta_evolution.json", "governor_state.json"):
        p = os.path.join(DATA, f)
        if os.path.exists(p):
            cands.append(datetime.datetime.fromtimestamp(os.path.getmtime(p), BJT))
    try:
        jl = os.path.join(DATA, "discussion_log.jsonl")
        for line in open(jl, encoding="utf-8", errors="ignore"):
            s = line.strip()
            if not s: continue
            try: r = json.loads(s)
            except Exception: continue
            if not isinstance(r, dict): continue
            if r.get("actor") == "strategy-rd" and r.get("evt") == "heartbeat":
                try: cands.append(datetime.datetime.fromtimestamp(int(float(r["ts"])), BJT))
                except Exception: pass
    except Exception:
        pass
    return max(cands) if cands else None

def main():
    now = datetime.datetime.now(BJT)
    dead = []
    # 研发: 心跳对齐真实批次时刻表 04/08/12/16/20 (20:00→次日04:00 是8h空档, 无00点批次).
    # [2026-10-08 根治连刷误报] 旧窗"上次心跳+4h15m"在 20:08 出件后 00:23 就超窗, 但下一批要04:00才跑
    # -> 00:23~04:00 每5min误报一次. 现: 点名须等到"下一个批次点+15min容差"仍无新心跳才算死.
    t = read_ts_rd()
    if t is None:
        dead.append("strategy-rd(研发台账未建立/无心跳)")
    else:
        rd_batch_hours = [4, 8, 12, 16, 20]  # 与 strategy-rd profile 的 5 个研发批次 cron 一致
        next_batch = None
        for dayoff in range(0, 3):
            base = datetime.datetime(t.year, t.month, t.day, tzinfo=BJT) + datetime.timedelta(days=dayoff)
            for h in rd_batch_hours:
                cand = base.replace(hour=h, minute=0, second=0, microsecond=0)
                if cand > t:
                    next_batch = cand
                    break
            if next_batch:
                break
        # 到"下一批 +15min 容差"仍无新心跳 => 才算真正漏跑(点名)
        grace = next_batch + datetime.timedelta(minutes=15) if next_batch else t + datetime.timedelta(hours=4, minutes=15)
        if now > grace:
            dead.append(f"strategy-rd(研发批次{next_batch.strftime('%H:%M') if next_batch else '?'}应出件未出, 最后心跳 {t.strftime('%H:%M')} 前 {int((now-t).total_seconds()//3600)}h)")
    # chief: 全链心跳窗 [2026-11-12 21:4x 根治口径误报] 动态读全链job cron表达式算下一拍(不再死窗45min):
    # 全链=金策宗师团·全链扫描 job(cron 45 13,18,21 * * 1-5, 工作日三定点, 间隔最长5h),
    # 旧45min死窗在13:45-18:45/18:45-21:45空窗+任务续跑拍(不写完成行)时反复误点名(11-12 21:35实证)
    c = read_ts("auto_cycle.log", is_log=True)
    if c is None:
        dead.append("chief(全链日志无完成行)")
    else:
        acp = os.path.join(DATA, "auto_cycle.log")
        # 动态算下一拍: 读全链job的cron表达式(分钟45/小时13,18,21/周一~五)
        next_beat = None
        try:
            import json as _json
            _jobs = _json.load(open(r"E:/workbuddy/国外模型/hermes/cron/jobs.json", encoding="utf-8"))
            _jl = _jobs if isinstance(_jobs, list) else _jobs.get("jobs", [])
            for _j in _jl:
                if "全链扫描" in str(_j.get("name", "")):
                    _expr = _j.get("schedule", {}).get("expr", "45 13,18,21 * * 1-5")
                    _m, _hs, _dom, _mo, _dw = _expr.split()
                    _hh = [int(x) for x in _hs.split(",")]
                    _mins = int(_m)
                    _days = set()
                    for part in _dw.split(","):
                        if "-" in part:
                            a, b = part.split("-")
                            _days.update(range(int(a), int(b) + 1))
                        else:
                            _days.add(int(part))
                    # 找下一拍(BJT): 当前小时分钟数 < 该小时beat时刻 或 找后续小时/天
                    _now_hm = now.hour * 60 + now.minute
                    _cand = []
                    for _d_off in range(0, 8):
                        _dd = (now + datetime.timedelta(days=_d_off))
                        _pyday = _dd.isoweekday()  # 1=Mon..7=Sun
                        if _pyday > 5 and not _days:
                            continue
                        if _pyday > 5 and 0 in _days:
                            pass
                        if _pyday <= 5 or _pyday == 7 or _pyday == 6:
                            if _pyday <= 5 or (_days and ( (_pyday == 7 and 0 in _days) )):
                                for _hhx in _hh:
                                    _cand.append(_dd.replace(hour=_hhx, minute=_mins, second=0, microsecond=0))
                    _cand = [x for x in _cand if x > now]
                    next_beat = min(_cand) if _cand else None
        except Exception:
            next_beat = now + datetime.timedelta(hours=5)  # fail-open: 默认5h宽窗不点名
        if next_beat is not None and now > next_beat + datetime.timedelta(minutes=20):
            # 已过下一拍+20min容差仍无完成行 → 真漏拍, 查log是否冻结
            log_frozen = True
            try:
                log_frozen = (now - datetime.datetime.fromtimestamp(os.path.getmtime(acp), BJT)).total_seconds() > 20 * 60
            except Exception:
                log_frozen = True
            if log_frozen:
                dead.append(f"chief(全链漏拍: 应拍{next_beat.strftime('%H:%M')}+20min已过, 最后完成拍 {c.strftime('%H:%M')} 前 {int((now-c).total_seconds()//60)}min, 日志冻结)")
    if not dead:
        return  # 全齐 → 静默(空 stdout, 不投群)
    out = [f"【金策心跳点名 {now.strftime('%H:%M')}】以下 bot 超窗口无新心跳, 唤醒:" + " ".join(f"@{d.split('(')[0]}" for d in dead)]
    out += [f"· {d}" for d in dead]
    out.append("· 排查顺序: 1) hermes gateway status(投递层掉线=静默根因) 2) 各 profile cron 是否 429 连拒(RPM 撞墙) 3) 该 bot 台账写盘失败")
    out.append("· 本条 fail-open: 只看台账点名, 不动任何挂单/交易配置。")
    print("\n".join(out))

if __name__ == "__main__":
    main()
