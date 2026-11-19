# -*- coding: utf-8 -*-
"""
exec_live_60137964.py — 顶级操盘手实盘执行器 (demo 账户 60137964)
================================================================
把 trader_cio_gate 放行的 8 单真下到 MT5 demo 账户。
安全: 只在 LIVE_TRADING_ENABLED=True 时真下单; 每单 RR≥2 / 盘感WR≥0.50 / 风控PASS。
"""
import json, os, sys, time, datetime, math
import MetaTrader5 as mt5

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
assert os.path.isdir(DATA), f"DATA 目录不存在: {DATA}"
sys.path.insert(0, ROOT + "/multi_agent/trading")

# ══ 账户 ══
ACCOUNT_ID = 60137964
PASSWORD = ""
SERVER = "TradeMaxGlobal-Demo"
SYSTEM_MAGIC = 20260708
LIVE_TRADING_ENABLED = False         # [2026-11-03 锁定] 上膛枪风险: 无调用方但手工跑会真下单 → 锁 False; 真正启用需先过闸并改回 True
RISK_PER_TRADE = 0.005
MIN_RR = 2.0

def load_gate_passed():
    """读 CIO 简报里放行的单 (从 trade_execution_log 最近一次 run), 去重."""
    log = json.load(open(os.path.join(DATA, "trade_execution_log.json"), encoding="utf-8"))
    last = log["runs"][-1]
    passed = last["passed"]
    # 去重: 同 symbol 只保留第一单 (防重复开仓)
    seen, out = set(), []
    for p in passed:
        if p["symbol"] in seen:
            continue
        seen.add(p["symbol"])
        out.append(p)
    return out

def existing_open_positions():
    """当前账户已有持仓 (防重复开仓): 返回 set of (symbol, direction)"""
    pos = mt5.positions_get() or []
    out = set()
    for p in pos:
        d = "BUY" if p.type == 0 else "SELL"
        out.add((p.symbol, d))
    return out

def mt5_connect():
    ok = mt5.initialize()
    if not ok:
        raise RuntimeError(f"MT5 initialize 失败 {mt5.last_error()}")
    ok = mt5.login(ACCOUNT_ID, password=PASSWORD, server=SERVER)
    if not ok:
        raise RuntimeError(f"MT5 login 失败 {mt5.last_error()}")
    info = mt5.account_info()
    print(f"[MT5] 已登录 {info.login} @ {info.server} 余额=${info.balance:.2f} 净值=${info.equity:.2f} 杠杆=1:{info.leverage}")
    return info

def place_order(p, equity):
    """下单: 用 CIO 提案的 symbol/direction/lots/SL/TP, 经 MT5 市价+挂单"""
    sym = p["symbol"]
    direction = p.get("direction", "")
    # [2026-10-21 chief L1·L4 币系冻结闸] 开新腿前过币系闸: 非白名单币系 0 放行, 白名单例外腿 0.5x.
    # 单一实现在 multi_agent/trading/crypto_freeze_gate.py (strategy-rd 429 崩后 L1 补接). 撤单不在此路径, 不受影响.
    # [2026-11-02 互审F2修复] 币系冻结闸 fail-open → fail-closed:
    # 闸加载/执行异常 = 拒单+告警(风控闸故障必须挡在开单前面, 与 EA 闸快照铁律对齐)
    try:
        import importlib.util
        _cf = importlib.util.spec_from_file_location(
            "crypto_freeze_gate", os.path.join(ROOT, "multi_agent", "trading", "crypto_freeze_gate.py"))
        _cfm = importlib.util.module_from_spec(_cf); _cf.loader.exec_module(_cfm)
        _fz, _exc, _fzwhy = _cfm.check_crypto_frozen(sym)
        if _fz:
            _cfm.log_veto(sym, "; ".join(_fzwhy) + " | exec_live 开单路径拦截")
            return {"symbol": sym, "ok": False, "reason": "①.5币系冻结闸: " + "; ".join(_fzwhy)}
        if _exc:
            _cap = float(_exc.get("max_scale", 0.5))
            p["lots"] = min(float(p.get("lots", 0.01)), max(0.01, 0.01 * _cap))  # 例外腿 0.5x 封顶(最小 0.01)
    except Exception as _e:
        # [互审F2] fail-closed: 冻结闸故障 = 全部拒单, 不再放行
        return {"symbol": sym, "ok": False,
                "reason": f"币系冻结闸故障(fail-closed拒单): {str(_e)[:80]}"}
    # 方向缺失/非开仓 → 拒绝 (顶级操盘手纪律: 不放方向不明的单子进实盘)
    if direction not in ("BUY", "SELL"):
        return {"symbol": sym, "ok": False, "reason": f"方向 {direction or 'None'} 非 BUY/SELL, 拒绝开仓"}
    lots = float(p.get("lots", 0.01))
    sl = float(p.get("sl") or 0)
    tp = float(p.get("tp") or 0)
    # 盘感/风控已在 gate 层过; 这里只做 MT5 下单 + 最小手数兜底
    if lots < 0.01:
        lots = 0.01
    if not mt5.symbol_select(sym, True):
        return {"symbol": sym, "ok": False, "reason": f"品种 {sym} 不在本账户 symbol 列表, 跳过"}
    tick = mt5.symbol_info_tick(sym)
    if tick is None or tick.ask == 0:
        return {"symbol": sym, "ok": False, "reason": "无报价"}
    is_buy = (direction == "BUY")
    price = tick.ask if is_buy else tick.bid
    otype = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
    # [2026-11-02 互审F3修复] SL/TP 分别兜底: 原逻辑 or 覆盖可能把有效TP覆成0(裸单)
    if sl == 0:
        sl = float(p.get("stop_loss") or 0)
    if tp == 0:
        tp = float(p.get("take_profit") or 0)
    # [互审F3] 兜底后仍缺 SL → 拒单(无止损单禁止进实盘, 顶级操盘手纪律)
    if sl == 0:
        return {"symbol": sym, "ok": False, "reason": "SL=0(含兜底) 无止损拒单"}
    req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": sym,
           "volume": lots, "type": otype, "price": price,
           "sl": sl, "tp": tp, "deviation": 20, "magic": SYSTEM_MAGIC,
           "comment": "CIO_gate_dry_to_live", "type_time": mt5.ORDER_TIME_GTC,
           "type_filling": mt5.ORDER_FILLING_IOC}
    res = mt5.order_send(req)
    if res is None:
        return {"symbol": sym, "ok": False, "reason": f"order_send None {mt5.last_error()}"}
    ok = res.retcode == mt5.TRADE_RETCODE_DONE
    return {"symbol": sym, "direction": direction, "lots": lots, "price": price,
            "sl": sl, "tp": tp, "ok": ok, "retcode": res.retcode,
            "comment": res.comment, "order": res.order}

