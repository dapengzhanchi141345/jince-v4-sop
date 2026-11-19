#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金策·进化营 — 24小时自主进化监督器 (evo_24x7_supervisor)
========================================================
设计目标（对应"加速进化 / 24h 不能停 / 要有自主意识 / 密集进化方案"）：
  1. 24 小时持续运行，永不自杀（干掉旧守护进程的 STOP_ON_HOLD 熔断）。
  2. 加速：本地真实 CSV 回测（确定性历史，fitness 跨周期可比）→ 真正累积进步；
     屏蔽原生产门槛（MT5 不可用时整轮 return None 跳过）。
  3. 自主意识：自修复（异常→记日志→冷却→重试）；自主反停滞（连续无进展自动
     升档变异/移民；现任为"亏货"则自动重置该品种基线强制重新探索）；
     决策日志（"意识"）+ 心跳文件 + 里程碑上报 Hermes。
  4. 密集进化方案：6 类轮转任务（广度/深挖/风险网格/regime/移民刷新/自检），
     短间隔高密度推进。

铁律：
  - 绝不初始化/登录 MT5，绝不动 Hermes 实盘（ensure_mt5 仅打补丁恒 True，
    _MT5_OBJ 始终为 None，无任何 MT5 连接）。
  - 所有落盘均在 E 盘（GoldstrategyEngine 下），不碰 C 盘。
  - RR>=2 / 仓位<=0.03 双铁律由引擎内部 _ensure_rr / _ensure_risk_cap 守住，不破。

运行：
  python evo_24x7_supervisor.py            # 前台 24h 常驻
  python evo_24x7_supervisor.py --once     # 跑一轮即退（验证用）
  python evo_24x7_supervisor.py --test     # 极小参数跑一轮验证（XAUUSD 2轮）
  python evo_24x7_supervisor.py --status   # 打印状态
