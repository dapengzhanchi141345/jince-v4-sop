# -*- coding: utf-8 -*-
"""
mt5_live_read.py — 金策宗师团 · MT5 活体实读统一入口 (V13 根治层, 2026-10-05)
================================================================
铁律: 任何"挂单X张/持仓Y张"报出去前必实读 MT5 活体, 派生簿只作留痕.
本模块给所有会报挂单/持仓的路径(6节点 jince_node / pending_orders.py 简报 /
crypto_pending.py·equity_pending.py 简报 / 看板账户卡 / 孤儿降终态工具)
提供同一套实读入口, 杜绝"各路径各读各的、有路径读旧快照"的复发病.

对外函数 (全部 fail-open: 任何异常返回 degraded=True 结果, 绝不 raise 崩调用链):
  live_read()                 -> dict: 账户+活挂单+活持仓 实读, 带 ts/degraded/errors
  live_read_for_magic(magic)  -> dict: 按 magic 过滤的活挂单/活持仓 (派生簿按 magic 分簿)
  settle_orphans_by_magic(st, magic) -> int: 派生簿里 status=open 但实读无对应 magic 活仓位的
        filled 孤儿条目自动降终态 (pnl 走 history_deals group=ticket 回填), 纯记账不发单.
  settle_all_orphans()        -> dict: 三 magic 全簿孤儿降终态 + pending 残留清账 (不写闸源)
  desync_flags(live, derived_pending_n, derived_open_n) -> list[str]: 派生簿 vs 实盘差异警示行

实读约定: 活体 = mt5.positions_get()/orders_get()/account_info() 当刻返回, 不读
任何快照文件. 调用方拿到 degraded=True 结果时按"实盘读取失败, 派生簿口径仅留痕"
处理, 不静默当实读.

GBK 安全: 对外文本只含汉字/ASCII/数字, 无 emoji/特殊符号, 可被 GBK pipe 安全捕获.
"""
import json
import os
import time
import threading

try:
    import MetaTrader5 as mt5
except Exception:
    mt5 = None

DATA = r"E:/GoldstrategyEngine/data"
_MAGIC_NAME = {20260902: "pending_orders_state.json",
               20260903: "crypto_pending_state.json",
               20260904: "equity_pending_state.json"}

# [t_528b267c 根因①] MT5 IPC 握手冻死自检: initialize 无返回=卡握手, 全循环 stall >60min
# 霸 JinCeAutoCycle 任务槽 (10-14 backtest TIMECAP 同族根因: 护栏在 initialize 之后,
# 卡 initialize 永远到不了). 修法=握手本身限时: 子代解释器 spawn(同 MT5 终端 IPC 可复用),
# 15s 硬超时 kill+degraded 放行 (fail-open, 不阻断主链, 下拍重来).
_HANDSHAKE_TIMEOUT_S = 15
_handshake_proc_lock = threading.Lock()
_handshake_pid = None  # 记录最近一次握手子进程 PID (留痕/排查)


def _bounded_mt5_handshake(timeout_s=_HANDSHAKE_TIMEOUT_S):
    """MT5 活体握手: 子代解释器跑 initialize+account_info, 15s 硬超时.
    子代成功且终端可复用 -> 父进程同解释器 initialize 秒级拿到同一终端句柄, 正常走主线程.
    卡死 -> TimeoutExpired kill, 返回 degraded (调用方按降级处理, 下拍重试).
    返回: (ok: bool, err: str)."""
    global _handshake_pid
    if mt5 is None:
        return False, "MetaTrader5 库不可用"
    # 子代 = 与 auto_run_cycle 相同的 ATE 解释器 (终端 IPC 可复用, 同进程树)
    import sys as _sys
    exe = _sys.executable  # 恒为 ate 解释器 (mt5_live_read 只被 ate 侧 import)
    code = ("import MetaTrader5 as m,sys;"
            "ok=m.initialize();sys.exit(0 if ok and m.account_info() else 1)")
    with _handshake_proc_lock:
        try:
            import subprocess as _sp
            p = _sp.run([exe, "-c", code], capture_output=True, timeout=timeout_s)
            if p.returncode == 0:
                return True, ""
            return False, "握手子代 rc=%s stderr=%s" % (p.returncode,
                    (p.stderr or b"").decode("utf-8", "replace")[:60])
        except Exception as ex:  # _sp.TimeoutExpired (子代已被 run 在超时路径 kill 掉) / 其他异常
            _handshake_pid = None
            return False, "initialize 握手 %ds 封顶触发: %s (IPC 冻死族), 按降级放行" % (
                timeout_s, str(ex)[:80])


