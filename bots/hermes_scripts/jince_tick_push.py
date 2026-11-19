# -*- coding: utf-8 -*-
"""金策看板行情实时喂 (no_agent 确定性, 0 LLM, 0 429, 每 5min):
根治「看板行情 30min 才换一拍, 看起来像冻结」。

设计(最稳, 不碰 30min 全链批量=不碰交易链):
  ① ATE 解释器活体实读 15 品种 tick (bid/ask/time), fail-open(终端断→沿用上份不崩)
  ② 写 data/tick_live.json (几 KB, 带 pushed_at + degraded 标记)
  ③ 推上 GitHub jince-trading-dashboard 仓 (同目录, 走已根治的 gh-api 兜底路)
  ④ 看板 HTML 注入一行 JS: 每 60s 拉 tick_live.json, 刷新价格区; 拉不到→显示降级提示

闭环铁律: 节点实数留痕; 429-proof(0 LLM); 行情价≠开单, 只供看盘。

用法: python jince_tick_push.py
      由 Hermes cron 每 5min 调 (no_agent, deliver=bot-chat 静默成功)
"""
import os, json, time, datetime, subprocess, base64, tempfile

ATE_PY = r"C:\Users\ASUS\.workbuddy\binaries\python\envs\ate\Scripts\python.exe"
DATA = r"E:\GoldstrategyEngine\data"
REPO = os.environ.get("JINCE_DASH_REPO", r"E:\workbuddy\金策宗师团\_github_mirror\jince-dashboard")
os.makedirs(REPO, exist_ok=True)  # [2026-11-05] WinError 267 根治: 目录不存在自创建(原 C:\Users\ASUS\jince-dashboard 本机无)
STAMP = os.path.join(REPO, ".tick_pushed")
GH_REPO = "dapengzhanchi141345/jince-trading-dashboard"  # REST API 用 (无 .git)
# [2026-11-09 防刷屏] 同一失败状态持续 N 拍时, 群内每 2h 才重申一次(状态变/恢复成功才即时报),
# 本地每拍仍全量留痕(tick_push_quiet.jsonl), 绝不静默吞。治 gh 卡认证/extnet 断期间每 5min 灌同一条。
ANOM_STATE = os.path.join(DATA, "tick_push_anomaly_state.json")
QUIET_LOG = os.path.join(DATA, "tick_push_quiet.jsonl")
REMIND_SEC = 2 * 3600

def _anomaly_gate(kind, detail):
    """返回 (是否投群, 同状态连续拍数). 首报/状态变/超 REMIND_SEC 才投群; 静默拍也计数留痕."""
    fp = kind + "|" + detail[:60]
    st = {}
    try:
        st = json.load(open(ANOM_STATE, encoding="utf-8"))
    except Exception:
        pass
    now_ts = time.time()
    changed = st.get("fingerprint") != fp
    stuck = 1 if (changed or not st) else st.get("stuck_count", 0) + 1
    should = changed or (now_ts - st.get("last_report_ts", 0) > REMIND_SEC)
    json.dump({"fingerprint": fp, "last_report_ts": now_ts if should else st.get("last_report_ts", 0),
               "stuck_count": stuck}, open(ANOM_STATE, "w", encoding="utf-8"), ensure_ascii=False)
    if not should:
        try:
            with open(QUIET_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": int(now_ts), "ev": "quiet_beat", "kind": kind,
                                    "stuck": stuck, "note": detail[:80]}, ensure_ascii=False) + "\n")
        except Exception:
            pass
    return should, stuck


def _anomaly_clear():
    try:
        os.unlink(ANOM_STATE)
    except OSError:
        pass
# [2026-11-03] gh 全路径解析: 会话 PATH 可能没 gh(旧PATH) → WinError 2; 绝对路径兜底(认证仍需 token)
_gh_full = r"C:\Users\Administrator\ghbin\bin\gh.exe"
GH = _gh_full if os.path.exists(_gh_full) else "gh"

# 15 品种 = 与 6 节点同表的动量监控池 (crypto 6 + 股指 3 + FX 5 + XAU)
SYMS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "JPYUSD",
        "BTCUSD", "ETHUSD", "SOLUSD", "KSMUSD", "UNIUSD", "DOTUSD",
        "MOMO.NAS", "RIOT.NAS", "JPN225", "US30"]


def _gh_api(*args, timeout=45):
    return subprocess.run([GH, "api", "-H", "User-Agent: jince-tick-push", *args],
                          capture_output=True, text=True, timeout=timeout, creationflags=0x08000000)


