# -*- coding: utf-8 -*-
"""
auto_run_cycle.py — 金策宗师团 自动全链 (LIVE 训练模式, 2026-09-25 起)
================================================================
李老师指令: 模拟号当实盘练一个月, 尽管开单 (带风控纪律)。
每轮自动:
  ① 对账: 只平"孤儿仓" (MT5 里 magic=20260902 但不在挂单状态机跟踪里的),
     状态机跟踪的持仓由 L1-L6 铁律管理, 绝不手平
  ② CIO 全链 (数据管家→看图识势→事件→研究→交易→风控→挂单交易部 LIVE 实挂)
  ③ 训练日志: 净值曲线 CSV + 每日绩效报告 (data/training_log/)
安全: 1%单笔 | ≤3仓 | 每品种≤3单/日 | 日亏3%熔断 | 连亏3笔冷却24h
"""
import os, sys, json, time, datetime, subprocess
# [2026-10-21 chief L1] OpenBLAS 内存墙修复: 限 OpenBLAS/OMP 线程=2 (父 env 被子进程继承, 各入口另自设双保险).
# 20:02 三腿(CIO/币圈/股指日内)全 退出码=1 "OpenBLAS Memory allocation failed" = 默认满线程×物理内存紧张(Free~771MB).
# 只修资源争抢, 不碰撤单/挂单/LIVE 配置.
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["OPENBLAS_NUM_THREADS"] = "2"
try:
    import msvcrt  # Windows-only: 双实例互斥锁 (t_528b267c 根因②)
except ImportError:
    msvcrt = None

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
LOG = os.path.join(DATA, "auto_cycle.log")
TLOG = os.path.join(DATA, "training_log")
# [2026-10-23 后台化] python.exe(带窗口) -> pythonw.exe(无窗口): 全链循环内部 20+ 处子脚本调用
# 全走此 PY, 每拉一个都弹黑框糊屏幕. 子脚本全部 capture_output 走管道(非控制台), 换 w 版无窗安全.
# 只换解释器, 交易逻辑/持仓/熔断/计数一字不动.
PY = "C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/pythonw.exe"
SWING_MAGIC = 20260902


def log(line):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_state():
    p = os.path.join(DATA, "pending_orders_state.json")
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            pass
    return {"pending": {}, "filled": {}, "daily_opens": {}, "consec_losses": 0,
            "cooldown_until": 0, "symbol_pause": {}, "history": []}


def save_state(st):
    json.dump(st, open(os.path.join(DATA, "pending_orders_state.json"), "w",
                       encoding="utf-8"), ensure_ascii=False, indent=2)


