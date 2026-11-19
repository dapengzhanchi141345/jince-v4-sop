"""SD 批锁利守护 (L0 热仓通道克隆 · magic 20261104 · 模拟户 60137964)
2026-11-15 李令: "直接锁利 不能让利润没了" —— 复用 jince_live24 L0 已验逻辑:
  - 热仓口径: |浮盈R|>=0.5R (R=开仓初始SL距离, 读 prac log, 防 SL 推后距离塌缩误判)
  - 双阈值触发(李 11-12 美元口径): 浮盈>$10 或 >=0.5R 先到先触发
  - 触发: SL 推 开仓价±$5 (半阈值地板, 浮盈不回吐到0)
  - 之后棘轮: SL = 更紧的 max(现SL, 峰值-0.6R, 峰值-$10) 只紧不松
  - 10016 预检: sell SL 须在当前价上方 / buy 下方; 距当前价 < stops_level 拒; tick 网格取整
  - 拒单 60s 冷却 + last_trail 去重(同值 SLTP no-op 不发)
  - 服务器端 SLTP 落盘: 守护死了, 最后推的 SL 仍零延迟触发(最后防线)
常驻 3s 轮询; 留痕 sd_profitlock_log.jsonl; stdout 静默(动作才打行, 计划任务回收).
"""
import os, sys, json, time, datetime as dt, argparse
os.environ.setdefault("MT5_TERMINAL", r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe")
os.environ.setdefault("MT5_LOGIN", "60137964")
import MetaTrader5 as mt5

MAGIC = 20261104
ROOT = r"E:\GoldstrategyEngine"
PRAC_LOG = os.path.join(ROOT, "data", "_manual_prac_log.jsonl")
PL_LOG = os.path.join(ROOT, "data", "sd_profitlock_log.jsonl")
SYM_PARAMS = os.path.join(ROOT, "research", "sd_symbol_params.json")
HOT_R = 0.5   # 缺省(品种无表时)
HOT_USD = 10.0
FLOOR_USD = 5.0
GIVEBACK_R = 0.3  # 缺省
COOLDOWN = 60.0
TICK = 10.0  # demo 0.01 手 10s 足够锁盈; 实盘放量再降 3s (与 jince_live24 L0 共终端, 降 tick=IPC 压力)

_sp_tbl = None


def sym_lock_params(sym):
    """分品种锁利参数 (trig/giveback); 缺省回退全局"""
    global _sp_tbl
    if _sp_tbl is None:
        _sp_tbl = {}
        if os.path.exists(SYM_PARAMS):
            try:
                _sp_tbl = json.load(open(SYM_PARAMS, encoding="utf-8")).get("params", {})
            except Exception:
                _sp_tbl = {}
    sp = _sp_tbl.get(sym) or {}
    return sp.get("trig", HOT_R), sp.get("giveback", GIVEBACK_R)

_state = {}   # key -> dict(sl, peak, last_trail, last_reject_ts)
_reject = {}  # sym -> ts


def open_risk(sym, px_open, pos_time=None, tol=0.0):
    """开仓初始SL距离 (R 基准): prac log 按 品种+开仓价 匹配 open 记录
    (挂单器 ticket=订单号, 成交后 position.ticket=持仓号, 两者不同, 故按价格匹配)
    M1修复: 容差 1e-6 过严(限价单正滑点成交即失配->该仓静默失保) -> 默认 2*tick 容差.
    P2修复(11-19, sd_guard_open_risk_price_mismatch_20261118): 失配不再静默回退旧腿,
    加三道闸: ①时间门=只认持仓开仓时间前6h内的open记录(旧腿记录作废)
    ②价差>15%价格=LOUD红警+返回None(跳过该仓推位, 安全侧) ③仍回退时warn带票号."""
    cands = []
    if os.path.exists(PRAC_LOG):
        for line in open(PRAC_LOG, encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("kind") == "open" and r.get("sym") == sym and r.get("price") is not None:
                cands.append(r)
    if pos_time is not None:
        cutoff = pos_time - dt.timedelta(hours=6)
        timed = []
        for r in cands:
            try:
                rts = dt.datetime.fromisoformat(str(r.get("ts", "")))
            except Exception:
                continue
            timed.append(r) if rts >= cutoff else None
        if timed:
            cands = timed
    tol = tol or 2e-4
    for r in cands:
        if abs(r["price"] - px_open) <= tol:
            rec = r
            break
    else:
        if not cands:
            with open(PL_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(dict(ts=dt.datetime.now().isoformat(), sym=sym, kind="loud",
                                         msg="open_risk 无匹配open记录(prac log缺登记), 跳过该仓推位")) + "\n")
            return None
        rec = cands[-1]  # 最近一条 open 兜底 (warn 留痕)
        gap = abs(rec.get("price", 0) - px_open) / max(px_open, 1e-9)
        with open(PL_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(ts=dt.datetime.now().isoformat(), sym=sym,
                                    kind="loud" if gap > 0.15 else "warn",
                                    msg="open_risk 价格失配%s: px_open=%.6f rec_px=%.6f gap=%.1f%% %s" % (
                                        "拒用(跳过推位)" if gap > 0.15 else "回退最近open",
                                        px_open, rec.get("price", 0), gap * 100,
                                        "pos_time=%s" % pos_time))) + "\n")
        if gap > 0.15:
            return None  # LOUD: 失配基准不推位, 安全侧
    risk = abs(rec.get("sl", 0) - rec.get("price", 0))
    return risk if risk > 0 else None


def push_sl(p, key, sym, new_sl, reason, live):
    info = mt5.symbol_info(sym)
    if info is None:
        mt5.symbol_select(sym, True)
        info = mt5.symbol_info(sym)
    if info is None:
        return
    dg = info.digits
    tick_sz = info.trade_tick_size or info.point
    new_sl = round(round(new_sl / tick_sz) * tick_sz, dg)  # tick 网格
    tick = mt5.symbol_info_tick(sym)
    # L1修复: 服务端规则 buy SL<bid / sell SL>ask (原用 ask/bid 在点差内边界会被拒进冷却)
    cur_px = tick.bid if p.type == 0 else tick.ask
    # 10016 预检: buy SL 必须在现价(bid)下方, sell SL 必须在现价(ask)上方
    if p.type == 0 and new_sl >= cur_px:
        return  # 已无利润可锁(价已跌破保本), 不推
    if p.type == 1 and new_sl <= cur_px:
        return
    if abs(cur_px - new_sl) < info.trade_stops_level * info.point:
        return  # 距现价太近会被拒
    st = _state.get(key, {})
    if st.get("last_trail") == new_sl:
        return  # 同值 no-op
    if time.time() - _reject.get(sym, 0) < COOLDOWN:
        return  # 拒单冷却
    # P0-3修复: dry(--once 无 --live) 不发单, 只留痕 (原 order_send 无条件=dry 不 dry)
    if not live:
        with open(PL_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(ts=dt.datetime.now().isoformat(), ticket=p.ticket, sym=sym,
                                     reason=reason + " [DRY]", new_sl=new_sl, rc=0, live=False)) + "\n")
        _state[key] = dict(st, last_trail=new_sl)  # P-1修复: dry 也登记 last_trail, 防每拍刷屏
        return
    req = dict(action=mt5.TRADE_ACTION_SLTP, position=p.ticket, symbol=sym,
               magic=MAGIC, sl=new_sl, tp=p.tp)
    res = mt5.order_send(req)
    rc = getattr(res, "retcode", None)
    if rc in (10009, 10010):
        _state[key] = dict(st, sl=new_sl, last_trail=new_sl)
        with open(PL_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(ts=dt.datetime.now().isoformat(), ticket=p.ticket,
                                     sym=sym, reason=reason, new_sl=new_sl, rc=rc,
                                     live=live)) + "\n")
        print("锁利 %s %s SL->%s (%s) [%s]" % (sym, p.ticket, new_sl, reason,
              "LIVE" if live else "DRY"), flush=True)
    else:
        _reject[sym] = time.time()
        with open(PL_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(ts=dt.datetime.now().isoformat(), ticket=p.ticket,
                                    sym=sym, reason=reason, new_sl=new_sl, rc=rc,
                                    err=mt5.last_error(), live=live)) + "\n")
        print("锁利拒单 %s rc=%s %s (冷却60s)" % (sym, rc, mt5.last_error()), flush=True)