def _retry(fn, tries=6, backoff=2, what="gh-api"):
    """[2026-10-08] gh api 间歇截断('unexpected end of JSON input')重试护栏:
    23:10/23:15/00:55 复现 = API 响应偶发截断(非 443 墙, 非限流), 一抖就 fail 报异常.
    截断窗可连挂数拍 -> 同拍内退避重试 tries 次(指数), 全挂才返回最后一次, 由调用方发声.
    判断: 只要 rc!=0 就重试(比只认 stderr 子串更稳, 防截断消息在 stdout/EOF/连接抖).
    [2026-11-11 chief] 子层异常兜底: fn() 本身抛 subprocess.TimeoutExpired/FileNotFoundError/
    json.JSONDecodeError 等 = 11-11 20:00/20:30/20:36 三拍 exit 1 根因(异常穿透到 __main__ catch).
    现: 捕获为 rc=999 失败拍继续退避重试, 绝不外抛(fail-open, 交给 11-09 防刷屏闸发声)."""
    import time as _t
    last = None
    for i in range(tries):
        try:
            last = fn()
        except Exception as _e:
            last = type('_FailResult', (), {'returncode': 999, 'stdout': '',
                                            'stderr': 'EXC: %s: %s' % (type(_e).__name__, str(_e)[:80])})()
        if last.returncode == 0:
            return last
        if i < tries - 1:
            _t.sleep(backoff * (i + 1))  # 2,4,6,8,10s 退避, 跨过快抖动窗
    return last

def pull_ticks():
    """ATE 活体实读 15 品种 tick -> {sym: {bid, ask, ts}}. 全断 fail-open 返回 {}."""
    code = ("import os, json, time, MetaTrader5 as m\n"
            "os.environ.pop('PYTHONPATH', None); os.environ.pop('PYTHONHOME', None)\n"
            "m.initialize()\n"
            "out = {}\n"
            "for s in %r:\n"
            "    t = m.symbol_info_tick(s)\n"
            "    if t and t.bid > 0:\n"
            "        out[s] = {'bid': t.bid, 'ask': t.ask, 'ts': int(time.time())}  # [11-16] 终端时钟偏快2h, tick ts 一律用本地读时刻, 防'未来戳'\n"
            "print(json.dumps(out))\n") % SYMS
    try:
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
        r = subprocess.run([ATE_PY, "-c", code], capture_output=True, text=True,
                           timeout=45, cwd=r"E:/GoldstrategyEngine", env=env,
                           creationflags=0x08000000)  # [2026-10-23 后台化] 不闪黑框, 保留 stdout
        for line in reversed(r.stdout.strip().splitlines()):
            if line.strip().startswith("{"):
                return json.loads(line)
        return {}
    except Exception:
        return {}


