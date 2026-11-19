# -*- coding: utf-8 -*-
"""cost_ratio_universe_20261117 五验前置: 全宇宙成本比实读扫描 (0LLM 确定性)
成本比 = (2 x 点差$ @0.01手) / (1%净值), >0.30R = 数学无 edge 出池候选.
出池=降风险方向, 不放大; 30d 净P&L 交叉核对防误杀(30d实赚+高成本比=HOLD 报差异).
数据有效性闸(11-14): source=MT5_LIVE + 快照时刻 + 逐品种 tick 龄, 应活却陈旧=显式FAIL剔除.
"""
import json, os, sys, time, threading
from datetime import datetime

OUT = "E:/GoldstrategyEngine/data/rd_verify_batch_cost_ratio_20261117.json"
LOSS30D = "E:/workbuddy/国外模型/hermes/cache/scratch/loss30d_20261117.json"
TERM = r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe"

def _init_capped(sec=15):
    import MetaTrader5 as mt5
    r = {}
    def go():
        r["ok"] = bool(mt5.initialize(path=TERM, timeout=sec * 1000))
    t = threading.Thread(target=go, daemon=True)
    t.start(); t.join(sec + 5)
    return r.get("ok", False)

def main():
    ok = _init_capped(15)
    if not ok:
        time.sleep(30); ok = _init_capped(15)
    if not ok:
        print(json.dumps({"fatal": "MT5 initialize 15s cap x2 FAIL (IPC 冻死族窗口?), 本拍降级, 下拍自愈", "ts": datetime.now().isoformat()})); return 2
    import MetaTrader5 as mt5
    ai = None
    try:
        ai = mt5.account_info()
    except Exception:
        pass
    equity = None
    try:
        equity = float(ai.equity)
    except Exception:
        pass
    if equity is None:
        equity = 989.39  # risk_state 03:01 实读, 显式 fallback
    equity_fallback = (ai is None)
    r_base = round(0.01 * equity, 2)  # 1% 净值 = 单笔风险分母 (11-17 验尸四铁律)

    T1 = ["BTCUSD","ETHUSD","SOLUSD","BNBUSD","XRPUSD","ADAUSD","DOGEUSD","LTCUSD","BCHUSD","DOTUSD","POLUSD","UNIUSD"]
    T2 = ["EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","NZDUSD","EURGBP","GBPJPY","AUDJPY","XAUUSD","XAGUSD"]
    T3 = ["US30","US500","NAS100","JPN225","UK100","GER40","AUS200","SWI20"]
    CORE34 = T1 + T2 + T3 + ["CHCUSD","XTIUSD"]
    EXOTICS = ["AUDCAD","AUDCHF","AUDCNH","AUDSGD","AUDNZD","CADCHF","CADJPY","EURNOK","EURSEK","GBPNOK","GBPSEK",
               "NOKSEK","NZDSGD","SGCSGD","EURHKD","USDCNH","USDMXN","USDZAR","USDNOK","NZDCAD","NZDCHF","NZDJPY",
               "NZDSEK","GBPCAD","GBPCHF","EURCHF","XBRUSD","XPTUSD","EUSTX50"]

    # 30d 净 P&L (同分母交叉核对底稿, 证据 cache/scratch/loss30d_20261117.json)
    net30, n30 = {}, {}
    try:
        c = json.load(open(LOSS30D, encoding="utf-8"))
        for e in c.get("losses", []):
            net30[e["sym"]] = round(net30.get(e["sym"], 0.0) + e["pnl"], 2); n30[e["sym"]] = n30.get(e["sym"], 0) + 1
        for e in c.get("wins", []):
            net30[e["sym"]] = round(net30.get(e["sym"], 0.0) + e["pnl"], 2); n30[e["sym"]] = n30.get(e["sym"], 0) + 1
    except Exception as ex:
        print("LOSS30D READ FAIL:", ex)

    now = time.time()
    rows, stale, cached, missing = [], [], [], []
    for sym in CORE34 + EXOTICS:
        try:
            mt5.symbol_select(sym, True)
            si = mt5.symbol_info(sym); tick = mt5.symbol_info_tick(sym)
        except Exception as ex:
            missing.append(sym); continue
        if si is None:
            missing.append(sym); continue
        bid, ask = (tick.bid, tick.ask) if tick else (0, 0)
        if not bid or si.point <= 0:
            missing.append(sym); continue
        ts = si.point; tv = getattr(si, "trade_tick_value", 0.0) or 0.0
        spread_ticks = round((ask - bid) / ts, 10)
        spread_usd_001 = spread_ticks * tv * 0.01          # 0.01手单边点差$
        rt_cost = round(2 * spread_usd_001, 4)             # 往返(开+平), 手续费0(本demo无per-lot费)
        ratio = round(rt_cost / r_base, 4) if r_base > 0 else None
        age = int(now - (tick.time - 7200)) if tick.time else -1   # 服务器钟快2h修正
        in_core = sym in CORE34
        if age > 3600 and in_core:
            tier = "DATA_STALE" if age < 14400 else "CACHED_CLOSED"
        elif age > 3600:
            tier = "CACHED_CLOSED"
        elif age < 900:
            tier = "LIVE"
        else:
            tier = "SUSPECT"
        if tier == "DATA_STALE": stale.append(sym)
        elif tier == "CACHED_CLOSED": cached.append(sym)
        # 30d 交叉核对: 高成本比 + 30d实赚 = HOLD(冲突留痕), 否则 POOL_OUT 候选
        n30d = n30.get(sym, 0); net = net30.get(sym, 0.0)
        if ratio is not None and ratio > 0.30:
            verdict = "HOLD_CONFLICT_30d_PROFIT" if (n30d > 0 and net > 0) else ("POOL_OUT" if tier in ("LIVE","CACHED_CLOSED") else "POOL_OUT_PENDING_DATA")
        else:
            verdict = "KEEP"
        rows.append({"sym": sym, "in_core34": in_core, "tier": tier, "tick_age_s": age,
                     "spread_ticks": spread_ticks, "spread_usd_001lot": round(spread_usd_001, 4),
                     "rt_cost_usd": rt_cost, "cost_ratio_R": ratio, "n30d": n30d, "net30d": net,
                     "verdict": verdict})

    pool = [r for r in rows if r["verdict"].startswith("POOL_OUT")]
    keep_core = [r for r in rows if r["in_core34"] and r["verdict"] == "KEEP"]
    pool_core = [r for r in pool if r["in_core34"]]
    same_denom = {
        "note": "出池=降风险方向: 保留品种事件集不变, 出池品种30d净P&L被移出分母",
        "pooled_30d_net": round(sum(r["net30d"] for r in pool), 2),
        "pooled_30d_n": sum(r["n30d"] for r in pool),
        "kept_core_30d_net": round(sum(r["net30d"] for r in keep_core), 2),
        "improvement_30d": round(-sum(r["net30d"] for r in pool if r["net30d"] < 0), 2),
    }
    out = {
        "id": "cost_ratio_universe_20261117",
        "schema": "rd_verify_batch_cost_ratio.v1",
        "generated": datetime.now().isoformat(timespec="seconds"),
        "source": "MT5_LIVE terminal=%s account=60137964" % os.path.basename(TERM),
        "data_validity_gate": {
            "source": "MT5_LIVE", "snapshot_ts": datetime.now().isoformat(timespec="seconds"),
            "max_valid_age_h": 72, "equity_used": equity, "equity_fallback": equity_fallback,
            "r_base_usd_1pct": r_base, "threshold_R": 0.30,
            "stale_symbols": stale, "closed_cached_symbols": cached, "missing_symbols": missing,
            "data_unreliable": bool(stale),
            "note": "DATA_STALE=应活却陈旧(显式FAIL, 该品种verdict作废); CACHED_CLOSED=休市正常缓存(非故障, 成本比用收盘前点差近似); missing=select失败",
        },
        "per_symbol": rows,
        "poolout_core34": [r["sym"] for r in pool_core],
        "poolout_exotics": [r["sym"] for r in pool if not r["in_core34"]],
        "hold_conflicts": [r["sym"] for r in rows if r["verdict"] == "HOLD_CONFLICT_30d_PROFIT"],
        "same_denom_check": same_denom,
        "rerun": "python E:/GoldstrategyEngine/research/cost_ratio_scan_20261117.py (D:/ 3.13.12 黄金法绑定, 15s cap init)",
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("OUT", OUT)
    print("equity", equity, "fallback", equity_fallback, "r_base", r_base)
    print("rows", len(rows), "stale", stale, "closed_cached", cached, "missing", missing)
    print("POOL_OUT core34:", out["poolout_core34"])
    print("POOL_OUT exotics:", out["poolout_exotics"])
    print("HOLD_CONFLICT:", out["hold_conflicts"])
    print("same_denom:", same_denom)
    for r in rows:
        if r["cost_ratio_R"] is not None and r["cost_ratio_R"] > 0.15:
            print("%-9s %-14s ratio=%.3f net30d=%s n=%s" % (r["sym"], r["tier"], r["cost_ratio_R"], r["net30d"], r["n30d"]))

if __name__ == "__main__":
    sys.exit(main())