def _f(obj, *keys, default=None):
    """MT5 named tuple 字段安全读 (字段缺失给 default, 不崩)."""
    for k in keys:
        v = getattr(obj, k, None)
        if v is not None:
            return v
    return default


def _ticket_to_int(val):
    """[L5 split-brain fix 2026-10-15] 票号归一: 裸 int / 数字串 / 'MT5_123' 前缀串 -> 裸 int.
    解析不了给 None (调用方跳过, 绝不崩). 双兼容: 派生簿 filled/pending 的 key 是带 MT5_ 前缀串,
    而 MT5 实读 ticket 是裸 int, 老逻辑拿 str 查 int 集合恒 False -> 活仓被误判孤儿, 污染
    day_realized_pnl/连亏/冷却/停挂闸 (chief 1057 放行, 边界只动本文件派生簿对账)."""
    try:
        s = str(val).strip()
        if s.upper().startswith("MT5_"):
            s = s[4:]
        return int(s)
    except Exception:
        return None


def live_read(max_wait_s=20):
    """实读 MT5 活体: 账户 + 活挂单 + 活持仓. 失败 fail-open 返回 degraded=True."""
    out = {"ts": int(time.time()), "degraded": True, "errors": [],
           "account": None, "n_orders": 0, "n_pos": 0, "orders": [], "positions": []}
    if mt5 is None:
        out["errors"].append("MetaTrader5 库不可用")
        return out
    # [t_528b267c 根因①] 握手限时自检: 父进程 initialize 前先跑 15s 有界的子代握手探活.
    # 子代活=终端 IPC 健康, 父 initialize 秒回; 子代超时/失败=IPC 冻死族, 直接按降级放行,
    # 绝不进父进程无返回的 initialize (10-19 19:32:36 全循环 stall 卡死点).
    hs_ok, hs_err = _bounded_mt5_handshake()
    if not hs_ok:
        out["errors"].append("MT5握手限时自检不通过: " + hs_err)
        return out
    try:
        ok = mt5.initialize()
        if not ok:
            out["errors"].append("initialize 失败 (终端未起?) %s" % str(mt5.last_error())[:60])
            return out
        acc = mt5.account_info()
        if acc is None:
            out["errors"].append("account_info 读不到 (未登录?)")
            return out
        out["account"] = {
            "login": _f(acc, "login"), "server": _f(acc, "server"),
            "currency": _f(acc, "currency"), "balance": _f(acc, "balance"),
            "equity": _f(acc, "equity"), "profit": _f(acc, "profit"),
            "margin_free": _f(acc, "margin_free", "free_margin"),
            "margin_level": _f(acc, "margin_level"), "leverage": _f(acc, "leverage"),
            "trade_allowed": _f(acc, "trade_allowed", "trading_allowed"),
        }
        # 活挂单: 全账户读, 条目带 magic 供调用方按簿过滤
        for o in (mt5.orders_get() or []):
            out["orders"].append({
                "ticket": _f(o, "ticket"), "symbol": _f(o, "symbol"),
                "type": _f(o, "type"), "volume": _f(o, "volume_current", "volume"),
                # [2026-10-13 修@None] MT5 TradeOrder 无 price 字段, 触发价=price_open(挂单)/price_current(市价兜底)
                "price": _f(o, "price_open", "price_current", "price_stoplimit"),
                "sl": _f(o, "sl"), "tp": _f(o, "tp"),
                "magic": _f(o, "magic"), "time": _f(o, "time_setup", "time"),
            })
        for p in (mt5.positions_get() or []):
            out["positions"].append({
                "ticket": _f(p, "ticket"), "symbol": _f(p, "symbol"),
                "type": _f(p, "type"), "volume": _f(p, "volume"),
                "price_open": _f(p, "price_open"), "price_current": _f(p, "price_current"),
                "sl": _f(p, "sl"), "tp": _f(p, "tp"), "profit": _f(p, "profit"),
                "magic": _f(p, "magic"), "time": _f(p, "time"), "comment": _f(p, "comment"),
            })
        out["n_orders"] = len(out["orders"])
        out["n_pos"] = len(out["positions"])
        out["degraded"] = False
    except Exception as e:
        out["errors"].append("实读异常: %s" % str(e)[:80])
    finally:
        try:
            mt5.shutdown()
        except Exception:
            pass
    return out