def main():
    now = datetime.datetime.now().astimezone()
    ticks = pull_ticks()
    n = len(ticks)
    last_pulled = now.strftime("%m-%d %H:%M")

    if n == 0:
        # fail-open: 终端断了/全品种无 tick -> 不写新 json (沿用上份), 投群点名 (绝不静默吞)
        # [11-09 防刷屏] 同状态持续 -> 2h 才重申, 本地留痕; 终端一恢复(成功)清状态, 下拍再断=即时报
        should, _stuck = _anomaly_gate("mt5_0sym", "MT5 实读 0 品种")
        if should:
            print(f"【金策行情喂-异常】{last_pulled} MT5 实读 0 品种 (终端 IPC 断?), 沿用上份 tick_live.json")
            return 1
        return 0  # 同状态卡住 -> 静默拍(本地留痕, 终端存活另有巡检/体检每30min确认)

    payload = {
        "generated": int(time.time()),
        "beijing": last_pulled,
        "n": n,
        "degraded": False,
        "syms": ticks,
    }
    jp = os.path.join(DATA, "tick_live.json")
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    # 推到 GitHub 同仓同目录 (gh-api 直连兜底: blob->tree->commit->ref)
    b64 = base64.b64encode(open(jp, "rb").read()).decode()
    # [2026-10-08] 取HEAD/建tree/建commit/推ref 全部走 _retry 重试护栏(不只 blob).
    # 08:10 exit=2 = 抖在"取远端HEAD"那步(旧版只给blob包了重试), 现全链都退避重试.
    gh = lambda *a: _retry(lambda: _gh_api(*a, timeout=45))

    # [2026-10-09] 整链推一次: 取HEAD->blob->tree->commit->PUT main指针.
    # 根治 422 "not a fast forward": 看板哨兵(10min git push)与行情喂(5min)撞同分钟
    # 写同一远端 main -> 本拍基于旧HEAD的PUT被拒. 422/快进失败则重拉新HEAD整链重走.
    def push_once():
        try:
            return _push_once_inner()
        except Exception as _e:
            # [2026-11-11 chief] json.loads截断/FileNotFoundError等最后一层兜底 -> 返回False走防刷屏闸, 不外抛exit 1
            return False, "push_once EXC %s: %s" % (type(_e).__name__, str(_e)[:80])

    def _push_once_inner():
        head = gh(f"repos/{GH_REPO}/commits/main", "--jq", ".sha").stdout.strip()
        if not head:
            return False, "gh api 拿不到远端 HEAD (443/API 抖?, 已重试仍全挂)"
        # ① blob
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"content": b64, "encoding": "base64"}, f); bp = f.name
        rb = _retry(lambda: subprocess.run([GH, "api", "-H", "User-Agent: jince-tick-push",
                             f"repos/{GH_REPO}/git/blobs", "--input", bp],
                            capture_output=True, text=True, timeout=45, creationflags=0x08000000))
        os.unlink(bp)
        blob_sha = json.loads(rb.stdout).get("sha") if rb.returncode == 0 else None
        if not blob_sha:
            return False, f"blob 上传失败: {(rb.stderr or '')[:100]}"
        # ② tree (远端 main tree 其它 entry + 替换 tick_live.json)
        rtree = gh(f"repos/{GH_REPO}/git/trees/{head}")
        remote_tree = json.loads(rtree.stdout) if rtree.returncode == 0 else {}
        entries = [e for e in remote_tree.get("tree", []) if e.get("path") != "tick_live.json"]
        entries.append({"path": "tick_live.json", "mode": "100644", "type": "blob", "sha": blob_sha})
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"tree": entries}, f); tp = f.name
        rt = _retry(lambda: subprocess.run(["gh", "api", "-H", "User-Agent: jince-tick-push",
                             f"repos/{GH_REPO}/git/trees", "--input", tp],
                            capture_output=True, text=True, timeout=45, creationflags=0x08000000))
        os.unlink(tp)
        new_tree = json.loads(rt.stdout).get("sha") if rt.returncode == 0 else None
        if not new_tree:
            return False, f"建 tree 失败: {(rt.stderr or '')[:100]}"
        # ③ commit (parent=远端 HEAD)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"message": f"tick_live update {last_pulled} ({n} syms)",
                       "tree": new_tree, "parents": [head]}, f); cp = f.name
        rc = _retry(lambda: subprocess.run(["gh", "api", "-H", "User-Agent: jince-tick-push",
                             f"repos/{GH_REPO}/git/commits", "--input", cp],
                            capture_output=True, text=True, timeout=45, creationflags=0x08000000))
        os.unlink(cp)
        new_commit = json.loads(rc.stdout).get("sha") if rc.returncode == 0 else None
        if not new_commit:
            return False, f"建 commit 失败: {(rc.stderr or '')[:100]}"
        # ④ 推 main 指针 (422/快进冲突=撞车, 上层重拉新HEAD重来)
        rf = gh("-X", "PUT", f"repos/{GH_REPO}/git/refs/heads/main", "-f", f"sha={new_commit}")
        if rf.returncode != 0:
            return False, f"推 main 指针失败: {(rf.stderr or '')[:120]}"
        return True, ""

    # 最多 3 轮: 轮与轮之间退避, 每轮重拉新 HEAD (快进冲突/443抖 都靠这愈合)
    ok, err = False, ""
    for attempt in range(3):
        ok, err = push_once()
        if ok:
            break
        time.sleep(3 * (attempt + 1))  # 3,6,9s 退避, 让撞车的另一写手先落完
    if not ok:
        # [11-09 防刷屏] 本地 tick_live.json 已写(看板实时条照活), 只有 gh 推送卡(外网断/卡认证);
        # 同状态持续 -> 群 2h 才重申, 静默拍本地全量留痕; 推送一恢复(成功)清状态, 再坏=即时报.
        should, stuck = _anomaly_gate("gh_push", err)
        if should:
            tail = (" (连续 %d 拍同状态, 本地写照跑, 群 2h 重申一次, 恢复即自动报)" % stuck) if stuck > 1 else ""
            print(f"【金策行情喂-异常】{last_pulled} 推 main 指针失败: {err}, 本地已写{tail}")
            return 6
        return 0  # 静默拍: 本地已写, 异常已报过 (tick_push_quiet.jsonl 留痕)

    open(STAMP, "w").write(str(time.time()))
    _anomaly_clear()  # 推活 -> 清卡滞状态, 下次再坏=状态变化即时报
    # 成功 -> 静默 (0 LLM, 0 刷屏)
    return 0


if __name__ == "__main__":
    try:
        rc = main()
        if rc:
            print(f"[tick_push] exit={rc}")
    except Exception as ex:
        # 护栏: 异常也发声, 绝不静默吞
        print(f"【金策行情喂-异常】{datetime.datetime.now():%m-%d %H:%M} {str(ex)[:150]}")
        raise SystemExit(1)