def step0_write_dashboard_snap():
    """治"看板卡旧日期/旧净值": 在 step2f 生成看板之前, 先把活体 MT5 账户实读写成
    data/_tmp_mt5snap.json (复用独立脚本 mt5_snapshot_write.py, fail-open 不崩全链)。
    Windows 计划任务环境 PYTHONPATH 干净, 直接 subprocess 跑, 无需 mt5_launch。"""
    try:
        r = subprocess.run([PY, os.path.join(ROOT, "mt5_snapshot_write.py")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT, timeout=90)
        for ln in (r.stdout or "").strip().splitlines():
            log("  " + ln)
        if r.returncode != 0:
            log("  [快照] 脚本退出码=%s %s" % (r.returncode, (r.stderr or "").strip()[:150]))
    except Exception as ex:
        log("  [快照] fail-open 跳过: %s" % str(ex)[:120])


def step1_d_reconcile_book_live():
    """[2026-10-05 V13 根治·统一实读入口] 派生簿对账: 三 magic 全簿的 filled 孤儿
    (status=open 但实读无同 magic 该票活仓位) 自动降终态(pnl 走 history_deals 回填)
    + pending 残留票清账. 纯数据源对账层, 不发单/不碰真闸源(event_risk.json/币系
    冻结桥一字不动). 排在 reconcile-orphans 之后, fail-open: 任何异常不影响全链."""
    try:
        import mt5_live_read
        r = mt5_live_read.settle_all_orphans()
        if "reason" in r:
            log("  [簿实对账] " + r["reason"])
        else:
            log("  [簿实对账] " + " ".join("%s=%s" % (k, v) for k, v in r.items()) + " (统一实读入口, 派生簿降为留痕)")
    except Exception as ex:
        log("  [簿实对账] fail-open 跳过: %s" % str(ex)[:120])


def step1_reconcile_orphans():
    """孤儿仓"收养"进挂单状态机 (不手平, 交给 L1-L6 铁律管理 SL/TP):
    MT5 里有某 magic 但对应状态机没跟踪的持仓 → 注册为 filled(开仓, regime=adopted),
    后续由 L2提前平/L3保本/L4吊灯/L1认盈亏 接管。这样残余单也纳入纪律管理。
    [2026-09-26 扩展] 原来只收养外汇(20260902), 币圈(20260903)/股指(20260904)孤儿没人管
    → SOLUSD 9单堆叠全是币圈孤儿。现在三个 magic 全收, 且收养后 can_open 认持仓数上限。
    """
    script = """
import MetaTrader5 as mt5, json, time, os
PAIRS = [
    (r'E:\\GoldstrategyEngine\\data\\pending_orders_state.json', 20260902, 'forex'),
    (r'E:\\GoldstrategyEngine\\data\\crypto_pending_state.json', 20260903, 'crypto'),
    (r'E:\\GoldstrategyEngine\\data\\equity_pending_state.json', 20260904, 'equity'),
]
mt5.initialize()
if not mt5.login(60137964, password='Lym141345$', server='TradeMaxGlobal-Demo'):
    print('MT5登录失败'); exit(0)
allpos = mt5.positions_get() or []
now_ts = int(time.time())
for STPATH, MAGIC, SRC in PAIRS:
    ST = json.load(open(STPATH, encoding='utf-8')) if os.path.exists(STPATH) else {'pending':{},'filled':{},'history':[]}
    tracked = {int(f['mt5_ticket']) for f in ST.get('filled', {}).values() if f.get('mt5_ticket')}
    pos = [p for p in allpos if p.magic == MAGIC]
    orphans = [p for p in pos if int(p.ticket) not in tracked]
    if SRC == 'crypto':
        # 币圈孤儿按 (sym,side) 记, layer 默认 range(震荡腿反复成交是主流); 交给 L1-L6
        layer_of = 'range'
    else:
        layer_of = 'trend'
    print(f'[{SRC}] 系统仓={len(pos)} 孤儿仓={len(orphans)}')
    for p in orphans:
        key = f'MT5_{p.ticket}'
        ST.setdefault('filled', {})[key] = {
            'sym': p.symbol, 'side': 'BUY' if p.type == 0 else 'SELL',
            'entry': p.price_open, 'fill_px': p.price_open,
            'sl': p.sl, 'tp': p.tp, 'lots': p.volume, 'regime': 'adopted',
            'layer': layer_of, 'src': SRC, 'risk_pct': 0.01, 'placed_ts': now_ts,
            'status': 'open', 'peak': p.price_open, 'last_pnl': None, 'mt5_ticket': p.ticket,
        }
        ST.setdefault('history', []).append({'ts': now_ts, 'evt': '孤儿仓收养进状态机',
                                              'sym': p.symbol, 'ticket': p.ticket, 'entry': p.price_open, 'layer': layer_of})
        print(f'  [{SRC}] 收养 #{p.ticket} {p.symbol} {p.volume}手 @{p.price_open} SL={p.sl} TP={p.tp}')
    json.dump(ST, open(STPATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
acc = mt5.account_info()
print(f'净值=${acc.equity:.2f} 总持仓={len(allpos)}')
mt5.shutdown()
"""
    r = subprocess.run([PY, "-c", "import os, time\n" + script], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
                       timeout=300)  # [t_528b267c] IPC 握手冻死防线: 原先无 timeout, initialize 卡死=全链 stall 任务槽
    for l in (r.stdout or "").strip().splitlines():
        log(f"  [收养] {l}")
    if r.returncode != 0:
        log(f"  [收养] 异常: {(r.stderr or '').strip()[:200]}")
    return r


def step1b_dedupe_trim():
    """[2026-09-26] 品种持仓堆叠自动修剪: 每品种实盘持仓>3单 → 砍回3 (保留 逆方向对冲+SL最紧).
    治 SOLUSD 9单/POLUSD 7单 同价堆叠. 只减仓不加仓 (保险丝原则), 用品种实际支持的 filling mode
    (build 6182 盲试 FOK/IOC 会 retcode=10030; 读 symbol_info.filling_mode 位掩码 0x1=FOK 0x2=IOC).
    MT5 'Algo Trading' 按钮关闭时 retcode=10027 → 只记日志不炸 (开关是用户在终端上点的)."""
    script = """
import MetaTrader5 as mt5, json, time, os
PAIRS = [
    (r'E:\\GoldstrategyEngine\\data\\pending_orders_state.json', 20260902),
    (r'E:\\GoldstrategyEngine\\data\\crypto_pending_state.json', 20260903),
    (r'E:\\GoldstrategyEngine\\data\\equity_pending_state.json', 20260904),
]
MAX_PER_SYM = 3
mt5.initialize()
if not mt5.login(60137964, password='Lym141345$', server='TradeMaxGlobal-Demo'):
    print('登录失败, 跳过堆叠修剪'); exit(0)
allpos = mt5.positions_get() or []
by_sym = {}
for p in allpos:
    by_sym.setdefault(p.symbol, []).append(p)
algo_off = False
for sym, ps in sorted(by_sym.items()):
    if len(ps) <= MAX_PER_SYM:
        continue
    net_buy = sum(1 for p in ps if p.type == 0); net_sell = len(ps) - net_buy
    def keep_score(p):
        opposite = (p.type == 0 and net_sell > net_buy) or (p.type == 1 and net_buy > net_sell)
        return (1 if opposite else 0, -abs((p.sl or 1e18) - p.price_open), p.ticket)
    order = sorted(ps, key=keep_score, reverse=True)
    cut = order[MAX_PER_SYM:]
    print(f'[{sym}] {len(ps)}→{MAX_PER_SYM}, 砍 {len(cut)}: ' + ', '.join(f'#{p.ticket}' for p in cut))
    for p in cut:
        tick = mt5.symbol_info_tick(sym)
        if tick is None: continue
        otype = mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY
        px = tick.bid if p.type == 0 else tick.ask
        sinfo = mt5.symbol_info(sym)
        fm = (sinfo.filling_mode if sinfo else 0)
        cands = ([mt5.ORDER_FILLING_IOC] if fm & 2 else []) + ([mt5.ORDER_FILLING_FOK] if fm & 1 else [])
        if not cands: cands = [0]
        for fill in cands:
            r = mt5.order_send({'action': mt5.TRADE_ACTION_DEAL, 'symbol': sym, 'volume': p.volume,
                                'type': otype, 'position': p.ticket, 'price': px, 'magic': p.magic,
                                'comment': 'dedupe_trim', 'deviation': 50,
                                'type_time': mt5.ORDER_TIME_GTC, 'type_filling': fill})
            if r and r.retcode == mt5.TRADE_RETCODE_DONE:
                print(f'  已砍 #{p.ticket} ({sym} 减回≤{MAX_PER_SYM})')
                break
            elif r:
                if r.retcode == 10027:
                    algo_off = True; break
                print(f'  砍失败 #{p.ticket} retcode={r.retcode} {r.comment}'); break
if algo_off:
    print('[!] 终端"算法交易"开关关闭(10027), 本轮修剪未执行 — 请在 MT5 终端点开 算法交易 按钮, 下轮自动重试')
mt5.shutdown()
"""
    r = subprocess.run([PY, "-c", "import os, time\n" + script], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
                       timeout=300)  # [t_528b267c] 同上: 修剪段加 timeout
    for l in (r.stdout or "").strip().splitlines():
        log(f"  [修剪] {l}")
    if r.returncode != 0:
        log(f"  [修剪] 异常: {(r.stderr or '').strip()[:200]}")
    return r


def step1c_dedupe_pending_orders():
    """[2026-09-26] 同价堆叠挂单自动去重: 同品种+同方向+同价位≥2张 → 保留票号最新1张, 撤掉旧的.
    治实盘89张挂单里 XRP@1.442×2 / UNI@10.957×2 / ADA@0.2307×2 等同价重复 (价到双倍成交).
    撤单同时清掉三个状态机 st['pending'] 里被撤票号的条目, 防 reevaluate '撤旧重挂' 把去重后的单再挂回来.
    只去重, 不动点位/RR (用户只授权清堆叠). 纯撤单, 失败开放."""
    r = subprocess.run(
        [PY, "-c", '''
import sys, json, os, time
sys.path.insert(0, "E:/GoldstrategyEngine")
import MetaTrader5 as mt5
ok = mt5.initialize()
mt5.login(60137964, password="Lym141345$", server="TradeMaxGlobal-Demo")
orders = [o for o in (mt5.orders_get() or [])]
groups = {}
for o in orders:
    groups.setdefault((o.symbol, int(o.type), o.price_open), []).append(o)
dups = {k: v for k, v in groups.items() if len(v) > 1}
to_del = []
for (sym, otype, px), lst in sorted(dups.items()):
    lst.sort(key=lambda o: o.ticket)
    for o in lst[:-1]:        # 保留票号最新1张, 撤掉旧的
        to_del.append(o)       # 带整张订单对象, 撤单请求字段齐全
out = {"deleted": [], "failed": [], "state_cleaned": []}
if to_del:
    for o in to_del:
        tk, sym, magic = o.ticket, o.symbol, o.magic
        # build 6182 撤单: TRADE_ACTION_REMOVE 需 挂单的全部关键字段 (缺 symbol/type/price 会 10013)
        # 挂单对象的成交量字段是 volume_current (没有 .volume, 用了会 AttributeError 崩)
        res = mt5.order_send({'action': mt5.TRADE_ACTION_REMOVE, 'ticket': tk,
                              'symbol': sym, 'type': o.type, 'price': o.price_open,
                              'magic': magic, 'volume': o.volume_current})
        rc = res.retcode if res is not None else -1
        if rc in (mt5.TRADE_RETCODE_DONE, 10007):   # 10007=done (order wasn't found) 也算已清
            out["deleted"].append({"ticket": tk, "sym": sym, "type": o.type, "px": o.price_open})
        else:
            out["failed"].append({"ticket": tk, "sym": sym, "type": o.type, "px": o.price_open, "retcode": rc,
                                  "note": "10027=终端算法交易关闭, 无法撤单, 保持挂单现状" if rc == 10027 else "未知"})
    # 清状态机里被撤票号的 pending 条目 (防撤了单状态机还认账 → reevaluate 重挂)
    state_files = [
        "E:/GoldstrategyEngine/multi_agent/trading/crypto_pending_state.json",
        "E:/GoldstrategyEngine/multi_agent/trading/pending_orders_state.json",
        "E:/GoldstrategyEngine/multi_agent/trading/equity_pending_state.json",
    ]
    deleted_tk = {d["ticket"] for d in out["deleted"]}
    for sf in state_files:
        if not os.path.exists(sf) or not deleted_tk:
            continue
        st = json.load(open(sf, encoding="utf-8"))
        pend = st.get("pending", {})
        hit = 0
        for tk in list(pend.keys()):
            key_int = int(tk) if str(tk).isdigit() else -1
            if key_int in deleted_tk:
                del pend[tk]
                hit += 1
        if hit:
            st["pending"] = pend
            json.dump(st, open(sf, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            out["state_cleaned"].append({"file": os.path.basename(sf), "removed": hit})
    print("[dedupe-pending]", json.dumps(out, ensure_ascii=False))
else:
    print("[dedupe-pending] 无同价堆叠挂单, 无需清理")
mt5.shutdown()
'''],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)  # [t_528b267c] 180->300: 留足撤单批次, 仍封顶防 IPC 冻死霸槽
    out = (r.stdout or "").strip()
    log(f"[step1c 同价挂单去重] {out or r.stderr.strip()[:120]}")
    return r.returncode


def step2_cio():
    r = subprocess.run([PY, "cio_orchestrator.py"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=os.path.join(ROOT, "multi_agent"), timeout=600)
    out = (r.stdout or "").strip()
    for l in out.splitlines():
        if any(x in l for x in ["═══", "CIO·", "完成", "挂单", "✓", "⛔", "⏸", "·"]):
            log(f"  [CIO] {l}")
    if r.returncode != 0:
        log(f"  [CIO] 退出码={r.returncode} 报错: {(r.stderr or '').strip()[:300]}")
    return r


def step2a_refresh_mt5_snapshot():
    """[2026-11-04 chief L1 · L6 数据管道格] data_health 的米 = mt5_live_read_*.json 快照池,
    10-27 起 0 写入者(dated 快照停 @10-27_1305, 遗留 refresh.json 停 @10-23) → 体温表 7 天拿旧源算。
    治: data_health 之前若最新 dated 快照 >900s, 重跑 tools/mt5_realtime_read.py(与 auto_market_cycle
    step1_read 同一写入者/同一 10 品种 schema), 同时写:
      ① dated 新文件 mt5_live_read_{ts}.json (ATR 日环比/历史留痕);
      ② 滚动当值 mt5_live_read_refresh.json (所有 glob+字典序取末 的读方 —
         gen_market_analysis/deep_dive/hermes_group_chat/ea_advisory_feed ref_price — 一并复活)。
    fail-open: 刷新失败不崩全链, data_health 按旧源自标 stale → 体温表整批保守 0 开(安全语义不变, 诚实报源冻结)。
    成本: 每 tick 一次短 MT5 读(与 step0 dashboard snap 同量级), 非 K线全量回填, 不与 00:10 静默窗争 IPC。
    0 开单 0 撤单 0 闸源写, 纯数据层。"""
    import glob as _glob
    pool = [f for f in _glob.glob(os.path.join(DATA, "mt5_live_read_*.json"))]
    if pool:
        fresh = max(pool, key=os.path.getmtime)
        age = time.time() - os.path.getmtime(fresh)
        if age <= 900:
            log("  [快照刷新] 最新米快照 %s 新鲜(%.0fs), 跳过" % (os.path.basename(fresh), age))
            return
        log("  [快照刷新] 最新米快照 %s 陈旧(%.0fs), 重读 MT5" % (os.path.basename(fresh), age))
    else:
        log("  [快照刷新] 无 dated 快照, 重读 MT5")
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    out_dated = os.path.join(DATA, "mt5_live_read_%s.json" % ts)
    out_refresh = os.path.join(DATA, "mt5_live_read_refresh.json")
    env = dict(os.environ)
    env["OMP_NUM_THREADS"] = "2"
    env["OPENBLAS_NUM_THREADS"] = "2"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        p = subprocess.run([PY, os.path.join(ROOT, "tools", "mt5_realtime_read.py")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=240, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                           cwd=ROOT, env=env)
        if p.returncode != 0:
            log("  [快照刷新] 读失败(退出码=%s, fail-open, data_health 将按旧源 stale 报): %s"
                % (p.returncode, ((p.stderr or p.stdout) or "").strip()[:150]))
            return
        data = json.loads((p.stdout or "").strip())
        if not data.get("symbols"):
            log("  [快照刷新] 无实读品种, 不写(fail-open, 下轮自补)")
            return
        json.dump(data, open(out_dated, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        json.dump(data, open(out_refresh, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        ok_n = sum(1 for s in data["symbols"] if s.get("available"))
        log("  [快照刷新] %s 实读成功 %d/%d 品种(账户 %s), dated+refresh 双写"
            % (os.path.basename(out_dated), ok_n, len(data["symbols"]), data.get("account_login")))
    except Exception as ex:
        log("  [快照刷新] 异常(fail-open, data_health 按旧源 stale 报): %s" % str(ex)[:120])


def step2_data_health():
    """[2026-10-26 L5 data_health producer 挂 30min 循环] 独立闸源 data_health.json 每轮刷新, 治洞③ stale 恒 True。

    根因: data_health.py 的米 = mt5_live_read_*.json (K线时间戳), 此前只盘窗/分析时手跑, 独立源 22:09 后没人刷 →
    体温表每 30min 读它判 stale(>1800s) → data_unreliable 恒 True = 闸永久锁死全市场 0 开 (非健康活闸)。
    挂点: CIO 全链(step2_cio)已实读刷新 mt5_live_read 之后、体温表(step2c_governor→write_risk_state)之前 →
    本轮算出最新 绿/黄/红 落独立源, 体温表同轮读到新鲜 ts → 不 stale → 闸健康。
    fail-open: MT5 断连/无新快照 → data_health.py 报"无快照不写"(保旧), 体温表判 stale → data_unreliable=True
    整批保守 0 开 (安全语义不变, 只记一行不阻断主循环); 0 下单 0 撤单, 纯闸源刷新。"""
    try:
        r = subprocess.run([PY, os.path.join(ROOT, "tools", "data_health.py")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT, timeout=120)
        for l in (r.stdout or "").strip().splitlines():
            log("  [data_health] " + l)
        if r.returncode != 0:
            log("  [data_health] 退出码=%d fail-open (保独立源旧值, 体温表判 stale 保守 0 开): %s"
                % (r.returncode, (r.stderr or "").strip()[:150]))
    except Exception as ex:
        log("  [data_health] 跳过错 (fail-open): %s" % str(ex)[:120])


def step2_s_tier_overlay():
    """[2026-10-18 strategy-rd 缺口收口] S级事件全停覆层. CIO 每拍重生成 event_risk.json
    只实现基础4级(FOMC 前1h顶多HIGH 0.3x), 不执行 event_tier_gate.json 的 S级全停判据
    (FOMC 提前360min halt / 提前60min scale=0). 本步在 CIO 之后、币系/总督/体温表之前,
    按 event_tier_gate.active_windows 时间窗把 event_risk.json 覆写到全停档.
    确定性 Python 覆层, fail-open(读不到gate/异常→no-op, 绝不阻断主循环), 0开单0正向提权, 纯否决/降档."""
    fp = os.path.join(DATA, "event_s_tier_overlay.py")
    if not os.path.exists(fp):
        return
    try:
        r = subprocess.run([PY, fp], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        for l in (r.stdout or "").strip().splitlines():
            log(f"  {l}")
        if r.returncode != 0:
            log(f"  [S级全停闸] 退出码={r.returncode} fail-open (报错:{(r.stderr or '').strip()[:150]})")
    except Exception as ex:
        log(f"  [S级全停闸] 异常 fail-open: {str(ex)[:120]}")


def step2b_crypto():
    """币圈挂单部: 每轮重估 8 币点位(趋势Stop+震荡Limit, R1-R5撤失效单) + L1-L5持仓处置。"""
    r = subprocess.run([PY, "crypto_pending.py"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=os.path.join(ROOT, "multi_agent", "trading"), timeout=600)
    out = (r.stdout or "").strip()
    for l in out.splitlines():
        if any(x in l for x in ["═══", "净值", "分配", "成交", "处置", "✓", "⛔", "撤", "L1", "L2", "L3", "L4", "L5"]):
            log(f"  [币圈] {l}")
    if r.returncode != 0:
        log(f"  [币圈] 退出码={r.returncode} 报错: {(r.stderr or '').strip()[:300]}")
    return r


def step2c_governor():
    """组合风险总督(第13部门): 管总敞口——总热量/净方向/相关簇/回撤刹车/波动率缩放, 只泄压不加仓。
step2c_governor 先跑; 其后把组合风险体温表写进 data/risk_state.json (L4 t_a3872914 承接),
供组合风险总督(第13部门)与事件快通道 event_guard.py 读它做"只泄压不加息"。fail-open。"""
    r = subprocess.run([PY, "portfolio_governor.py"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=os.path.join(ROOT, "multi_agent", "trading"), timeout=600)
    out = (r.stdout or "").strip()
    for l in out.splitlines():
        if any(x in l for x in ["═══", "净值", "heat", "回撤", "泄压", "⚠", "仪表盘"]):
            log(f"  [总督] {l}")
    if r.returncode != 0:
        log(f"  [总督] 退出码={r.returncode} 报错: {(r.stderr or '').strip()[:300]}")
    # risk_state.json 落盘 (写体温表, 不发明数字, 全读上一步刚刷的 governor_state 等源)
    try:
        r2 = subprocess.run([PY, os.path.join(ROOT, "write_risk_state.py")],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT, timeout=60)
        for l in (r2.stdout or "").strip().splitlines():
            log(f"  [风控体温表] {l}")
        if r2.returncode != 0:
            log(f"  [风控体温表] 退出码={r2.returncode} fail-open 跳过")
    except Exception as ex:
        log(f"  [风控体温表] fail-open 跳过: {str(ex)[:120]}")
    return r


def step2d_equity():
    """股指/美股日内猎杀部(第15部门): T3股指8+大股16 前日高低流动性池猎杀, kill zone+点差税+不过夜三道闸。"""
    r = subprocess.run([PY, "equity_pending.py"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=os.path.join(ROOT, "multi_agent", "trading"), timeout=600)
    out = (r.stdout or "").strip()
    for l in out.splitlines():
        if any(x in l for x in ["═══", "净值", "成交", "处置", "撤", "✓", "⛔", "✗", "闸门"]):
            log(f"  [股指/美股日内] {l}")
    if r.returncode != 0:
        log(f"  [股指/美股日内] 退出码={r.returncode} 报错: {(r.stderr or '').strip()[:300]}")
    return r


def step2e_meta():
    """自我进化部(第16部门): 滚动30笔按层统计边衰(expectancy/SQN/胜率) → 生成下轮挂单部的仓位缩放快照 + 有效分散度EP。"""
    r = subprocess.run([PY, "meta_evolver.py"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=os.path.join(ROOT, "multi_agent", "trading"), timeout=600)
    out = (r.stdout or "").strip()
    for l in out.splitlines():
        if any(x in l for x in ["═══", "缩放", "样本", "EP", "边衰"]):
            log(f"  [进化] {l}")
    if r.returncode != 0:
        log(f"  [进化] 退出码={r.returncode} 报错: {(r.stderr or '').strip()[:300]}")
    return r


def step2e1_ea_feed():
    """L5 EA 开单 feed (2026-11-02 chief 派钩): 纯文件读 3 闸源+状态簿 → data/ea_advisory.csv/.json,
    喂终端内 EA(L5 开单腿)与看板开单自检面板。确定性一行、0 LLM、0 写闸源。
    fail-open: 报错只记一行, 绝不阻断进化/全链主循环。"""
    r = subprocess.run([PY, "ea_advisory_feed.py"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=os.path.join(ROOT, "multi_agent", "trading"), timeout=300)
    out = (r.stdout or "").strip()
    for l in out.splitlines():
        if "[L5 ea_feed]" in l:
            log(f"  {l}")
    if r.returncode != 0:
        log(f"  [EA feed] 退出码={r.returncode} 报错: {(r.stderr or '').strip()[:300]}")
    return r


def step2f_advisory():
    """每日全品种研判部(第17部门): 亚/欧/美盘各1次全品种系统分析(248个)→方向预判+目标止损→提前挂单,
    次日自动反思对账(天天练习)。脚本内部做盘口窗口门控+幂等(错过不追, 下盘补), 循环轮内只反思。fail-open。"""
    r = subprocess.run([PY, "daily_advisory.py"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=os.path.join(ROOT, "multi_agent", "trading"), timeout=900)
    out = (r.stdout or "")
    for l in out.splitlines():
        if any(x in l for x in ["[研判]", "[反思]", "[看板", "胜率", "晋升"]):
            log(f"  [研判] {l}")
    if r.returncode != 0:
        log(f"  [研判] 退出码={r.returncode} 报错: {(r.stderr or '').strip()[:300]}")
    # [2026-10-05 盘感岗 chief] 0.573 edge → 高RR人工操盘候选生成器 + 24h自我复盘循环.
    # 每轮 [反思] 对账后顺手跑一次: ①出够格候选(只留痕不挂单) ②回填对错+期望R 写 lessons.
    # fail-open: 任一脚本异常只记一行, 绝不阻断研判/全链主循环.
    try:
        r2 = subprocess.run([PY, os.path.join(DATA, "discretion_candidate.py")],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        for l in (r2.stdout or "").splitlines():
            if l.strip():
                log(f"  [操盘候选] {l.strip()}")
        if r2.returncode != 0:
            log(f"  [操盘候选] 退出码={r2.returncode} 报错: {(r2.stderr or '').strip()[:200]}")
        r3 = subprocess.run([PY, os.path.join(DATA, "discretion_review_24h.py")],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        for l in (r3.stdout or "").splitlines():
            if l.strip():
                log(f"  [24h复盘] {l.strip()}")
        if r3.returncode != 0:
            log(f"  [24h复盘] 退出码={r3.returncode} 报错: {(r3.stderr or '').strip()[:200]}")
    except Exception as ex:
        log(f"  [操盘候选] 生成/复盘跳过错 (fail-open): {ex}")
    # [2026-10-20 11:50 影子交易接入] 候选产出后立即导入影子组合（沙盒，0 order_send）。
    # 顺序保证：discretion_candidate.py 已写完 discretion_candidates.json -> 此时导入最准。
    # 幂等：同一 candidate id 重复导入不产生重复影子单，故每轮调用无副作用。
    # fail-open: 导入异常只记一行, 绝不阻断主循环。
    try:
        r4 = subprocess.run([PY, os.path.join(DATA, "shadow_portfolio.py")],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        for l in (r4.stdout or "").splitlines():
            if l.strip():
                log(f"  [影子导入] {l.strip()}")
        if r4.returncode != 0:
            log(f"  [影子导入] 退出码={r4.returncode} 报错: {(r4.stderr or '').strip()[:200]}")
    except Exception as ex:
        log(f"  [影子导入] 跳过错 (fail-open): {ex}")
    return r


def step2g_alpha_if_events_moved():
    """[2026-09-30 strategy-rd] alpha_rating 事件面动才刷: HIGH 事件进/退 24h 窗口才触发
    alpha_researcher.py 单刷评级 (不随 30min 空转). 判据: 本次 HIGH 集合的 (ts,symbol) 指纹
    与上次落盘指纹不同才跑. 失败开放: 任何异常只记一行不阻断主循环。"""
    fp_path = os.path.join(DATA, "alpha_event_fingerprint.json")
    try:
        ev = json.load(open(os.path.join(DATA, "event_risk.json"), encoding="utf-8"))
        hi = [e for e in ev.get("events", []) if "HIGH" in str(e.get("impact", e.get("level", ""))).upper()]
        fp = json.dumps(sorted([(e.get("time"), str(e.get("symbol", e.get("symbols")))) for e in hi]),
                        ensure_ascii=False)
        last = json.load(open(fp_path, encoding="utf-8")).get("fp") if os.path.exists(fp_path) else None
        if fp != last:
            r = subprocess.run([PY, "alpha_researcher.py"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                               cwd=os.path.join(ROOT, "multi_agent", "research"), timeout=300)
            json.dump({"fp": fp, "ts": int(time.time()), "rc": r.returncode},
                      open(fp_path, "w", encoding="utf-8"))
            log(f"  [alpha] HIGH事件指纹变化 -> 刷新评级 (rc={r.returncode}, HIGH={len(hi)})")
        else:
            log(f"  [alpha] HIGH事件面未动({len(hi)}支), 跳过刷评级 (省预算)")
    except Exception as ex:
        log(f"  [alpha] 事件触发跳过错 (fail-open): {ex}")


def step2h_edge_tracker_refresh():
    """[2026-10-02 P1 周会⑥.0] 胜负回填线: 每轮 30min 循环自动 refresh edge_tracker.
    上轮实拉销账: refresh 之前是手跑的, 外网断/循环降级时文件会再次陈旧 (停 09-30 14:56 无 session_tag).
    挂进 main() 后, 每轮自动从 MT5 history_deals 拉近 30 天平仓 → 写
    data/edge_tracker.json (含 _session_tag 亚/欧/美×精选/非精选 8 组同分母分解).
    fail-open: MT5 连不上 / refresh 异常 → 记一行不阻断主循环 (文件保上次内容, 不写脏).
    不烧 key / 不动交易动作 (纯 stats 重算, 确定性 Python)."""
    try:
        r = subprocess.run([PY, "-c", '''
import sys, json, os
sys.path.insert(0, "E:/GoldstrategyEngine")
import MetaTrader5 as mt5
ok = mt5.initialize()
if not ok:
    print("[edge_refresh] mt5 init 失败, 跳过 (fail-open, 保上次文件)")
    sys.exit(0)
try:
    import edge_tracker
    edge_tracker.refresh(mt5, days=30)
    c = edge_tracker._load()
    n_syms = len(c.get("symbols", {}))
    n_tag = sum(1 for v in c["symbols"].values() if isinstance(v, dict) and v.get("session_tag"))
    print(f"[edge_refresh] 品种 {n_syms} | 带分盘口 {n_tag} | updated {c.get('updated')}")
except Exception as e:
    print(f"[edge_refresh] refresh 异常 (fail-open): {e}")
finally:
    mt5.shutdown()
'''], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
        for l in (r.stdout or "").splitlines():
            if l.strip():
                log(f"  [edge] {l.strip()}")
    except Exception as ex:
        log(f"  [edge] refresh 跳过错 (fail-open): {ex}")


def step2h2_liquidity_universe_refresh():
    """[2026-10-21 chief 方案D] 流动性宇宙刷新线: 每轮 30min 循环自动刷新.

    背景: chief 方案D 要求「流动性 Top-N 宇宙」做准入闸 (setup_universe.combo_allowed),
    但宇宙数据此前靠手跑 —— 停几小时后美股龙头会被 peak 采样漏掉,
    导致美股信号全部被 liquidity 闸拦掉 (候选归零, 影子样本断流).

    频率控制: 宇宙重建要扫 248 个品种 × 多窗口 peak 采样 (约 30~60s),
    不能每轮都跑。TTL=6h: 覆盖至少一个完整美盘时段 (peak 采样含 4h 偏移窗口),
    保证美股龙头不会因采样时点而漏榜。

    fail-open: MT5 连不上 / 异常 → 保上次文件不写脏, 记一行不阻断主循环。
    不烧 key / 不动交易动作 (纯 tick 统计, 确定性 Python)。"""
    import json as _json
    UNI = os.path.join(DATA, "liquidity_universe.json")
    TTL_H = 6
    try:
        need = True
        if os.path.exists(UNI):
            try:
                d = _json.load(open(UNI, encoding="utf-8"))
                gen = d.get("generated", "")
                if gen:
                    from datetime import datetime as _dt
                    age_h = (_dt.now() - _dt.strptime(gen, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600.0
                    if age_h < TTL_H:
                        need = False
                        log(f"  [universe] 宇宙仍新鲜 ({age_h:.1f}h < {TTL_H}h), {len(d.get('symbols', []))} 品种, 跳过重建")
            except Exception:
                need = True   # 文件损坏 -> 必须重建
        if not need:
            return
        r = subprocess.run([PY, "-u", os.path.join(DATA, "liquidity_universe.py")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=280)
        for l in (r.stdout or "").splitlines():
            if l.strip().startswith(("流动性宇宙", "扫描", "落盘")):
                log(f"  [universe] {l.strip()}")
        if r.returncode != 0:
            log(f"  [universe] 重建退出码={r.returncode} (fail-open): {(r.stderr or '').strip()[:160]}")
    except Exception as ex:
        log(f"  [universe] 刷新跳过错 (fail-open): {ex}")


def step2i_shadow_feed():
    """[2026-10-20 L5 P1 影子喂样链] 影子单判定 → discretion_edge_mined 喂样, 每轮 30min 循环自动跑.
    破死循环出口: 14 天 0 实单 0 回填 → edge 层饿死 (ts 钉 10-05 > TTL 7 天, expR 否决门禁用)。
    链: shadow_evaluator.py (只读行情判定, 0 order_send 沙盒) → shadow_edge_feed.py (幂等喂样, 0 LLM 确定性)。
    契约 (L4 #865/#866 焊死): paper 0 金线 / 只喂真判定单 / 纸面 18.3R 判词基线 0 计入影子分母 /
    50 笔前 INSUFFICIENT 不 GO。fail-open: 任一脚本异常只记一行, 绝不阻断主循环 (A4: 挂后 2 个 30min
    循环 ts 未跳=缺陷回滚锚, 第 1 循环未跳=结算窗非故障)。不烧 key / 不动交易动作。

    [2026-10-20 21:40 冷启动机制 · 经 chief 验收裁决]
    新重构的 shadow_edge_feed.py 严禁直接切正式写入, 必须走三阶段:
      阶段1 冷启动: 前 3 轮强制 --dry-run (只算不写, 输出 diff)
      阶段2 正式: 连续 3 轮 dry-run 输出与预期一致且无异常 -> 移除 --dry-run
      阶段3 回滚: dry-run 阶段若 sum_r_total / verdict 出现非预期偏差 -> 停在 dry-run 并告警
    状态位落 data/shadow_feed_coldstart.json, 防止人工误操作跳过验证期。"""
    state_path = os.path.join(DATA, "shadow_feed_coldstart.json")
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        st = {}
    phase = st.get("phase", "COLDSTART")          # COLDSTART -> LIVE
    dry_runs = int(st.get("dry_runs_ok", 0) or 0)
    baseline = st.get("baseline")                  # 首轮 dry-run 记录的基线值
    REQUIRED_OK = 3                                # chief 指定: 连续 3 轮一致才切正式

    feed_args = []
    if phase != "LIVE":
        feed_args = ["--dry-run"]
    for name in ("shadow_evaluator.py", "shadow_edge_feed.py"):
        args = [PY, os.path.join(ROOT, "data", name)]
        if name == "shadow_edge_feed.py" and feed_args:
            args += feed_args
        try:
            r = subprocess.run(args,
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
            for l in (r.stdout or "").splitlines():
                if any(x in l for x in ("[影子喂样]", "裁决", "INSUFFICIENT", "PASSING",
                                         "LIVE_CANDIDATE", "FAILED", "MARGINAL",
                                         "[eval]", "让出", "DRY-RUN")):
                    log("  [影子] " + l.strip())
            if r.returncode != 0:
                log("  [影子] %s 退出码=%d 报错: %s (fail-open)" % (
                    name, r.returncode, (r.stderr or "").strip()[:200]))
                continue
            if name != "shadow_edge_feed.py" or r.returncode != 0:
                continue

            # ── 冷启动状态机推进 ──────────────────────────────────
            out = r.stdout or ""
            cur = {"sum_r_total": None, "verdict": None, "decided_total": None}
            try:
                ed = json.load(open(os.path.join(DATA, "discretion_edge_mined.json"),
                                    encoding="utf-8"))
                sh = ed.get("_shadow", {})
                cur["sum_r_total"] = sh.get("sum_r_total")
                cur["verdict"] = sh.get("verdict")
                cur["decided_total"] = sh.get("decided_total")
            except Exception:
                pass

            if phase != "LIVE":
                if baseline is None:
                    baseline = cur
                    st["baseline"] = cur
                    log("  [影子] 冷启动第1轮, 已记录基线: %s" % json.dumps(cur, ensure_ascii=False))
                else:
                    # 与基线比对: 判定与累计R 不得出现非预期偏差
                    drift = []
                    for k in ("sum_r_total", "verdict"):
                        if cur.get(k) != baseline.get(k):
                            drift.append("%s: %s -> %s" % (k, baseline.get(k), cur.get(k)))
                    if drift:
                        log("  [影子] ⚠️ 冷启动偏差, 保持 dry-run 不切正式: %s" % "; ".join(drift))
                        st["phase"] = "COLDSTART"
                        st["drift"] = drift
                        st["dry_runs_ok"] = 0
                    else:
                        dry_runs += 1
                        st["dry_runs_ok"] = dry_runs
                        log("  [影子] 冷启动 dry-run %d/%d 轮, 输出与基线一致"
                            % (dry_runs, REQUIRED_OK))
                        if dry_runs >= REQUIRED_OK:
                            st["phase"] = "LIVE"
                            st["switched_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                            log("  [影子] ✅ 连续 %d 轮 dry-run 一致 -> 切正式写入 (下一轮起生效)"
                                % REQUIRED_OK)
            st["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            try:
                with open(state_path, "w", encoding="utf-8") as f:
                    json.dump(st, f, ensure_ascii=False, indent=1)
            except Exception:
                pass
        except Exception as ex:
            log("  [影子] %s 跳过错 (fail-open): %s" % (name, ex))


def step3_training_log():
    """净值曲线 + 每日绩效报告 (跨日时生成前一日报告)。
    [t_528b267c 根因①] MT5 读段改 300s 封顶子代: 原先进程内 initialize/login 无超时,
    卡 IPC 握手=全链 stall 霸任务槽 (10-19 19:32:36 卡死点就在此段). 子代超时/失败
    只记一行 fail-open, 状态机/日报逻辑照跑 (读旧净值口径由子代 JSON 带出)."""
    mt5_ok = False
    snap = {"equity": None, "balance": None, "n_pos": 0}
    script = """
import MetaTrader5 as mt5, json, sys
ok = mt5.initialize()
if not ok:
    print(json.dumps({"error": "initialize 失败: %s" % str(mt5.last_error())[:60]})); sys.exit(0)
if not mt5.login(60137964, password="Lym141345$", server="TradeMaxGlobal-Demo"):
    print(json.dumps({"error": "登录失败: %s" % str(mt5.last_error())[:60]})); sys.exit(0)
acc = mt5.account_info()
pos = mt5.positions_get(magic=20260902) or []
mt5.shutdown()
print(json.dumps({"equity": acc.equity, "balance": acc.balance, "n_pos": len(pos)}))
"""
    try:
        r = subprocess.run([PY, "-c", script], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
                           timeout=300)
        outl = (r.stdout or "").strip()
        for line in outl.splitlines():
            if line.startswith("{"):
                d = json.loads(line)
                if "error" in d:
                    log(f"  [训练] MT5读降级(fail-open): {d['error']}")
                else:
                    snap = d
                    mt5_ok = True
        if r.returncode != 0:
            log(f"  [训练] MT5读子代退出码={r.returncode} 报错: {(r.stderr or '').strip()[:150]}")
    except subprocess.TimeoutExpired:
        log("  [训练] MT5读 300s 封顶超时 (IPC 冻死族防线, fail-open) — 本拍净值曲线跳过")
    except Exception as ex:
        log(f"  [训练] MT5读跳过错 (fail-open): {ex}")

    st = load_state()
    os.makedirs(TLOG, exist_ok=True)
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    csv = os.path.join(TLOG, "equity_curve.csv")
    if not os.path.exists(csv):
        open(csv, "w", encoding="utf-8").write("ts,equity,balance,n_pos,n_pend,consec_losses\n")
    if mt5_ok:
        with open(csv, "a", encoding="utf-8") as f:
            f.write(f"{str(datetime.datetime.now())},{snap['equity']:.2f},"
                    f"{snap['balance']:.2f},{snap['n_pos']},{len(st.get('pending', {}))},{st.get('consec_losses', 0)}\n")

    # 每日报告: 状态里记 last_report_date; 若跨日(昨天的日期 != last_report_date 且 last_report_date 非空/初始) 则出昨日报
    last_rep = st.get("last_report_date", "")
    if last_rep and last_rep != today:
        # 生成 last_rep 那天的报告
        day = last_rep
        rows = [l for l in open(csv, encoding="utf-8").read().splitlines()
                if l.startswith(day)]
        if len(rows) >= 2:
            eq_first = float(rows[0].split(",")[1])
            eq_last = float(rows[-1].split(",")[1])
            trades = [h for h in st.get("history", []) if datetime.datetime.fromtimestamp(h.get("ts", 0)).strftime("%Y-%m-%d") == day]
            wins = sum(1 for h in trades if h.get("evt") in ("L5止盈/离场",) and h.get("pnl", 0) > 0)
            losses = sum(1 for h in trades if h.get("evt") == "L1止损/反转认亏")
            wr = (wins / (wins + losses)) if (wins + losses) else float("nan")
            rp = os.path.join(TLOG, f"daily_report_{day.replace('-', '')}.md")
            with open(rp, "w", encoding="utf-8") as f:
                f.write(f"# 训练日报 {day}\n\n")
                f.write(f"- 当日净值: ${eq_first:.2f} → ${eq_last:.2f} (**{eq_last - eq_first:+.2f}**)\n")
                f.write(f"- 样本数: {len(rows)} 轮 | 当日成交事件: 止盈{wins} 认亏{losses} | 胜率: {wr:.0%}\n")
                f.write(f"- 连亏计数(当前): {st.get('consec_losses', 0)} | 冷却: {'是' if time.time() < st.get('cooldown_until', 0) else '否'}\n")
                f.write(f"- 挂单记录: {sum(1 for h in trades if '挂单' in h.get('evt',''))} 笔 | 撤单: {sum(1 for h in trades if '撤单' in h.get('evt',''))} 笔\n\n")
                f.write("## 事件明细\n")
                for h in trades[-30:]:
                    f.write(f"  - {datetime.datetime.fromtimestamp(h.get('ts', 0)).strftime('%H:%M')} {h.get('evt')} {h.get('sym','')} {h.get('why','')}\n")
                f.write("\n---\n**模拟账号实盘训练 | 历史表现≠未来收益**\n")
            log(f"  [日报] 已生成 {rp}")
        st["last_report_date"] = today
        save_state(st)
    elif not last_rep:
        st["last_report_date"] = today
        save_state(st)
    if mt5_ok:
        log(f"  [训练] 净值=${snap['equity']:.2f} 系统仓={snap['n_pos']} 挂单={len(st.get('pending', {}))} 曲线已落盘")
    else:
        log(f"  [训练] MT5读降级本拍, 挂单={len(st.get('pending', {}))} 状态机/日报照跑 (fail-open, 曲线本拍跳过)")


def step2j_evolution():
    """[2026-10-21 · 主动进化] 周期性自主进化步进：增量跑1代、提升闸门、监督台账、落盘 incumbent。

    设计原则（对齐用户要求：自主进化升级 / 开发新策略 / 相互检查监督）：
      · TTL 6h，fail-open：未到周期直接跳过，绝不阻塞主交易链
      · 重活（多代 campaign、≥10 代深度优化）走 tools/run_evolution.py 手动触发
      · 本步只保证系统「一直在进化」，每周期微调候选基因组，发现的更优 genome 经
        supervision 审查通过后才替换 incumbent（宁可不进化也不引入退化策略）
      · 全程只读行情 + 只写本地 JSON，绝不下单
    """
    try:
        import time as _t
        EVOLVE_TTL = 6 * 3600
        _ed = os.path.join(ROOT, "evolution")
        try:
            import atomic_json
        except Exception:
            class _A:
                @staticmethod
                def read_json(p, d=None):
                    try:
                        return json.load(open(p, encoding="utf-8"))
                    except Exception:
                        return d
                @staticmethod
                def write_json(p, v, **k):
                    d = os.path.dirname(p)
                    if d and not os.path.isdir(d):
                        os.makedirs(d, exist_ok=True)
                    tmp = p + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(v, f, ensure_ascii=False, indent=1)
                    os.replace(tmp, p)
            atomic_json = _A()
        last = atomic_json.read_json(os.path.join(_ed, "last_run.json"), {"ts": 0})
        if _t.time() - float(last.get("ts", 0)) < EVOLVE_TTL:
            return
        # [2026-10-21 chief L1] 根修: 旧调用按"种群进化"幻影API(uni/pop_size/seed/bars_n +
        # load_incumbent/step/_save_incumbent/export_run), 真类__init__只认save_dir、方法集是
        # 网格优化器(optimize_strategy/optimize_all_strategies/get_optimal_params/adapt_to_symbol)
        # -> 构造即TypeError被fail-open吞, 进化部每拍静默跳过从未真跑(last_run.json空至今).
        # 最小内存方案: 每拍只进化OTAS(1策略), XAUUSD代表品种 h1/h4/d1=1000根(500根样本太薄,
        # 默认参数仅2笔<5必HOLD), 默认max_iterations=50采样, 不调optimize_all_strategies
        # (6策略x全组合=内存/OpenBLAS再爆). OMP/OPENBLAS=2 由本文件顶部已设(幂等补一道).
        os.environ["OMP_NUM_THREADS"] = "2"
        os.environ["OPENBLAS_NUM_THREADS"] = "2"
        from evolution_engine import EvolutionEngine
        import pandas as _pd
        import MetaTrader5 as _MT5
        eng = EvolutionEngine(_ed)
        h1 = h4 = d1 = _pd.DataFrame()
        if _MT5.initialize():
            def _rates(sym, tf, n=1000):
                r = _MT5.copy_rates_from_pos(sym, tf, 0, n)
                return _pd.DataFrame(r) if r is not None and len(r) else _pd.DataFrame()
            h1 = _rates("XAUUSD", _MT5.TIMEFRAME_H1)
            h4 = _rates("XAUUSD", _MT5.TIMEFRAME_H4)
            d1 = _rates("XAUUSD", _MT5.TIMEFRAME_D1)
            _MT5.shutdown()
        if not (len(h1) and len(h4) and len(d1)):
            log("  [进化] XAUUSD K线取数失败(h1/h4/d1有缺), fail-open 跳过 (不刷TTL, 下拍再试)")
            return
        res = eng.optimize_strategy("OTAS", h1, h4, d1)  # 网格采样50组合, trades<5自动HOLD, 有果自动_save_best_params
        atomic_json.write_json(os.path.join(_ed, "last_run.json"), {"ts": _t.time(), "strategy": "OTAS", "bars": 1000})
        if res is not None:
            log("  [进化] OTAS 采样50组合 → 最优 PF=%.2f WR=%.1f%% 交易=%d 参数=%s (已落盘)" % (res.pf, res.win_rate, res.trades, res.params))
        else:
            log("  [进化] OTAS 采样50组合 → 全部交易数<5样本不足, 按纪律HOLD (不引入未验证参数, 采样结论已落盘)")
    except Exception as e:
        log("  [进化] 步进异常(fail-open 跳过): %s" % str(e)[:120])


def _acquire_single_instance_lock():
    """[2026-10-19 t_528b267c 根因②] 双实例互斥: msvcrt 文件锁非阻塞取锁.
    10-13 / 10-19 两次双 auto_run_cycle 同跑事故(41740 父=27568 自 fork 子副本 +
    旧实例卡死霸 JinCeAutoCycle 槽 IgnoreNew): 新实例取不到锁 -> 记一行即安全退,
    绝不跟旧实例互踩(state 旧快照覆盖 = 10-26 38张连号票同族根因).
    锁跟 open handle 走: 本进程活到 main() 结束自动释放, 无需显式 unlock.
    msvcrt 不可用(非 Windows) -> fail-open 放行不阻断."""
    if msvcrt is None:
        return
    lp = os.path.join(DATA, "auto_cycle.lock")
    os.makedirs(DATA, exist_ok=True)
    fh = open(lp, "a+")
    global _LOCK_FH
    _LOCK_FH = fh  # 防 GC 收走 handle (收了锁就没了)
    try:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        log("[双实例闸] 取 auto_cycle.lock 失败 — 上一实例霸锁, 本实例安全退 (防 state 旧快照互踩)")
        sys.exit(0)


def step0_refresh_exp_r_gate():
    """[2026-11-03 御史补闸] 闸快照自愈。

    问题: jince_gate.json 的唯一写入器 tools/mt5_live_console.py 是交互式 HTTP 控制台,
    被人关掉/终端重启就停更 → 闸龄 >600s → 所有下单路径 fail-closed 全拒 → 整条链“安全地停摆”
    (今天 07:59 就停更了, 08:14 实测已陈旧 860s)。
    本步在主循环每轮开头按 incumbent_genome.json 重写一次快照, 与 console 写同样的内容/同样的原子替换。
    写失败绝不动旧文件 (旧文件陈旧 → 下游继续 fail-closed, 语义不变)。
    """
    try:
        inc_p = os.path.join(ROOT, "evolution", "incumbent_genome.json")
        with open(inc_p, encoding="utf-8") as f:
            inc = json.load(f)
        exp_r = inc.get("fitness", {}).get("exp_r", inc.get("exp_r"))
        if not isinstance(exp_r, (int, float)):
            log("[闸自愈] incumbent exp_r 非数值, 保留旧闸 (下游 fail-closed)")
            return
        appdata = os.environ.get("APPDATA", "")
        base = os.path.join(appdata, "MetaQuotes", "Terminal")
        cands = [os.path.join(base, "7643C0B96C7AD5841307C9E1EB0B9252", "MQL5", "Files", "jince_gate.json")]
        import glob as _glob
        cands += [p for p in _glob.glob(os.path.join(base, "*", "MQL5", "Files", "jince_gate.json"))
                  if p not in cands]
        gate = next((p for p in cands if os.path.exists(p)), None)
        if not gate:
            log("[闸自愈] 找不到 jince_gate.json, 跳过 (下游 fail-closed)")
            return
        snap = {"exp_r": exp_r, "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                "source": "auto_run_cycle gate_refresh(incumbent_genome.json)", "rid": "base"}
        tmp = gate + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snap, f, indent=2, ensure_ascii=False)
        os.replace(tmp, gate)
        log("[闸自愈] jince_gate.json exp_r=%.4f 已刷新" % exp_r)
    except Exception as e:
        log("[闸自愈] 失败(fail-closed 交下游): %s" % str(e)[:100])


def main():
    _acquire_single_instance_lock()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log("")
    log("=" * 60)
    log(f"[全链自动运行] {now}")
    log("=" * 60)
    # [风控位] 循环开头刷新换网分级冻结闸 state (B腿 _freeze_gate_block 读它开单, 必须活体不是手跑快照).
    # fail-open: 异常/超时静默跳过, 绝不阻断交易主循环; 读不到 flag 时 _freeze_gate_block 自身 fail-closed 兜底.
    # [2026-10-23 strategy-rd L5 · 805加固延伸] 刷新fail-open根因=MT5 IPC冻死族(同10-21 daily_advisory):
    # 旧=单次跑不动就静默跳过, B腿读旧态无留痕. 现: 间隔10s × 2拍retry扛瞬冻; 全黑才退
    # _mt5_readonly_probe.py(独立IPC直连探针)只读核对账户实数, 留痕不静默. 纯韧性层: 0下单0撤单, 不阻断主循环.
    _gate_ok = False
    for _i in range(2):
        try:
            _r = subprocess.run([PY, os.path.join(ROOT, "risk_network_gate.py")],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT, timeout=60)
            _lg = (_r.stdout or "").strip().splitlines()
            if _lg:
                log("[风控闸] " + " | ".join(_lg[:3]))
            if _r.returncode == 0:
                _gate_ok = True   # 跑通即成功(即使无输出), 不误判失败
            break
        except Exception:
            if _i < 1:
                log("[风控闸] 刷新第%d拍受阻(IPC冻死?), 10s后第2拍" % (_i + 1))
                time.sleep(10)
    if not _gate_ok:
        log("[风控闸] risk_network_gate.py 刷新失败 — fail-open 跳过, B腿仍读上次 state (fail-closed 兜底)")
        # 全黑兜底: 直连探针只读核对(独立IPC路径), 证明账户活着+数据不静默沿旧 (同 daily_advisory 10-21 范式)
        try:
            _pr = subprocess.run([PY, os.path.join(ROOT, "_mt5_readonly_probe.py")],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT, timeout=90)
            _pj = None
            for _ln in (_pr.stdout or "").strip().splitlines():
                _ln = _ln.strip()
                if _ln.startswith("{"):
                    _pj = json.loads(_ln)
                    break
            if _pj:
                log("[风控闸] 直连探针核对: connect=%s acct=%s equity=%s 持仓=%d (IPC冻结期账户实数已核对, 不静默沿旧)"
                    % (_pj.get("connect"), _pj.get("account"), _pj.get("equity"), len(_pj.get("positions") or [])))
            else:
                log("[风控闸] 直连探针输出未解析到JSON, 核对欠 (fail-open, 下轮自补)")
        except Exception as _e:
            log("[风控闸] 直连探针异常 (%s), 核对欠 (fail-open, 下轮自补)" % str(_e)[:80])
    # [2026-11-11 挂死防护·每步心跳留痕] 17:27全链挂死30min被计划任务超时强杀, 日志零痕迹定位不到步.
    # 现: 每步开始前打心跳行, 挂死时看最后一条心跳=卡在哪步(防"失明"再静默; 配合计划任务30min强杀自愈).
    def _step_run(name, fn):
        log("[步骤心跳] %s 开始 %s" % (name, datetime.datetime.now().strftime("%H:%M:%S")))
        fn()
        log("[步骤心跳] %s 完成" % name)
    _step_run("step0_exp_r", step0_refresh_exp_r_gate)
    _step_run("step0_dashboard", step0_write_dashboard_snap)
    _step_run("step1_orphans", step1_reconcile_orphans)
    _step_run("step1d_reconcile", step1_d_reconcile_book_live)
    _step_run("step1b_dedupe", step1b_dedupe_trim)
    _step_run("step1c_pending", step1c_dedupe_pending_orders)
    _step_run("step2_cio", step2_cio)
    _step_run("step2a_mt5snap", step2a_refresh_mt5_snapshot)
    _step_run("step2_datahealth", step2_data_health)
    _step_run("step2_s_tier", step2_s_tier_overlay)
    _step_run("step2b_crypto", step2b_crypto)
    _step_run("step2d_equity", step2d_equity)
    _step_run("step2c_governor", step2c_governor)
    _step_run("step2e_meta", step2e_meta)
    _step_run("step2e1_eafeed", step2e1_ea_feed)
    _step_run("step2f_advisory", step2f_advisory)
    # [2026-10-10 用户令"学会根据分析优化做单方向"] 方向反馈环: 研判准头表+提权/降级闸
    import subprocess as _sp, os as _os
    _df = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "direction_feedback.py")
    if _os.path.exists(_df):
        try:
            _r = _sp.run([PY, _df], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            for _l in (_r.stdout or "").splitlines():
                if _l.strip():
                    log("  [方向反馈环] " + _l.strip())
        except Exception as _e:
            log("  [方向反馈环] 异常: %s" % str(_e)[:80])
    _step_run("step2g_alpha", step2g_alpha_if_events_moved)
    _step_run("step2h_edge", step2h_edge_tracker_refresh)
    _step_run("step2h2_universe", step2h2_liquidity_universe_refresh)
    _step_run("step2i_shadow", step2i_shadow_feed)
    _step_run("step2j_evo", step2j_evolution)
    _step_run("step3_trainlog", step3_training_log)
    log(f"[全链自动运行完成] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
