# -*- coding: utf-8 -*-
"""auto_soul_exit_watch_1119.py — 10分钟出场反馈哨(李令11-19"移动保护出场后立即反馈+无反转找机会再进场"):
检测magic 20261104仓位消失 → 分类出场原因(锁盈移动保护/止盈/原止损/手动) → 立即报(微信)
→ 盈利侧出场: 重扫灵魂门, 方向未反转=立即自主再进场(0.01同格, 12h红线再登记)+报; 已反转/无信号=报"不再进场, 观察".
亏损侧出场: 报"按制度止损不追", 后续新信号由30min巡市哨覆盖. 无事件=静默.
"""
import json, os, sys, time, subprocess, datetime as dt

ROOT = "E:/GoldstrategyEngine"
BASE = os.path.join(ROOT, "data")
SNAP = os.path.join(BASE, "auto_soul_exit_snap.json")
MAGIC = 20261104


def load_snap():
    try:
        return json.load(open(SNAP, encoding="utf-8"))
    except Exception:
        return {}


def main():
    import MetaTrader5 as mt5
    assert mt5.initialize(), "mt5 init fail"
    now = dt.datetime.now()
    cur = {}
    for p in (mt5.positions_get() or ()):
        if p.magic == MAGIC:
            cur[str(p.ticket)] = {"sym": p.symbol, "price_open": p.price_open, "sl": p.sl, "tp": p.tp,
                                  "opened_ts": dt.datetime.fromtimestamp(p.time).isoformat(),
                                  "side": "BUY" if p.type == 0 else "SELL"}
    prev = load_snap()
    gone = {k: v for k, v in prev.items() if k not in cur}
    reports = []
    if gone:
        deals = mt5.history_deals_get(now - dt.timedelta(hours=1), now + dt.timedelta(hours=2, minutes=5))  # 服务器时间=本地+2h: 近3h窗口
        by_pos = {}
        for d in (deals or []):
            if d.entry == mt5.DEAL_ENTRY_OUT:
                by_pos.setdefault(str(d.position_id), []).append(d)
        params = json.load(open(os.path.join(BASE, "auto_soul_params.json"), encoding="utf-8"))
        cells, default = params.get("cells", {}), params.get("default", {"sl_mult": 1.0, "tp_mult": 3.0})
        # R-C8 扫描只跑一次(多票消失共享结果)
        p2x = subprocess.run(["D:/jince_sass/.venv/Scripts/python.exe",
                              os.path.join(ROOT, "research", "soul_scan_1119.py")],
                             capture_output=True, text=True, timeout=300, cwd=ROOT)
        scan_all = {}
        try:
            scan_all = json.load(open(os.path.join(BASE, "soul_scan_1119.json"), encoding="utf-8"))
        except Exception:
            pass
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import auto_soul_sweep_1119 as sw
        reentered = 0
        for t, v in gone.items():
            ds = by_pos.get(t, [])
            close_price = ds[-1].price if ds else None
            pnl = round(sum(d.profit + d.commission for d in ds), 3) if ds else None
            reason = ds[-1].reason if ds else None  # 1=SL 2=TP 3=ByClient 4=exchange/close
            side = v["side"]
            entry = v["price_open"]
            profit_side = False
            if close_price is not None:
                profit_side = (close_price > entry) if side == "BUY" else (close_price < entry)
            if reason == mt5.DEAL_REASON_TP:
                label = "止盈命中"
            elif reason == mt5.DEAL_REASON_SL:
                label = ("移动保护锁盈(止损被推过保本)" if profit_side else "原结构止损")
            elif reason in (mt5.DEAL_REASON_CLIENT, 4):
                label = "客户端平仓(移动保护锁盈/哨兵, 非SL非TP)"
            else:
                label = f"未知原因({reason})"
            line = f"[出场反馈] {v['sym']} 单{t} 进{entry} 出{close_price} {label} 盈亏{pnl}"
            # R10: 平仓必留痕(验尸/进化材料) + 红线登记作废
            with open(os.path.join(BASE, "order_lifecycle.jsonl"), "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ev": "close", "ts": dt.datetime.now().isoformat(), "sym": v["sym"], "ticket": t,
                    "close_price": close_price, "pnl": pnl, "cause": label, "magic": MAGIC,
                    "actor": "出场反馈哨(R10全平仓留痕)"}, ensure_ascii=False) + "\n")
            try:
                regf2 = os.path.join(BASE, "redline_registry.jsonl")
                if os.path.exists(regf2):
                    rr2 = [json.loads(x) for x in open(regf2, encoding="utf-8") if x.strip()]
                    ch = False
                    for r2 in rr2:
                        if str(r2.get("ticket")) == t and not r2.get("handled"):
                            r2["handled"] = True; r2["handled_ts"] = dt.datetime.now().isoformat()
                            r2["note"] = "已出场, 红线作废"
                            ch = True
                    if ch:
                        with open(regf2, "w", encoding="utf-8") as fh2:
                            for r2 in rr2:
                                fh2.write(json.dumps(r2, ensure_ascii=False) + "\n")
            except Exception:
                pass
            if profit_side:
                # R-C8: 扫描结果=loop前一次性跑好(scan_all), 多票共享
                sig = next((s for s in scan_all.get("signals", []) if s.get("sym") == v["sym"]), None)
                swp = (sig or {}).get("sweeps", {})
                key = "UP" if side == "BUY" else "DN"
                alive = bool(sig and swp.get(key, {}).get("passed") and swp.get(key, {}).get("recent")
                              and sig.get("signal") == side)
                frozen = False
                try:
                    fw = json.load(open(os.path.join(BASE, "event_freeze_windows.json"), encoding="utf-8"))
                    scope = "JPY" if "JPY" in v["sym"] else "FX"
                    for w in fw.get("windows", []):
                        sc = w.get("scope", "all")
                        if sc == "all" or scope in sc.split(","):
                            ws = dt.datetime.fromisoformat(w["start"]).replace(tzinfo=None)
                            we = dt.datetime.fromisoformat(w["end"]).replace(tzinfo=None)
                            if ws <= dt.datetime.now() <= we:
                                frozen = True
                except Exception:
                    pass
                if alive and not frozen and not any(c["sym"] == v["sym"] for c in cur.values()):
                    sym = v["sym"]
                    cell = cells.get(sym, default)
                    # R-C3 每拍再进场上限1 (连环出场不连环开单)
                    if reentered >= 1:
                        line += " | 再进场额度本拍已用, 下拍覆盖"
                        reports.append(line); continue
                    # R-C4 闸对齐: D4尾龄 + 防磨平(与巡市哨同规则)
                    if sw.m30_stale(sym) > 2.0:
                        line += " | 数据尾龄>2h禁入(D4), 交巡市哨"
                        reports.append(line); continue
                    try:
                        import numpy as np
                        m = np.load(os.path.join(ROOT, "data", "tf_cache", f"{sym}_M30.npz"))
                        h, l, c3 = m["h"], m["l"], m["c"]
                        pc3 = np.concatenate(([c3[0]], c3[:-1]))
                        tr = np.maximum(h - l, np.maximum(np.abs(h - pc3), np.abs(l - pc3)))
                        R = round(cell["sl_mult"] * float(tr[-15:].mean()), 6)
                        si0 = mt5.symbol_info(sym)
                        if si0 and si0.point and R / si0.point < 4 * max(si0.spread, si0.trade_tick_size / si0.point):
                            raise ValueError(f"R<4×现点差防磨平(R={R/si0.point:.1f}点,点差{si0.spread}点)")
                    except Exception as ex:
                        line += f" | 再进场跳过: {ex} (巡市哨下拍覆盖)"
                        reports.append(line)
                        continue
                    tx = mt5.symbol_info_tick(sym)
                    _t1 = tx.time
                    time.sleep(3)
                    tx2 = mt5.symbol_info_tick(sym)
                    if tx2 and tx2.time > _t1:
                        px = tx2.ask if side == "BUY" else tx2.bid
                        sl = round(px - R, 6) if side == "BUY" else round(px + R, 6)
                        tp = round(px + cell["tp_mult"] * R, 6) if side == "BUY" else round(px - cell["tp_mult"] * R, 6)
                        fm = mt5.symbol_info(sym).filling_mode
                        ftype = mt5.ORDER_FILLING_RETURN if fm & 4 else (mt5.ORDER_FILLING_IOC if fm & 2 else mt5.ORDER_FILLING_FOK)
                        rr = mt5.order_send({"action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": 0.01,
                            "type": mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL, "magic": MAGIC,
                            "comment": "reentry-1119", "type_time": mt5.ORDER_TIME_GTC, "type_filling": ftype,
                            "deviation": 30, "position": 0, "sl": sl, "tp": tp})
                        if rr.retcode == 10009:
                            time.sleep(3)
                            chk = [p3 for p3 in (mt5.positions_get() or ()) if p3.ticket == rr.order]
                            if not chk:
                                line += f" | 再进场验收失败: 单{rr.order} 10009后未在账, P1取证"
                                reports.append(line); continue
                            reentered += 1
                            ts = dt.datetime.now().isoformat()
                            for ff, row in (("order_lifecycle.jsonl", {"ev": "place", "ts": ts, "sym": sym, "side": side, "vol": 0.01,
                                "price": px, "sl": sl, "tp": tp, "magic": MAGIC, "wave": "reentry-1119", "params_ver": cell.get("src", "default攒样"),
                                "ticket": rr.order, "rc": 10009, "actor": "出场反馈哨(李令: 无反转立即找机会再进场)", "live": True}),
                               ("_manual_prac_log.jsonl", {"kind": "open", "ts": ts, "sym": sym, "price": px, "sl": sl, "tp": tp,
                                "magic": MAGIC, "wave": "reentry-1119", "ticket": rr.order, "actor": "exit_watch_reentry"})):
                                with open(os.path.join(BASE, ff), "a", encoding="utf-8") as fh:
                                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                            with open(os.path.join(BASE, "redline_registry.jsonl"), "a", encoding="utf-8") as fh:
                                fh.write(json.dumps({"ts": ts, "sym": sym, "ticket": rr.order,
                                    "due": (dt.datetime.now() + dt.timedelta(hours=12)).isoformat(), "handled": False}, ensure_ascii=False) + "\n")
                            line += f" | 方向未反转=已当场再进场 单{rr.order} @{px} SL{sl} TP{tp} [12h红线已登记]"
                        else:
                            line += f" | 再进场失败 rc={rr.retcode} {rr.comment} (巡市哨下拍重试)"
                    else:
                        line += " | feed不活, 再进场交巡市哨"
                elif alive:
                    line += " | 冻结窗内/已有仓=暂不再进, 窗后巡市哨覆盖"
                elif sig:
                    line += f" | 方向已反转(现信号{sig.get('signal')}≠原{side})=不再进场, 观察"
                else:
                    line += " | 无新信号=不再进场, 观察"
            else:
                line += " | 按制度止损不追, 后续新信号由巡市哨覆盖"
            reports.append(line)
    with open(SNAP, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False)
    mt5.shutdown()
    if reports:
        print("\n".join(reports))


if __name__ == "__main__":
    main()