"""
import os, sys, json, time, csv, signal, types, threading
import numpy as np

# ═══ 0. pandas 轻量 shim（引擎仅在 MT5 分支用到 pd.DataFrame，已被本地 CSV 覆盖，不会触发）═══
if 'pandas' not in sys.modules:
    class _DataFrame:
        def __init__(self, *a, **k): pass
    sys.modules['pandas'] = types.SimpleNamespace(DataFrame=_DataFrame)

# ═══ 1. 路径与常量 ═══
BASE = r"E:\GoldstrategyEngine"
DATA_DIR = os.path.join(BASE, "data")
EVOLVE_DIR = os.path.join(DATA_DIR, "continuous_evolution")
STATE_FILE = os.path.join(EVOLVE_DIR, "evo_supervisor_state.json")
JOURNAL_FILE = os.path.join(EVOLVE_DIR, "evo_decision_journal.jsonl")
HEARTBEAT_FILE = os.path.join(EVOLVE_DIR, "evo_heartbeat.json")
BREAKTHROUGH_FILE = os.path.join(EVOLVE_DIR, "evo_breakthroughs.log")
LOCK_FILE = os.path.join(EVOLVE_DIR, "evo_supervisor.lock")
LOG_FILE = os.path.join(EVOLVE_DIR, "evo_supervisor.log")

CSV_BARS = int(os.environ.get("EVO_CSV_BARS", "4000"))      # 每品种回测取最近 N 根
INTERVAL_SEC = int(os.environ.get("EVO_INTERVAL", "60"))    # 周期之间间隔（秒）
ERROR_COOLDOWN = 30
CORE_SYMBOLS = ["XAUUSD", "BTCUSD", "ETHUSD", "EURUSD", "GBPUSD", "USDJPY", "GBPJPY"]
EVO_STATE_PATH = os.path.join(EVOLVE_DIR, "evolution_state.json")

# Hermes 总线（可选里程碑上报，失败静默）
AGENT_COMMONS = r"E:\AgentCommons\bus\inbox\hermes"
NOTIFY_HERMES = os.environ.get("EVO_NOTIFY", "1") == "1"
_NOTIFY_COOLDOWN_UNTIL = 0

os.makedirs(EVOLVE_DIR, exist_ok=True)

# ═══ 2. 日志 ═══
_log_lock = threading.Lock()
def log(msg, level="INFO"):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}][{level}] {msg}"
    with _log_lock:
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
    print(line, flush=True)
    # 日志轮转（>20MB 截断到 2MB）
    try:
        if os.path.getsize(LOG_FILE) > 20 * 1024 * 1024:
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                data = f.read()
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write(data[-2 * 1024 * 1024:])
    except Exception:
        pass


# ═══ 3. 导入引擎并打补丁（本地 CSV + 屏蔽 MT5 门槛）═══
import continuous_evolution_v2 as ce

_orig_load = ce.BacktestEngine._load_history
_csv_cache = {}

def _csv_load_history(self, symbol):
    """本地真实 CSV 确定性加载（覆盖 MT5/合成）。优先 M15>H1>H4>D1；取最近 CSV_BARS 根。"""
    if symbol in _csv_cache:
        return _csv_cache[symbol]
    base = os.path.join(BASE, "data")
    for tf in ("M15", "H1", "H4", "D1"):
        p = os.path.join(base, f"{symbol}_{tf}.csv")
        if os.path.exists(p):
            path = p
            break
    else:
        path = None
    spread = (ce.SYMBOL_CONFIG.get(symbol, {}) or {}).get("spread", 0.1)
    if path is None:
        return _orig_load(self, symbol)  # 无 CSV 则降级合成（不崩）
    closes, highs, lows, spreads = [], [], [], []
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            r = csv.DictReader(f)
            for row in r:
                try:
                    closes.append(float(row["close"]))
                    highs.append(float(row["high"]))
                    lows.append(float(row["low"]))
                    if row.get("spread"):
                        try:
                            spreads.append(float(row["spread"]))
                        except Exception:
                            pass
                except Exception:
                    pass
    except Exception:
        return _orig_load(self, symbol)
    n = len(closes)
    if n == 0:
        return _orig_load(self, symbol)
    if n > CSV_BARS:
        closes, highs, lows = closes[-CSV_BARS:], highs[-CSV_BARS:], lows[-CSV_BARS:]
        if spreads:
            spreads = spreads[-CSV_BARS:]
    if spreads:
        spread = float(np.mean(spreads)) if spreads else spread
    res = ((np.array(closes, dtype=float), np.array(highs, dtype=float),
            np.array(lows, dtype=float)), float(spread))
    _csv_cache[symbol] = res
    return res

# 打补丁：本地 CSV 加载 + 屏蔽 MT5 门槛（ensure_mt5 恒 True 但绝不真正连接）
ce.BacktestEngine._load_history = _csv_load_history
ce.ensure_mt5 = lambda: True
# _MT5_OBJ 保持 None → 引擎内部 engine.mt5 is None → 不触碰 MT5；MT5_AVAILABLE 保持 False（诚实标注降级/本地）

log(f"引擎已加载并打补丁 | 本地CSV模式 | 核心品种={len(CORE_SYMBOLS)} | CSV_BARS={CSV_BARS}")


# ═══ 4. 状态/日志/心跳 ═══
def _read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def load_state():
    s = _read_json(STATE_FILE)
    if not isinstance(s, dict):
        s = {}
    s.setdefault("cycle_count", 0)
    s.setdefault("total_cycles", 0)
    s.setdefault("total_improvements", 0)
    s.setdefault("no_improve_cycles", 0)
    s.setdefault("tactic_level", 0)
    s.setdefault("mission_index", 0)
    s.setdefault("last_best", {})
    s.setdefault("started_at", time.strftime("%Y-%m-%d %H:%M:%S"))
    s.setdefault("last_error", None)
    s.setdefault("last_cycle_at", None)
    s.setdefault("total_errors", 0)
    return s

def save_state(s):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        log(f"保存监督状态失败: {e}", "WARN")

def journal(entry):
    try:
        with open(JOURNAL_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass

def heartbeat(status, extra=None):
    d = {"status": status, "ts": time.time(),
         "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    if extra:
        d.update(extra)
    try:
        with open(HEARTBEAT_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, default=str)
    except Exception:
        pass

def read_evo_state():
    return _read_json(EVO_STATE_PATH, {}) or {}

def pick_weak_symbol(evo_state):
    bps = (evo_state.get("best_per_symbol") or {})
    best = None
    for sym in CORE_SYMBOLS:
        rec = bps.get(sym)
        fit = rec.get("fitness") if isinstance(rec, dict) else None
        score = fit if fit is not None else -1e9  # None(未找到) 视为最弱
        if best is None or score < best[1]:
            best = (sym, score)
    return best[0] if best else CORE_SYMBOLS[0]

def reset_symbol_in_state(sym):
    """自主重置：把某品种的最优记录置空，强制下一轮重新随机探索（打破亏货基线）。"""
    st = read_evo_state()
    bps = st.get("best_per_symbol") or {}
    if sym in bps:
        bps[sym] = None
    if (st.get("best_strategy") or {}).get("name") and (st.get("best_strategy") or {}).get("symbol") == sym:
        st["best_strategy"] = None
    st["best_per_symbol"] = bps
    try:
        with open(EVO_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=2, ensure_ascii=False, default=str)
        return True
    except Exception:
        return False


# ═══ 5. 密集进化任务计划（6 类轮转）═══
# 每类任务明确目标，避免"无脑重复跑 GA"。
MISSIONS = [
    {"id": "BREADTH",   "desc": "广度维护：7品种各浅进化一轮，保基线不退化",
     "symbol": None, "rounds": 6,  "budget": 120, "imm": 3, "mut": 0.15},
    {"id": "DEPTH_WEAK","desc": "弱点深挖：对当前最弱品种深进化(多轮)",
     "symbol": "WEAK", "rounds": 18, "budget": 240, "imm": 3, "mut": 0.20},
    {"id": "RISKGRID",  "desc": "风险网格：加大移民探索 SL/TP/仓位/风险参数",
     "symbol": None, "rounds": 10, "budget": 150, "imm": 6, "mut": 0.15},
    {"id": "REGIME",    "desc": "regime 探索：高变异强度搜趋势/震荡适配参数",
     "symbol": None, "rounds": 10, "budget": 150, "imm": 4, "mut": 0.30},
    {"id": "IMMIGRATE", "desc": "移民刷新：强移民+高重置，注入全新基因打破收敛",
     "symbol": None, "rounds": 8,  "budget": 120, "imm": 8, "mut": 0.15},
    {"id": "AUDIT",     "desc": "自检：MIN_TRADES 清理、亏货基线重置、日志轮转",
     "symbol": "AUDIT", "rounds": 0, "budget": 0, "imm": 3, "mut": 0.15},
]

def next_mission(state):
    # 每 12 个周期强制插一次 AUDIT；否则按 MISSIONS 轮转（跳过独立 AUDIT 项）
    idx = state["mission_index"]
    if state["cycle_count"] > 0 and state["cycle_count"] % 12 == 0:
        state["mission_index"] = len(MISSIONS) - 1  # AUDIT
        return MISSIONS[-1]
    rot = [m for m in MISSIONS if m["id"] != "AUDIT"]
    m = rot[idx % len(rot)]
    state["mission_index"] = (idx + 1) % len(rot)
    return m


# ═══ 6. 里程碑上报 Hermes（可选，仅正向突破，限频）═══
def notify_hermes(text):
    global _NOTIFY_COOLDOWN_UNTIL
    if not NOTIFY_HERMES:
        return
    now = time.time()
    if now < _NOTIFY_COOLDOWN_UNTIL:
        return
    _NOTIFY_COOLDOWN_UNTIL = now + 3600  # 1小时限频
    try:
        if not os.path.isdir(AGENT_COMMONS):
            return
        import uuid
        msg = {
            "from": "evo_24x7_supervisor",
            "to": "hermes",
            "type": "evolution_milestone",
            "text": text,
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        fn = os.path.join(AGENT_COMMONS, f"evo_milestone_{int(now*1000)}.json")
        with open(fn, "w", encoding="utf-8") as f:
            json.dump(msg, f, ensure_ascii=False, indent=2)
        log(f"已向 Hermes 上报里程碑: {text[:60]}", "INFO")
    except Exception as e:
        log(f"上报 Hermes 失败(忽略): {e}", "WARN")


# ═══ 7. 单轮进化执行 ═══
def run_one_cycle(state):
    mission = next_mission(state)
    # 反停滞升档：连续无进展 → tactic_level 提升（加大变异/移民）
    tl = state["tactic_level"]
    imm = mission["imm"] + (3 if tl >= 1 else 0) + (3 if tl >= 2 else 0)
    mut = mission["mut"] + (0.10 if tl >= 1 else 0) + (0.10 if tl >= 2 else 0)
    ce.IMMIGRANTS_PER_GEN = max(1, int(imm))
    ce.MUTATE_STD_BASE = min(0.6, mut)
    if tl >= 1:
        ce.MUTATE_STD_STAG = min(0.8, mut + 0.15)

    symbol = mission["symbol"]
    if symbol == "WEAK":
        symbol = pick_weak_symbol(read_evo_state())
    if symbol == "AUDIT":
        return run_audit(state, mission, tl)

    log(f"▶ 周期#{state['cycle_count']} 任务={mission['id']} 品种={symbol or 'ALL'} "
        f"轮={mission['rounds']} 预算={mission['budget']}s 移民={ce.IMMIGRANTS_PER_GEN} "
        f"变异={ce.MUTATE_STD_BASE:.2f} 战术档={tl}")

    t0 = time.time()
    result = ce.run_continuous_evolution(
        max_rounds=mission["rounds"],
        symbol=symbol,
        per_symbol_budget_sec=mission["budget"],
    )
    elapsed = time.time() - t0

    if result is None:
        log("⚠ run_continuous_evolution 返回 None（异常跳过），不计入进展", "WARN")
        return None

    # 读取新状态，计算进展
    evo = read_evo_state()
    bps = evo.get("best_per_symbol") or {}
    improved = 0
    snap = {}
    for sym in CORE_SYMBOLS:
        rec = bps.get(sym)
        fit = rec.get("fitness") if isinstance(rec, dict) else None
        samp = rec.get("sample_size") if isinstance(rec, dict) else None
        snap[sym] = {"fit": fit, "samp": samp}
        prev = state["last_best"].get(sym)
        prev_fit = prev.get("fit") if isinstance(prev, dict) else None
        if fit is not None and (prev_fit is None or fit > prev_fit + 1e-6):
            improved += 1
            # 正向突破（样本足且 fitness>0）→ 里程碑上报
            if fit > 0 and (samp or 0) >= 30:
                with _log_lock:
                    try:
                        with open(BREAKTHROUGH_FILE, "a", encoding="utf-8") as f:
                            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {sym} | "
                                    f"fit={fit:.2f} samp={samp} rounds={mission['rounds']}\n")
                    except Exception:
                        pass
                notify_hermes(f"进化突破：{sym} 出现正向候选 fitness={fit:.2f} 样本={samp}（本地CSV回测，待人工复核）")
    state["last_best"] = snap
    state["total_cycles"] += 1
    state["cycle_count"] += 1
    if improved > 0:
        state["no_improve_cycles"] = 0
        state["total_improvements"] += improved
        state["tactic_level"] = 0  # 有进展→回落常规档
        log(f"✅ 进展：{improved} 个品种 fitness 提升 | 用时 {elapsed:.0f}s")
    else:
        state["no_improve_cycles"] += 1
        if state["no_improve_cycles"] >= 4 and state["tactic_level"] < 1:
            state["tactic_level"] = 1
            log(f"🧠 自主意识：连续 {state['no_improve_cycles']} 轮无进展 → 升档至战术1(加强变异/移民)")
        elif state["no_improve_cycles"] >= 8 and state["tactic_level"] < 2:
            state["tactic_level"] = 2
            log(f"🧠 自主意识：连续 {state['no_improve_cycles']} 轮无进展 → 升档至战术2(强重置)")
            # 自主重置：把所有"亏货/未找到"品种基线清空，强制重新探索
            resets = 0
            for sym in CORE_SYMBOLS:
                rec = bps.get(sym)
                fit = rec.get("fitness") if isinstance(rec, dict) else None
                if fit is None or fit <= 0:
                    if reset_symbol_in_state(sym):
                        resets += 1
            if resets:
                log(f"🧠 自主意识：已重置 {resets} 个亏货/空基线品种，强制重新随机探索")

    journal({
        "cycle": state["cycle_count"], "mission": mission["id"], "symbol": symbol or "ALL",
        "rounds": mission["rounds"], "tactic_level": tl, "imm": ce.IMMIGRANTS_PER_GEN,
        "mut": round(ce.MUTATE_STD_BASE, 3), "improved": improved,
        "no_improve": state["no_improve_cycles"], "elapsed_s": round(elapsed, 1),
        "best_snapshot": snap, "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    return result


def run_audit(state, mission, tl):
    """自检任务：不跑 GA，只做治理（清理伪最优、重置亏货、日志轮转）。"""
    log(f"▶ 周期#{state['cycle_count']} 任务=AUDIT 自检治理")
    evo = read_evo_state()
    bps = evo.get("best_per_symbol") or {}
    MIN_TRADES = 30
    cleared = 0
    for sym in list(bps.keys()):
        rec = bps.get(sym)
        if not isinstance(rec, dict):
            continue
        samp = rec.get("sample_size") or 0
        fit = rec.get("fitness")
        # 样本不足 或 明确亏货 → 清空，杜绝伪最优继承
        if samp < MIN_TRADES or (fit is not None and fit <= 0):
            bps[sym] = None
            cleared += 1
    if cleared:
        evo["best_per_symbol"] = bps
        try:
            with open(EVO_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(evo, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            log(f"AUDIT 写回失败: {e}", "WARN")
    # 日志轮转：决策日志 >5MB 截断到 1MB
    try:
        if os.path.exists(JOURNAL_FILE) and os.path.getsize(JOURNAL_FILE) > 5 * 1024 * 1024:
            with open(JOURNAL_FILE, "r", encoding="utf-8", errors="replace") as f:
                data = f.read()
            with open(JOURNAL_FILE, "w", encoding="utf-8") as f:
                f.write(data[-1 * 1024 * 1024:])
    except Exception:
        pass
    state["cycle_count"] += 1
    state["total_cycles"] += 1
    log(f"✅ AUDIT 完成：清理伪最优/亏货 {cleared} 项 | 累计周期 {state['cycle_count']}")
    journal({"cycle": state["cycle_count"], "mission": "AUDIT", "cleared": cleared,
             "ts": time.strftime("%Y-%m-%d %H:%M:%S")})
    return {"audit": True, "cleared": cleared}


# ═══ 8. PID 锁（防重复运行）═══
def read_pid_alive(pid):
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        h = kernel32.OpenProcess(0x0400, False, pid)
        if h == 0:
            return False
        kernel32.CloseHandle(h)
        return True
    except Exception:
        return False

def acquire_lock():
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                pid = int(f.read().strip())
            if pid != os.getpid() and read_pid_alive(pid):
                log(f"⚠ 已有实例运行 (PID={pid})，本进程退出（防重复）", "WARN")
                return False
        except Exception:
            pass
    try:
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    return True

def release_lock():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception:
        pass


# ═══ 9. 主循环 ═══
def run_forever():
    if not acquire_lock():
        sys.exit(0)
    state = load_state()
    log(f"🚀 金策·进化营 24h 自主进化监督器启动 | 间隔={INTERVAL_SEC}s | 任务={len(MISSIONS)}类")
    heartbeat("started", {"cycle_count": state["cycle_count"]})

    def _sigterm(signum, frame):
        log("📴 收到终止信号，优雅退出")
        release_lock()
        sys.exit(0)
    signal.signal(signal.SIGINT, _sigterm)
    signal.signal(signal.SIGTERM, _sigterm)

    while True:
        try:
            state = load_state()  # 每次重载（AUDIT/外部可能改）
            res = run_one_cycle(state)
            save_state(state)
            state["last_cycle_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            state["last_error"] = None
            heartbeat("running", {"cycle": state["cycle_count"],
                                  "no_improve": state["no_improve_cycles"],
                                  "tactic": state["tactic_level"]})
        except Exception as e:
            state["total_errors"] = state.get("total_errors", 0) + 1
            state["last_error"] = f"{type(e).__name__}: {str(e)[:200]}"
            save_state(state)
            log(f"❌ 周期异常（自修复中，不退出）: {state['last_error']}", "ERROR")
            heartbeat("error", {"error": state["last_error"]})
            time.sleep(ERROR_COOLDOWN)
            continue
        # 周期之间短间隔 → 高密度
        try:
            for _ in range(INTERVAL_SEC):
                time.sleep(1)
        except Exception:
            pass


def run_once(test=False):
    if not acquire_lock():
        sys.exit(0)
    state = load_state()
    if test:
        # 极小参数验证：XAUUSD 2 轮
        log("🧪 TEST 模式：XAUUSD 2 轮验证")
        t0 = time.time()
        res = ce.run_continuous_evolution(max_rounds=2, symbol="XAUUSD", per_symbol_budget_sec=60)
        log(f"🧪 TEST 完成 用时{time.time()-t0:.0f}s 结果={'OK' if res else 'None'}")
        if res:
            log(f"   XAUUSD best: {res.get('XAUUSD')}")
        release_lock()
        return
    state = load_state()
    try:
        run_one_cycle(state)
        save_state(state)
    finally:
        release_lock()
    log("单次运行结束")


def print_status():
    state = load_state()
    hb = _read_json(HEARTBEAT_FILE, {})
    evo = read_evo_state()
    bps = evo.get("best_per_symbol") or {}
    print("=" * 60)
    print("金策·进化营 24h 自主进化监督器 — 状态")
    print("=" * 60)
    print(f"启动时间    : {state.get('started_at')}")
    print(f"最后周期    : {state.get('last_cycle_at')}")
    print(f"累计周期    : {state['total_cycles']}")
    print(f"累计进展    : {state['total_improvements']}")
    print(f"连续无进展  : {state['no_improve_cycles']}")
    print(f"战术档位    : {state['tactic_level']}")
    print(f"累计错误    : {state['total_errors']}")
    print(f"最后错误    : {state.get('last_error')}")
    print(f"心跳状态    : {hb.get('status')} @ {hb.get('time')}")
    print("-" * 60)
    print("各品种最优(本地CSV回测):")
    for sym in CORE_SYMBOLS:
        rec = bps.get(sym)
        if isinstance(rec, dict):
            print(f"  {sym:8s} fit={rec.get('fitness')} samp={rec.get('sample_size')} "
                  f"name={rec.get('name')}")
        else:
            print(f"  {sym:8s} None(未找到/已重置)")
    print("=" * 60)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="金策·进化营 24h 自主进化监督器")
    ap.add_argument("--once", action="store_true", help="跑一轮即退（验证/单次）")
    ap.add_argument("--test", action="store_true", help="极小参数验证一轮")
    ap.add_argument("--status", action="store_true", help="打印状态")
    ap.add_argument("--interval", type=int, help="覆盖周期间隔(秒)")
    args = ap.parse_args()
    global INTERVAL_SEC
    if args.interval:
        INTERVAL_SEC = max(5, args.interval)
    if args.status:
        print_status()
        return
    if args.test:
        run_once(test=True)
        return
    if args.once:
        run_once(test=False)
        return
    run_forever()


if __name__ == "__main__":
    main()
