#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策·训练机制·全宇宙回测后台跑 (每日 00:10 起, 不占 01:30 验收枪).
no_agent 0 LLM, 429-proof. 跑 backtest_engine.py 全宇宙 -> backtest_edge.json
末尾写 backtest_edge_run_stamp.json(生成时戳+品种数+耗时), 供 01:30 验收枪判'有没有新产物'.
另加 引擎自检哨兵: 全宇宙里 胜率>0.9 且 n>500 的腿数 记入 sentinels 字段,
供验收枪判'引擎虚高'事故(>3 条即引擎口径有问题, 验收自动打回).
红线: 历史回测≠未来收益; 只产数据不碰实盘.
"""
import os, json, time, subprocess, datetime, sys
# [2026-10-09 修] cron 运行器 reader 按 UTF-8 读本脚本 stdout, 而 cron 环境 locale=GBK ->
#   中文 print 出 0xd3(GBK 字节) 崩 reader 线程(UnicodeDecodeError). 强制 UTF-8 出字节流, 根除.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
ATE = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/pythonw.exe"
ROOT = r"E:\GoldstrategyEngine"
DATA = ROOT + "/data"

def main():
    t0 = time.time()
    import os as _os
    # [2026-10-09 修正] 每日固定 SMOKE 3主品种含黄金(~6.7h, 00:10起 06:50收, 不撞下轮).
    #   全宇宙164品种按 2.2h/品种 要~15天, 排不进窗口 -> FULL 只留 env 手动触发, 引擎提速(挂@strategy-rd)后再排周日.
    mode = _os.environ.get("JINCE_BT_MODE", "SMOKE")
    argv = [mode] if mode == "SMOKE" else []           # 无 argv => run_universe 全宇宙 tradable
    # [2026-10-09 根因修复] 剥掉父(cron运行器)的 PYTHONPATH/PYTHONHOME, 否则其不兼容 numpy 被继承
    #   -> 子进程 ATE 报 No module named 'numpy._core._multiarray_umath' 0.2s 崩. 干净环境才用 ATE venv 自带 numpy.
    child_env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    # [2026-10-09 防复发闸①] 开跑前快检: 干净环境验 numpy/pandas 可 import (治 cron PYTHONPATH 污染
    #   -> 子进程 numpy 0.2s 崩, 01:30 枪空转 3 个月根子).
    # [L5 2026-11-02 C单] 预检分类: 依赖缺失=真 bug 硬 fail; MT5 终端挂(任务A)=预期 outage 干净跳过 rc=4 不刷 rc=1.
    _precode = ("import sys\n"
                "try:\n"
                "    import numpy, pandas\n"
                "    import MetaTrader5 as m\n"
                "except Exception as _e:\n"
                "    print('PRECHECK_DEP_FAIL', repr(_e)[:120]); sys.exit(1)\n"
                "_res = m.initialize()\n"
                "_ok = _res[0] if isinstance(_res, tuple) else bool(_res)\n"
                "print('PRECHECK_MT5_OK', _ok, 'numpy=', numpy.__version__)\n")
    pre = subprocess.run([ATE, "-c", _precode],
                         capture_output=True, text=True, timeout=120, cwd=ROOT, env=child_env)
    _pout = (pre.stdout or "") + "\n" + (pre.stderr or "")
    if "PRECHECK_DEP_FAIL" in _pout:
        raise SystemExit("快检不过(依赖缺失/环境污染), 不开 6.7h 长跑, fail-fast: %s" % _pout[-300:])
    if "PRECHECK_MT5_OK True" not in _pout:
        # MT5 终端不可用但依赖齐 -> 本拍干净跳过 (rc=4 落 stamp 留痕, 等任务 A 终端恢复), 不刷 rc=1
        _stamp = {"ts": datetime.datetime.now().isoformat(), "rc": 4, "mode": mode,
                  "skip": "mt5_unavailable", "pre": _pout[-200:]}
        json.dump(_stamp, open(os.path.join(DATA, "backtest_edge_run_stamp.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("[全宇宙回测] MT5 终端不可用 (initialize 失败), 本拍干净跳过 rc=4 (不刷屏, 待任务A终端恢复)")
        raise SystemExit(0)
    print("快检过(干净环境 numpy/pandas/MT5 init OK), 开跑 mode=%s" % mode)
    # [2026-10-09 L5-fix] 竞写防: 启子进程前先探活, 已有 backtest_engine SMOKE 在跑就等它收工复用产物, 不并启第二枪
    #   (同参双进程写同一真源=4185式脏痕, L4@risk-officer 点名焊死; 探活=wmic 查命令行含 backtest_engine 的活进程)
    import re as _re
    try:
        chk = subprocess.run(["wmic", "process", "where", "name like 'python%' and commandline like '%backtest_engine%'", "get", "ProcessId", "/format:list"],
                             capture_output=True, text=True, env=child_env, timeout=30,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        pids = [l.strip() for l in chk.stdout.splitlines() if l.strip().startswith("ProcessId") and l.strip() != "ProcessId="]
        pids = [x.split("=", 1)[1] for x in pids if "=" in x]
        if pids:
            print("[防竞写] 已有 backtest_engine 子进程在跑 PIDs=%s, 不并启, 轮询其收工(每5min查一次, 上限7h)再读产物" % pids)
            deadline = time.time() + 7 * 3600
            while time.time() < deadline:
                time.sleep(300)
                chk2 = subprocess.run(["wmic", "process", "where", "name like 'python%' and commandline like '%backtest_engine%'", "get", "ProcessId", "/format:list"],
                                      capture_output=True, text=True, env=child_env, timeout=30,
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                still = [x for x in (l.strip() for l in chk2.stdout.splitlines() if "ProcessId=" in l) if x.split("=", 1)[1] in pids]
                if not still:
                    print("[防竞写] 已有枪收工, 复用其产物(不重跑)")
                    r = subprocess.CompletedProcess(args=["reuse"], returncode=0, stdout="", stderr="")
                    break
            else:
                raise SystemExit("[防竞写] 等待已有枪超时7h, 升级22:00兜底")
        # [2026-10-09 @hermes 修] 原判 "reuse" not in r.stderr 永真(CompletedProcess stderr 为空) ->
        #   复用场景反而重跑第二枪(竞写防白防). 改 reused 标志直判.
        reused = ("r" in dir()) and (getattr(r, "args", None) == ["reuse"])  # [修] pids空时 r 未定义, 守卫防 UnboundLocalError
        if not reused:
            r = subprocess.run([ATE, os.path.join(ROOT, "backtest_engine.py")] + argv,
                               capture_output=True, text=True, cwd=ROOT, env=child_env)
    except Exception as _e:
        print("[防竞写] 探活异常(%s), 降级直跑(幂等, 不阻断)" % _e)
        r = subprocess.run([ATE, os.path.join(ROOT, "backtest_engine.py")] + argv,
                           capture_output=True, text=True, cwd=ROOT, env=child_env)
    stamp_mode = mode
    rc = r.returncode
    stamp = {"ts": datetime.datetime.now().isoformat(), "rc": rc, "mode": stamp_mode, "elapsed_s": round(time.time()-t0,1),
             "stdout_tail": (r.stdout or "")[-500:], "stderr_tail": (r.stderr or "")[-500:]}
    # 读新产物(如果 rc=0 且文件刷新)
    edge = os.path.join(DATA, "backtest_edge.json")
    out_meta = {}
    if os.path.exists(edge):
        try:
            d = json.load(open(edge, encoding="utf-8"))
            out_meta["generated"] = d.get("generated")
            out_meta["symbols_tested"] = d.get("symbols_tested")
            # 引擎自检哨兵: 全宇宙 胜率虚高腿数(口径事故早预警)
            bad = 0
            for sym, dd in (d.get("per_symbol") or {}).items():
                for name, rr in (dd.get("strats") or {}).items():
                    if isinstance(rr, dict) and rr.get("n",0) > 500 and (rr.get("wr") or 0) > 0.9:
                        bad += 1
            out_meta["sentinels_high_wr_legs"] = bad
            out_meta["engine_selfcheck_pass"] = bad == 0  # [2026-10-09] n>500且wr>0.9=引擎虚高实锤, 出现即打回
        except Exception as e:
            out_meta["edge_read_err"] = str(e)[:80]
    stamp.update(out_meta)
    json.dump(stamp, open(os.path.join(DATA, "backtest_edge_run_stamp.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("全宇宙回测收工 rc=%s 耗时%.0fs 产物戳: %s" % (rc, time.time()-t0, json.dumps(out_meta, ensure_ascii=False)[:300]))
    # 非零退出也要 fail-loud(no_agent 非零会报警), 但已落 stamp 供 01:30 判
    if rc != 0:
        if rc in (3, 4):
            # [2026-10-14 L5] rc=3 引擎锁让位; [2026-11-02 L5 C单] rc=4 MT5 终端不可用让位 —
            #   均非失败(下一拍可重跑), 退出码 0 不当失败, 免 no_agent 误报警刷屏(防第 6 次 rc 刷).
            print("[全宇宙回测] rc=%d 让位(3=另一引擎在跑 / 4=MT5 终端不可用), 本拍跳过等下拍, 非失败. 引擎stderr尾: %s" % (rc, ((r.stderr or r.stdout) or "")[-300:]))
            raise SystemExit(0)
        raise SystemExit(1)

if __name__ == "__main__":
    main()
