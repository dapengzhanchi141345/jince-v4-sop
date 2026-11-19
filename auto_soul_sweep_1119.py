# -*- coding: utf-8 -*-
"""auto_soul_sweep_1119.py — 30分钟自动巡市哨(李令11-19"给你全部灵魂, 不再让我提醒"):
自动扫描灵魂门 → 合格才自动开单(分品种赚钱格, 0.01攒样级) → 12h红线登记/处理 → 开单立即报(stdout).
闸: D4数据尾龄>2h禁入 / 事件冻结窗(event_freeze_windows.json) / 日位guard / 同magic去重 / 每拍最多2开 / feed活.
静默=无开单无红线事件; 开单或红线=stdout报回微信.
"""
import json, os, sys, time, subprocess, datetime as dt
import numpy as np

ROOT = "E:/GoldstrategyEngine"
BASE = os.path.join(ROOT, "data")
CACHE = os.path.join(ROOT, "data", "tf_cache")
MAGIC = 20261104
WAVE = "autosoul-1119"
VENV = "D:/jince_sass/.venv/Scripts/python.exe"
PY313 = "D:/workbuddy/binaries/python/versions/3.13.12/python.exe"


def load_json(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def in_freeze(now, scope):
    fw = load_json(os.path.join(BASE, "event_freeze_windows.json")) or {}
    for w in fw.get("windows", []):
        if scope in (w.get("scope") or "all").split(",") or w.get("scope") == "all":
            s = dt.datetime.fromisoformat(w["start"]); e = dt.datetime.fromisoformat(w["end"])
            if s.tzinfo is not None:
                s, e = s.replace(tzinfo=None), e.replace(tzinfo=None)  # 全部按BJT本地
            if s <= now <= e:
                return w.get("note", "")
    return None


def m30_stale(sym):
    f = os.path.join(CACHE, f"{sym}_M30.npz")
    if not os.path.exists(f):
        return 99.0
    m = np.load(f)
    tail = float(m["t"][-1]) + 1800
    return (time.time() - tail) / 3600.0


def atr30(sym):
    m = np.load(os.path.join(CACHE, f"{sym}_M30.npz"))
    h, l, c = m["h"], m["l"], m["c"]
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return float(tr[-15:].mean())


def main():
    now = dt.datetime.now()
    reports = []
    # R1-A4 冻结窗滚动: 20:00-20:59 自动追加次日美数据窗(20:30-21:30 all), 不再靠手动
    try:
        fwf = os.path.join(BASE, "event_freeze_windows.json")
        fw = load_json(fwf) or {"windows": []}
        nxt = (now + dt.timedelta(days=1)).strftime("%Y-%m-%dT")
        has_next = any(w.get("start", "").startswith(nxt + "20:30") for w in fw.get("windows", []))
        if not has_next and (20 <= now.hour < 21 or now.hour == 19):
            fw.setdefault("windows", []).append({"start": nxt + "20:30:00+08:00", "end": nxt + "21:30:00+08:00",
                                                  "scope": "all", "note": "美数据窗(巡市哨每日自动滚动, 晨学哨可加窄)"})
            json.dump(fw, open(fwf, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            reports.append(f"[冻结窗] 已自动追加 {nxt[:10]} 美数据窗 20:30-21:30")
    except Exception:
        pass
    # R1-A1 数据自鲜: 参考品种(BTC)M30尾龄>45min → 先跑数据官刷新再扫
    if m30_stale("BTCUSD") > 0.75:
        p0 = subprocess.run([PY313, os.path.join(ROOT, "jince_data_officer.py")],
                            capture_output=True, text=True, timeout=240, cwd=ROOT)
        time.sleep(8)
        if p0.returncode != 0:
            reports.append(f"[数据官刷新失败 rc={p0.returncode}] {(p0.stderr or '').strip()[-150:]} (D4尾龄闸兜底)")
    # 0) 红线登记: 到期未处理 → 跑红线哨
    reg_f = os.path.join(BASE, "redline_registry.jsonl")
    regs = []
    if os.path.exists(reg_f):
        regs = [json.loads(x) for x in open(reg_f, encoding="utf-8") if x.strip()]
    due = [r for r in regs if not r.get("handled") and dt.datetime.fromisoformat(r["due"]) <= now]
    if due:
        env = dict(os.environ, JINCE_REDLINE_FORCE="1")
        p = subprocess.run([PY313, "E:/workbuddy/国外模型/hermes/scripts/jince_redline_force_wrapper.py"],
                           capture_output=True, text=True, timeout=300, env=env, cwd=ROOT)
        out = (p.stdout or "").strip()
        for r in due:
            r["handled"] = True; r["handled_ts"] = now.isoformat()
        # R6 清理: 已处理且超过24h的登记项丢弃, 防文件膨胀
        regs = [r for r in regs if not (r.get("handled") and (now - dt.datetime.fromisoformat(r.get("handled_ts", r.get("ts", now.isoformat())))) < dt.timedelta(hours=24))]
        with open(reg_f, "w", encoding="utf-8") as f:
            for r in regs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        if out:
            reports.append(f"[红线] " + " | ".join(f"{r['sym']}" for r in due) + f" → {out[:200]}")
        else:
            reports.append(f"[红线] 到期{len(due)}腿 已处理(静默收尾)")
    # 1) 跑灵魂门扫描(venv, 快)
    p = subprocess.run([VENV, os.path.join(ROOT, "research", "soul_scan_1119.py")],
                       capture_output=True, text=True, timeout=300, cwd=ROOT)
    scan = load_json(os.path.join(BASE, "soul_scan_1119.json")) or {}
    sigs = [s for s in scan.get("signals", [])]
    if not sigs:
        if due:
            print("\n".join(reports))
        return
    # 2) 选单: 按位移幅度排序取前2, 过闸
    params = load_json(os.path.join(BASE, "auto_soul_params.json")) or {}
    cells, default = params.get("cells", {}), params.get("default", {"sl_mult": 1.0, "tp_mult": 3.0})
    guard = params.get("day_pos_guard", {})
    cap = int(params.get("max_open_per_beat", 2))
    import MetaTrader5 as mt5
    assert mt5.initialize(), "mt5 init fail"
    held = {p2.symbol for p2 in (mt5.positions_get() or ()) if p2.magic == MAGIC}
    pend = {o.symbol for o in (mt5.orders_get() or ()) if o.magic == MAGIC}
    ranked = sorted(sigs, key=lambda s: abs(float(s.get("sweeps", {}).get("UP" if s.get("signal") == "BUY" else "DN", {}).get("disp_atr", 0) or 0)), reverse=True)
    opened = []
    for s in ranked:
        if len(opened) >= cap:
            break
        sym = s.get("sym")
        side = s.get("signal")
        if s.get("entry_type") != "market":
            continue  # 限价模式=限价通道10015未修, 跳过(等通道修复后放开)
        disp = abs(float(s.get("sweeps", {}).get("UP" if side == "BUY" else "DN", {}).get("disp_atr", 0) or 0))
        if sym in held or sym in pend:
            continue
        scope = "JPY" if "JPY" in sym else "FX"
        fz = in_freeze(now, "all") or in_freeze(now, scope)
        if fz:
            continue  # 冻结窗内0新开
        dpos = s.get("day_pos")
        if side == "BUY" and dpos is not None and dpos >= guard.get("buy_max", 0.97):
            continue
        if side == "SELL" and dpos is not None and dpos <= guard.get("sell_min", 0.03):
            continue
        if m30_stale(sym) > 2.0:
            continue  # D4 数据尾禁入
        cell = cells.get(sym, default)
        R = round(cell["sl_mult"] * atr30(sym), 6)
        # R9 闸: R点距 < 4×最小点差 = 点差磨平循环, 跳过(验尸岗材料)
        si0 = mt5.symbol_info(sym)
        if si0 and si0.point and si0.trade_tick_size:
            R_pts = R / si0.point
            min_spread_pts = max(si0.spread, si0.trade_tick_size / si0.point)
            if R_pts < 4 * min_spread_pts:
                with open(os.path.join(BASE, "task_ledger.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": dt.datetime.now().isoformat(), "by": "auto_soul_sweep",
                        "task": f"{sym} R={R_pts:.1f}点 < 4×点差{min_spread_pts:.1f}点, 跳过(防磨平)", "live": True}, ensure_ascii=False) + "\n")
                continue
        t = mt5.symbol_info_tick(sym)
        if not t:
            continue
        _t1 = t.time
        time.sleep(3)
        t2 = mt5.symbol_info_tick(sym)
        if not t2 or t2.time <= _t1:
            continue
        px = t2.ask if side == "BUY" else t2.bid
        sl = round(px - R, 6) if side == "BUY" else round(px + R, 6)
        tp = round(px + cell["tp_mult"] * R, 6) if side == "BUY" else round(px - cell["tp_mult"] * R, 6)
        fm = mt5.symbol_info(sym).filling_mode
        ftype = mt5.ORDER_FILLING_RETURN if fm & 4 else (mt5.ORDER_FILLING_IOC if fm & 2 else mt5.ORDER_FILLING_FOK)
        r = mt5.order_send({"action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": 0.01,
            "type": mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL, "magic": MAGIC,
            "comment": WAVE, "type_time": mt5.ORDER_TIME_GTC, "type_filling": ftype,
            "deviation": 30, "position": 0, "sl": sl, "tp": tp})
        if r.retcode != 10009:
            continue
        time.sleep(3)
        # R1-A2 开单验收: 10009≠在账, 3秒后positions_get确认
        chk = [p3 for p3 in (mt5.positions_get() or ()) if p3.ticket == r.order]
        if not chk:
            reports.append(f"[验收失败] {sym} 单{r.order} 10009后3秒未在账, 立P1取证 (rc=10009 但位置缺失)")
            continue
        ts = now.isoformat()
        with open(os.path.join(BASE, "order_lifecycle.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ev": "place", "ts": ts, "sym": sym, "side": side, "vol": 0.01, "price": px,
                "sl": sl, "tp": tp, "magic": MAGIC, "wave": WAVE, "disp_atr": disp, "day_pos": dpos,
                "params_ver": cell.get("src", "default攒样"), "ticket": r.order, "rc": 10009,
                "actor": f"自动巡市哨30min(李令'全部灵魂'授权, 无需提醒)", "live": True}, ensure_ascii=False) + "\n")
        with open(os.path.join(BASE, "_manual_prac_log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"kind": "open", "ts": ts, "sym": sym, "price": px, "sl": sl, "tp": tp,
                "magic": MAGIC, "wave": WAVE, "ticket": r.order, "actor": "auto_soul_sweep"}, ensure_ascii=False) + "\n")
        with open(reg_f, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": ts, "sym": sym, "ticket": r.order,
                "due": (now + dt.timedelta(hours=12)).isoformat(), "handled": False}, ensure_ascii=False) + "\n")
        with open(os.path.join(BASE, "task_ledger.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": ts, "by": "auto_soul_sweep", "task": f"自动开单 {sym} {side} @{px} (位移{disp}ATR)",
                "live": True}, ensure_ascii=False) + "\n")
        opened.append(f"{sym} {side} @{px} (位移{disp}×ATR, 格={cell.get('src','default')}, SL{sl} TP{tp}, 单{r.order})")
    if opened:
        reports.insert(0, "[自动开单] " + " | ".join(opened) + f" [12h红线已登记, 锁利守护接管]")
    mt5.shutdown()
    if reports:
        print("\n".join(reports))


if __name__ == "__main__":
    main()
