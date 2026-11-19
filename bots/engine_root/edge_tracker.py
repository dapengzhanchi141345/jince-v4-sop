# edge_tracker.py — 实盘 edge 跟踪器 (D1/D4/D5 核心依赖)
#
# 从 MT5 history_deals 按 symbol / strategy 累计 pf / 胜率 / 样本数,
# 持久化 data/edge_tracker.json. 提供:
#   is_symbol_allowed(sym)   品种级门控 (D1): 实盘 pf<1.0 禁开
#   is_strategy_allowed(st)  策略级门控 (D5): 实盘 pf<1.0 禁该策略信号
#   live_edge_score(sym)     实盘 edge 分 (D4 截面排名改用实盘 edge)
#
# 设计原则 (治本核心):
#   - 样本 < MIN_TRADES: 用回测 pf 兜底 (≥BACKTEST_PF_MIN=1.2 才开) → 回测虚高品种
#     被挡在门外, 只有 KEEP 验证宇宙能开, 先积累实盘样本.
#   - 样本 ≥ MIN_TRADES: 严格用实盘 pf (≥LIVE_PF_MIN=1.0 才开) → 负 edge 品种被掐掉.
#   - 无 MT5 / 无数据: 失败开放(回退允许), 绝不静默停摆.
import os
import json
import time
import re

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CACHE = os.path.join(DATA_DIR, "edge_tracker.json")

MIN_TRADES = 15          # [2026-09-01] 实盘样本阈值 (原20; 降到15以捕获XAGUSD类n=16负edge)
LIVE_PF_MIN = 0.95       # [2026-08-18-A] 实盘 pf 门槛 (1.0→0.95, 让边际正 edge 品种恢复开仓)
_STOCK_CLASSES = ("stock",)   # [2026-08-18-A] D3 禁股票类: fallback 阶段也不放行股票类
BACKTEST_PF_MIN = 1.2     # 样本不足时回测 pf 兜底门槛
STRAT_PF_MIN = 1.0       # 策略级 pf 门槛
FLOAT_LOSS_BUDGET = 0.02 # 总浮亏 > 净值 2% 暂停新开 (D2)
# [2026-09-01 V3.1] 实盘强 edge 直通门槛: 样本<MIN_TRADES 但实盘已证实
#   pf≥LIVE_STRONG_PF 且 n≥LIVE_STRONG_N → 放行(放大已验证赢家).
LIVE_STRONG_N = 5
# [2026-09-01 V3.1.1] 1.3→1.15: 低样本(n=5~10)实盘 pf 极噪(单笔盈亏即可大幅摆动),
# 1.3 门槛会让赢家在小幅回撤时翻回 blocked(与"放大赢家"相悖). 1.15 仍为明确正 edge 栏,
# 配合 n≥5 与步骤1(≥15笔硬 pf 闸)负 edge 仍被掐, 不会误放 bleed 品种.
LIVE_STRONG_PF = 1.15

_KNOWN_STRATS = ["SDP", "ICT", "DIV", "MR", "VP", "TREND", "BO"]
_cache = None
_cache_mtime = 0.0   # [2026-09-01 V3.1.1] 跟踪缓存文件 mtime, 文件变化时强制重载(防 stale 缓存)
# WFV 白名单全局 (模块级, 支持 is_wfv_allowed / get_wfv_pf / live_edge_score 共享)
_WFV_CACHE = {}
_WFV_WHITELIST = set()
_WFV_LOADED_AT = 0
_WFV_TTL = 86400 * 7
WFV_DATA_PATH = os.path.join(DATA_DIR, "wfv_edge.json")
_last_refresh = 0