def live_read_for_magic(magic, max_wait_s=20):
    """按 magic 过滤的活体实读 (派生簿三 magic 分簿: 20260902 外汇 / 20260903 币 / 20260904 股指).
    degraded 语义同 live_read: 读不到实仓时调用方必须 fail-open 保留派生簿原条目."""
    r = live_read(max_wait_s)
    r["n_orders_magic"] = sum(1 for o in r["orders"] if o.get("magic") == magic)
    r["n_pos_magic"] = sum(1 for p in r["positions"] if p.get("magic") == magic)
    r["orders_magic"] = [o for o in r["orders"] if o.get("magic") == magic]
    r["positions_magic"] = [p for p in r["positions"] if p.get("magic") == magic]
    return r


def _orphan_pnl(magic, ticket):
    """history_deals 回填孤儿条目 pnl (group=ticket, 近 48h). 读不到给 None."""
    try:
        deals = mt5.history_deals_get(int(time.time()) - 172800, int(time.time()),
                                      group=int(ticket))
        return round(sum((d.profit + d.swap + d.commission) for d in (deals or [])), 2)
    except Exception:
        return None


def _settle_state_orphans(st, magic, positions, note="orphan_settle"):
    """单簿: filled 里 status=open 且实读(全账户仓位)无该 magic 该票 -> 降终态.
    pnl 走 history_deals 回填, 连亏/冷却口径同 crypto _reconcile_orphans. 返回条数."""
    n = 0
    live_tickets = set(t for t in (_ticket_to_int(p["ticket"]) for p in positions
                                   if p.get("magic") == magic and p.get("ticket") is not None)
                       if t is not None)
    now = int(time.time())
    for tk, f in list(st.get("filled", {}).items()):
        if f.get("status") not in ("open", None):
            continue
        if _ticket_to_int(tk) in live_tickets:
            continue
        pnl = f.get("last_pnl")
        if pnl is None:
            pnl = _orphan_pnl(magic, tk)
        if pnl is None:
            pnl = 0.0
        f["last_pnl"] = round(pnl, 2)
        f["status"] = "终态"
        f["settled_ts"] = now
        f["settled_by"] = note
        st["day_realized_pnl"] = round(st.get("day_realized_pnl", 0.0) + pnl, 2)
        st["day_realized_date"] = time.strftime("%Y-%m-%d")
        if pnl <= 0:
            st["consec_losses"] = st.get("consec_losses", 0) + 1
            if st.get("consec_losses", 0) >= 3:
                st["cooldown_until"] = now + 24 * 3600
            # [2026-10-13 L5-fix] 写侧不覆盖风控 dict 停挂(_risk_xau2_cancel_sync 写 {paused,until_ts,scope,reason}):
            #   旧写法无条件写 int, 风控带留痕的 dict 会被冲掉(停挂到期口径丢失). dict 且 until_ts 更晚 > 保留 dict.
            _old_pa = st.get("symbol_pause", {}).get(f.get("sym", "?"))
            _new_pa = now + 24 * 3600
            if not (isinstance(_old_pa, dict) and _old_pa.get("until_ts", 0) >= _new_pa):
                st.setdefault("symbol_pause", {})[f.get("sym", "?")] = _new_pa
        else:
            st["consec_losses"] = 0
        st.setdefault("history", []).append(
            {"ts": now, "evt": "孤儿降终态(实读无仓位)", "sym": f.get("sym"),
             "pnl": round(pnl, 2), "ticket": tk})
        n += 1
    return n