def check_exp_r_gate():
    """[2026-11-02 互审F4修复] 下单前 exp_r 总闸: 与 EA 闸1 同源(fail-closed)。
    闸快照缺失/损坏/超时(>10min) = 拒单。"""
    gate = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                        "7643C0B96C7AD5841307C9E1EB0B9252", "MQL5", "Files", "jince_gate.json")
    try:
        with open(gate, "r", encoding="utf-8") as f:
            g = json.load(f)
        exp_r = float(g["exp_r"])
        age = time.time() - os.path.getmtime(gate)
        if age > 600:
            return False, f"闸快照陈旧({int(age)}s>600s), fail-closed 拒单"
        if exp_r <= 0.1:
            return False, f"exp_r={exp_r} <= 0.1 阈值, 闸1拒单"
        return True, f"exp_r={exp_r} 放行"
    except Exception as e:
        return False, f"闸快照读取失败(fail-closed拒单): {str(e)[:60]}"


def main():
    print("═" * 60)
    print("  顶级操盘手 · 实盘执行器 (demo 60137964)")
    print("═" * 60)
    info = mt5_connect()
    equity = float(info.equity)
    # [2026-11-02 互审F4] 下单前 exp_r 总闸(fail-closed): 不过闸全批拒单
    gate_ok, gate_why = check_exp_r_gate()
    print(f"[闸1] {gate_why}")
    if not gate_ok:
        json.dump({"ts": datetime.datetime.now().isoformat(), "account": ACCOUNT_ID,
                   "blocked_by": gate_why, "n_passed": 0, "orders": []},
                  open(os.path.join(DATA, "live_execution_60137964.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print("[执行] 闸1拦截, 本轮 0 单")
        mt5.shutdown()
        return
    # [2026-11-03 锁定] LIVE_TRADING_ENABLED 实执行 (原仅写 JSON 标签不真拦)
    if not LIVE_TRADING_ENABLED:
        json.dump({"ts": datetime.datetime.now().isoformat(), "account": ACCOUNT_ID,
                   "blocked_by": "LIVE_TRADING_ENABLED=False (执行器已锁定)", "n_passed": 0, "orders": []},
                  open(os.path.join(DATA, "live_execution_60137964.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print("[执行] LIVE_TRADING_ENABLED=False, 执行器已锁定, 0 单")
        mt5.shutdown()
        return
    # [2026-11-02 互审F1修复] 激活防重复开仓检查(原为死代码)
    have = existing_open_positions()
    if have:
        print(f"[防重] 账户已有持仓: {sorted(have)}")
    passed = [p for p in load_gate_passed()
              if (p["symbol"], p.get("direction", "")) not in have]
    skipped = len(load_gate_passed()) - len(passed)
    if skipped:
        print(f"[防重] 跳过 {skipped} 单(同品种同方向已持仓)")
    print(f"[闸门放行单] {len(passed)} 单")
    results = []
    for p in passed:
        r = place_order(p, equity)
        results.append(r)
        status = "✓" if r.get("ok") else "✗"
        extra = f"ticket={r.get('order')}" if r.get("ok") else f"{r.get('reason') or r.get('comment')}"
        print(f"  {status} {r['symbol']:8} {r.get('direction',''):5} {r.get('lots',0)}手 @ {r.get('price','?')} "
              f"SL={r.get('sl',0)} TP={r.get('tp',0)} → {extra}")
    # 写执行记录
    rec = {"ts": datetime.datetime.now().isoformat(), "account": ACCOUNT_ID,
           "equity": equity, "live_trading": LIVE_TRADING_ENABLED,
           "n_passed": len(passed), "n_ok": sum(1 for r in results if r.get("ok")),
           "n_fail": sum(1 for r in results if not r.get("ok")),
           "orders": results}
    json.dump(rec, open(os.path.join(DATA, "live_execution_60137964.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2, default=str)
    print(f"\n[执行] 成功 {rec['n_ok']}/{len(passed)} | 失败 {rec['n_fail']}")
    # 持仓快照
    pos = mt5.positions_get() or []
    print(f"[持仓] 账户现有 {len(pos)} 仓:")
    for pp in pos:
        print(f"   {pp.symbol} {'BUY' if pp.type==0 else 'SELL'} {pp.volume} @ {pp.price_open} "
              f"SL={pp.sl} TP={pp.tp} 浮盈={pp.profit:+.2f}")
    mt5.shutdown()

if __name__ == "__main__":
    main()