def tick_once(live):
    positions = mt5.positions_get() or []
    for p in positions:
        if p.magic != MAGIC:
            continue
        key = "%s_%s" % (p.symbol, p.ticket)
        st = _state.get(key, dict(peak_r=0.0))
        risk = open_risk(p.symbol, p.price_open, pos_time=dt.datetime.fromtimestamp(p.time))  # 开仓初始SL距离(价格), 防 SL 推后塌缩误判; P2: 时间门+LOUD拒用
        if not mt5.symbol_select(p.symbol, True):
            continue
        info = mt5.symbol_info(p.symbol)
        tick = mt5.symbol_info_tick(p.symbol)
        if info is None or tick is None or risk is None or risk <= 0:
            continue
        is_buy = p.type == 0
        sgn = 1 if is_buy else -1
        cur = tick.bid if is_buy else tick.ask
        prof_r = (cur - p.price_open) * sgn / risk      # 当前浮盈 R
        peak_r = max(st.get("peak_r", 0.0), prof_r)    # 峰值 R (只记浮盈)
        _state[key] = dict(st, peak_r=peak_r)
        trig, gb = sym_lock_params(p.symbol)
        # 锁利触发: 【峰值】>= 品种 trig (分品种深优; 缺省0.5)
        # BUGFIX 11-15终审: 原用当前浮盈做触发 -> 回吐期(浮盈<trig)棘轮停推, 峰值利润没锁住
        #  (李彦明观察到的"浮盈10刀->反转止损离场"正是此洞). 改峰值口径: 峰值到过 trig,
        #  之后任何时刻都按 峰值-gb 地板推 SL (回吐也锁, 只紧不松)
        if peak_r < trig:
            continue
        # 棘轮地板: 峰值回吐 gb 后锁, 且 floor=开仓价(0R, 浮盈永不回吐成亏)
        lock_r = max(peak_r - gb, 0.0)
        # P0-2修复(11-15三方审查): 原 target=open+lock_r*risk 对 SELL 方向反了
        # (卖锁盈=SL下移到开仓价下方; 原式推 SL 上移=亏损侧, 空单永不锁/越锁越宽).
        # sgn: buy +1 (SL 上提锁盈), sell -1 (SL 下移锁盈)
        target = p.price_open + sgn * lock_r * risk
        cur_sl = p.sl
        # 方向感知 skip (L3: SL==开仓价=0R地板也视为已锁): buy SL在上方=已锁; sell SL在下方=已锁
        if cur_sl > 0:
            if is_buy and cur_sl >= target - 1e-12:
                continue  # 已锁到位, 不推
            if (not is_buy) and cur_sl <= target + 1e-12:
                continue
        push_sl(p, key, p.symbol, target, "锁利: 峰值%.2fR->锁%.2fR%s (trig=%.1f gb=%.1f)" % (
            peak_r, lock_r, "" if is_buy else "[sell]", trig, gb), live)
        # M2修复: peak 落盘 (重启不自失; 心跳拉起/1min 自愈后棘轮续推链不断)
        # P-1修复(11-15御史处方): 只落 peak, 不无条件写 last_trail(拒单后同值no-op永久拦住重试)
        _state[key] = dict(_state.get(key), peak_r=peak_r)
        try:
            with open(os.path.join(ROOT, "data", "sd_peak_state.json"), "w", encoding="utf-8") as f:
                json.dump({k: dict(v, peak_r=v.get("peak_r", 0.0)) for k, v in _state.items()}, f)
        except Exception:
            pass
    alive = set("%s_%s" % (p.symbol, p.ticket) for p in positions if p.magic == MAGIC)
    for k in list(_state):
        if k not in alive:
            del _state[k]