def settle_orphans_by_magic(st, magic, note="orphan_settle"):
    """派生簿自动降终态: 读一次 MT5 活体, 把 st['filled'] 里 status in (open, None)
    但实读无同 magic 该票活仓位的孤儿条目结算掉. 纯记账不发单.
    fail-open: 实读降级/异常一律保留原条目, 返回 0. 返回本轮结算条目数."""
    if not st or not st.get("filled"):
        return 0
    r = live_read_for_magic(magic)
    if r["degraded"]:
        return 0
    return _settle_state_orphans(st, magic, r["positions"], note=note)


def settle_all_orphans():
    """三 magic 全簿对账: filled 孤儿降终态 (pnl 回填) + pending 残留清账 (实读无此票).
    纯数据源对账层, 不碰挂单循环真闸源 (event_risk.json / 币系冻结桥一字不动).
    fail-open: 实读降级时整轮不结算(防误杀真仓), 任一步异常不影响 30min 全链.
    返回 {簿文件名: 处置条数} 或 {reason: 降级说明}."""
    r = live_read()
    if r["degraded"]:
        return {"reason": "MT5 实读降级, 本轮不结算(保留原条目): %s"
                % "; ".join(r["errors"])[:120]}
    live_orders = set(t for t in (_ticket_to_int(o["ticket"]) for o in r["orders"]
                                  if o.get("ticket") is not None)
                      if t is not None)
    res = {}
    for magic, name in _MAGIC_NAME.items():
        p = DATA + "/" + name
        try:
            with open(p, encoding="utf-8") as fh:
                st = json.load(fh)
        except Exception:
            continue
        n = 0
        if st.get("filled"):
            n += _settle_state_orphans(st, magic, r["positions"])
        for tk in list(st.get("pending", {}).keys()):
            _pk = _ticket_to_int(tk)
            if _pk is not None and _pk not in live_orders:
                st["pending"].pop(tk, None)
                st.setdefault("history", []).append(
                    {"ts": int(time.time()), "evt": "派生簿残留票清账(实读无此挂单)", "ticket": _pk})
                n += 1
        if n:
            try:
                with open(p, "w", encoding="utf-8") as fh:
                    json.dump(st, fh, ensure_ascii=False, indent=2)
            except Exception:
                pass
        res[name] = n
    return res


def desync_flags(live, derived_pending_n, derived_open_n):
    """派生簿 vs 实读差异警示行 (GBK 安全). 无差异返回 [].
    live = live_read() 结果; degraded 时给一条降级警示行, 绝不静默当实读."""
    flags = []
    if live.get("degraded"):
        flags.append("MT5 实盘读取失败, 本轮只有派生簿留痕口径, 挂单/持仓数不作实盘断言: %s"
                     % "; ".join(live.get("errors", []))[:100])
        return flags
    if derived_pending_n != live.get("n_orders", 0):
        flags.append("派生挂单%d/实盘%d — 以实读为准, 派生簿仅留痕"
                     % (derived_pending_n, live.get("n_orders", 0)))
    if derived_open_n != live.get("n_pos", 0):
        flags.append("派生持仓%d/实盘%d — 以实读为准, 派生簿仅留痕"
                     % (derived_open_n, live.get("n_pos", 0)))
    return flags


if __name__ == "__main__":
    out = live_read()
    acc = out.get("account") or {}
    print("[实读] 活体: degraded=%s 账户=%s 挂单=%d 持仓=%d"
          % (out["degraded"], acc.get("login"), out["n_orders"], out["n_pos"]))
    for e in out["errors"]:
        print("[实读] ! " + e)