def _load():
    """加载 edge 统计缓存。

    [2026-09-01 V3.1.1] mtime 感知重载: 统计文件被外部进程(另一 run_trader 实例 /
    周期统计重算)更新后, 下次调用自动重载, 避免 daemon 长期持有陈旧 _cache 而误杀
    已验证赢家。实测: edge_tracker.json 在 daemon 启动 8 分钟后才写好(23:54 vs 23:46),
    旧 memoize 导致 CADJPY/AUDCHF/EURGBP 一直被 SKIP, 尽管新进程里 is_symbol_allowed
    已返回 True —— 这就是 V3.1「放大赢家」在实盘不生效的根因。
    """
    global _cache, _cache_mtime
    try:
        _m = os.path.getmtime(CACHE)
    except Exception:
        _m = 0.0
    if _cache is not None and _m <= _cache_mtime:
        return _cache
    try:
        if os.path.exists(CACHE):
            _cache = json.load(open(CACHE, encoding="utf-8"))
        else:
            _cache = {"symbols": {}, "strategies": {}, "updated": 0}
    except Exception:
        _cache = {"symbols": {}, "strategies": {}, "updated": 0}
    _cache_mtime = _m
    return _cache


def _save():
    global _cache_mtime
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        json.dump(_cache, open(CACHE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        try:
            _cache_mtime = os.path.getmtime(CACHE)
        except Exception:
            pass
    except Exception:
        pass


def _pf_of(s):
    gl = s.get("gross_l", 0.0)
    gw = s.get("gross_w", 0.0)
    if gl <= 0:
        return 99.0 if gw > 0 else 0.0
    return gw / gl


def _utc_hour_of(ts):
    """ts(UTC 秒) → 北京小时 (0-23)。纯 Python, 确定性。"""
    return int((ts // 3600 + 8) % 24)


try:
    from zoneinfo import ZoneInfo
    _EET = ZoneInfo("Europe/Helsinki")   # server 钟 DST 感知 (同 resolve_session_window SERVER_TZ 口径)
except Exception:
    _EET = None

_KILL_HOURS = {8, 9, 10, 13, 14, 15}   # server 钟精选时段, 必须与 resolve_session_window.HARDCODED 一致
_CN_US = (21, 22, 23, 0, 1)            # 研讨 6 节点线: 美盘开评 21:00 → 收口 02:00 (北京)


def _session_tag_of(ts):
    """研讨 6 节点线时段标签: 亚(北京08-15)/欧(15-21)/美(21-02) × 精选/非精选。

    精选 = server 钟 8/9/10/13/14/15 (kill-zone, 与 resolve_session_window.HARDCODED 同源;
    server 钟 EET DST 感知, 非漂移日 server=北京-4(冬)/-5(夏))。
    [2026-09-30 棋盘 t_22d83f88] 每条 edge 统计带时段标签; 分组统计只准同分母组内比,
    禁止跨组比胜率(铁律: 子集胜率差=选择效应, 不算 edge)。
    """
    b = _utc_hour_of(ts)
    if b in _CN_US:
        cn = "美"
    elif 15 <= b <= 20:
        cn = "欧"
    else:
        cn = "亚"
    if _EET is not None:
        import datetime as _dt
        h = _dt.datetime.fromtimestamp(ts, tz=_EET).hour
    else:
        h = int((ts // 3600 + 3) % 24)
    return ("%s:精选" % cn) if h in _KILL_HOURS else ("%s:非精选" % cn)


def _gate_flags_of(now, span_sec=86400):
    """gate_flags: 是否被 事件窗/休市门 拦截。
    - event_guard_active: 读 data/event_guard_last.json level ∈ {MED, HIGH}
    - blocked_hours: 读 data/event_guard_blocked.json (缺失=[])
    - active_now: 当前时刻是否落在 blocked_hours 窗口内
    纯 Python 只读文件, 失败开放(缺文件 = 无拦截), 不改开单行为。
    """
    flags = {"event_guard_active": False, "blocked_hours": [], "active_now": False}
    try:
        p = os.path.join(DATA_DIR, "event_guard_last.json")
        if os.path.exists(p):
            lvl = str(json.load(open(p, encoding="utf-8")).get("level", "")).upper()
            flags["event_guard_active"] = lvl in ("MED", "HIGH")
    except Exception:
        pass
    try:
        p = os.path.join(DATA_DIR, "event_guard_blocked.json")
        if os.path.exists(p):
            d = json.load(open(p, encoding="utf-8"))
            for e in d.get("events", []):
                st, en = e.get("start_ts"), e.get("end_ts")
                if st and en and int(en) >= now:
                    flags["blocked_hours"].append([int(st), int(en), str(e.get("title", ""))[:40]])
            flags["active_now"] = any(st <= now <= en for st, en, _t in flags["blocked_hours"])
    except Exception:
        pass
    return flags


def _load_retired_legs():
    """[2026-10-07 L5 退役持久化] 读 data/retired_legs.json -> {sym: {scale, reason}}.
    源文件由 策略-rd (L5) 维护; 缺失/坏文件 = {} (失败开放, 不误抹、不误退)。"""
    try:
        p = os.path.join(DATA_DIR, "retired_legs.json")
        if os.path.exists(p):
            d = json.load(open(p, encoding="utf-8"))
            return d.get("legs", {}) if isinstance(d, dict) else {}
    except Exception:
        pass
    return {}


def _apply_retired_flag(flags, sym, c, retired):
    """[2026-10-07 L5 退役持久化] merge 退役旗标, 防每轮 refresh 抹掉:
    1) 该 sym 在 retired_legs.json 名录 -> 补 retired/scale/retired_reason (循环必 merge);
    2) 旧 gate_flags 已写 retired=true (名录外的历史遗留) -> 保留, 不被覆盖。
    只改 gate_flags 内键, 不动任何开单行为 (开单真闸源=pending_orders D级否决, 非此字段)。"""
    try:
        r = retired.get(sym)
        if r:
            flags["retired"] = True
            flags["scale"] = r.get("scale", 0)
            flags["retired_reason"] = r.get("reason", "L5 RETIRE")
            flags["retired_by"] = r.get("by", "strategy-rd")
            flags["retired_ts"] = r.get("ts", 0)
        # 旧旗标保留: 上一轮已 retired=true 且非名录内 -> 不抹
        if c.get("symbols", {}).get(sym, {}).get("gate_flags", {}).get("retired") \
           and not flags.get("retired"):
            old = c["symbols"][sym]["gate_flags"]
            for k in ("retired", "scale", "retired_reason", "retired_by", "retired_ts"):
                if k in old:
                    flags[k] = old[k]
    except Exception:
        pass


def _session_breakdown(deals, span_sec=86400):
    """按 session_tag 分组统计 (同分母分组: 禁跨组比胜率铁律随数据落盘)。"""
    g = {}
    for d in deals:
        s = g.setdefault(_session_tag_of(d.time),
                         {"n": 0, "wins": 0, "gross_w": 0.0, "gross_l": 0.0})
        s["n"] += 1
        if d.profit > 0:
            s["wins"] += 1
            s["gross_w"] += d.profit
        else:
            s["gross_l"] += -d.profit
    out = {}
    for k, v in g.items():
        out[k] = {"n": v["n"],
                  "wr": round(v["wins"] / v["n"], 3) if v["n"] else 0.0,
                  "gross_w": round(v["gross_w"], 2),
                  "gross_l": round(v["gross_l"], 2),
                  "pf": round(_pf_of(v), 3),
                  "exp_R": None}   # 期望 R 口径=实盘盈亏/固定风险单位, 由上层标定; 不跨组比较
    return out


def get_backtest_pf(symbol):
    """从回测缓存读 pf (容错返回 None)。"""
    try:
        p = os.path.join(DATA_DIR, "_ub_partial.json")
        if os.path.exists(p):
            d = json.load(open(p, encoding="utf-8"))
            st = d.get(symbol, {}).get("stats", {})
            return st.get("pf")
    except Exception:
        return None
    return None


def refresh(mt5=None, days=30):
    """从 MT5 成交历史刷新实盘 edge。需 mt5 已初始化。

    [2026-10-20 21:55 陈旧残留修复 · 经 Hermes chief 确认]
    原缺陷: 本函数只覆盖「近 days 天内有平仓的品种」, 其余品种的旧记录**永不清除**。
      实测: MT5 近30天真实平仓仅 46 笔 (22 品种), 而 edge_tracker.json 记录
      164 品种 n 总和 1100 —— 其中 142 个品种 / n=1054 (占 95.8%) 是数月前的
      历史残留, 早已不在当前 MT5 成交历史里。
      危害: is_symbol_allowed() 用 `s["n"] >= MIN_TRADES` 判定「实盘样本充足」,
      幽灵样本会把老品种伪装成「实盘验证过的赢家/ losers」, 直接影响开仓门控。
    修复: refresh 时把「近 days 天无平仓」的品种移出 symbols 主表,
      转入 _archived 段保留 (不物理删除, 保留历史可追溯性)。
      同时给每个品种打 data_fresh 标记, 供门控层判断样本是否新鲜。
    """
    global _last_refresh
    if mt5 is None:
        import MetaTrader5 as mt5
    now = time.time()
    from_d = now - days * 86400
    try:
        deals = mt5.history_deals_get(int(from_d), int(now))
    except Exception:
        return
    if not deals:
        return
    sym_stat = {}
    strat_stat = {}
    for d in deals:
        if d.entry != 1:           # 只看平仓成交 (一笔交易盈亏)
            continue
        sym = d.symbol
        s = sym_stat.setdefault(sym, {"n": 0, "wins": 0,
                                      "gross_w": 0.0, "gross_l": 0.0, "_deals": []})
        s["n"] += 1
        s["_deals"].append(d)
        if d.profit > 0:
            s["wins"] += 1
            s["gross_w"] += d.profit
        else:
            s["gross_l"] += -d.profit
        # 策略解析 (从 comment 提取已知策略名, 不可靠时跳过不影响品种级)
        m = re.search(r"\b(" + "|".join(_KNOWN_STRATS) + r")\b",
                      str(d.comment or ""))
        if m:
            stn = m.group(1)
            ss = strat_stat.setdefault(stn, {"n": 0, "wins": 0,
                                             "gross_w": 0.0, "gross_l": 0.0, "_deals": []})
            ss["n"] += 1
            ss["_deals"].append(d)
            if d.profit > 0:
                ss["wins"] += 1
                ss["gross_w"] += d.profit
            else:
                ss["gross_l"] += -d.profit
    # [2026-10-07 L5 XAU RETIRE 持久化] 退役名录: 源 = data/retired_legs.json (策略-rd 台账)
    #   循环重建 edge_tracker 时 merge 进 XAU 等品种 gate_flags, 防每轮 refresh 抹掉 retired 旗标(反复犯老病)
    retired = _load_retired_legs()
    c = _load()
    # [2026-09-30 棋盘 t_22d83f88] 同分母分组统计: 每条统计附 session_tag 分解 (亚/欧/美 × 精选/非精选)
    #   + gate_flags (事件窗/休市门 拦截标记). 铁律: 报告只能同组内比, 禁跨组比胜率。
    guard = _gate_flags_of(now)
    for sym, s in sym_stat.items():
        entry = {
            "n": s["n"],
            "wr": round(s["wins"] / s["n"], 3) if s["n"] else 0,
            "gross_w": round(s["gross_w"], 2),
            "gross_l": round(s["gross_l"], 2),
            "pf": round(_pf_of(s), 3),
        }
        if s.get("_deals"):
            entry["session_tag"] = _session_breakdown(s["_deals"])
        c["symbols"][sym] = entry
        c["symbols"][sym]["gate_flags"] = guard
        # [2026-10-07 L5 RETIRE 持久化] merge 退役旗标: 该品种在退役名录/旧 gate_flags.retired 则补回
        _apply_retired_flag(c["symbols"][sym]["gate_flags"], sym, c, retired)
    for stn, ss in strat_stat.items():
        entry = {
            "n": ss["n"],
            "wr": round(ss["wins"] / ss["n"], 3) if ss["n"] else 0,
            "gross_w": round(ss["gross_w"], 2),
            "gross_l": round(ss["gross_l"], 2),
            "pf": round(_pf_of(ss), 3),
        }
        if ss.get("_deals"):
            entry["session_tag"] = _session_breakdown(ss["_deals"])
        c["strategies"][stn] = entry
        c["strategies"][stn]["gate_flags"] = guard

    # ── [2026-10-20] 陈旧残留归档 ──────────────────────────────
    # 本轮无平仓的品种: 移出 symbols 主表, 转入 _archived 段。
    # 目的: 防止数月前的历史 n/pf 继续被 is_symbol_allowed 当作「实盘样本充足」使用。
    # 保留而不物理删除: 历史可追溯, 且 _archived 不参与任何门控判断。
    stale_syms = [k for k, v in c["symbols"].items()
                  if isinstance(v, dict) and k not in sym_stat]
    if stale_syms:
        arch = c.setdefault("_archived", {})
        arch.setdefault("symbols", {})
        for k in stale_syms:
            arch["symbols"][k] = c["symbols"].pop(k)
        arch["archived_at"] = int(now)
        arch["archive_reason"] = ("近 %d 天 MT5 无平仓成交, 样本已不新鲜; "
                                  "移出主表避免污染品种门控" % days)
        arch["n_archived"] = len(arch["symbols"])
    # 记录本轮实际覆盖范围, 供上层判断数据新鲜度
    c["fresh_window_days"] = days
    c["fresh_symbol_count"] = len(sym_stat)
    c["fresh_close_count"] = sum(s["n"] for s in sym_stat.values())
    # [2026-10-20 chief 裁决] 60 天无成交 -> 自动归档并禁止再产生任何建议
    #   实现: 额外拉一次 60 天窗口, 找出 60 天内也无平仓的品种, 记入 _archived_60d。
    try:
        d60 = mt5.history_deals_get(int(now - 60 * 86400), int(now))
        sym60 = set()
        if d60:
            for d in d60:
                if d.entry == 1:
                    sym60.add(d.symbol)
        c["_archived_60d"] = sorted([k for k in c["symbols"]
                                     if k not in sym60])
        c["_active_60d"] = sorted([k for k in c["symbols"] if k in sym60])
    except Exception:
        c.setdefault("_archived_60d", [])
    # 顶层 gate_flags 单一源 (rd_cycle 出报告读这里), 避免每条重复膨胀
    c["gate_flags"] = guard
    c["same_denom_rule"] = ("session_tag 组内同分母: 亚/欧/美 × 精选/非精选 8 组各算各的; "
                            "禁止跨组比胜率(子集胜率差=选择效应, 不算 edge)")
    c["updated"] = int(now)
    _last_refresh = int(now)
    _save()


def refresh_if_stale(mt5, stale_sec=300):
    """带时间戳的刷新 (避免每轮拉历史, 5 分钟一次)。"""
    global _last_refresh
    if time.time() - _last_refresh > stale_sec:
        refresh(mt5)


def _symbol_class(symbol):
    """读品种类别 (与 symbol_universe cls 一致); 失败用后缀兜底 (.NYS/.NAS/.BAT=stock)。"""
    try:
        import symbol_universe as su
        cfg = su.UNIVERSE.get(symbol)
        if cfg and cfg.get("cls"):
            return cfg["cls"]
    except Exception:
        pass
    if any(symbol.endswith(suf) for suf in (".NYS", ".NAS", ".BAT", ".L", ".PA", ".DE", ".HK")):
        return "stock"
    return None


def load_wfv_edge(force=False):
    """加载 WFV 样本外验证白名单。格式: per_symbol[sym]["summary"][strat] = {wfo_pf, wr, n, oos_folds, train_pf_med}"""
    global _WFV_CACHE, _WFV_WHITELIST, _WFV_LOADED_AT
    now = time.time()
    if not force and _WFV_WHITELIST and (now - _WFV_LOADED_AT) < _WFV_TTL:
        return
    _WFV_WHITELIST.clear()
    _WFV_CACHE.clear()
    try:
        if not os.path.exists(WFV_DATA_PATH):
            _WFV_LOADED_AT = now
            return
        with open(WFV_DATA_PATH, encoding="utf-8") as f:
            d = json.load(f)
        ps = d.get("per_symbol", {})
        for sym, v in ps.items():
            summary = v.get("summary", {}) if isinstance(v, dict) else {}
            for strat, m in summary.items():
                if not isinstance(m, dict):
                    continue
                wfo = m.get("wfo_pf", 0)
                folds = m.get("oos_folds", 0)
                if wfo >= 1.1 and folds >= 3:
                    _WFV_WHITELIST.add((sym, strat))
                    _WFV_CACHE[(sym, strat)] = {
                        "wfo_pf": wfo,
                        "wr": m.get("wr", 0),
                        "n": m.get("n", 0),
                        "oos_folds": folds,
                        "train_pf_med": m.get("train_pf_med", 0),
                    }
        _WFV_LOADED_AT = now
        print(f"[edge_tracker] WFV 白名单加载: {len(_WFV_WHITELIST)} 个 (symbol,strat) 组合")
    except Exception as e:
        print(f"[edge_tracker] WFV 加载失败: {e}")


def get_wfv_pf(symbol, strategy=None):
    """从 WFV 白名单查样本外 pf。无 strategy 时返回该品种最佳 wfo_pf。"""
    load_wfv_edge()
    if strategy:
        return _WFV_CACHE.get((symbol, strategy), {}).get("wfo_pf")
    # 无策略: 返回该品种所有策略中最高 wfo_pf
    best = 0.0
    for (sym, strat), m in _WFV_CACHE.items():
        if sym == symbol and m.get("wfo_pf", 0) > best:
            best = m["wfo_pf"]
    return best if best > 0 else None


def is_wfv_allowed(symbol, strategy=None):
    """WFV 门控: (symbol, strategy) 对是否在白名单中。strategy=None 时检查任意策略。"""
    load_wfv_edge()
    if strategy:
        return (symbol, strategy) in _WFV_WHITELIST
    # 无策略: 检查该品种任何策略在白名单中
    return any(s == symbol for s, _ in _WFV_WHITELIST)


def is_symbol_allowed(symbol):
    """品种级门控 (D1)。

    优先级 (2026-09-01 修正: 信任实盘 > 回测):
      1. 实盘样本 ≥ MIN_TRADES → 严格实盘 pf (≥LIVE_PF_MIN 才开).
         即使 WFV/回测说 OK, 实盘负 edge 也一律掐掉 —— 治 EURUSD/USDJPY 等
         WFV 样本外验证通过、但实盘退化的品种漏水 (实盘 > 回测, 永远优先).
      2. 实盘样本不足 → WFV 样本外白名单 (次级, 允许先积累实盘样本).
      3. 仍不足 → 回测 pf 兜底 (≥BACKTEST_PF_MIN, 股票类禁).
    失败开放: 无缓存/无数据 → 回退允许 (绝不静默停摆).
    """
    c = _load()
    s = c["symbols"].get(symbol)
    cls = _symbol_class(symbol)
    # [2026-10-20 21:50] Universe 硬切割（Hermes chief 裁决）:
    #   交易宇宙锁定为「近30天有真实平仓且非加密」的白名单品种。
    #   白名单外的品种一律不得产生入场建议 —— 无论其 WFV/回测/历史 pf 多好。
    #   观察项(XRPUSD 等 n 过小者)与加密品种同样禁止入场。
    #   白名单文件: data/universe_whitelist.json（由 data/universe_whitelist.py 生成）
    try:
        import universe_whitelist as uw
        if not uw.is_allowed(symbol):
            return False
    except Exception:
        # 白名单模块缺失 -> 失败开放, 不静默停摆（与本函数既有语义一致）
        pass
    # [2026-10-20] 样本新鲜度校验: 若该品种已被归档(近30天无成交),
    #   其 n/pf 属于历史残留, 不得再当作「实盘样本充足」来判定开不开仓。
    #   已归档时 s 为 None, 落到 WFV/回测兜底分支 —— 语义正确。
    # 1) 实盘样本充足: 实盘 pf 最高优先级 (覆盖 WFV/回测)
    if s and s["n"] >= MIN_TRADES:
        return s["pf"] >= LIVE_PF_MIN
    # 1.5) [2026-09-01 V3.1] 实盘强 edge 直通: 即便样本<MIN_TRADES, 只要实盘已
    #   证实 pf≥LIVE_STRONG_PF 且 n≥LIVE_STRONG_N 即放行(放大已验证赢家
    #   EURCHF/AUDCHF/EURGBP/CADJPY 等, 实盘 PF 1.38~5.05 却被样本门槛挡门外).
    #   实盘真金验证比回测可靠; 且样本累积到 MIN_TRADES 后若 pf 跌破 LIVE_PF_MIN,
    #   步骤1会自动重新封禁(自愈). 股票类不走此直通(防广度 bleed 复发).
    if s and s["n"] >= LIVE_STRONG_N and s["pf"] >= LIVE_STRONG_PF:
        if cls not in _STOCK_CLASSES:
            return True
    # 2) 实盘样本不足: WFV 样本外白名单 (先积累实盘数据)
    if is_wfv_allowed(symbol):
        if cls in _STOCK_CLASSES:
            return False
        return True
    # 3) 样本不足: 回测 pf 兜底
    bp = get_backtest_pf(symbol)
    if bp is None or bp < BACKTEST_PF_MIN:
        return False
    if cls in _STOCK_CLASSES:
        return False
    return True


def is_strategy_allowed(strat):
    """策略级门控 (D5)。样本不足不硬禁(品种级已兜底)。"""
    if not strat:
        return True
    c = _load()
    s = c["strategies"].get(strat)
    if not s or s["n"] < MIN_TRADES:
        return True
    return s["pf"] >= STRAT_PF_MIN


def live_edge_score(symbol):
    """实盘 edge 分 (D4)。优先 WFV wfo_pf, 其次实盘 pf×wr, 最后 1.0 兜底。"""
    load_wfv_edge()
    # WFV 白名单优先 (样本外验证, 最可靠)
    wfv_pf = get_wfv_pf(symbol)
    if wfv_pf is not None and wfv_pf >= 1.1:
        return min(3.0, wfv_pf * 0.5)  # 封顶 3.0
    c = _load()
    s = c["symbols"].get(symbol)
    if not s:
        return 1.0
    pf = s.get("pf", 1.0)
    wr = s.get("wr", 0.5)
    sc = pf * (0.5 + wr)
    return max(0.1, min(3.0, sc))


# ═══ [2026-08-20 P1] 统计验证辅助函数 ═══
def _sharpe_of(trades):
    """计算夏普比率 (简化版: 平均收益/收益标准差)。空列表返回 0.0。"""
    if not trades or len(trades) < 2:
        return 0.0
    mean = sum(trades) / len(trades)
    if mean == 0:
        return 0.0
    variance = sum((t - mean) ** 2 for t in trades) / len(trades)
    std = variance ** 0.5
    return mean / std if std > 0 else 0.0


def _max_consecutive_losses(trades):
    """最大连续亏损笔数。空列表返回 0。"""
    if not trades:
        return 0
    max_loss = 0
    current_loss = 0
    for t in trades:
        if t < 0:
            current_loss += 1
            max_loss = max(max_loss, current_loss)
        else:
            current_loss = 0
    return max_loss


def _monthly_return_variance(trades, trade_dates):
    """月收益方差 (波动率代理)。样本不足返回 None。"""
    if len(trades) < 20 or len(trade_dates) < 20:
        return None
    from collections import defaultdict
    monthly = defaultdict(float)
    for t, d in zip(trades, trade_dates):
        month_key = d[:7]  # "YYYY-MM"
        monthly[month_key] += t
    if len(monthly) < 3:
        return None
    vals = list(monthly.values())
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    return round(var, 4)


if __name__ == "__main__":
    import MetaTrader5 as mt5
    if mt5.initialize():
        refresh(mt5)
        mt5.shutdown()
    c = _load()
    print(f"[edge_tracker] 品种样本数: {len(c['symbols'])} 策略样本数: {len(c['strategies'])}")
    for sym, s in sorted(c["symbols"].items(), key=lambda x: x[1].get("pf", 0))[:10]:
        print(f"  {sym:12} pf={s['pf']:.2f} wr={s['wr']:.2f} n={s['n']} "
              f"允许={is_symbol_allowed(sym)}")
