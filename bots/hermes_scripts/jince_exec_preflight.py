# -*- coding: utf-8 -*-
"""金策·执行预检 (预实盘验证层, 确定性 0LLM)
治"代码错了实盘才发现": 所有开单路径在 OrderSend 前必须过 preflight_order()。
规则(与外部 MQL5 Pre-flight 工程一致):
  P1 volume: 低于min/超max/非step倍数 -> 10014 (HKG类 min=1 step=1: 0.01必拒)
  P2 stops:  距市价 < stops_level+spread回退(3x) 或 不上tick网格 -> 10016
  P3 cost:   spread/ATR > mult(常态1.0, 事件窗3.0) -> 拒单
  P4 session: trade_mode 禁交易/收盘 -> 拒单
基准: data/exec_spec_fixture.json (ATE实读抓取, --fetch 用 ATE python 重抓)
自检: 默认模式=纯stdlib 对 fixture 跑规则自测(已知失败例必须被拒), 结果落 exec_preflight_selftest.json
用法:
  python jince_exec_preflight.py            # 自检(哨)
  python jince_exec_preflight.py --fetch    # ATE python 实读刷新 fixture
"""
import json, os, sys, time, datetime

DATA = r"E:\GoldstrategyEngine\data"
FIX = os.path.join(DATA, "exec_spec_fixture.json")
SELFTEST_OUT = os.path.join(DATA, "exec_preflight_selftest.json")
SPREAD_FALLBACK_MULT = 3.0   # stops_level=0 时按 3x spread 回退(外部工程常用, 保守)
TICK_GRID_TOL = 1e-9


def _load_fix():
    if not os.path.exists(FIX):
        return None
    return json.load(open(FIX, encoding="utf-8"))