def _acquire_lock():
    """实例唯一: lock 文件记 pid; 若锁主 pid 还活(OpenProcess 判活) -> 自退.
    BUGFIX 11-15终审: 原 CIM/wmic 命令行核验 30s 冷启动超时被 except 吞掉 -> 锁静默失效双开.
    改 OpenProcess(QUERY_INFORMATION) 判活: PID 复用假阳性窗口极小(1min 心跳 + 进程刚起),
    快且无 subprocess."""
    lock = os.path.join(ROOT, "data", "sd_profitlock.lock")
    import ctypes
    pid = os.getpid()
    try:
        if os.path.exists(lock):
            old = json.load(open(lock, encoding="utf-8")).get("pid")
            if old and old != pid:
                k = ctypes.windll.kernel32
                h = k.OpenProcess(0x0400, False, int(old))  # PROCESS_QUERY_INFORMATION
                if h:
                    k.CloseHandle(h)
                    print("已存在活实例 pid=%s -> 新实例自退" % old, flush=True)
                    return False
        with open(lock, "w", encoding="utf-8") as f:
            json.dump({"pid": pid, "ts": time.strftime("%F %T")}, f)
    except Exception as e:
        print("lock 异常(保守继续单跑): %s" % e, flush=True)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--once", action="store_true", help="单拍(cron验收用)")
    args = ap.parse_args()
    ok = mt5.initialize()
    if not ok:
        print("INIT FAIL %s" % (mt5.last_error(),))
        sys.exit(1)
    a = mt5.account_info()
    if a is None or int(a.login) != 60137964:
        print("账户不对=%s 拒跑" % (getattr(a, "login", None),))
        sys.exit(1)
    # M2修复: 启动时恢复 peak 状态 (重启/1min 心跳自愈后棘轮续推链不断)
    _peak_file = os.path.join(ROOT, "data", "sd_peak_state.json")
    if os.path.exists(_peak_file):
        try:
            for k, v in json.load(open(_peak_file, encoding="utf-8")).items():
                _state[k] = dict(v, peak_r=v.get("peak_r", 0.0))
        except Exception:
            pass
    if not _acquire_lock():
        mt5.shutdown()
        return
    if args.once:
        tick_once(args.live)
        mt5.shutdown()
        return
    print("SD锁利守护启动 live=%s magic=%d pid=%d" % (args.live, MAGIC, os.getpid()), flush=True)
    while True:
        try:
            tick_once(args.live)
        except Exception as e:
            print("tick 异常(自愈继续): %s" % e, flush=True)
        time.sleep(TICK)
    mt5.shutdown()


if __name__ == "__main__":
    main()
