"""全品种 供需区 E3 挂单器 · 参数驱动 · 模拟户 60137964 magic 20261104 · 2026-11-15
用法: python place_sd_all.py --params sd_all_best_params.json [--live]
默认 dry-run 打印计划; --live 才真挂单.
纪律: 0.01手 / SL+TP 必挂 / 12h强平哨(挂后排cron) / 防叠单 / 纯ASCII注释 / prac log 留痕
"""
import os, sys, json, time, argparse, datetime as dt
os.environ.setdefault("MT5_TERMINAL", r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe")
os.environ.setdefault("MT5_LOGIN", "60137964")
import MetaTrader5 as mt5
import numpy as np

MAGIC = 20261104
ROOT = r"E:\GoldstrategyEngine"
DATA = os.path.join(ROOT, "research", "allsyms_m15")
PRAC_LOG = os.path.join(ROOT, "data", "_manual_prac_log.jsonl")
SYM_PARAMS = os.path.join(ROOT, "research", "sd_symbol_params.json")


def log_prac(rec):
    rec["ts"] = dt.datetime.now().isoformat()
    with open(PRAC_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def cur_events(sym, params, p, sp):
    """当前可挂事件: 最近已完结交易日 高低价±zf 区 + 限价可挂侧(sell@zhi上沿/buy@dl下沿)
    slc/tpmul 用该品种深优参数 sp (sd_symbol_params.json), 缺省回退全局 p"""
    z = np.load(os.path.join(DATA, sym + "_M15.npz"))
    t, o, h, l, c = z["t"], z["o"], z["h"], z["l"], z["c"]
    n = len(t)
    import sd_zone_oe_20261115 as M
    days = {}
    for i in range(1, n):
        dk = M.day_of(int(t[i]))
        if dk in days:
            days[dk] = (max(days[dk][0], h[i]), min(days[dk][1], l[i]))
        else:
            days[dk] = (h[i], l[i])
    dk_sorted = sorted(days)
    if len(dk_sorted) < 2:
        return []
    # 区 = 最近一个【已完结】交易日的高低 (币系今天未完=退一日)
    # P1-5修复(11-15三方审查): 原 "最后一根bar+15min<now" 只证数据旧, 不证日完结(周一刷到半日数据
    # 会把进行中日当区=前视/与回测不同分母). 改: (dk+1)日 00:15 UTC 已过才算该日完结.
    import time as _time
    zone_dk = None
    for cand in (dk_sorted[-1], dk_sorted[-2]):
        i0 = int(np.searchsorted(t, cand * 86400, "left"))
        i1 = int(np.searchsorted(t, (cand + 1) * 86400, "left"))
        if i1 > i0 and (cand + 1) * 86400 + 900 <= _time.time():
            zone_dk = cand
            break
    if zone_dk is None:
        return []
    dh, dl = days[zone_dk]
    # P1-6修复: zf 读 final 层 (原读顶层 params, final.zf 改了永远回退 0.3)
    zt = p.get("zf", 0.3) * (dh - dl)
    if zt <= 0:
        return []
    tick = mt5.symbol_info_tick(sym)
    if tick is None:
        return []
    bid, ask = tick.bid, tick.ask
    out = []
    # v2 无参品种(BNB/LTC 事件不足)不挂: 主表 no_trade 标记
    if sp and sp.get("no_trade"):
        print("%s no_trade(v2无参) 跳过" % sym, flush=True)
        return []
    slc = sp.get("slc", p.get("slc", 0.3)) if sp else p.get("slc", 0.3)
    tpmul = sp.get("tpmul", p.get("tpmul", 4.0)) if sp else p.get("tpmul", 4.0)
    # 空: 供给区 [dh-zt, dh]; SELL_LIMIT @ 上沿dh (需 bid<dh, 限价可挂侧)
    ep = dh
    if bid < ep:
        sl = ep + slc * zt
        risk = abs(sl - ep)
        tp = ep - tpmul * risk
        out.append(dict(sym=sym, side="sell", price=round(ep, 5), sl=round(sl, 5), tp=round(tp, 5),
                        trigger="supply_break_retest"))
    # 多: 需求区 [dl, dl+zt]; BUY_LIMIT @ 下沿dl (需 ask>dl, 限价可挂侧)
    epb = dl
    if ask > epb:
        slb = epb - slc * zt
        riskb = abs(epb - slb)
        tpb = epb + tpmul * riskb
        out.append(dict(sym=sym, side="buy", price=round(epb, 5), sl=round(slb, 5), tp=round(tpb, 5),
                        trigger="demand_break_retest"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", required=True)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--syms", default="", help="逗号分隔子集, 默认参数文件内全部")
    args = ap.parse_args()
    params = json.load(open(args.params, encoding="utf-8"))
    p = params.get("final", params)  # 定案参数在 final 子字典
    syms = args.syms.split(",") if args.syms else (params.get("symbols") or
        sorted(os.path.basename(x)[:-4].replace("_M15", "") for x in __import__("glob").glob(os.path.join(DATA, "*.npz"))))
    ok = mt5.initialize()
    if not ok:
        print("INIT FAIL", mt5.last_error()); sys.exit(1)
    # 分品种深优参数表 (缺省=全局 p)
    sp_all = {}
    if os.path.exists(SYM_PARAMS):
        sp_all = json.load(open(SYM_PARAMS, encoding="utf-8")).get("params", {})
    acct = mt5.account_info()
    if acct is None or int(acct.login) != 60137964:
        print("账户不对: 期望 60137964, 实际=%s -> 拒挂单" % (getattr(acct, "login", None),))
        sys.exit(1)
    ti = mt5.terminal_info()
    print("trade_allowed=%s connected=%s 余额=$%.2f" % (ti.trade_allowed, ti.connected, acct.balance))
    if not ti.trade_allowed:
        print("trade_allowed=False -> 10027 风险, 先干 run 记录, 不挂单"); live = False
    else:
        live = args.live
    # [11-15 同日区闸] 同日区(同 zone_dk)只挂一批: agent 反复重跑脚本 -> 整批 skip 收口, 零新挂单
    import os as _os
    _zone_state = _os.path.join(ROOT, "data", "sd_all_zone_state.json")
    _done_dk = None
    if _os.path.exists(_zone_state):
        try:
            _st = json.load(open(_zone_state, encoding="utf-8"))
            _done_dk = _st.get("last_zone_dk")
        except Exception:
            _done_dk = None
    # 取任一品种今日区日期作代表(与 cur_events 内 zone 计算同源: 最近已完结交易日)
    import sd_zone_oe_20261115 as _M, time as _time
    _today_zone_dk = None
    for sym in syms:
        try:
            _z = np.load(os.path.join(DATA, sym + "_M15.npz"))
            _t = _z["t"]
            _days = {}
            for _i in range(1, len(_t)):
                _dk = _M.day_of(int(_t[_i]))
                if _dk in _days:
                    _days[_dk] = (max(_days[_dk][0], _z["h"][_i]), min(_days[_dk][1], _z["l"][_i]))
                else:
                    _days[_dk] = (_z["h"][_i], _z["l"][_i])
            _dks = sorted(_days)
            for _cand in (_dks[-1], _dks[-2]):
                _i0 = int(np.searchsorted(_t, _cand * 86400, "left"))
                _i1 = int(np.searchsorted(_t, (_cand + 1) * 86400, "left"))
                if _i1 > _i0 and (_cand + 1) * 86400 + 900 <= _time.time():  # P-2修复(11-15御史): 与 cur_events:50 同一条式子, 整日结束才认
                    _today_zone_dk = _cand
                    break
            if _today_zone_dk is not None:
                break
        except Exception:
            continue
    if _today_zone_dk is not None and _done_dk == _today_zone_dk:
        log_prac(dict(kind="batch", n=0, live=False, spec="SD-E3S1 同日区已挂, 整批skip",
                      zone_dk=_today_zone_dk, note="agent重跑被同日区闸拦截, 零新挂单"))
        print("[同日区闸] zone_dk=%s 已挂过一批, 整批 skip, 退出" % _today_zone_dk)
        return 0
    placed, skipped, failed = [], [], []
    # [11-15三方审查P1-4修复] dedup 口径: state in (0,1) = STARTED(0)+PLACED(1) 都是"在册挂单"
    # (MT5 ENUM_ORDER_STATE: 1=PLACED 已被服务器接受的活挂单; 失效/撤单=从 orders_get 消失, 不算叠单).
    # 原"只认 state==0"使在册活挂单(state=1)对 dedup 不可见 -> 三叠 16 单实案(10:23/11:51).
    existing = [o for o in (mt5.orders_get() or []) if o.state in (0, 1)]  # 在册挂单都算
    # [11-17 主bot闸读断环] L4退役(symbol_pause) + 币系冻结(crypto_freeze_gate.family_freeze) + 出池(excluded_symbols) -> 品种级skip, 防补跑哨/agent重跑再挂违规单
    _gate_skip = {}
    try:
        _pos = json.load(open(os.path.join(ROOT, "data", "pending_orders_state.json"), encoding="utf-8"))
        for _s, _v in (_pos.get("symbol_pause") or {}).items():
            if isinstance(_v, dict) and _v.get("paused"):
                _gate_skip[_s.upper()] = "L4退役symbol_pause"
    except Exception:
        pass
    try:
        _cg = json.load(open(os.path.join(ROOT, "data", "crypto_freeze_gate.json"), encoding="utf-8"))
        _ff = (_cg.get("family_freeze") or {}).get("crypto") or {}
        if _ff.get("active"):
            for _s in ("BTCUSD", "ETHUSD", "XRPUSD", "SOLUSD", "DOGEUSD", "LTCUSD", "XLMUSD", "ADAUSD", "POLUSD", "TAOUSD"):
                _gate_skip.setdefault(_s, "币系冻结至%s" % _ff.get("until", "?"))
    except Exception:
        pass
    for _s in (params.get("excluded_symbols") or []):
        _gate_skip.setdefault(_s.upper(), "出池excluded_symbols")
    if _gate_skip:
        print("[闸读] 品种级skip: %s" % json.dumps(_gate_skip, ensure_ascii=False))
        log_prac(dict(kind="gate_read", ts=dt.datetime.now().isoformat(), skip=_gate_skip))
    for sym in syms:
        if sym.upper() in _gate_skip:
            skipped.append((sym, "gate_skip: %s" % _gate_skip[sym.upper()]))
            continue
        if not mt5.symbol_select(sym, True):
            skipped.append((sym, "select_fail")); continue
        info = mt5.symbol_info(sym)
        tm = getattr(info, "trade_mode", None)
        if tm == 4 and not live:
            pass
        evs = cur_events(sym, params, p, sp_all.get(sym))
        if not evs:
            skipped.append((sym, "no_live_event")); continue
        dg = info.digits if info else 5
        for e in evs:
            e["price"] = round(e["price"], dg)
            e["sl"] = round(e["sl"], dg)
            e["tp"] = round(e["tp"], dg)
            # 防叠单: 同 magic+品种+方向, 挂单位 1 tick 内=叠单 (tick 取整后同价/相邻 tick 都算)
            pt = getattr(info, "point", 1e-5) or 1e-5
            # [11-17哨修] existing 混合 TradeOrder namedtuple(orders_get) + dict(本批新挂, L231),
            # 裸 o.magic 对 dict 必崩(周一21:18/22:40两次挂单失败的共同根因=只要挂上1单后续品种全崩).
            # 统一归一口径: dict/.get, 对象/getattr, 语义与旧版完全一致.
            def _og(o, k, d=None):
                return o.get(k, d) if isinstance(o, dict) else getattr(o, k, d)
            dup = any(_og(o, "magic") == MAGIC and _og(o, "symbol") == sym and
                      ((e["side"] == "sell" and _og(o, "type") == mt5.ORDER_TYPE_SELL_LIMIT) or
                       (e["side"] == "buy" and _og(o, "type") == mt5.ORDER_TYPE_BUY_LIMIT))
                      and abs((_og(o, "price_open", 0) or 0) - e["price"]) <= pt for o in existing)
            if dup:
                skipped.append((sym, "dup"))
                continue
            vol = 0.01
            sym_info = mt5.symbol_info(sym)
            if sym_info and getattr(sym_info, "volume_min", 0.01) > vol:
                vol = sym_info.volume_min
            # P2修复(11-15御史): 手数按 volume_step 取整 (防 10014 步进不符)
            vstep = getattr(sym_info, "volume_step", 0.01) if sym_info else 0.01
            if vstep:
                import math as _m
                vol = max(vstep, _m.ceil(round(vol / vstep, 6)) * vstep)
            # P1修复: stops_level 预检 (SL/TP 距挂单价 < stops_level 会被 10016/10018 拒, 提前拦)
            stops_lv = getattr(info, "trade_stops_level", 0) or 0
            ptick = getattr(info, "point", 1e-5) or 1e-5
            if stops_lv and (abs(e["sl"] - e["price"]) < stops_lv * ptick or
                             abs(e["tp"] - e["price"]) < stops_lv * ptick):
                skipped.append((sym, "stops_level: SL/TP 距离不足, 该品种本批跳过"))
                continue
            otype = mt5.ORDER_TYPE_SELL_LIMIT if e["side"] == "sell" else mt5.ORDER_TYPE_BUY_LIMIT
            # J修复: PENDING 单 type_filling 用 FOK 非法(10030->改 IOC 也非法), 用 RETURN
            req = dict(action=mt5.TRADE_ACTION_PENDING, symbol=sym, volume=vol, type=otype,
                       price=e["price"], deviation=10, magic=MAGIC,
                       comment="SD-E3S1-" + sym, type_time=mt5.ORDER_TIME_GTC,
                       type_filling=mt5.ORDER_FILLING_RETURN,
                       sl=e["sl"], tp=e["tp"])
            if not live:
                placed.append(dict(sym=sym, side=e["side"], price=e["price"], sl=e["sl"], tp=e["tp"],
                                   vol=vol, dry=True))
                print("[DRY] %s %s_LIMIT %.5f SL=%.5f TP=%.5f %.2f手" % (
                    sym, e["side"].upper(), e["price"], e["sl"], e["tp"], vol))
                continue
            rc, err, ticket = None, None, None
            for attempt in range(3):
                res = mt5.order_send(req)
                rc = getattr(res, "retcode", None)
                # P1-8/J修复: 成功码收口 (10008挂单受理/10009完成/10010已挂), 且核 res.order>0;
                # 10019=NO_MONEY 移出成功集 (原误算成功=phantom open); 10014/10018/10019 终态记 failed(L2)
                if rc in (10008, 10009, 10010) and getattr(res, "order", 0) > 0:
                    ticket = res.order
                    placed.append(dict(sym=sym, side=e["side"], price=e["price"], sl=e["sl"], tp=e["tp"],
                                       vol=vol, ticket=ticket, rc=rc))
                    print("[LIVE] %s %s_LIMIT %.5f SL=%.5f TP=%.5f ticket=%s (rc=%s)" % (
                        sym, e["side"].upper(), e["price"], e["sl"], e["tp"], ticket, rc))
                    log_prac(dict(kind="open", sym=sym, side=e["side"], vol=vol, magic=MAGIC,
                                  price=e["price"], sl=e["sl"], tp=e["tp"], retcode=rc,
                                  ticket=ticket, spec="SD-E3S1 11轮最优"))
                    # P1-4补强: 本批新挂单入 existing, 防同批同价二次挂 (循环内去重)
                    existing.append(dict(magic=MAGIC, symbol=sym, type=otype,
                                        price_open=e["price"], state=1))
                    break
                err = mt5.last_error()
                print("[RETRY%d] %s rc=%s err=%s" % (attempt, sym, rc, err))
                if rc == 10030:
                    req["type_filling"] = mt5.ORDER_FILLING_IOC
                if rc in (10014, 10018, 10019):
                    failed.append((sym, rc, err))  # L2: 终态记 failed, 不再静默消失
                    break
                time.sleep(1)
            else:
                failed.append((sym, rc, err))
    print("\n=== 汇总: 挂=%d 跳=%d 败=%d (live=%s)" % (len(placed), len(skipped), len(failed), live))
    for s in skipped:
        print("  跳:", s)
    for f in failed:
        print("  败:", f)
    if live and placed and not failed and _today_zone_dk is not None:  # P-3修复(11-15御史): 有失败不许写区闸, 当日可补挂
        log_prac(dict(kind="batch", n=len(placed), live=True, spec="SD-E3S1 全品种挂单批"))
        # [11-15 同日区闸] 记录本区已挂
        try:
            json.dump(dict(last_zone_dk=_today_zone_dk, last_ts=time.strftime("%F %T"), n=len(placed)),
                      open(os.path.join(ROOT, "data", "sd_all_zone_state.json"), "w"), ensure_ascii=False)
        except Exception:
            pass
    mt5.shutdown()
    # 制度(11-15李令): 每次开单必带进化钩子 -> 参数表版本 + 逐单 lifecycle 台账(验尸哨消费)
    try:
        _pv = json.load(open(SYM_PARAMS, encoding="utf-8")).get("version", 0)  # 11-16修: 原读 ROOT 层(无此文件)恒0, 改 SYM_PARAMS(research/)
    except Exception:
        _pv = 0
    json.dump(dict(ts=time.strftime("%F %T"), live=live, params_ver=_pv, placed=placed, skipped=skipped, failed=failed,
                   params=params), open(os.path.join(ROOT, "research", "sd_place_log_%s.json" % dt.datetime.now().strftime("%Y%m%d")), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    _lc = os.path.join(ROOT, "data", "order_lifecycle.jsonl")
    with open(_lc, "a", encoding="utf-8") as _f:
        for o in placed:
            _f.write(json.dumps(dict(ev="open", ts=time.strftime("%F %T"), sym=o.get("sym"), side=o.get("side"),
                                      price=o.get("price"), sl=o.get("sl"), tp=o.get("tp"),
                                      params_ver=_pv, ticket=o.get("ticket"), live=live), ensure_ascii=False) + "\n")
    print("留痕 -> research/sd_place_log_*.json (params_ver=%s) + order_lifecycle.jsonl 逐单 %d 条" % (_pv, len(placed)))


if __name__ == "__main__":
    main()