def fetch_fixture():
    """ATE python 实读刷新 fixture(需 MetaTrader5 模块)."""
    import MetaTrader5 as mt5
    assert mt5.initialize(), "mt5 init fail"
    time.sleep(2)
    keep = [k for k in dir(mt5.symbol_info("EURUSD")) if any(
        x in k.lower() for x in ("volume_min", "volume_max", "volume_step", "stop", "freeze", "digits", "point", "tick_size", "spread", "trade_mode"))]
    out = {}
    for s in ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", "XPTUSD", "BTCUSD", "ETHUSD",
              "US30", "US2000", "FRA40", "0700.HKG", "6618.HKG", "2382.HKG"]:
        if mt5.symbol_select(s):
            info = mt5.symbol_info(s)
            if info is None:
                continue
            row = {k: getattr(info, k) for k in keep if not k.startswith("_")}
            # BUGFIX 11-14: 快照实读价(没有bid_now则selftest退化用旧价=自检失真, 李彦明问"测试数据是否有效"实锤)
            try:
                rates = mt5.symbol_info_tick(s)
                if rates is not None:
                    row["bid_now"] = rates.bid
                    row["ask_now"] = rates.ask
                    row["snapshot_ts"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
            out[s] = row
    json.dump(out, open(FIX, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    mt5.shutdown()
    n_snap = sum(1 for v in out.values() if v.get("bid_now"))
    print("fixture 刷新: %d 品种, 实读价快照 %d" % (len(out), n_snap))
    return out


def norm_volume(spec, vol):
    """P1: 归一到合法手数. 返回 (ok, vol_used, why)."""
    vmin, vmax, vstep = spec.get("volume_min", 0.01), spec.get("volume_max", 1e9), spec.get("volume_step", 0.01)
    import math
    if vstep and vstep > 0:
        n = math.floor(vol / vstep + TICK_GRID_TOL)
        vol_used = round(n * vstep, 10)
    else:
        vol_used = vol
    if vol_used < vmin:
        return False, None, "10014: 归一后%.4f低于min%.4f (请求%.4f)" % (vol_used, vmin, vol)
    if vol_used > vmax:
        return False, None, "10014: 归一后%.4f超max%.4f" % (vol_used, vmax)
    if vstep and abs(vol_used / vstep - round(vol_used / vstep)) > TICK_GRID_TOL:
        return False, None, "10014: 非step倍数"
    return True, vol_used, ""


def check_stops(side, bid, ask, sl, tp, spec):
    """P2: SL/TP 距离与tick网格. 返回 (ok, why)."""
    digits = spec.get("digits", 5)
    point = spec.get("point", 1e-5) or 1e-5
    tick = spec.get("trade_tick_size", point) or point
    stop_lvl = spec.get("trade_stops_level", 0) or 0
    spread = (ask - bid) if (ask and bid) else 0.0
    min_dist = stop_lvl * point + SPREAD_FALLBACK_MULT * spread  # stops_level=0 -> 3x spread 回退
    def on_grid(p):
        return abs(p / tick - round(p / tick)) <= TICK_GRID_TOL
    bad = []
    if sl:
        if not on_grid(sl):
            bad.append("SL不上tick网格")
        if side == "BUY" and bid - sl < min_dist:
            bad.append("SL距市价<%.2f(3x spread回退)" % min_dist)
        if side == "SELL" and sl - ask < min_dist:
            bad.append("SL距市价<%.2f" % min_dist)
    if tp:
        if not on_grid(tp):
            bad.append("TP不上tick网格")
        if side == "BUY" and tp - bid < min_dist:
            bad.append("TP距市价不足")
        if side == "SELL" and ask - tp < min_dist:
            bad.append("TP距市价不足")
    return (len(bad) == 0), ("10016: " + ";".join(bad) if bad else "")


def check_cost(spec, atr, mult=1.0):
    """P3: 点差成本闸. spread价格距离 = spread(点)*point."""
    point = spec.get("point", 1e-5) or 1e-5
    spread_px = (spec.get("spread", 0) or 0) * point
    if atr and atr > 0:
        return spread_px / atr <= mult, "spread/ATR=%.2f>%.1f" % (spread_px / atr, mult)
    return True, ""


def preflight_order(order, spec, atr=None, event_cost_mult=1.0):
    """总闸: order={symbol, side, vol, sl, tp, bid, ask} -> (PASS/REJECT, reasons[])"""
    reasons = []
    tm = spec.get("trade_mode")
    if tm in (0, 1):  # DISABLED / CLOSEONLY
        reasons.append("P4: 交易模式禁开仓(trade_mode=%s)" % tm)
    ok, vol_used, why = norm_volume(spec, order.get("vol", 0.01))
    if not ok:
        reasons.append(why)
    ok2, why2 = check_stops(order.get("side", "BUY"), order.get("bid"), order.get("ask"),
                            order.get("sl"), order.get("tp"), spec)
    if not ok2:
        reasons.append(why2)
    ok3, why3 = check_cost(spec, atr, event_cost_mult)
    if not ok3:
        reasons.append("P3: " + why3)
    return ("REJECT", reasons) if reasons else ("PASS", [])


def selftest():
    fix = _load_fix()
    res = {"ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "fixture_symbols": sorted((fix or {}).keys()), "checks": [], "fails": []}
    if not fix:
        res["fails"].append("fixture缺失: 需 ATE python 跑 --fetch")
        json.dump(res, open(SELFTEST_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("自检FAIL: fixture缺失")
        return 1
    age_h = (time.time() - os.path.getmtime(FIX)) / 3600
    res["fixture_age_h"] = round(age_h, 1)
    if age_h > 72:
        res["fails"].append("fixture超72h未刷新, 需 ATE python 跑 --fetch")
    # BUGFIX 11-14: 数据有效性闸——无实读价快照=自检在旧价上跑, 结果不可信, 必须显式FAIL不许静默
    no_snap = [k for k, v in fix.items() if not v.get("bid_now")]
    if no_snap:
        res["fails"].append("以下品种缺实读价快照(bid_now), 自检退化为旧价=结果不可信, 需 ATE 跑 --fetch 刷新: %s" % ",".join(no_snap))
    C = []  # (名, 订单, 期望, 说明)
    if "0700.HKG" in fix:
        s = fix["0700.HKG"]; px = s.get("bid_now") or 4000.0
        C.append(("HKG拒绝0.01", {"side": "BUY", "vol": 0.01, "bid": px, "ask": px + 0.1}, "REJECT", "10014根因复现"))
        C.append(("HKG接受1股", {"side": "BUY", "vol": 1, "bid": px, "ask": px + 0.1, "sl": px - 100, "tp": px + 300}, "PASS", "归一后=1股"))
        C.append(("HKG 1.5股归一到1股", {"side": "BUY", "vol": 1.5, "bid": px, "ask": px + 0.1, "sl": px - 100}, "PASS", "step=1 -> floor(1.5)=1"))
    if "EURUSD" in fix:
        s = fix["EURUSD"]; bid = s.get("bid_now") or 1.10; ask = s.get("ask_now") or bid + 0.00018
        C.append(("EURUSD正常单", {"side": "BUY", "vol": 0.01, "bid": bid, "ask": ask, "sl": bid - 0.003, "tp": bid + 0.009}, "PASS", ""))
        C.append(("EURUSD SL贴市价", {"side": "BUY", "vol": 0.01, "bid": bid, "ask": ask, "sl": bid - 0.00002}, "REJECT", "10016: 距离<3x spread"))
    if "XAUUSD" in fix:
        s = fix["XAUUSD"]; bid = s.get("bid_now") or 3880.0; ask = s.get("ask_now") or bid + 0.32
        C.append(("XAU事件窗成本闸", {"side": "BUY", "vol": 0.01, "bid": bid, "ask": ask, "sl": bid - 20, "tp": bid + 60}, "PASS", "ATR=50 常态通过; 事件窗mult=3.0时按spread 0.32/ATR判"))
    for name, order, expect, note in C:
        sym = order.get("symbol") or ("0700.HKG" if "HKG" in name else ("EURUSD" if "EURUSD" in name or "SL贴市" in name else "XAUUSD"))
        spec = fix.get(sym)
        if spec is None:
            continue
        order["symbol"] = sym
        verdict, reasons = preflight_order(order, spec, atr=50.0 if sym == "XAUUSD" else None)
        ok = verdict == expect
        res["checks"].append({"name": name, "symbol": sym, "expect": expect, "got": verdict,
                              "reasons": reasons, "note": note, "ok": ok})
        if not ok:
            res["fails"].append("规则自测不过: %s 期望%s 实得%s %s" % (name, expect, verdict, reasons))
    json.dump(res, open(SELFTEST_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if res["fails"]:
        print("预检自检 FAIL: %d项 失败%d" % (len(res["checks"]), len(res["fails"])))
        for f in res["fails"]:
            print("  FAIL:", f)
    # 全绿静默(stdout空=不投递); 结果仍落 exec_preflight_selftest.json
    return 0 if not res["fails"] else 2


if __name__ == "__main__":
    if "--fetch" in sys.argv:
        fetch_fixture()
    else:
        sys.exit(selftest())
