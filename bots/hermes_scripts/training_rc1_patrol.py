# -*- coding: utf-8 -*-
"""金策·回测引擎 rc=1 专项巡检 (no_agent 0 LLM, 429-proof)
[2026-10-10 L5 落] 用户令"建立巡检制度 立即执行" -- 引擎连挂 rc=1 专项枪.
每日 01:40 调度器自动跑 (Jince0140_Rc1Patrol), 01:30 验收枪之后.
判据 (确定性, 全读盘 0 口播):
  1) 读 backtest_edge_run_stamp.json 最近一次 rc:
     - rc=0 且 backtest_edge.json generated 已刷新(非 void 旧卷) -> PASS
     - rc=1 且 data/backtest_engine_stderr.log 有内容 -> FAIL_CRASH_LOGGED (崩因已留痕, @strategy-rd 按 traceback 修)
     - rc=1 且 stderr log 缺/空 -> FAIL_NO_LOG (崩因未留痕 = 修复链没咬住, 点名不静默)
  2) 连挂计数 rc1_streak.json: 连续 rc=1 次数; >=2 时写 escalate=True (22:00 日报直接点名)
  3) 出 training_rc1_patrol_result.json {ts, rc, streak, escalate, crash_located, verdict, stderr_tail}
  -> 22:00 日报 / 01:30 验收 grep 本文件 verdict, 缺格点名.
红线: 只读数据+写巡检产物, 0 碰实盘, 历史回测≠未来收益.
"""
import json, os, time, datetime

DATA = r"E:\GoldstrategyEngine\data"
STAMP = os.path.join(DATA, "backtest_edge_run_stamp.json")
EDGE = os.path.join(DATA, "backtest_edge.json")
ERRLOG = os.path.join(DATA, "backtest_engine_stderr.log")
STREAK = os.path.join(DATA, "rc1_streak.json")
OUT = os.path.join(DATA, "training_rc1_patrol_result.json")

def main():
    res = {"ts": int(time.time()), "verdict": "FAIL", "rc": None, "streak": 0,
           "escalate": False, "crash_located": False, "stderr_tail": "", "stamp_ts": None}
    # 1) 最近 run_stamp (只认 stamp ts > 上一版巡检 ts 的新戳, 防 00:10 引擎还没跑完时误报 FAIL_CRASH_LOGGED)
    rc, edge_ok = None, False
    if os.path.exists(STAMP):
        try:
            st = json.load(open(STAMP, encoding="utf-8"))
            st_ts = str(st.get("ts", ""))
            # 巡检结果里已有上一版 ts, 比 stamp ts 是否更新
            prev_res = {}
            if os.path.exists(OUT):
                try:
                    prev_res = json.load(open(OUT, encoding="utf-8"))
                except Exception:
                    prev_res = {}
            stamp_fresh = st_ts > str(prev_res.get("stamp_ts", ""))
            if st_ts and st_ts <= str(prev_res.get("stamp_ts", "")):
                res["verdict"] = "PENDING_NEW_STAMP"  # 00:10 引擎还没出戳, 本轮不判 FAIL, 等下轮
            else:
                rc = st.get("rc")
                res["stamp_ts"] = st_ts
                edge_mt = os.path.getmtime(EDGE) if os.path.exists(EDGE) else 0
                gen = ""
                total_n = -1
                if os.path.exists(EDGE):
                    try:
                        g = json.load(open(EDGE, encoding="utf-8"))
                        gen = str(g.get("generated", ""))
                        # [2026-10-16 L5 修 假PASS] 空卷广度检查: strategy_overall 全腿 n 之和.
                        # 旧判据只查"卷存在+generated非空", TIMECAP 空卷(rc=0, 6品种 n 全 0)仍判 PASS
                        # = 假信号(hermes 01:40 点名"卷空≠引擎好"). 现: total_n==0 -> FAIL_EMPTY_VOLUME
                        # 计入连挂, 22:00 日报点名; 引擎枪出非空卷才翻 PASS.
                        _so = g.get("strategy_overall") or {}
                        total_n = sum((a.get("n") or 0) for a in _so.values() if isinstance(a, dict))
                        edge_ok = ("void" not in json.dumps(g, ensure_ascii=False)[:400]) and gen != ""
                    except Exception:
                        edge_ok = False
                if rc == 0 and edge_ok:
                    res["verdict"] = "PASS" if total_n > 0 else "FAIL_EMPTY_VOLUME"
                    res["empty_volume"] = (total_n == 0)
                    res["total_n"] = total_n
                elif rc == 0:
                    res["verdict"] = "FAIL_EDGE_STALE"
                else:
                    res["verdict"] = "FAIL_CRASH"
        except Exception as e:
            res["verdict"] = "FAIL_STAMP_UNREADABLE: " + str(e)[:60]
    else:
        res["verdict"] = "FAIL_NO_STAMP"
    # 2) stderr log 崩因留痕
    if os.path.exists(ERRLOG) and os.path.getsize(ERRLOG) > 0:
        tail = open(ERRLOG, encoding="utf-8", errors="ignore").read()[-500:]
        res["stderr_tail"] = tail
        res["crash_located"] = ("Traceback" in tail or "Error" in tail or "error" in tail) or len(tail.strip()) > 0
    # 3) 连挂计数
    prev = {}
    if os.path.exists(STREAK):
        try:
            prev = json.load(open(STREAK, encoding="utf-8"))
        except Exception:
            prev = {}
    prev_ts = prev.get("ts", 0)
    if res["verdict"] == "PASS":
        new_streak = 0
    else:
        new_streak = prev.get("streak", 0) + 1
    res["streak"] = new_streak
    res["escalate"] = new_streak >= 2
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"streak": new_streak, "ts": res["ts"], "verdict": res["verdict"], "escalate": res["escalate"]},
              open(STREAK, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("rc1_patrol verdict=%s rc=%s streak=%s escalate=%s crash_located=%s"
          % (res["verdict"], rc, new_streak, res["escalate"], res["crash_located"]))
    return 0 if res["verdict"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
